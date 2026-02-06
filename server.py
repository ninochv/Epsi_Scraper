#!/usr/bin/env python3
# server.py
from __future__ import annotations
import os
import sys
import sqlite3
import secrets
import datetime as dt
from typing import Optional

from flask import Flask, request, jsonify, Response, abort, render_template
from cryptography.fernet import Fernet, InvalidToken
from apscheduler.schedulers.background import BackgroundScheduler

from wigor_to_calendar import (
    login_discover_and_collect,
    default_two_weeks,
    BASE_URL as WIGOR_BASE_URL,
)

# ================== CONFIG ==================
# Repertoire de donnees (pour Docker, utiliser /data)
DATA_DIR = os.getenv("DATA_DIR", os.path.dirname(__file__))
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE = os.getenv("EPSI_DB", os.path.join(DATA_DIR, "users.db"))
ICS_DIR = os.getenv("ICS_DIR", os.path.join(DATA_DIR, "public"))
os.makedirs(ICS_DIR, exist_ok=True)

# cle de chiffrement - DOIT etre persistante en prod
# Si non definie, on cree/charge depuis un fichier local dans DATA_DIR
def _load_or_create_fernet_key() -> str:
    key_file = os.path.join(DATA_DIR, ".fernet_key")
    env_key = os.getenv("FERNET_KEY")
    if env_key:
        return env_key
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    # Creer une nouvelle cle et la sauvegarder
    new_key = Fernet.generate_key().decode()
    with open(key_file, "w") as f:
        f.write(new_key)
    return new_key

FERNET_KEY = _load_or_create_fernet_key()
FERNET = Fernet(FERNET_KEY.encode())

# refresh toutes les heures
REFRESH_MIN = int(os.getenv("REFRESH_MIN", "60"))

app = Flask(__name__)

# ================== DB helpers ==================
def _users_columns() -> set[str]:
    con = sqlite3.connect(DATABASE)
    try:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(users)")
        return {row[1] for row in cur.fetchall()}  # row[1] = name
    finally:
        con.close()

def init_db():
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    # Schéma minimal “neuf”
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
          token TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          enc_password BLOB NOT NULL,
          ics_path TEXT,
          last_updated TEXT
        )
        """
    )
    con.commit()
    # Migration douce : ajouter les colonnes legacy si absentes
    try:
        cur.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in cur.fetchall()}
        if "base_url" not in cols:
            cur.execute(
                "ALTER TABLE users ADD COLUMN base_url TEXT NOT NULL DEFAULT ?",
                (WIGOR_BASE_URL,),
            )
            con.commit()
        # certaines vieilles DB ont 'tel' NOT NULL
        if "tel" not in cols:
            cur.execute(
                "ALTER TABLE users ADD COLUMN tel TEXT NOT NULL DEFAULT ''"
            )
            con.commit()
    except sqlite3.OperationalError:
        # vieilles versions SQLite ou schéma exotique : ignorer
        pass
    finally:
        con.close()

def db_insert_user(username: str, enc_password: bytes) -> str:
    token = secrets.token_urlsafe(24)
    cols = _users_columns()

    # colonnes de base
    column_names = ["token", "username", "enc_password", "ics_path", "last_updated"]
    values = [token, username, enc_password, None, None]

    # colonnes optionnelles (legacy)
    if "base_url" in cols:
        column_names.append("base_url")
        values.append(WIGOR_BASE_URL)
    if "tel" in cols:
        column_names.append("tel")
        values.append(username)  # convention: Tel = username

    placeholders = ",".join(["?"] * len(values))
    sql = f"INSERT INTO users ({','.join(column_names)}) VALUES ({placeholders})"

    con = sqlite3.connect(DATABASE)
    try:
        cur = con.cursor()
        cur.execute(sql, values)
        con.commit()
        return token
    finally:
        con.close()

def db_get_user(token: str) -> Optional[dict]:
    con = sqlite3.connect(DATABASE)
    try:
        cur = con.cursor()
        cur.execute("SELECT token, username, enc_password, ics_path, last_updated FROM users WHERE token = ?", (token,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "token": row[0],
            "username": row[1],
            "enc_password": row[2],
            "ics_path": row[3],
            "last_updated": dt.datetime.fromisoformat(row[4]) if row[4] else None,
        }
    finally:
        con.close()

def db_all_users():
    con = sqlite3.connect(DATABASE)
    try:
        cur = con.cursor()
        cur.execute("SELECT token, username, enc_password FROM users")
        for token, username, enc_password in cur.fetchall():
            yield {"token": token, "username": username, "enc_password": enc_password}
    finally:
        con.close()

def db_update_cache(token: str, ics_path: str):
    con = sqlite3.connect(DATABASE)
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE users SET ics_path = ?, last_updated = ? WHERE token = ?",
            (ics_path, dt.datetime.utcnow().isoformat(), token),
        )
        con.commit()
    finally:
        con.close()

# ================== helpers ==================
def encrypt_pwd(p: str) -> bytes:
    return FERNET.encrypt(p.encode())

def decrypt_pwd(b: bytes) -> str:
    return FERNET.decrypt(b).decode()

def save_ics(token: str, ics_bytes: bytes) -> str:
    path = os.path.join(ICS_DIR, f"{token}.ics")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(ics_bytes)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # écriture atomique
    return path

def generate_rolling_ics(username: str, password: str) -> bytes:
    today = dt.date.today()
    dmin, dmax = default_two_weeks(today)
    cal = login_discover_and_collect(username, password, dmin, dmax)
    return cal.to_ical()

# ================== scheduler ==================
SCHED = BackgroundScheduler()

def refresh_all_users():
    app.logger.info("Refresh horaire: regeneration ICS (fenêtre 14 jours)")
    for u in db_all_users():
        try:
            pwd = decrypt_pwd(u["enc_password"])
            ics_bytes = generate_rolling_ics(u["username"], pwd)
            path = save_ics(u["token"], ics_bytes)
            db_update_cache(u["token"], path)
            app.logger.info("OK refresh %s", u["username"])
        except InvalidToken:
            app.logger.error("Fernet token invalide pour %s", u["username"])
        except Exception as e:
            app.logger.exception("Echec refresh %s: %s", u["username"], e)

# ================== HTTP ==================
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "username et password requis"}), 400

    # test rapide + première génération
    try:
        ics_bytes = generate_rolling_ics(username, password)
    except Exception as e:
        return jsonify({"error": f"échec connexion/génération: {e}"}), 400

    token = db_insert_user(username, encrypt_pwd(password))
    path = save_ics(token, ics_bytes)
    db_update_cache(token, path)

    feed_url = f"{request.url_root.rstrip('/')}/feed/{token}.ics"
    return jsonify({"token": token, "feed_url": feed_url})

@app.route("/feed/<token>.ics", methods=["GET"])
def feed(token):
    u = db_get_user(token)
    if not u:
        abort(404)
    if not u["ics_path"] or not os.path.exists(u["ics_path"]):
        try:
            pwd = decrypt_pwd(u["enc_password"])
            ics_bytes = generate_rolling_ics(u["username"], pwd)
            path = save_ics(u["token"], ics_bytes)
            db_update_cache(u["token"], path)
        except Exception as e:
            app.logger.exception("Echec generation on-demand %s", e)
            return f"Erreur ICS: {e}", 500
    else:
        with open(u["ics_path"], "rb") as f:
            ics_bytes = f.read()

    resp = Response(ics_bytes, mimetype="text/calendar; charset=utf-8")
    resp.headers["Content-Disposition"] = f'inline; filename="{token}.ics"'
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/healthz")
def healthz():
    return "ok"

# ================== INIT pour gunicorn ==================
def _init_app():
    """Initialise la DB et le scheduler. Appele au demarrage."""
    init_db()
    if not SCHED.running:
        SCHED.add_job(
            refresh_all_users,
            "interval",
            minutes=REFRESH_MIN,
            id="hourly_refresh",
            replace_existing=True
        )
        SCHED.start()

# Initialisation automatique (compatible gunicorn)
_init_app()

def main():
    """Point d'entree pour execution directe (dev)."""
    try:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)
    finally:
        if SCHED.running:
            SCHED.shutdown()

if __name__ == "__main__":
    main()

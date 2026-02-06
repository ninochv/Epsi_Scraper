# ============================================
# Dockerfile pour Epsi Scraper - Dokploy ready
# ============================================
FROM python:3.12-slim

# Metadata
LABEL maintainer="epsi-scraper"
LABEL description="Wigor to ICS calendar converter"

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DATA_DIR=/data

# Installer les dependances systeme
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Creer un utilisateur non-root
RUN useradd --create-home --shell /bin/bash appuser

# Repertoire de travail
WORKDIR /app

# Copier les requirements et installer les dependances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY server.py .
COPY wigor_to_calendar.py .
COPY templates/ ./templates/

# Creer les repertoires pour les donnees persistantes
RUN mkdir -p /data/public && chown -R appuser:appuser /data /app

# Passer a l'utilisateur non-root
USER appuser

# Variables d'environnement pour les donnees persistantes
ENV EPSI_DB=/data/users.db
ENV ICS_DIR=/data/public

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1

# Exposer le port
EXPOSE ${PORT}

# Commande de demarrage avec gunicorn
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - server:app"]

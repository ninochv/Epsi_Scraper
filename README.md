# Epsi Scraper - Wigor to ICS

Convertisseur d'emploi du temps Wigor (EPSI) vers le format ICS pour integration dans vos applications calendrier.

## Fonctionnalites

- **Connexion securisee CAS** : Authentification via le portail CAS Wigor
- **Export ICS** : Convertit l'emploi du temps en format iCalendar standard
- **Serveur web** : Interface simple pour generer un lien ICS personnel
- **Refresh automatique** : Regeneration toutes les heures (configurable)
- **Fenetre de 14 jours** : Couvre les 2 prochaines semaines par defaut
- **Docker ready** : Pret pour le deploiement sur Dokploy, Railway, etc.

## Deploiement Dokploy (recommande)

### Option 1 : Depuis un repo Git

1. Dans Dokploy, creez une nouvelle application
2. Selectionnez "Docker" comme type de build
3. Connectez votre repository Git
4. Configurez les variables d'environnement :
   - `PORT` : 8080 (ou le port de votre choix)
   - `FERNET_KEY` : (optionnel) cle de chiffrement personnalisee
   - `REFRESH_MIN` : 60 (intervalle de refresh)
5. Ajoutez un volume persistant monte sur `/data`
6. Deployez !

### Option 2 : Docker Compose local

```bash
# Cloner et lancer
git clone <repo-url>
cd Epsi_Scraper
docker-compose up -d

# Voir les logs
docker-compose logs -f
```

### Variables d'environnement Docker

| Variable | Description | Valeur par defaut |
|----------|-------------|-------------------|
| `PORT` | Port du serveur | `8080` |
| `FERNET_KEY` | Cle de chiffrement (generee auto si vide) | - |
| `REFRESH_MIN` | Intervalle de refresh (minutes) | `60` |
| `DATA_DIR` | Repertoire des donnees | `/data` |

> **Important** : Montez un volume sur `/data` pour persister la base de donnees et les fichiers ICS.

## Installation locale

```bash
# Cloner le projet
git clone <repo-url>
cd Epsi_Scraper

# Installer les dependances
pip install -r requirements.txt
```

## Utilisation

### Mode serveur web (recommande)

```bash
python server.py
```

Ouvrez http://localhost:8080 dans votre navigateur, entrez vos identifiants Wigor, et recevez un lien ICS a ajouter dans votre calendrier.

### Mode ligne de commande

```bash
# Mode interactif (mot de passe masque)
python wigor_to_calendar.py --user prenom.nom

# Avec mot de passe en argument
python wigor_to_calendar.py --user prenom.nom --password "votre_mdp"

# Via variable d'environnement
$env:WIGOR_PASS="votre_mdp"
python wigor_to_calendar.py --user prenom.nom

# Avec plage de dates personnalisee
python wigor_to_calendar.py --user prenom.nom --from 2026-02-01 --to 2026-02-28

# Mode debug avec dump des reponses HTML
python wigor_to_calendar.py --user prenom.nom --debug --dump-dir ./debug_html
```

## Configuration

Variables d'environnement disponibles :

| Variable | Description | Valeur par defaut |
|----------|-------------|-------------------|
| `EPSI_DB` | Chemin de la base SQLite | `users.db` |
| `ICS_DIR` | Dossier des fichiers ICS | `public` |
| `FERNET_KEY` | Cle de chiffrement Fernet | Auto-generee et sauvegardee |
| `REFRESH_MIN` | Intervalle de refresh (minutes) | `60` |
| `PORT` | Port du serveur web | `8080` |

## Integration calendrier

Une fois le lien ICS genere, ajoutez-le comme "abonnement calendrier" :

- **Google Calendar** : Parametres > Ajouter un agenda > A partir d'une URL
- **Apple Calendar** : Fichier > Nouvel abonnement au calendrier
- **Outlook** : Ajouter un calendrier > S'abonner depuis le web

## Structure du projet

```
Epsi_Scraper/
├── Dockerfile             # Image Docker
├── docker-compose.yml     # Orchestration Docker
├── server.py              # Serveur Flask principal
├── wigor_to_calendar.py   # Logique de scraping et generation ICS
├── requirements.txt       # Dependances Python
├── .env.example           # Exemple de configuration
├── .dockerignore          # Fichiers ignores par Docker
├── templates/
│   └── index.html         # Interface web
└── /data/                 # (Docker) Donnees persistantes
    ├── users.db           # Base de donnees utilisateurs
    ├── .fernet_key        # Cle de chiffrement
    └── public/            # Fichiers ICS generes
```

## Securite

- Les mots de passe sont chiffres avec Fernet (symmetric encryption)
- La cle de chiffrement est persistee dans `/data/.fernet_key`
- Ne partagez jamais votre lien ICS personnel
- En production, definissez `FERNET_KEY` comme variable d'environnement

## Dependances

- Flask >= 2.0
- requests >= 2.28
- beautifulsoup4 >= 4.12
- icalendar >= 5.0
- pytz >= 2023.0
- cryptography >= 41.0
- apscheduler >= 3.10
- gunicorn >= 21.0

## Licence

MIT

# Application de gestion commerciale (Flask)



Application web moderne pour gerer:

- les clients

- les rendez-vous commerciaux

- les suivis (follow-up)

- le pipeline commercial



## Stack

- Backend: Flask (Python)

- Frontend: HTML/CSS/JS + Bootstrap 5

- Base de donnees: SQLite (`crm.sqlite3`)



## Fonctionnalites

- Dashboard avec statistiques et repartition pipeline

- CRUD clients (avec etape pipeline)

- CRUD rendez-vous + marquage termine + creation rapide de suivi

- Suivis: creation, filtre, marquage termine, retard visuel

- Authentification avec mot de passe hash + connexion email/username

- Recherche, filtres et pagination

- Export CSV clients et rendez-vous

- Theme moderne vert/blanc + mode sombre



## Structure

```

app.py

models/

routes/

templates/

static/

```



## Lancement

1. Creer un environnement virtuel:

   - `py -m venv .venv`

2. Installer les dependances:

   - `py -m pip install -r requirements.txt`

3. Demarrer l'application:

   - `py app.py`

4. Ouvrir:

   - [http://127.0.0.1:5000](http://127.0.0.1:5000)



## Compte de demonstration

- Email: `admin@crm.local`

- Username: `admin`

- Mot de passe: `admin123`



> Important: changer `SECRET_KEY` et les identifiants en production.


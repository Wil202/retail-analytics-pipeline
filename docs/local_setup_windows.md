# Installer et visualiser le projet sur ta machine (Windows)

Durée : environ 45 min la première fois (dont ~10 min de téléchargements). Les commandes sont à taper dans
**PowerShell**. Remplace `<toi>` par ton nom d'utilisateur Windows.

---

## 1. Installer les prérequis (une seule fois)

| Outil | Où | Option importante |
|---|---|---|
| Python 3.12 | https://www.python.org/downloads/windows/ | cocher **« Add python.exe to PATH »** |
| PostgreSQL 16 | https://www.postgresql.org/download/windows/ (installeur EDB) | noter le mot de passe de l'utilisateur `postgres` ; port 5432 |
| Git | https://git-scm.com/download/win | options par défaut |

Docker Desktop est une alternative à l'installation de PostgreSQL (voir l'étape 4, variante B). Il est plus
lourd sur un portable ; l'installeur PostgreSQL est le chemin le plus simple.

Vérification, dans un **nouveau** PowerShell :

```powershell
py -3.12 --version          # Python 3.12.x
git --version
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" --version
```

## 2. Récupérer le projet

1. Télécharge `retail-analytics-pipeline.zip` depuis la conversation avec Claude.
2. Clic droit → **Extraire tout…** vers `C:\Users\<toi>\Documents\`.
3. Tu obtiens `C:\Users\<toi>\Documents\retail-analytics-pipeline\`.

```powershell
cd $HOME\Documents\retail-analytics-pipeline
dir      # README.md, src, sql, dashboard, tests, docs...
```

## 3. Créer TON dépôt Git (avant toute publication)

L'archive ne contient pas d'historique Git. Crée-le à ton nom : c'est toi qui seras l'auteur des commits.

```powershell
git init -b main
git config user.name  "Prénom Nom"
git config user.email "ton.adresse@exemple.com"     # l'adresse de ton compte GitHub
git add -A
git status               # .env, .venv et data/raw ne doivent PAS apparaître
git commit -m "Pipeline Online Retail II : ingestion, qualité, PostgreSQL, marts, dashboard, tests"
```

## 4. Préparer PostgreSQL

### Variante A — PostgreSQL installé (recommandé)

Choisis un mot de passe pour l'utilisateur du projet (exemple ci-dessous : `MonMotDePasse2026`).

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost
```

Dans `psql` (le mot de passe demandé est celui de `postgres`, choisi à l'installation) :

```sql
CREATE USER retail WITH PASSWORD 'MonMotDePasse2026';
CREATE DATABASE retail OWNER retail;
CREATE DATABASE retail_test OWNER retail;
\q
```

### Variante B — Docker Desktop

```powershell
copy .env.example .env     # puis remplace change_me dans .env (étape 6)
docker compose up -d
docker compose ps          # attendre « healthy » ; crée aussi retail_test automatiquement
```

## 5. Créer l'environnement Python

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell refuse (« l'exécution de scripts est désactivée »), autorise les scripts pour ton
utilisateur uniquement, puis relance l'activation :

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

L'invite commence alors par `(.venv)`. Installe ensuite les versions exactes testées :

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt
pip install -e .
```

## 6. Configurer la connexion

```powershell
copy .env.example .env
notepad .env
```

Remplace **les trois** occurrences de `change_me` par ton mot de passe, puis enregistre :

```
POSTGRES_PASSWORD=MonMotDePasse2026
DATABASE_URL=postgresql+psycopg://retail:MonMotDePasse2026@localhost:5432/retail
TEST_DATABASE_URL=postgresql+psycopg://retail:MonMotDePasse2026@localhost:5432/retail_test
```

Si ton mot de passe contient `@`, `:`, `/` ou `#`, encode-le dans les deux URL (`@` → `%40`, `:` → `%3A`,
`/` → `%2F`, `#` → `%23`). `.env` est ignoré par Git : il ne sera jamais publié.

```powershell
python -m retail_analytics.cli check-db     # affiche « PostgreSQL 16.x … »
```

## 7. Lancer le pipeline

Démonstration rapide (échantillon synthétique, 4 051 lignes, quelques secondes) :

```powershell
python -m retail_analytics.cli run --source sample
```

Vraies données (1,07 M lignes ; prévois ~4 Go de RAM libres et 2 à 3 min) :

```powershell
python -m retail_analytics.cli fetch-uci --mirror   # source officielle UCI, sinon copie épinglée (SHA-256 vérifié)
python -m retail_analytics.cli run --source uci
python -m retail_analytics.cli report --output docs\analysis_uci.md
```

Résultat attendu : `Lignes lues : 1067371`, `Ventes valides : 1003340 (94.0%)`, `Doublons exacts : 34335`.
Si tu obtiens d'autres chiffres, note-les : c'est une information à investiguer, pas à masquer.

## 8. Visualiser le dashboard

```powershell
streamlit run dashboard\app.py
```

Le navigateur s'ouvre sur **http://localhost:8501** (sinon, ouvre l'adresse à la main).

- **Dataset** : `uci_online_retail_ii` (données réelles) est sélectionné par défaut ;
  `synthetic_sample` porte un bandeau « données synthétiques ».
- **Période**, **Pays**, **Taille des classements**, **Classer les produits par** : filtres.
- Premier affichage : ~6 s sur les données réelles, puis instantané (cache).

Pour arrêter le serveur : `Ctrl + C` dans PowerShell.

## 9. Lancer les tests

```powershell
$env:REQUIRE_DB = "1"; pytest -q
```

Attendu : `101 passed, 3 skipped` (les 3 tests ignorés sont ceux sur données réelles, à lancer sur demande) :

```powershell
$env:RUN_REAL_DATA = "1"; pytest tests\test_real_data.py
```

`REQUIRE_DB=1` fait échouer les tests d'intégration si la base est injoignable, au lieu de les ignorer.
**C'est le premier test sur une vraie machine Windows** : si quelque chose échoue, copie le message d'erreur
complet dans la conversation.

## 10. Me connecter le dossier (optionnel)

Pour que je puisse travailler directement sur ta copie :

1. Ouvre cette conversation dans l'**application de bureau Claude** sur ce PC.
2. Utilise le bouton **« Add folder »** (ajouter un dossier) et choisis
   `C:\Users\<toi>\Documents\retail-analytics-pipeline`.
3. Envoie un message. Je pourrai alors lire et modifier les fichiers, et y exécuter des commandes.

Limite à connaître : ces commandes s'exécutent dans une machine virtuelle Linux qui voit ton dossier, pas
dans Windows lui-même. Elles ne remplacent donc pas le test Windows de l'étape 9, que tu dois lancer
toi-même.

## 11. Publier sur GitHub (quand tu le décides)

1. Crée un dépôt **vide** `retail-analytics-pipeline` sur GitHub (sans README ni licence).
2. Remplace le titulaire du copyright dans `LICENSE` par ton nom, puis commite.
3. Pousse :

```powershell
git remote add origin https://github.com/<ton-compte>/retail-analytics-pipeline.git
git push -u origin main
```

4. Onglet **Actions** : le workflow `tests` démarre (PostgreSQL de test inclus). Il n'a encore jamais tourné
   sur GitHub : vérifie qu'il passe au vert. Le badge du README s'affichera alors.

Avant de pousser, vérifie qu'aucun fichier sensible n'est suivi :

```powershell
git ls-files | Select-String -Pattern "\.env$|\.venv|data/raw|\.rda|\.xlsx"   # ne doit rien afficher
```

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `py` n'est pas reconnu | Python absent du PATH | réinstaller Python en cochant « Add to PATH » |
| `Activate.ps1 … désactivée` | politique d'exécution | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Connexion PostgreSQL impossible : … refused` | service arrêté | `services.msc` → démarrer `postgresql-x64-16` |
| `password authentication failed` | mot de passe différent dans `.env` | corriger les 3 lignes de `.env` |
| `Base incompatible … v…` | base créée par une autre version | utiliser une base vide (ou supprimer les schémas `raw`, `staging`, `marts`, `meta`) |
| `Chargement impossible : un autre chargement est en cours` | un chargement tourne déjà | attendre sa fin |
| `MemoryError` pendant `run --source uci` | RAM insuffisante | fermer des applications ; 4 Go libres nécessaires |
| Le port 8501 est occupé | autre Streamlit ouvert | `streamlit run dashboard\app.py --server.port 8502` |
| Dashboard « Aucun dataset chargé » | pipeline pas encore lancé | étape 7 |

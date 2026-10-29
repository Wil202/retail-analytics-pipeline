# Architecture et décisions

## Principe : trois couches en base, nettoyage en Python

| Couche | Contenu | Écrite par | Règle |
|---|---|---|---|
| `raw` | texte brut + provenance | `load.py` | insertion seule, jamais modifiée |
| `staging` | lignes typées + indicateurs qualité | `load.py` (upsert) | 1 ligne raw = 1 ligne staging |
| `marts` | vues analytiques | `sql/02_marts.sql` | 100 % dérivées, reconstruites à chaque run |
| `meta` | journal des runs, version active | `load.py` | traçabilité |

Le nettoyage est fait en Pandas (transform.py) et les agrégats en SQL (marts). Les deux sont séparés
pour pouvoir tester le nettoyage sans base et rejouer les marts sans relire la source. Ce n'est donc pas un
ELT « pur » (où toute transformation se ferait en SQL après chargement) : le brut est bien conservé en base,
mais le typage a lieu avant l'écriture de `staging`.

## Responsabilités des modules

| Module | Responsabilité | Ne fait pas |
|---|---|---|
| `sources.py` | télécharger et vérifier les fichiers (UCI, miroir SHA-256) | lire leur contenu |
| `extract.py` | lire CSV / XLSX / RDA en texte, avec provenance | typer ou juger les valeurs |
| `transform.py` | typer, classer chaque ligne, marquer les doublons | supprimer des lignes, accéder à la base |
| `validate.py` | schéma bloquant, seuil d'illisibilité, rapport qualité | modifier les données |
| `load.py` / `db.py` | écrire raw + staging + marts dans une transaction, verrou, version de schéma | calculer des KPI |
| `sql/02_marts.sql` | agrégats analytiques | logique de nettoyage |
| `kpis.py` | requêtes paramétrées du dashboard + référence Pandas pour les tests | affichage |
| `report.py` | rapport Markdown depuis les marts | interprétation (dans `findings.md`) |
| `cli.py` | arguments, messages, codes de sortie | logique métier ou réseau |
| `dashboard/app.py` | affichage, filtres, cache | calculs (tous délégués à `kpis.py`) |

## Décisions

**1. Ne jamais supprimer, toujours marquer.** Chaque ligne problématique reste visible avec un
`line_type` et, si besoin, un `invalid_reason`. Les KPI filtrent sur `is_valid_sale`. On peut donc
auditer chaque exclusion et changer une règle sans perte d'information.

**2. Idempotence par clé de provenance.** La clé `(dataset, file_sha256, source_sheet, source_row)`
identifie une ligne du fichier source. Un rechargement du même fichier est un no-op sur `raw`
(`ON CONFLICT DO NOTHING`) et un upsert sur `staging` (une règle de nettoyage modifiée s'applique).
Une clé métier (facture + produit) aurait été fausse : le dataset contient de vrais doublons exacts.

**3. Version active par dataset.** `meta.dataset_current` pointe vers l'empreinte du fichier actif ;
`staging.current_sales_lines` ne lit que celle-là. Charger une nouvelle version ne double donc pas
les ventes, et l'historique brut reste disponible pour l'audit.

**4. Une seule transaction.** raw + staging + version active + marts + statut du run sont validés
ensemble. En cas d'erreur, rien n'est modifié et le run est marqué `failed` (testé avec une panne simulée).

**5. Validation à deux niveaux.** Un schéma invalide ou plus de 5 % de lignes illisibles signifient un
fichier inattendu : arrêt avant toute écriture. Les problèmes de qualité « normaux » (clients manquants,
annulations…) sont mesurés et documentés, pas bloquants.

**6. COPY plutôt que `to_sql`.** `COPY FROM STDIN` vers une table temporaire puis `INSERT … SELECT …
ON CONFLICT` : ~1,07 M lignes en ~90 s, contre plusieurs dizaines de minutes en INSERT ligne à ligne.

**7. Vues matérialisées reconstruites (DROP + CREATE).** Plus simple que `REFRESH` pour faire évoluer
leur définition ; sans risque car elles ne contiennent que des données dérivées.

**8. KPI définis une fois, vérifiés deux fois.** `kpis.py` contient les requêtes SQL filtrables utilisées
par le dashboard et une implémentation Pandas de référence. Les tests vérifient qu'elles concordent et
qu'elles égalent le mart `kpi_summary`. Le dashboard n'a aucune valeur codée en dur.

**9. Clients distincts non additifs.** `daily_country_sales` est au grain jour × pays où CA, unités et
commandes s'additionnent (une facture = un jour, un pays). Les clients distincts sont toujours recalculés
depuis `fct_sales` avec les filtres.

**10. Sécurité.** Connexion via variables d'environnement (`.env` ignoré par Git, `.env.example` sans
secret). Requêtes paramétrées ; la seule partie dynamique du SQL (`ORDER BY`) passe par une liste blanche.
Les tests refusent de tourner sur une base dont le nom ne finit pas par `_test`.

**11. Source de repli vérifiée.** UCI étant parfois injoignable, le pipeline peut lire la copie du
package R `onlineretail2` (`.rda`, via `pyreadr`), épinglée par commit et SHA-256. Le fichier officiel reste
prioritaire, et `tests/test_real_data.py` contrôle le nombre de lignes et la période par rapport à la page UCI.

**12. Rapport généré.** `report.py` écrit `docs/analysis_*.md` directement depuis les marts : aucun chiffre
n'est recopié à la main. L'interprétation est rédigée séparément (`findings.md`).

**13. Schéma versionné, sans outil de migration.** `meta.schema_info` contient la version du schéma persistant
(`db.SCHEMA_VERSION`, testée contre `01_schema.sql`). Une base incompatible est refusée avant toute écriture,
avec un message explicite. Les marts, reconstruits à chaque chargement, ne sont pas versionnés. Alembic
serait disproportionné pour 4 tables ; à envisager dès la première vraie migration de données.

**14. Verrou de chargement borné.** Le verrou consultatif PostgreSQL attend au plus `PIPELINE_LOCK_TIMEOUT`
secondes (900 par défaut, pour un chargement réel de ~2 min), puis échoue avec un message clair.

**15. Vue par défaut du dashboard = totaux des marts.** La période par défaut couvre les ventes ET les
annulations (une annulation postérieure à la dernière vente est comptée), et les produits sont classés au CA
net : la première vue d'un visiteur ne contredit ni les marts, ni l'analyse (`findings.md`).

**16. Dépendances reproductibles.** `requirements.txt` liste les dépendances directes ; `constraints.txt` fige
toutes les versions (transitives comprises) de l'environnement testé. La CI installe avec les deux.

## Performances mesurées (1 067 371 lignes réelles, PostgreSQL 16 local)

| Étape | Durée | Pic mémoire |
|---|---|---|
| Lecture `.rda` + nettoyage | ~25 s | — |
| Lecture `.xlsx` (2 feuilles, openpyxl) + nettoyage, `--dry-run` | 126 s | 1,7 Go |
| Chargement complet (`run --source uci`) | ~110 s | 2,1 Go |
| Dashboard, premier affichage (4 requêtes, cache froid côté Streamlit) | ~6 s | — |
| Dashboard, 1 mois × 1 pays | ~0,5 s | — |

Le coût du dashboard vient des `COUNT(DISTINCT)` sur 1 M de lignes. Une table de faits matérialisée et
indexée a été prototypée : 8× plus rapide sur une vue filtrée, mais aucun gain sur la vue complète. Elle n'a
pas été adoptée (complexité de migration pour un gain limité) ; voir `docs/review.md`.

## Ce qui n'est pas inclus, et quand l'ajouter

| Outil | Pourquoi pas maintenant | Quand l'ajouter |
|---|---|---|
| dbt | 1 fichier SQL de marts, déjà testé | > 10 modèles, besoin de lignage et de tests SQL déclaratifs |
| Airflow / Dagster | source statique, run à la demande | sources récurrentes, dépendances entre jobs, reprise sur erreur |
| Cloud (BigQuery…) | volume ~1 M lignes, PostgreSQL suffit | volumes > dizaines de Go ou partage multi-équipe |
| Parquet | pas nécessaire au volume actuel | cache de la lecture xlsx (lente) entre runs |

## Pistes d'évolution

1. Cache Parquet de la lecture xlsx (plusieurs minutes avec openpyxl).
2. Migrer `02_marts.sql` vers dbt avec tests `unique` / `not_null` / `accepted_values`.
3. Analyse RFM et cohortes clients (d'après les analyses publiques, environ trois quarts des lignes réelles ont un `customer_id` ; à confirmer avec le rapport qualité).
4. Lecture `.xlsx` en flux (openpyxl `read_only`) et COPY par lots pour réduire le pic mémoire (2,1 Go).

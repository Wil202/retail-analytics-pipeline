# Revue avant publication — retail-analytics-pipeline

Revue de type « Staff Data Engineer » réalisée le 2026-10-20, après l'audit QA (`docs/qa_report.md`).
Méthode : mesures avant jugement (Git, lint, plans SQL, chronométrages et mémoire sur 1,07 M de lignes,
captures d'écran du dashboard réel), puis correction des P0/P1 avec un test pour chacun.

**Classement.** P0 = bloquant ou risque sérieux ; P1 = fiabilité ou conception importante ; P2 = amélioration facultative.

## Synthèse

| | Trouvés | Corrigés | Restants |
|---|---|---|---|
| P0 | 1 | 0 (action de ta part, guidée) | 1 |
| P1 | 8 | 8 | 0 |
| P2 | 12 | 6 | 6 |

## P0

| ID | Problème | Preuve | Résolution |
|---|---|---|---|
| P0-1 | **Les 3 commits locaux ont pour auteur « Claude <noreply@anthropic.com> ».** Publiés tels quels, ils attribueraient tout le portfolio à quelqu'un d'autre. | `git log --format='%an <%ae>'` | Non corrigé ici : réécrire l'historique est une opération que je ne fais pas sans ton accord. L'archive `.zip` ne contient pas d'historique : `docs/local_setup_windows.md` §3 te fait créer le premier commit à ton nom. |

## P1 — corrigés

| ID | Problème | Preuve | Correction | Test |
|---|---|---|---|---|
| P1-1 | **Vue par défaut du dashboard ≠ marts** dès qu'une annulation est postérieure à la dernière vente (période par défaut calculée sur les seules ventes). | test sur l'ancien code : annulé 0 £ affiché contre 2 £ dans `kpi_summary` | période = ventes ∪ annulations | `test_review::test_dashboard_default_period_reproduces_mart_totals` (échoue sur l'ancien code) |
| P1-2 | **Top 10 produits classé par défaut au CA brut** : sur les données réelles, il met en avant deux produits dont les ventes ont été annulées à 100 % et à 95 %, contredisant l'analyse du projet. | capture d'écran avant / après | classement par défaut au CA net | `test_dashboard::test_dashboard_ranks_products_by_net_revenue_by_default` |
| P1-3 | **Verrou de chargement sans délai** : un chargement bloqué fige tous les suivants indéfiniment. | lecture du code (`pg_advisory_lock`) | `lock_timeout` (900 s, `PIPELINE_LOCK_TIMEOUT`) + message dédié, code 2 | `test_review::test_waiting_for_the_load_lock_is_bounded` |
| P1-4 | **Schéma non versionné** : avec une base créée par une autre version, `CREATE TABLE IF NOT EXISTS` garde l'ancienne table, et l'erreur arrive plus tard, obscure (COPY). | lecture du code | `meta.schema_info` + contrôle avant toute écriture ; les bases antérieures (v1) sont acceptées | `test_review::test_incompatible_schema_*`, `*_created_before_versioning_*`, `test_schema_version_constant_matches_sql_script` |
| P1-5 | **Dépendances transitives non figées** (NumPy, PyArrow…) : deux installations à des dates différentes ne sont pas identiques ; un avertissement de dépréciation NumPy dans pandas l'a déjà montré. | `pip freeze` | `constraints.txt` (52 paquets, aucun spécifique à un OS) | installation neuve avec contraintes = environnement testé (`diff` vide) |
| P1-6 | **Aucune intégration continue** : « tous les tests passent » n'était vérifiable que sur ma machine. | — | `.github/workflows/ci.yml` (PostgreSQL de service, `REQUIRE_DB=1`, contraintes, reproductibilité de l'échantillon) | étapes rejouées à l'identique sans `.env` : 100 passed (+1 test ajouté ensuite) ; **jamais exécuté sur GitHub** |
| P1-7 | **Licence annoncée mais absente** : le README dit « MIT », mais sans fichier `LICENSE` le code est juridiquement « tous droits réservés ». | `ls LICENSE` | `LICENSE` MIT, avec mention que le dataset n'est pas inclus | — |
| P1-8 | **Chemin officiel `.xlsx` jamais exécuté à l'échelle** (seul le miroir `.rda` l'avait été). | — | fichier de 1 067 371 lignes au format UCI (2 feuilles) reconstruit à partir des vraies données → **chiffres identiques** au `.rda` ; 126 s, 1,7 Go | exécution manuelle (fichier de 48 Mo non versionné) |

## P2 — corrigés (coût faible, gain net)

| ID | Problème | Correction |
|---|---|---|
| P2-1 | Téléchargement, vérification SHA-256 et décompression mélangés à la CLI | module `sources.py` ; `cli.py` ne garde que les arguments et les messages (testé) |
| P2-2 | Dashboard : axe des mois sans année (deux « December »), noms de produits tronqués, en-têtes mi-français mi-anglais, double négation « ↓ -£716 426 » | axe `%b %Y`, `labelLimit`, en-têtes français, annulations dans l'aide du KPI |
| P2-3 | Le dashboard ouvrait par défaut l'échantillon synthétique (ordre alphabétique) | données réelles d'abord |
| P2-4 | Bouton « Deploy » et menu développeur visibles des visiteurs | `.streamlit/config.toml` : `toolbarMode = "viewer"` |
| P2-5 | Aucun visuel dans le README | capture réelle du dashboard (`docs/img/dashboard.png`), données réelles, non retouchée |
| P2-6 | Le terme « ELT » est inexact : le typage se fait en Python avant le chargement de staging | architecture décrite comme hybride ; tableau des responsabilités par module |

## P2 — non corrigés (documentés)

| ID | Constat mesuré | Pourquoi pas maintenant |
|---|---|---|
| P2-7 | Dashboard : ~6 s au premier affichage sur 1 M de lignes (`COUNT(DISTINCT)`), puis instantané grâce au cache. | Table de faits matérialisée prototypée : 8× plus rapide filtrée (0,19 → 0,02 s), **aucun gain** sur la vue complète. Gain limité face à une migration vue → vue matérialisée. |
| P2-8 | Pic mémoire de 2,1 Go au chargement (DataFrame complet + conversion pour COPY). | Acceptable sur un portable de 8 Go ; COPY par lots et lecture `.xlsx` en flux en v2. |
| P2-9 | `marts.daily_country_sales` n'est lu ni par le dashboard ni par le rapport (seulement par un test de cohérence). | Utile pour une future optimisation (grain additif vérifié : 0 facture sur plusieurs jours ou pays) ; à supprimer si elle reste inutilisée. |
| P2-10 | `requirements.txt` et `pyproject.toml` décrivent tous deux les dépendances. | Rôles différents (application vs paquet) ; `constraints.txt` fait foi pour la reproductibilité. |
| P2-11 | Le dashboard se connecte avec l'utilisateur propriétaire du schéma (droits d'écriture). | Usage local ; en déploiement, créer un rôle en lecture seule sur `marts`. |
| P2-12 | Lint `ruff` : 12 remarques de style (fonction `main` à nombreux `return`, `datetime.UTC`…), **0 bug potentiel**. Le seul avertissement bugbear (un `pytest.raises(Exception)` trop large dans un test ajouté pendant cette revue) a été corrigé. | Pas d'impact ; ajouter `ruff` à la CI en v2. |

## Vérifié sans problème

- **Secrets** : aucun dans l'historique Git (recherche de mots de passe, clés AWS, jetons GitHub, clés privées) ; `.env` jamais suivi ; les données UCI ne sont pas versionnées.
- **Fichiers indésirables** : 58 fichiers suivis ; le plus gros est l'échantillon synthétique (316 Ko). Un seul binaire, la capture du dashboard (PNG, 0,2 Mo). Ni `.venv`, ni cache, ni données sources.
- **Séparation des responsabilités** : aucun calcul dans le dashboard (tout passe par `kpis.py`) ; nettoyage sans accès à la base ; SQL des marts sans logique de nettoyage.
- **SQL** : requêtes paramétrées ; seul `ORDER BY` est dynamique, filtré par une liste blanche ; contraintes `CHECK` et clés étrangères sur staging.
- **Cohérence métier** : sur les données réelles, la vue par défaut du dashboard, `kpi_summary`, le rapport et la somme de chaque mart sont égaux au centime.

## Ce que je n'ai pas pu vérifier

- Exécution sous **Windows** (ta machine) : à faire avec `docs/local_setup_windows.md` §9.
- Le workflow **GitHub Actions** sur GitHub, et le badge du README.
- **Docker** : registre d'images inaccessible depuis l'environnement de revue.
- Le `.xlsx` **téléchargé chez UCI** : vérifié sur une reconstruction au même format, pas sur le fichier officiel.

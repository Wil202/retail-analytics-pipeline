# Rapport QA et fiabilité — retail-analytics-pipeline

Audit réalisé le 2026-10-20 sur le commit `60bb517`. Environnement : Python 3.12.3, PostgreSQL 16.15
local, pandas 2.3.3, SQLAlchemy 2.1.5, Streamlit 1.66.0.

## Méthode

1. **Inventaire des points d'entrée** : CLI `retail_analytics.cli` (`generate-sample`, `fetch-uci`,
   `check-db`, `run`, `report`), `dashboard/app.py`, API Python (`run_pipeline`, `kpis.*`).
2. **État de référence** : 65 tests passés, 3 ignorés (opt-in). Avec la base arrêtée : 43 passés et 25 ignorés,
   **sans aucun signal d'alerte**.
3. **Sondes manuelles** (scripts hors dépôt) sur 11 fichiers piégés et 3 scénarios de base de données.
4. **Un test par défaut, écrit avant la correction**, puis vérifié en échec : 12 tests en échec et 1 module
   impossible à importer.
5. **Corrections**, puis relance des sondes, de la suite complète et du pipeline sur les 1 067 371 lignes réelles.

Aucun test existant n'a été supprimé ou affaibli. Aucun résultat attendu n'a été modifié. Les tests
d'intégration ne touchent qu'une base dont le nom se termine par `_test`.

## Défauts trouvés et corrigés

Sévérité : **Haute** = résultat faux ou perte d'information silencieuse ; **Moyenne** = échec ou blocage
sans explication ; **Basse** = confort ou diagnostic.

| ID | Sév. | Symptôme observé (avant) | Correction | Test |
|---|---|---|---|---|
| D7 | Haute | `01/12/2010` lu comme le **12 janvier** : dates européennes inversées sans avertissement | ordre jour/mois déduit de toute la colonne ; ambigu → avertissement ; mélangé → non deviné ; option `--date-order` | `test_edge_cases::test_day_first_*`, `*_ambiguous_*`, `*_mixed_*` |
| D13 | Haute | dashboard : cache de 5 min, d'où les **anciens chiffres** affichés après un rechargement | clé de cache = n° du run actif ; liste des datasets non mise en cache | `test_reliability::test_dashboard_shows_new_data_immediately_after_reload` |
| D16 | Haute | dashboard : une seule date choisie → **filtre ignoré en silence**, toute la période affichée | filtrage sur le jour choisi + message | `test_dashboard_single_date_selection_filters_that_day` |
| D9 | Haute | dataset sans vente valide (annulations seules) : `kpi_summary` vide alors que `kpis()` compte £6 ; rapport « lancez d'abord le pipeline » (faux) | `kpi_summary` construit depuis `meta.dataset_current` | `test_cancellation_only_dataset_has_a_consistent_summary` |
| D8 | Haute | dates 2099 et 1900 acceptées comme ventes | raison `date_out_of_range` (bornes 2000-01-01 et maintenant + 1 j), date conservée | `test_out_of_range_dates_are_invalid` |
| D10 | Moyenne | si l'enregistrement de l'échec échoue, l'**erreur d'origine est masquée** et le run reste `running` à vie | erreur d'origine toujours relancée ; runs `running` marqués `failed` (« interrompu ») au chargement suivant | `test_error_while_recording_failure_*`, `test_interrupted_runs_*` |
| D11 | Moyenne | 4 chargements simultanés → **3 échecs** `UniqueViolation pg_namespace` | verrou consultatif PostgreSQL autour du chargement | `test_concurrent_loads_are_serialised` |
| D14 | Moyenne | hôte injoignable → `check-db` **bloqué > 2 min** | `connect_timeout` (10 s, `DB_CONNECT_TIMEOUT`) | `test_unreachable_host_fails_fast` |
| D1 | Moyenne | base arrêtée ou non configurée → **trace Python** brute (`run`, `report`) | erreurs attendues traitées dans `main()` : 1 ligne + code 2 (env) / 3 (données) | `test_run_without_*`, `test_report_without_*`, `test_invalid_source_file_*` |
| D5 | Moyenne | CSV Windows-1252 → `UnicodeDecodeError` | repli cp1252 + avertissement dans le rapport qualité | `test_cp1252_csv_is_read_with_warning` |
| D6 | Moyenne | date US avec secondes `12/1/2010 08:26:00` → rejetée | formats avec et sans secondes | `test_us_date_with_seconds_is_parsed` |
| D2 | Moyenne | base de test absente → 25 tests ignorés, **suite verte** | `REQUIRE_DB=1` transforme ces skips en échecs (CI) | vérifié : 28 erreurs avec `REQUIRE_DB=1` et base injoignable |
| D15 | Basse | téléchargements sans délai (`urlretrieve`) ; fichier partiel du miroir conservé | `urlopen(timeout=60)`, fichier `.part` supprimé en cas d'échec | `test_mirror.py` (inchangé, passe) |
| D3 | Basse | fichier de 0 octet → `EmptyDataError` | `ValueError : Fichier vide` → code 3 | `test_zero_byte_file_gives_clear_error` |
| D4 | Basse | CSV à `;` → liste de colonnes manquantes sans explication | message indiquant le séparateur probable | `test_semicolon_separator_error_mentions_separator` |
| D12 | Basse | « Unspecified » classé comme un pays (24e, £10 927) | mesuré (`unspecified_country_lines` = 756) et signalé dans le dashboard | `test_unspecified_country_is_counted_in_quality_report` |

Défauts trouvés à la relecture pendant les corrections :
- **D17 (Basse)** : doublons détectés via une empreinte de 64 bits, donc un risque théorique de faux doublon par collision. La comparaison porte désormais sur les valeurs. Sur données réelles, le résultat est identique : 34 335 doublons.
- **D18 (Basse)** : avec une installation non éditable, les fichiers `sql/` sont introuvables et l'erreur était obscure. Le message indique maintenant `pip install -e .`.
- **D20 (Moyenne)** : dashboard, une coupure de la base *pendant* la session affichait une exception Streamlit.
  Elle donne maintenant un message dédié (`test_dashboard_db_lost_during_session_shows_error` : échoue sur
  l'ancien code, passe sur le nouveau).
- **D19 (Moyenne)** : `report` plantait pour un dataset sans client ni vente (division par zéro, `float(None)`). Couvert par `test_cancellation_only_dataset_*`.

## Vérifié sans défaut

| Point | Constat |
|---|---|
| Précision des montants | `SUM(arrondi par ligne)` − `SUM(quantité × prix)` = **0,00 £** sur 1 003 340 ventes réelles |
| Rechargement du même fichier | 0 nouvelle ligne brute, KPI identiques (tests existants + run réel n° 6) |
| Valeurs nulles | client ou description manquants conservés et non invalidants ; texte « NA » (Namibie) non converti en manquant |
| Doublons | 1re occurrence gardée, suivantes marquées ; quasi-doublons non fusionnés |
| Clone Windows (`core.autocrlf=true`) | test de reproductibilité de l'échantillon OK (simulé sous Linux) |
| Base injoignable au démarrage du dashboard | message d'erreur, aucune exception (test passé avant correction) |
| Injection SQL | paramètres liés ; seul `ORDER BY` dynamique, filtré par liste blanche (test existant) |

## Commandes exécutées et résultats observés

```bash
REQUIRE_DB=1 pytest -q -W error::DeprecationWarning --cov=retail_analytics
#   avant : 65 passed, 3 skipped | nouveaux tests avant correction : 12 failed, 1 passed + 1 module en erreur
#   après : 91 passed, 3 skipped, couverture 91 %, aucun avertissement de dépréciation
TEST_DATABASE_URL=postgresql+psycopg://u:p@127.0.0.1:1/x_test pytest -q              # 62 passed, 31 skipped
REQUIRE_DB=1 TEST_DATABASE_URL=postgresql+psycopg://u:p@127.0.0.1:1/x_test pytest -q # 62 passed, 3 skipped, 28 errors
RUN_REAL_DATA=1 pytest tests/test_real_data.py                                       # 3 passed
python -m retail_analytics.cli run --source uci     # 1 067 371 lignes, 1 003 340 valides, 34 335 doublons, 0 nouvelle ligne raw
python -m retail_analytics.cli report --output docs/analysis_uci.md                  # chiffres identiques ; 2 libellés modifiés
DATABASE_URL=postgresql+psycopg://u:p@127.0.0.1:1/x python -m retail_analytics.cli run --source sample  # exit 2, message d'une ligne
DB_CONNECT_TIMEOUT=3 DATABASE_URL=postgresql+psycopg://u:p@10.255.255.1:5432/x python -m retail_analytics.cli report  # exit 2 en 4 s
```

Les 3 tests ignorés sont les contrôles sur données réelles (opt-in). Ils ont été exécutés à part et sont passés.

Performance : le nettoyage des 1,07 M lignes prend 16,7 s après corrections, contre 15,4 s avant. L'inférence de
l'ordre des dates s'exécute une seule fois, avec un pré-filtre sur `/`.

## Risques restants (non corrigés ou non vérifiables ici)

1. **Exécution sous Windows** non testée sur une vraie machine : seul un clone `autocrlf` a été simulé.
   Le poste cible étant sous Windows, lancez `REQUIRE_DB=1 pytest` en local.
2. **Docker** : `docker compose config` est valide, mais le conteneur n'a jamais démarré (registres d'images
   bloqués dans l'environnement d'audit).
3. **Fichier officiel UCI `.xlsx`** : chemin testé sur de petits `.xlsx` synthétiques, pas sur le fichier réel de 43 Mo.
4. **Dates ambiguës** : sans aucun jour > 12 dans le fichier, l'ordre US est *supposé* (avec avertissement).
   C'est inévitable sans information externe ; `--date-order` permet de trancher.
5. **Migrations de schéma** : `CREATE TABLE IF NOT EXISTS` ne modifie pas une table existante. Une base
   créée par une version antérieure dont les colonnes diffèrent doit être recréée. Il n'y a pas d'outil de migration.
6. **Verrou de chargement sans délai** : si un chargement se bloque (sans planter), les suivants attendent
   indéfiniment. Mitigation : `pg_terminate_backend` manuel.
7. **Borne « maintenant + 1 jour »** : une ligne datée dans le futur deviendra valide une fois cette date passée.
   Cela ne concerne aucune ligne du dataset réel.
8. **Garde-fou des tests** : il repose sur le suffixe `_test` du nom de la base de test.

# Qualité des données

Les mesures ci-dessous sont produites à chaque exécution dans `data/reports/<dataset>_quality.json`,
dans `meta.load_runs.quality_report` (JSONB) et dans `marts.data_quality`.

## Problèmes connus du dataset Online Retail II et traitement

| Problème | Détection | Traitement | Exclu des KPI ? |
|---|---|---|---|
| `Customer ID` manquant | valeur vide | conservé, `has_customer = false` | non pour le CA ; oui pour les clients distincts |
| `Description` manquante | valeur vide | conservée, libellé produit = le plus fréquent du code, sinon `UNKNOWN` | non |
| Doublons exacts | toutes colonnes métier identiques (`row_hash`) | 1re occurrence gardée, suivantes `is_duplicate = true` | oui (suivantes) |
| Annulations / retours | facture préfixée `C`, quantité négative | `line_type = cancellation` | du CA brut ; déduites dans le CA net |
| Ajustements de créances | facture préfixée `A` | `bad_debt_adjustment` | oui |
| Codes non produits | `POST`, `DOT`, `M`, `C2`, `D`, `S`, `B`, `CRUK`, `PADS`, `BANK CHARGES`, `AMAZONFEE`, `ADJUST*`, `TEST*`, `gift_*` | `non_product` | oui |
| Quantité négative hors annulation | quantité ≤ 0 sans `C` (casse, perte…) | `stock_adjustment` | oui |
| Prix nul ou négatif | prix ≤ 0 | `zero_price` | oui |
| Valeur illisible | quantité/date/prix non convertible, quantité non entière, facture ou code vide | `invalid` + `invalid_reason` | oui |
| Date aberrante | lisible mais avant 2000-01-01 ou après maintenant + 1 jour | `invalid`, raison `date_out_of_range`, date conservée | oui |
| Dates « a/b/AAAA » | ordre jour/mois déduit de toute la colonne ; ambigu → ordre US + avertissement ; mélangé → non interprété (`bad_date`) | `--date-order` pour forcer | si illisible |
| Pays « Unspecified » | valeur de la source = pays inconnu (756 lignes réelles) | conservé, compté dans `unspecified_country_lines`, signalé dans le dashboard | non |
| CSV non UTF-8 | échec de décodage UTF-8 | relu en cp1252 + avertissement dans le rapport | — |
| Libellés multiples par code | `COUNT(DISTINCT description) > 1` | libellé le plus fréquent (`mode()`) | — |
| Casse des codes | `85123a` vs `85123A` | codes et factures mis en majuscules | — |
| `Customer ID` en flottant (`12345.0`) | lecture xlsx | converti en texte entier `12345` | — |
| Espaces parasites | — | `strip` + espaces multiples réduits | — |

La liste des codes non produits a été établie à partir de la documentation et des analyses publiques du
dataset ; elle est centralisée dans `transform.NON_PRODUCT_PATTERN` et testée.

## Garde-fous bloquants

- Colonnes obligatoires absentes ou fichier vide → arrêt (`SchemaValidationError`).
- Fichier vide, encodage inconnu, séparateur autre que la virgule → arrêt avec message explicite (code 3).
- Plus de 5 % de lignes `invalid` → arrêt : c'est le signe d'un format inattendu (séparateur, format de
  date, mauvais fichier), pas d'un problème de qualité. Seuil réglable : `--max-invalid-ratio`.

## Mesures sur le vrai dataset (1 067 371 lignes, run du 2026-10-20)

| Mesure | Valeur |
|---|---|
| Ventes valides | 1 003 340 (94,0 %) |
| Doublons exacts | 34 335 |
| Annulations | 19 494 lignes, 8 292 factures |
| Codes non produits | 4 715 |
| Ajustements de stock | 3 457 |
| Prix nuls | 2 695 |
| Ajustements de créances (`A`) | 6 |
| Lignes illisibles | 0 |
| `Customer ID` manquant | 243 007 lignes (13,1 % du CA valide) |
| `Description` manquante | 4 382 lignes, aucune parmi les ventes valides |
| Codes à plusieurs libellés | 596 |

Point d'attention : deux ventes géantes annulées le jour même (80 995 et 74 215 unités) restent des
ventes valides, compensées par leur annulation dans le CA net. Voir [findings.md](findings.md).

## Mesures sur l'échantillon synthétique (graine 42)

| Mesure | Valeur | Injecté par le générateur |
|---|---|---|
| Lignes totales | 4 051 | — |
| Ventes valides | 3 895 (96,2 %) | — |
| Doublons exacts | 40 | 40 |
| Annulations (lignes) | 30 | 30 |
| Ajustements de stock | 12 | 12 |
| Prix nuls | 8 | 8 |
| Non-produits | 62 (frais de port surtout) | ~8 % des commandes + 2 |
| Ajustement de créance | 1 | 1 |
| Illisibles | 3 (quantité, date, code manquant) | 3 |

Les tests vérifient que chaque anomalie injectée est détectée en quantité exacte.

## Hypothèses

- Les prix sont unitaires et en GBP, TVA non précisée par la source.
- Une facture appartient à un seul pays et un seul horodatage.
- L'annulation d'une ligne est valorisée à son propre prix, sans rapprochement avec la vente d'origine.
- Les ventes sans client identifié sont de vraies ventes (clients invités) : elles restent dans le CA.

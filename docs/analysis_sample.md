# Analyse — échantillon SYNTHÉTIQUE

> ⚠️ Données **inventées** par `sample_data.py` : aucune conclusion métier n'est possible.

_Rapport généré automatiquement le 2026-10-20 14:53 UTC depuis les marts PostgreSQL — run #3, fichier `online_retail_sample.csv`, SHA-256 `d6821ca921ee…`. Régénérer : `python -m retail_analytics.cli report --dataset synthetic_sample`._

## Indicateurs globaux

| Indicateur | Valeur |
|---|---|
| Période des ventes valides | 01/01/2024 → 31/12/2025 |
| CA brut | £191 357 |
| Montant annulé | £1 115 |
| CA net des annulations | £190 241 |
| Commandes (factures avec ≥ 1 vente valide) | 897 |
| Factures d'annulation | 30 |
| Clients identifiés distincts | 290 |
| Unités vendues | 45 582 |
| Panier moyen (CA brut / commande) | £213 |
| Part du CA sans client identifié | 19.7% |
| Marge | non calculable (aucun coût dans les données) |

## Qualité des données

4 051 lignes lues, **aucune supprimée** ; 3 895 ventes valides (96.2%).

| Catégorie | Lignes |
|---|---|
| sale | 3 935 |
| invalid | 3 |
| zero_price | 8 |
| non_product | 62 |
| cancellation | 30 |
| stock_adjustment | 12 |
| bad_debt_adjustment | 1 |
| doublons exacts (toutes catégories, exclus) | 40 |
| client manquant (toutes lignes) | 768 |
| description manquante (toutes lignes) | 2 |
| codes produit à plusieurs libellés | 0 |

## Tendance mensuelle

| Mois | CA brut | Annulé | CA net | Commandes | Clients |
|---|---|---|---|---|---|
| 2024-01 | £7 979 | £1 | £7 977 | 31 | 27 |
| 2024-02 | £3 284 | £338 | £2 947 | 13 | 11 |
| 2024-03 | £3 203 | £30 | £3 173 | 19 | 17 |
| 2024-04 | £6 938 | £73 | £6 865 | 33 | 25 |
| 2024-05 | £6 495 | £60 | £6 434 | 37 | 28 |
| 2024-06 | £6 342 | £3 | £6 339 | 30 | 25 |
| 2024-07 | £7 316 | £0 | £7 316 | 30 | 22 |
| 2024-08 | £6 175 | £0 | £6 175 | 31 | 28 |
| 2024-09 | £9 822 | £0 | £9 822 | 54 | 40 |
| 2024-10 | £8 887 | £46 | £8 842 | 38 | 29 |
| 2024-11 | £9 628 | £307 | £9 321 | 55 | 44 |
| 2024-12 | £10 584 | £25 | £10 560 | 36 | 29 |
| 2025-01 | £4 552 | £4 | £4 549 | 20 | 16 |
| 2025-02 | £5 877 | £0 | £5 877 | 25 | 20 |
| 2025-03 | £7 540 | £0 | £7 540 | 36 | 31 |
| 2025-04 | £5 628 | £138 | £5 491 | 33 | 25 |
| 2025-05 | £6 367 | £15 | £6 353 | 42 | 37 |
| 2025-06 | £8 967 | £19 | £8 948 | 40 | 36 |
| 2025-07 | £6 556 | £0 | £6 556 | 39 | 32 |
| 2025-08 | £6 083 | £10 | £6 073 | 40 | 30 |
| 2025-09 | £10 666 | £29 | £10 636 | 62 | 47 |
| 2025-10 | £16 621 | £15 | £16 606 | 59 | 43 |
| 2025-11 | £15 606 | £4 | £15 603 | 54 | 39 |
| 2025-12 | £10 239 | £0 | £10 239 | 40 | 27 |

Le premier et le dernier mois peuvent être partiels (ventes du 01/01/2024 au 31/12/2025).

**Comparaison à périmètre égal (janvier–novembre)** : 2024 = £76 068, 2025 = £94 464 (+24.2% de CA brut, +21.3% de commandes).

Commandes par jour de semaine : lun 148, mar 142, mer 159, jeu 154, ven 147, dim 147.

## Produits (top 10)

Par CA brut :

| revenue_rank | stock_code | product_name | gross_revenue | cancelled_amount | net_revenue | units_sold |
|---|---|---|---|---|---|---|
| 1 | 70023 | PICNIC BLANKET CHECK | £21 020 | £0 | £21 020 | 1 406 |
| 2 | 70019 | HERB PLANTER TRIO | £17 810 | £10 | £17 801 | 1 790 |
| 3 | 70004 | BAMBOO SERVING TRAY | £16 647 | £251 | £16 396 | 1 860 |
| 4 | 70014 | WALL CLOCK RETRO | £16 488 | £138 | £16 350 | 1 319 |
| 5 | 70018 | DOORMAT WELCOME HOME | £11 464 | £24 | £11 440 | 1 442 |
| 6 | 70003 | LINEN TABLE NAPKIN SET | £9 581 | £46 | £9 536 | 1 474 |
| 7 | 70017 | STRING LIGHTS WARM | £7 985 | £0 | £7 985 | 1 342 |
| 8 | 70009 | WOODEN PHOTO FRAME | £7 195 | £4 | £7 191 | 1 693 |
| 9 | 70024 | WATER BOTTLE STEEL | £6 851 | £20 | £6 831 | 1 384 |
| 10 | 70027 | BIRD FEEDER HANGING | £6 687 | £0 | £6 687 | 1 693 |

Par CA net des annulations :

| net_revenue_rank | stock_code | product_name | net_revenue | units_sold | orders |
|---|---|---|---|---|---|
| 1 | 70023 | PICNIC BLANKET CHECK | £21 020 | 1 406 | 144 |
| 2 | 70019 | HERB PLANTER TRIO | £17 801 | 1 790 | 130 |
| 3 | 70004 | BAMBOO SERVING TRAY | £16 396 | 1 860 | 136 |
| 4 | 70014 | WALL CLOCK RETRO | £16 350 | 1 319 | 138 |
| 5 | 70018 | DOORMAT WELCOME HOME | £11 440 | 1 442 | 132 |
| 6 | 70003 | LINEN TABLE NAPKIN SET | £9 536 | 1 474 | 133 |
| 7 | 70017 | STRING LIGHTS WARM | £7 985 | 1 342 | 123 |
| 8 | 70009 | WOODEN PHOTO FRAME | £7 191 | 1 693 | 133 |
| 9 | 70024 | WATER BOTTLE STEEL | £6 831 | 1 384 | 135 |
| 10 | 70027 | BIRD FEEDER HANGING | £6 687 | 1 693 | 115 |

Concentration : les 20 % de produits les plus vendus (sur 30) réalisent 48.6% du CA brut.

Plus grosses annulations :

| invoice_day | invoice | stock_code | product_name | units | cancelled_amount |
|---|---|---|---|---|---|
| 2024-11-07 | C703966 | 70022 | ADVENT CALENDAR FELT | 24 | £287 |
| 2024-02-29 | C703969 | 70004 | BAMBOO SERVING TRAY | 28 | £251 |
| 2025-04-03 | C703968 | 70014 | WALL CLOCK RETRO | 11 | £138 |
| 2024-02-24 | C703982 | 70011 | SCENTED CANDLE VANILLA | 23 | £86 |
| 2024-10-16 | C703965 | 70003 | LINEN TABLE NAPKIN SET | 7 | £46 |

## Géographie (top 10 sur 8 pays)

| revenue_rank | country | gross_revenue | revenue_share | orders | customers |
|---|---|---|---|---|---|
| 1 | United Kingdom | £145 274 | 75.9% | 686 | 221 |
| 2 | Germany | £13 252 | 6.9% | 56 | 21 |
| 3 | EIRE | £7 753 | 4.0% | 38 | 12 |
| 4 | France | £7 712 | 4.0% | 38 | 11 |
| 5 | Netherlands | £7 504 | 3.9% | 35 | 11 |
| 6 | Portugal | £3 805 | 2.0% | 14 | 5 |
| 7 | Belgium | £3 722 | 1.9% | 19 | 4 |
| 8 | Spain | £2 334 | 1.2% | 11 | 5 |

## Clients

290 clients identifiés, dont 212 (73.1%) ont passé au moins deux commandes ; 2.53 commandes par client en moyenne. Les ventes sans client identifié (19.7% du CA) sont exclues de ces calculs.

## Jours atypiques (Tukey, 3×IQR)

| invoice_day | gross_revenue | orders | upper_bound | direction |
|---|---|---|---|---|
| 2025-10-08 | £2 224 | 6 | £1 784 | high |
| 2025-10-21 | £1 934 | 4 | £1 784 | high |
| 2024-06-10 | £1 851 | 3 | £1 784 | high |
| 2025-11-28 | £1 847 | 8 | £1 784 | high |
| 2025-12-26 | £1 819 | 5 | £1 784 | high |
| 2024-10-02 | £1 796 | 4 | £1 784 | high |

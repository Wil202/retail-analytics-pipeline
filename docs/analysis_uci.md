# Analyse — Online Retail II (données réelles)

> Source : Online Retail II, UCI Machine Learning Repository, DOI 10.24432/C5CG6D, CC BY 4.0.

_Rapport généré automatiquement le 2026-10-20 14:53 UTC depuis les marts PostgreSQL — run #6, fichier `onlineretail2.rda`, SHA-256 `be2480b1fcb1…`. Régénérer : `python -m retail_analytics.cli report --dataset uci_online_retail_ii`._

## Indicateurs globaux

| Indicateur | Valeur |
|---|---|
| Période des ventes valides | 01/12/2009 → 09/12/2011 |
| CA brut | £19 643 862 |
| Montant annulé | £716 426 |
| CA net des annulations | £18 927 436 |
| Commandes (factures avec ≥ 1 vente valide) | 39 516 |
| Factures d'annulation | 7 405 |
| Clients identifiés distincts | 5 852 |
| Unités vendues | 11 188 044 |
| Panier moyen (CA brut / commande) | £497 |
| Part du CA sans client identifié | 13.1% |
| Marge | non calculable (aucun coût dans les données) |

## Qualité des données

1 067 371 lignes lues, **aucune supprimée** ; 1 003 340 ventes valides (94.0%).

| Catégorie | Lignes |
|---|---|
| sale | 1 037 004 |
| invalid | 0 |
| zero_price | 2 695 |
| non_product | 4 715 |
| cancellation | 19 494 |
| stock_adjustment | 3 457 |
| bad_debt_adjustment | 6 |
| doublons exacts (toutes catégories, exclus) | 34 335 |
| client manquant (toutes lignes) | 243 007 |
| description manquante (toutes lignes) | 4 382 |
| codes produit à plusieurs libellés | 596 |

## Tendance mensuelle

| Mois | CA brut | Annulé | CA net | Commandes | Clients |
|---|---|---|---|---|---|
| 2009-12 | £797 901 | £19 558 | £778 343 | 1 666 | 951 |
| 2010-01 | £612 297 | £7 466 | £604 832 | 1 049 | 701 |
| 2010-02 | £537 910 | £12 575 | £525 334 | 1 189 | 771 |
| 2010-03 | £761 706 | £9 604 | £752 102 | 1 647 | 1 051 |
| 2010-04 | £646 341 | £10 025 | £636 316 | 1 435 | 939 |
| 2010-05 | £643 492 | £37 193 | £606 299 | 1 484 | 965 |
| 2010-06 | £696 583 | £26 337 | £670 246 | 1 612 | 1 034 |
| 2010-07 | £632 994 | £17 133 | £615 862 | 1 507 | 924 |
| 2010-08 | £674 038 | £12 398 | £661 640 | 1 402 | 910 |
| 2010-09 | £869 243 | £27 686 | £841 557 | 1 789 | 1 136 |
| 2010-10 | £1 094 436 | £25 451 | £1 068 985 | 2 244 | 1 492 |
| 2010-11 | £1 429 701 | £35 099 | £1 394 602 | 2 719 | 1 606 |
| 2010-12 | £775 638 | £17 548 | £758 090 | 1 550 | 884 |
| 2011-01 | £670 380 | £91 525 | £578 855 | 1 081 | 739 |
| 2011-02 | £507 800 | £8 336 | £499 464 | 1 093 | 757 |
| 2011-03 | £689 834 | £10 504 | £679 329 | 1 440 | 973 |
| 2011-04 | £515 378 | £33 316 | £482 062 | 1 235 | 853 |
| 2011-05 | £739 953 | £8 948 | £731 005 | 1 668 | 1 054 |
| 2011-06 | £737 559 | £13 714 | £723 845 | 1 525 | 990 |
| 2011-07 | £688 219 | £11 407 | £676 812 | 1 452 | 946 |
| 2011-08 | £724 216 | £22 927 | £701 290 | 1 339 | 933 |
| 2011-09 | £1 028 320 | £16 981 | £1 011 340 | 1 818 | 1 259 |
| 2011-10 | £1 103 314 | £41 613 | £1 061 701 | 2 005 | 1 361 |
| 2011-11 | £1 452 116 | £24 991 | £1 427 125 | 2 751 | 1 660 |
| 2011-12 | £614 491 | £174 091 | £440 400 | 816 | 614 |

Le premier et le dernier mois peuvent être partiels (ventes du 01/12/2009 au 09/12/2011).

**Comparaison à périmètre égal (janvier–novembre)** : 2010 = £8 598 741, 2011 = £8 857 090 (+3.0% de CA brut, -3.7% de commandes).

Commandes par jour de semaine : lun 6 245, mar 7 147, mer 7 115, jeu 8 167, ven 5 988, sam 30, dim 4 824.

## Produits (top 10)

Par CA brut :

| revenue_rank | stock_code | product_name | gross_revenue | cancelled_amount | net_revenue | units_sold |
|---|---|---|---|---|---|---|
| 1 | 22423 | REGENCY CAKESTAND 3 TIER | £330 590 | £16 545 | £314 045 | 26 478 |
| 2 | 85123A | WHITE HANGING HEART T-LIGHT HOLDER | £261 169 | £9 387 | £251 782 | 94 719 |
| 3 | 85099B | JUMBO BAG RED RETROSPOT | £182 681 | £2 169 | £180 512 | 97 176 |
| 4 | 23843 | PAPER CRAFT , LITTLE BIRDIE | £168 470 | £168 470 | £0 | 80 995 |
| 5 | 47566 | PARTY BUNTING | £148 318 | £1 239 | £147 080 | 28 200 |
| 6 | 84879 | ASSORTED COLOUR BIRD ORNAMENT | £129 324 | £774 | £128 550 | 80 082 |
| 7 | 22086 | PAPER CHAIN KIT 50'S CHRISTMAS | £117 760 | £1 462 | £116 299 | 35 084 |
| 8 | 23166 | MEDIUM CERAMIC TOP STORAGE JAR | £81 701 | £77 480 | £4 221 | 78 033 |
| 9 | 79321 | CHILLI LIGHTS | £80 541 | £636 | £79 905 | 15 841 |
| 10 | 22197 | SMALL POPCORN HOLDER | £79 520 | £617 | £78 904 | 88 499 |

Par CA net des annulations :

| net_revenue_rank | stock_code | product_name | net_revenue | units_sold | orders |
|---|---|---|---|---|---|
| 1 | 22423 | REGENCY CAKESTAND 3 TIER | £314 045 | 26 478 | 3 918 |
| 2 | 85123A | WHITE HANGING HEART T-LIGHT HOLDER | £251 782 | 94 719 | 5 464 |
| 3 | 85099B | JUMBO BAG RED RETROSPOT | £180 512 | 97 176 | 4 013 |
| 4 | 47566 | PARTY BUNTING | £147 080 | 28 200 | 2 674 |
| 5 | 84879 | ASSORTED COLOUR BIRD ORNAMENT | £128 550 | 80 082 | 2 807 |
| 6 | 22086 | PAPER CHAIN KIT 50'S CHRISTMAS | £116 299 | 35 084 | 2 018 |
| 7 | 79321 | CHILLI LIGHTS | £79 905 | 15 841 | 1 135 |
| 8 | 22197 | SMALL POPCORN HOLDER | £78 904 | 88 499 | 2 322 |
| 9 | 22386 | JUMBO BAG PINK POLKADOT | £75 458 | 39 437 | 2 245 |
| 10 | 84347 | ROTATING SILVER ANGELS T-LIGHT HLDR | £70 970 | 31 409 | 756 |

Concentration : les 20 % de produits les plus vendus (sur 4 724) réalisent 78.1% du CA brut.

Plus grosses annulations :

| invoice_day | invoice | stock_code | product_name | units | cancelled_amount |
|---|---|---|---|---|---|
| 2011-12-09 | C581484 | 23843 | PAPER CRAFT , LITTLE BIRDIE | 80 995 | £168 470 |
| 2011-01-18 | C541433 | 23166 | MEDIUM CERAMIC TOP STORAGE JAR | 74 215 | £77 184 |
| 2011-04-18 | C550456 | 21108 | FAIRY CAKE FLANNEL ASSORTED COLOUR | 3 114 | £6 539 |
| 2011-04-18 | C550456 | 85123A | WHITE HANGING HEART T-LIGHT HOLDER | 1 930 | £4 922 |
| 2011-04-18 | C550456 | 48185 | DOORMAT FAIRY CAKE | 670 | £4 522 |

## Géographie (top 10 sur 43 pays)

| revenue_rank | country | gross_revenue | revenue_share | orders | customers |
|---|---|---|---|---|---|
| 1 | United Kingdom | £16 801 019 | 85.5% | 36 184 | 5 334 |
| 2 | EIRE | £623 414 | 3.2% | 581 | 3 |
| 3 | Netherlands | £549 773 | 2.8% | 216 | 22 |
| 4 | Germany | £383 289 | 1.9% | 753 | 107 |
| 5 | France | £311 090 | 1.6% | 598 | 93 |
| 6 | Australia | £167 800 | 0.9% | 89 | 15 |
| 7 | Spain | £97 767 | 0.5% | 144 | 38 |
| 8 | Switzerland | £94 025 | 0.5% | 85 | 22 |
| 9 | Sweden | £86 319 | 0.4% | 99 | 19 |
| 10 | Denmark | £67 423 | 0.3% | 42 | 12 |

## Clients

5 852 clients identifiés, dont 4 234 (72.4%) ont passé au moins deux commandes ; 6.25 commandes par client en moyenne. Les ventes sans client identifié (13.1% du CA) sont exclues de ces calculs.

## Jours atypiques (Tukey, 3×IQR)

| invoice_day | gross_revenue | orders | upper_bound | direction |
|---|---|---|---|---|
| 2011-12-09 | £198 095 | 44 | £96 054 | high |
| 2011-11-14 | £111 349 | 106 | £96 054 | high |
| 2011-09-20 | £108 364 | 70 | £96 054 | high |
| 2010-11-15 | £103 336 | 102 | £96 054 | high |
| 2010-09-27 | £102 425 | 85 | £96 054 | high |

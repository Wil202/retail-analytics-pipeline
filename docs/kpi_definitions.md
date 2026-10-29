# Définitions des KPI

Toutes les définitions s'appliquent à la **version active** du dataset. Implémentation SQL dans
`sql/02_marts.sql` et `src/retail_analytics/kpis.py`, référence Pandas dans `kpis.compute_kpis`.

| KPI | Définition | Remarque |
|---|---|---|
| Vente valide | `line_type = 'sale' AND NOT is_duplicate` | quantité > 0, prix > 0, vrai produit (contrainte SQL) |
| CA brut | `SUM(quantity × unit_price)` des ventes valides | GBP, TVA non précisée |
| Montant annulé | `−SUM(line_amount)` des lignes `cancellation` sur codes produits, non dupliquées | positif |
| CA net | CA brut − montant annulé | approximation : les annulations ne sont pas rattachées à leur vente |
| Commandes | factures distinctes avec ≥ 1 vente valide | |
| Clients | `customer_id` distincts non nuls avec ≥ 1 vente valide | non additif entre périodes / pays |
| Panier moyen | CA brut / commandes | vide si 0 commande |
| Unités | `SUM(quantity)` des ventes valides | |
| Part du CA sans client | CA des ventes sans `customer_id` / CA brut | mesure la couverture client |
| CA net produit | CA brut du produit − annulations du produit (même période / pays) | classement `net_revenue` ; un produit annulé sans vente sur la période apparaît avec un CA brut nul |
| Taux d'annulation (produit) | unités annulées / unités vendues | par `stock_code` ; peut dépasser 1 ou valoir 1 (vente géante annulée) |
| Jour atypique | CA du jour hors de [Q1 − 3·IQR ; Q3 + 3·IQR] | règle de Tukey sur les jours ayant des ventes |
| Marge | **non calculée** | aucun coût dans les données |

## Vérification croisée

Les tests d'intégration exigent l'égalité entre :
1. les valeurs calculées à la main sur un mini-jeu de 10 lignes (`tests/test_kpis.py`) ;
2. la référence Pandas ;
3. la requête SQL filtrable utilisée par le dashboard, avec et sans filtres ;
4. le mart pré-calculé `marts.kpi_summary` ;
5. la somme du CA de chaque mart (`monthly_sales`, `country_sales`, `product_performance`, `daily_country_sales`)
   et la somme des annulations de `monthly_sales` et `product_performance` ;
6. le rapport généré (`report.py`), testé contre les mêmes KPI.

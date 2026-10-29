-- Couche analytique. Entièrement dérivée de staging.current_sales_lines : elle est reconstruite à chaque
-- exécution (DROP + CREATE dans une seule transaction), sans toucher aux données raw/staging.
--
-- Définitions (voir docs/kpi_definitions.md) :
--   vente valide       = line_type = 'sale' ET NOT is_duplicate (quantité > 0, prix > 0, vrai produit)
--   CA brut            = SUM(quantity * unit_price) des ventes valides, en GBP
--   montant annulé     = -SUM(line_amount) des lignes d'annulation (factures 'C') produit, non dupliquées
--   CA net             = CA brut - montant annulé
--   commandes          = factures distinctes ayant au moins une vente valide
--   clients            = customer_id distincts (non nuls) ayant au moins une vente valide
-- Pas de marge : le dataset ne contient aucun coût.

DROP MATERIALIZED VIEW IF EXISTS
    marts.daily_anomalies, marts.data_quality, marts.country_sales, marts.product_performance,
    marts.daily_country_sales, marts.monthly_sales, marts.kpi_summary, marts.dim_product;
DROP VIEW IF EXISTS marts.fct_sales, marts.fct_cancellations;

-- Faits ligne à ligne (vues simples : toujours alignées sur staging, utilisées par les filtres du dashboard).
CREATE VIEW marts.fct_sales AS
SELECT dataset,
       invoice,
       invoice_date,
       invoice_date::date                        AS invoice_day,
       date_trunc('month', invoice_date)::date   AS invoice_month,
       stock_code,
       description,
       quantity,
       unit_price,
       line_amount,
       customer_id,
       country
FROM staging.current_sales_lines
WHERE is_valid_sale;

CREATE VIEW marts.fct_cancellations AS
SELECT dataset, invoice, invoice_date, invoice_date::date AS invoice_day,
       date_trunc('month', invoice_date)::date AS invoice_month,
       stock_code, quantity, unit_price, -line_amount AS cancelled_amount, customer_id, country
FROM staging.current_sales_lines
WHERE line_type = 'cancellation' AND is_product_code AND NOT is_duplicate;

-- Libellé produit : la description la plus fréquente par code (un code peut avoir plusieurs libellés).
CREATE MATERIALIZED VIEW marts.dim_product AS
SELECT dataset,
       stock_code,
       mode() WITHIN GROUP (ORDER BY description) AS product_name,
       COUNT(DISTINCT description)                AS description_variants
FROM staging.current_sales_lines
WHERE is_product_code AND description IS NOT NULL AND NOT is_duplicate
GROUP BY dataset, stock_code;

CREATE MATERIALIZED VIEW marts.kpi_summary AS
WITH s AS (
    SELECT dataset,
           SUM(line_amount)                                    AS gross_revenue,
           COUNT(DISTINCT invoice)                             AS orders,
           COUNT(DISTINCT customer_id)                         AS customers,
           SUM(quantity)                                       AS units,
           COUNT(*)                                            AS sale_lines,
           SUM(line_amount) FILTER (WHERE customer_id IS NULL) AS revenue_without_customer,
           MIN(invoice_date)                                   AS first_sale_at,
           MAX(invoice_date)                                   AS last_sale_at
    FROM marts.fct_sales GROUP BY dataset
), c AS (
    SELECT dataset, SUM(cancelled_amount) AS cancelled_amount, COUNT(DISTINCT invoice) AS cancelled_invoices
    FROM marts.fct_cancellations GROUP BY dataset
)
-- Une ligne par dataset ACTIF, même sans vente valide (ex. fichier composé uniquement d'annulations) :
-- le résumé ne doit jamais « disparaître » alors que des annulations existent.
SELECT d.dataset,
       COALESCE(s.gross_revenue, 0)                                AS gross_revenue,
       COALESCE(c.cancelled_amount, 0)                             AS cancelled_amount,
       COALESCE(s.gross_revenue, 0) - COALESCE(c.cancelled_amount, 0) AS net_revenue,
       COALESCE(s.orders, 0)                                       AS orders,
       COALESCE(s.customers, 0)                                    AS customers,
       COALESCE(s.units, 0)                                        AS units,
       COALESCE(s.sale_lines, 0)                                   AS sale_lines,
       ROUND(s.gross_revenue / NULLIF(s.orders, 0), 2)             AS avg_order_value,
       ROUND(COALESCE(s.revenue_without_customer, 0) / NULLIF(s.gross_revenue, 0), 4) AS revenue_share_without_customer,
       COALESCE(c.cancelled_invoices, 0)                           AS cancelled_invoices,
       s.first_sale_at,
       s.last_sale_at
FROM meta.dataset_current d
LEFT JOIN s USING (dataset)
LEFT JOIN c USING (dataset);

CREATE MATERIALIZED VIEW marts.monthly_sales AS
WITH s AS (
    SELECT dataset, invoice_month,
           SUM(line_amount) AS gross_revenue, COUNT(DISTINCT invoice) AS orders,
           COUNT(DISTINCT customer_id) AS customers, SUM(quantity) AS units
    FROM marts.fct_sales GROUP BY dataset, invoice_month
), c AS (
    SELECT dataset, invoice_month, SUM(cancelled_amount) AS cancelled_amount
    FROM marts.fct_cancellations GROUP BY dataset, invoice_month
)
-- FULL JOIN : un mois avec des annulations mais aucune vente valide reste visible.
SELECT dataset, invoice_month,
       COALESCE(s.gross_revenue, 0) AS gross_revenue, COALESCE(s.orders, 0) AS orders,
       COALESCE(s.customers, 0) AS customers, COALESCE(s.units, 0) AS units,
       COALESCE(c.cancelled_amount, 0) AS cancelled_amount,
       COALESCE(s.gross_revenue, 0) - COALESCE(c.cancelled_amount, 0) AS net_revenue,
       ROUND(s.gross_revenue / NULLIF(s.orders, 0), 2) AS avg_order_value
FROM s FULL JOIN c USING (dataset, invoice_month);

-- Grain jour x pays : CA, unités, commandes et lignes sont additifs à ce grain (une facture = un jour, un pays).
-- Les clients distincts NE le sont PAS : ils sont recalculés depuis fct_sales quand on filtre.
CREATE MATERIALIZED VIEW marts.daily_country_sales AS
SELECT dataset, invoice_day, country,
       SUM(line_amount) AS gross_revenue, COUNT(DISTINCT invoice) AS orders,
       SUM(quantity) AS units, COUNT(*) AS sale_lines
FROM marts.fct_sales GROUP BY dataset, invoice_day, country;

CREATE MATERIALIZED VIEW marts.product_performance AS
WITH s AS (
    SELECT dataset, stock_code, SUM(line_amount) AS gross_revenue, SUM(quantity) AS units_sold,
           COUNT(DISTINCT invoice) AS orders, COUNT(DISTINCT customer_id) AS customers
    FROM marts.fct_sales GROUP BY dataset, stock_code
), c AS (
    SELECT dataset, stock_code, SUM(-quantity) AS units_cancelled, SUM(cancelled_amount) AS cancelled_amount
    FROM marts.fct_cancellations GROUP BY dataset, stock_code
)
-- FULL JOIN : un produit annulé mais jamais vendu sur la période (vente antérieure au 01/12/2009) reste
-- visible avec un CA brut nul ; sinon ses annulations disparaîtraient des classements.
, sc AS (
    SELECT dataset, stock_code,
           COALESCE(s.gross_revenue, 0) AS gross_revenue, COALESCE(s.units_sold, 0) AS units_sold,
           COALESCE(s.orders, 0) AS orders, COALESCE(s.customers, 0) AS customers,
           COALESCE(c.units_cancelled, 0) AS units_cancelled, COALESCE(c.cancelled_amount, 0) AS cancelled_amount
    FROM s FULL JOIN c USING (dataset, stock_code)
)
SELECT sc.dataset, sc.stock_code, COALESCE(p.product_name, 'UNKNOWN') AS product_name,
       sc.gross_revenue, sc.units_sold, sc.orders, sc.customers, sc.units_cancelled, sc.cancelled_amount,
       sc.gross_revenue - sc.cancelled_amount AS net_revenue,
       ROUND(sc.units_cancelled::numeric / NULLIF(sc.units_sold, 0), 4) AS cancellation_rate_units,
       RANK() OVER (PARTITION BY sc.dataset ORDER BY sc.gross_revenue DESC) AS revenue_rank,
       RANK() OVER (PARTITION BY sc.dataset ORDER BY sc.gross_revenue - sc.cancelled_amount DESC) AS net_revenue_rank
FROM sc
LEFT JOIN marts.dim_product p USING (dataset, stock_code);

CREATE MATERIALIZED VIEW marts.country_sales AS
SELECT dataset, country,
       SUM(line_amount) AS gross_revenue, COUNT(DISTINCT invoice) AS orders,
       COUNT(DISTINCT customer_id) AS customers, SUM(quantity) AS units,
       ROUND(SUM(line_amount) / SUM(SUM(line_amount)) OVER (PARTITION BY dataset), 4) AS revenue_share,
       RANK() OVER (PARTITION BY dataset ORDER BY SUM(line_amount) DESC) AS revenue_rank
FROM marts.fct_sales GROUP BY dataset, country;

-- Qualité : répartition de TOUTES les lignes (valides ou non) de la version active.
CREATE MATERIALIZED VIEW marts.data_quality AS
SELECT dataset, line_type, is_duplicate, COALESCE(invalid_reason, '') AS invalid_reason,
       COUNT(*) AS lines, COALESCE(SUM(line_amount), 0) AS amount,
       COUNT(*) FILTER (WHERE NOT has_customer) AS lines_without_customer
FROM staging.current_sales_lines
GROUP BY dataset, line_type, is_duplicate, COALESCE(invalid_reason, '');

-- Anomalies : jours dont le CA sort de [Q1 - 3*IQR ; Q3 + 3*IQR] (règle de Tukey, valeurs « extrêmes »).
CREATE MATERIALIZED VIEW marts.daily_anomalies AS
WITH d AS (
    SELECT dataset, invoice_day, SUM(line_amount) AS gross_revenue, COUNT(DISTINCT invoice) AS orders
    FROM marts.fct_sales GROUP BY dataset, invoice_day
), q AS (
    SELECT dataset,
           percentile_cont(0.25) WITHIN GROUP (ORDER BY gross_revenue) AS q1,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY gross_revenue) AS q3
    FROM d GROUP BY dataset
)
SELECT d.dataset, d.invoice_day, d.gross_revenue, d.orders,
       ROUND((q.q1 - 3 * (q.q3 - q.q1))::numeric, 2) AS lower_bound,
       ROUND((q.q3 + 3 * (q.q3 - q.q1))::numeric, 2) AS upper_bound,
       CASE WHEN d.gross_revenue > q.q3 + 3 * (q.q3 - q.q1) THEN 'high' ELSE 'low' END AS direction
FROM d JOIN q USING (dataset)
WHERE d.gross_revenue > q.q3 + 3 * (q.q3 - q.q1)
   OR d.gross_revenue < q.q1 - 3 * (q.q3 - q.q1);

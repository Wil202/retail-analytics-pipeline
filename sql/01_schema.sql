-- Schéma persistant du pipeline. Idempotent : peut être rejoué sans perte de données.
--   raw      : copie fidèle de la source (texte), jamais modifiée après insertion
--   staging  : lignes typées + indicateurs de qualité (1 ligne raw = 1 ligne staging)
--   marts    : tables analytiques dérivées (reconstruites par 02_marts.sql)
--   meta     : traçabilité des exécutions et version active de chaque dataset

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS meta;

-- Version du schéma persistant (une seule ligne). Vérifiée par db.init_schema avant toute écriture.
-- Une base antérieure au versionnage a exactement le schéma v1 : la ligne y est simplement ajoutée.
CREATE TABLE IF NOT EXISTS meta.schema_info (
    singleton   BOOLEAN     PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    version     INTEGER     NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO meta.schema_info (version) VALUES (1) ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE IF NOT EXISTS meta.load_runs (
    run_id            BIGSERIAL PRIMARY KEY,
    dataset           TEXT        NOT NULL,
    source_file       TEXT        NOT NULL,
    file_sha256       CHAR(64)    NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    status            TEXT        NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    rows_extracted    INTEGER,
    rows_new_raw      INTEGER,
    rows_staging      INTEGER,
    quality_report    JSONB,
    error_message     TEXT,
    pipeline_version  TEXT
);

-- Fichier actif par dataset : les marts ne lisent QUE cette version, ce qui évite de compter deux fois
-- les ventes si une nouvelle version du fichier source est chargée.
CREATE TABLE IF NOT EXISTS meta.dataset_current (
    dataset      TEXT PRIMARY KEY,
    file_sha256  CHAR(64)    NOT NULL,
    run_id       BIGINT      NOT NULL REFERENCES meta.load_runs (run_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.sales_lines (
    dataset       TEXT     NOT NULL,
    file_sha256   CHAR(64) NOT NULL,
    source_file   TEXT     NOT NULL,
    source_sheet  TEXT     NOT NULL,
    source_row    INTEGER  NOT NULL,
    invoice       TEXT,
    stock_code    TEXT,
    description   TEXT,
    quantity      TEXT,
    invoice_date  TEXT,
    unit_price    TEXT,
    customer_id   TEXT,
    country       TEXT,
    run_id        BIGINT   NOT NULL REFERENCES meta.load_runs (run_id),
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Clé naturelle de provenance : recharger le même fichier n'insère aucune ligne.
    PRIMARY KEY (dataset, file_sha256, source_sheet, source_row)
);

CREATE TABLE IF NOT EXISTS staging.sales_lines (
    dataset          TEXT     NOT NULL,
    file_sha256      CHAR(64) NOT NULL,
    source_sheet     TEXT     NOT NULL,
    source_row       INTEGER  NOT NULL,
    invoice          TEXT,
    stock_code       TEXT,
    description      TEXT,
    quantity         INTEGER,
    invoice_date     TIMESTAMP,
    unit_price       NUMERIC(12, 4),
    customer_id      TEXT,
    country          TEXT,
    line_amount      NUMERIC(14, 2),
    line_type        TEXT     NOT NULL,
    invalid_reason   TEXT,
    is_product_code  BOOLEAN  NOT NULL,
    has_customer     BOOLEAN  NOT NULL,
    has_description  BOOLEAN  NOT NULL,
    row_hash         TEXT     NOT NULL,
    is_duplicate     BOOLEAN  NOT NULL,
    is_valid_sale    BOOLEAN  NOT NULL,
    run_id           BIGINT   NOT NULL REFERENCES meta.load_runs (run_id),
    PRIMARY KEY (dataset, file_sha256, source_sheet, source_row),
    FOREIGN KEY (dataset, file_sha256, source_sheet, source_row)
        REFERENCES raw.sales_lines (dataset, file_sha256, source_sheet, source_row),
    CONSTRAINT chk_line_type CHECK (line_type IN (
        'invalid', 'bad_debt_adjustment', 'cancellation', 'non_product',
        'stock_adjustment', 'zero_price', 'sale')),
    CONSTRAINT chk_valid_sale CHECK (
        NOT is_valid_sale OR (line_type = 'sale' AND NOT is_duplicate AND quantity > 0 AND unit_price > 0))
);

CREATE INDEX IF NOT EXISTS ix_staging_valid_date
    ON staging.sales_lines (dataset, file_sha256, invoice_date) WHERE is_valid_sale;

-- Vue sur la version active de chaque dataset.
CREATE OR REPLACE VIEW staging.current_sales_lines AS
SELECT s.*
FROM staging.sales_lines s
JOIN meta.dataset_current c USING (dataset, file_sha256);

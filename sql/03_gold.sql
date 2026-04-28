-- =====================================================================
-- GOLD LAYER — analytics-ready star schema for Power BI
--
-- Star schema:
--   FactOrderItems   (grain: 1 row per item line on an order)
--   FactPayments     (grain: 1 row per payment installment)
--   FactReviews      (grain: 1 row per review)
--   DimDate          (calendar dim, multi-year)
--   DimCustomer      (SCD Type 1, conformed on customer_unique_id)
--   DimProduct       (SCD Type 1)
--   DimSeller        (SCD Type 1)
--   DimGeography     (state + city rollup)
--
-- Run:
--   duckdb data/warehouse.duckdb < sql/03_gold.sql
-- =====================================================================

PRAGMA threads=8;
SET memory_limit = '4GB';

-- ---------------------------------------------------------------------
-- Silver views
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW sv_orders         AS SELECT * FROM read_parquet('data/silver/orders.parquet');
CREATE OR REPLACE VIEW sv_order_items    AS SELECT * FROM read_parquet('data/silver/order_items.parquet');
CREATE OR REPLACE VIEW sv_order_payments AS SELECT * FROM read_parquet('data/silver/order_payments.parquet');
CREATE OR REPLACE VIEW sv_order_reviews  AS SELECT * FROM read_parquet('data/silver/order_reviews.parquet');
CREATE OR REPLACE VIEW sv_products       AS SELECT * FROM read_parquet('data/silver/products.parquet');
CREATE OR REPLACE VIEW sv_sellers        AS SELECT * FROM read_parquet('data/silver/sellers.parquet');
CREATE OR REPLACE VIEW sv_customers      AS SELECT * FROM read_parquet('data/silver/customers.parquet');
CREATE OR REPLACE VIEW sv_geolocation    AS SELECT * FROM read_parquet('data/silver/geolocation.parquet');

-- =====================================================================
-- DimDate — full calendar covering 2016-09 to 2018-10 (Olist range) + buffer
-- =====================================================================
COPY (
    WITH dates AS (
        SELECT CAST(d AS DATE) AS date
        FROM range(DATE '2016-01-01', DATE '2019-12-31', INTERVAL 1 DAY) t(d)
    )
    SELECT
        CAST(strftime(date, '%Y%m%d') AS INTEGER) AS date_key,        -- yyyymmdd surrogate
        date,
        year(date)                          AS year,
        quarter(date)                       AS quarter,
        month(date)                         AS month,
        strftime(date, '%B')                AS month_name,
        day(date)                           AS day,
        dayofweek(date)                     AS day_of_week,
        strftime(date, '%A')                AS day_name,
        dayofyear(date)                     AS day_of_year,
        weekofyear(date)                    AS week_of_year,
        CASE WHEN dayofweek(date) IN (0,6) THEN TRUE ELSE FALSE END AS is_weekend,
        CONCAT(year(date), '-Q', quarter(date)) AS year_quarter,
        strftime(date, '%Y-%m')             AS year_month
    FROM dates
) TO 'data/gold/DimDate.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- DimCustomer — conformed at customer_unique_id (the real person)
-- Multiple Olist customer_id rows collapse via DENSE_RANK surrogate.
-- =====================================================================
COPY (
    WITH base AS (
        SELECT
            customer_unique_id,
            -- pick the most recent zip/city/state for the unique customer
            FIRST(customer_zip_prefix ORDER BY customer_id DESC) AS customer_zip_prefix,
            FIRST(customer_city       ORDER BY customer_id DESC) AS customer_city,
            FIRST(customer_state      ORDER BY customer_id DESC) AS customer_state,
            COUNT(DISTINCT customer_id) AS n_orders_per_unique
        FROM sv_customers
        GROUP BY customer_unique_id
    )
    SELECT
        DENSE_RANK() OVER (ORDER BY customer_unique_id) AS customer_key,
        customer_unique_id,
        customer_zip_prefix,
        customer_city,
        customer_state,
        n_orders_per_unique,
        CASE WHEN n_orders_per_unique > 1 THEN TRUE ELSE FALSE END AS is_repeat_customer
    FROM base
) TO 'data/gold/DimCustomer.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- bridge: per-order customer_id → customer_key (for fact joins)
COPY (
    SELECT
        c.customer_id,
        d.customer_key
    FROM sv_customers c
    JOIN read_parquet('data/gold/DimCustomer.parquet') d
        ON c.customer_unique_id = d.customer_unique_id
) TO 'data/gold/_bridge_customer.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- DimProduct
-- =====================================================================
COPY (
    SELECT
        DENSE_RANK() OVER (ORDER BY product_id) AS product_key,
        product_id,
        category_pt,
        category_en,
        photos_qty,
        weight_g,
        length_cm,
        height_cm,
        width_cm,
        -- bucket weight for analysis convenience
        CASE
            WHEN weight_g IS NULL THEN 'unknown'
            WHEN weight_g < 500    THEN '0-500g'
            WHEN weight_g < 2000   THEN '500g-2kg'
            WHEN weight_g < 10000  THEN '2-10kg'
            ELSE '10kg+'
        END AS weight_bucket
    FROM sv_products
) TO 'data/gold/DimProduct.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- DimSeller
-- =====================================================================
COPY (
    SELECT
        DENSE_RANK() OVER (ORDER BY seller_id) AS seller_key,
        seller_id,
        seller_zip_prefix,
        seller_city,
        seller_state
    FROM sv_sellers
) TO 'data/gold/DimSeller.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- DimGeography — state-level rollup
-- Brazil has 27 states; we add region grouping (5 macro-regions).
-- =====================================================================
COPY (
    WITH states AS (
        SELECT DISTINCT customer_state AS state FROM sv_customers
        UNION
        SELECT DISTINCT seller_state   AS state FROM sv_sellers
    )
    SELECT
        DENSE_RANK() OVER (ORDER BY state) AS geography_key,
        state,
        CASE state
            WHEN 'AC' THEN 'North'  WHEN 'AM' THEN 'North'  WHEN 'AP' THEN 'North'
            WHEN 'PA' THEN 'North'  WHEN 'RO' THEN 'North'  WHEN 'RR' THEN 'North'
            WHEN 'TO' THEN 'North'
            WHEN 'AL' THEN 'Northeast' WHEN 'BA' THEN 'Northeast' WHEN 'CE' THEN 'Northeast'
            WHEN 'MA' THEN 'Northeast' WHEN 'PB' THEN 'Northeast' WHEN 'PE' THEN 'Northeast'
            WHEN 'PI' THEN 'Northeast' WHEN 'RN' THEN 'Northeast' WHEN 'SE' THEN 'Northeast'
            WHEN 'DF' THEN 'Central-West' WHEN 'GO' THEN 'Central-West'
            WHEN 'MT' THEN 'Central-West' WHEN 'MS' THEN 'Central-West'
            WHEN 'ES' THEN 'Southeast' WHEN 'MG' THEN 'Southeast'
            WHEN 'RJ' THEN 'Southeast' WHEN 'SP' THEN 'Southeast'
            WHEN 'PR' THEN 'South' WHEN 'RS' THEN 'South' WHEN 'SC' THEN 'South'
            ELSE 'Unknown'
        END AS region
    FROM states
    WHERE state IS NOT NULL
) TO 'data/gold/DimGeography.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- FactOrderItems — primary fact, grain = 1 line item
-- =====================================================================
COPY (
    SELECT
        oi.order_id,
        oi.order_item_id,
        CAST(strftime(o.order_purchase_ts, '%Y%m%d') AS INTEGER) AS purchase_date_key,
        CAST(strftime(o.order_delivered_customer_ts, '%Y%m%d') AS INTEGER) AS delivered_date_key,
        CAST(strftime(o.order_estimated_delivery_ts, '%Y%m%d') AS INTEGER) AS estimated_date_key,
        bc.customer_key,
        dp.product_key,
        ds.seller_key,
        o.order_status,
        oi.price,
        oi.freight_value,
        oi.price + oi.freight_value AS total_value,
        DATE_DIFF('day', o.order_purchase_ts, o.order_delivered_customer_ts) AS delivery_days,
        DATE_DIFF('day', o.order_estimated_delivery_ts, o.order_delivered_customer_ts) AS delivery_vs_estimate_days,
        CASE WHEN o.order_delivered_customer_ts <= o.order_estimated_delivery_ts THEN 1 ELSE 0 END AS on_time_flag
    FROM sv_order_items oi
    JOIN sv_orders o
        ON oi.order_id = o.order_id
    LEFT JOIN read_parquet('data/gold/_bridge_customer.parquet') bc
        ON o.customer_id = bc.customer_id
    LEFT JOIN read_parquet('data/gold/DimProduct.parquet') dp
        ON oi.product_id = dp.product_id
    LEFT JOIN read_parquet('data/gold/DimSeller.parquet') ds
        ON oi.seller_id = ds.seller_id
) TO 'data/gold/FactOrderItems.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- FactPayments — grain = 1 payment row
-- =====================================================================
COPY (
    SELECT
        p.order_id,
        p.payment_sequential,
        CAST(strftime(o.order_purchase_ts, '%Y%m%d') AS INTEGER) AS purchase_date_key,
        bc.customer_key,
        p.payment_type,
        p.payment_installments,
        p.payment_value
    FROM sv_order_payments p
    JOIN sv_orders o ON p.order_id = o.order_id
    LEFT JOIN read_parquet('data/gold/_bridge_customer.parquet') bc
        ON o.customer_id = bc.customer_id
) TO 'data/gold/FactPayments.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- FactReviews — grain = 1 review row
-- =====================================================================
COPY (
    SELECT
        r.review_id,
        r.order_id,
        CAST(strftime(o.order_purchase_ts, '%Y%m%d') AS INTEGER) AS purchase_date_key,
        CAST(strftime(r.review_creation_ts, '%Y%m%d') AS INTEGER) AS review_date_key,
        bc.customer_key,
        r.review_score,
        DATE_DIFF('day', r.review_creation_ts, r.review_answer_ts) AS response_days
    FROM sv_order_reviews r
    JOIN sv_orders o ON r.order_id = o.order_id
    LEFT JOIN read_parquet('data/gold/_bridge_customer.parquet') bc
        ON o.customer_id = bc.customer_id
) TO 'data/gold/FactReviews.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- Sanity counts — print to stdout for a quick eyeball
-- =====================================================================
SELECT 'DimDate'         AS table, COUNT(*) AS rows FROM read_parquet('data/gold/DimDate.parquet')
UNION ALL SELECT 'DimCustomer',     COUNT(*) FROM read_parquet('data/gold/DimCustomer.parquet')
UNION ALL SELECT 'DimProduct',      COUNT(*) FROM read_parquet('data/gold/DimProduct.parquet')
UNION ALL SELECT 'DimSeller',       COUNT(*) FROM read_parquet('data/gold/DimSeller.parquet')
UNION ALL SELECT 'DimGeography',    COUNT(*) FROM read_parquet('data/gold/DimGeography.parquet')
UNION ALL SELECT 'FactOrderItems',  COUNT(*) FROM read_parquet('data/gold/FactOrderItems.parquet')
UNION ALL SELECT 'FactPayments',    COUNT(*) FROM read_parquet('data/gold/FactPayments.parquet')
UNION ALL SELECT 'FactReviews',     COUNT(*) FROM read_parquet('data/gold/FactReviews.parquet');

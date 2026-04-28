-- =====================================================================
-- SILVER LAYER — clean, type-cast, deduplicate, conform
--
-- Reads Parquet from data/bronze/, writes Parquet to data/silver/.
-- DuckDB engine (in-process columnar SQL — same mental model as Synapse/Fabric).
--
-- Run:
--   duckdb data/warehouse.duckdb < sql/02_silver.sql
-- =====================================================================

PRAGMA threads=8;
SET memory_limit = '4GB';

-- ---------------------------------------------------------------------
-- Bronze views (lazy reads, no copy)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW br_orders               AS SELECT * FROM read_parquet('data/bronze/orders.parquet');
CREATE OR REPLACE VIEW br_order_items          AS SELECT * FROM read_parquet('data/bronze/order_items.parquet');
CREATE OR REPLACE VIEW br_order_payments       AS SELECT * FROM read_parquet('data/bronze/order_payments.parquet');
CREATE OR REPLACE VIEW br_order_reviews        AS SELECT * FROM read_parquet('data/bronze/order_reviews.parquet');
CREATE OR REPLACE VIEW br_products             AS SELECT * FROM read_parquet('data/bronze/products.parquet');
CREATE OR REPLACE VIEW br_sellers              AS SELECT * FROM read_parquet('data/bronze/sellers.parquet');
CREATE OR REPLACE VIEW br_customers            AS SELECT * FROM read_parquet('data/bronze/customers.parquet');
CREATE OR REPLACE VIEW br_geolocation          AS SELECT * FROM read_parquet('data/bronze/geolocation.parquet');
CREATE OR REPLACE VIEW br_category_translation AS SELECT * FROM read_parquet('data/bronze/category_translation.parquet');

-- ---------------------------------------------------------------------
-- silver.orders — typed timestamps, status normalized, dedup on order_id
-- ---------------------------------------------------------------------
COPY (
    SELECT
        order_id,
        customer_id,
        LOWER(TRIM(order_status))                         AS order_status,
        TRY_CAST(order_purchase_timestamp     AS TIMESTAMP) AS order_purchase_ts,
        TRY_CAST(order_approved_at            AS TIMESTAMP) AS order_approved_ts,
        TRY_CAST(order_delivered_carrier_date AS TIMESTAMP) AS order_delivered_carrier_ts,
        TRY_CAST(order_delivered_customer_date AS TIMESTAMP) AS order_delivered_customer_ts,
        TRY_CAST(order_estimated_delivery_date AS TIMESTAMP) AS order_estimated_delivery_ts
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingested_at DESC) AS rn
        FROM br_orders
    )
    WHERE rn = 1
) TO 'data/silver/orders.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- ---------------------------------------------------------------------
-- silver.order_items — composite key (order_id, order_item_id)
-- ---------------------------------------------------------------------
COPY (
    SELECT
        order_id,
        CAST(order_item_id AS INTEGER) AS order_item_id,
        product_id,
        seller_id,
        TRY_CAST(shipping_limit_date AS TIMESTAMP) AS shipping_limit_ts,
        CAST(price         AS DECIMAL(12,2))       AS price,
        CAST(freight_value AS DECIMAL(12,2))       AS freight_value
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY order_id, order_item_id
                                  ORDER BY _ingested_at DESC) AS rn
        FROM br_order_items
    )
    WHERE rn = 1
) TO 'data/silver/order_items.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- ---------------------------------------------------------------------
-- silver.order_payments — installment grain
-- ---------------------------------------------------------------------
COPY (
    SELECT
        order_id,
        CAST(payment_sequential   AS INTEGER)        AS payment_sequential,
        LOWER(TRIM(payment_type))                    AS payment_type,
        CAST(payment_installments AS INTEGER)        AS payment_installments,
        CAST(payment_value        AS DECIMAL(12,2))  AS payment_value
    FROM br_order_payments
) TO 'data/silver/order_payments.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- ---------------------------------------------------------------------
-- silver.order_reviews
-- ---------------------------------------------------------------------
COPY (
    SELECT
        review_id,
        order_id,
        CAST(review_score AS INTEGER)                AS review_score,
        review_comment_title,
        review_comment_message,
        TRY_CAST(review_creation_date AS TIMESTAMP) AS review_creation_ts,
        TRY_CAST(review_answer_timestamp AS TIMESTAMP) AS review_answer_ts
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY _ingested_at DESC) AS rn
        FROM br_order_reviews
    )
    WHERE rn = 1
) TO 'data/silver/order_reviews.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- ---------------------------------------------------------------------
-- silver.products — join EN translation, sane null handling
-- ---------------------------------------------------------------------
COPY (
    SELECT
        p.product_id,
        p.product_category_name              AS category_pt,
        COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category_en,
        CAST(p.product_name_lenght        AS INTEGER) AS name_length,
        CAST(p.product_description_lenght AS INTEGER) AS description_length,
        CAST(p.product_photos_qty         AS INTEGER) AS photos_qty,
        CAST(p.product_weight_g           AS INTEGER) AS weight_g,
        CAST(p.product_length_cm          AS INTEGER) AS length_cm,
        CAST(p.product_height_cm          AS INTEGER) AS height_cm,
        CAST(p.product_width_cm           AS INTEGER) AS width_cm
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY _ingested_at DESC) AS rn
        FROM br_products
    ) p
    LEFT JOIN br_category_translation t
           ON p.product_category_name = t.product_category_name
    WHERE p.rn = 1
) TO 'data/silver/products.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- ---------------------------------------------------------------------
-- silver.sellers
-- ---------------------------------------------------------------------
COPY (
    SELECT
        seller_id,
        CAST(seller_zip_code_prefix AS INTEGER) AS seller_zip_prefix,
        UPPER(TRIM(seller_city))                 AS seller_city,
        UPPER(TRIM(seller_state))                AS seller_state
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY seller_id ORDER BY _ingested_at DESC) AS rn
        FROM br_sellers
    )
    WHERE rn = 1
) TO 'data/silver/sellers.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- ---------------------------------------------------------------------
-- silver.customers — note Olist quirk: customer_id is per-order;
-- customer_unique_id is the real person across orders.
-- ---------------------------------------------------------------------
COPY (
    SELECT
        customer_id,
        customer_unique_id,
        CAST(customer_zip_code_prefix AS INTEGER) AS customer_zip_prefix,
        UPPER(TRIM(customer_city))                 AS customer_city,
        UPPER(TRIM(customer_state))                AS customer_state
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _ingested_at DESC) AS rn
        FROM br_customers
    )
    WHERE rn = 1
) TO 'data/silver/customers.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- ---------------------------------------------------------------------
-- silver.geolocation — collapse multi-row zip prefixes to centroid
-- ---------------------------------------------------------------------
COPY (
    SELECT
        CAST(geolocation_zip_code_prefix AS INTEGER) AS zip_prefix,
        AVG(geolocation_lat) AS lat,
        AVG(geolocation_lng) AS lng,
        ANY_VALUE(UPPER(TRIM(geolocation_city)))  AS city,
        ANY_VALUE(UPPER(TRIM(geolocation_state))) AS state
    FROM br_geolocation
    GROUP BY zip_prefix
) TO 'data/silver/geolocation.parquet' (FORMAT PARQUET, COMPRESSION SNAPPY);

-- =====================================================================
-- SILVER LAYER (T-SQL) — clean, type-cast, deduplicate, conform
-- Reads bronze.* (loaded by Python from Parquet), writes silver.*
-- =====================================================================
USE olist;
GO

-- ---------------------------------------------------------------------
-- silver.orders — typed timestamps, status normalized, dedup on order_id
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.orders;

INSERT INTO silver.orders (
    order_id, customer_id, order_status,
    order_purchase_ts, order_approved_ts,
    order_delivered_carrier_ts, order_delivered_customer_ts,
    order_estimated_delivery_ts
)
SELECT
    order_id,
    customer_id,
    LOWER(LTRIM(RTRIM(order_status))) AS order_status,
    TRY_CAST(order_purchase_timestamp     AS DATETIME2) AS order_purchase_ts,
    TRY_CAST(order_approved_at            AS DATETIME2) AS order_approved_ts,
    TRY_CAST(order_delivered_carrier_date AS DATETIME2) AS order_delivered_carrier_ts,
    TRY_CAST(order_delivered_customer_date AS DATETIME2) AS order_delivered_customer_ts,
    TRY_CAST(order_estimated_delivery_date AS DATETIME2) AS order_estimated_delivery_ts
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingested_at DESC) AS rn
    FROM bronze.orders
) x
WHERE rn = 1;

-- ---------------------------------------------------------------------
-- silver.order_items — composite key (order_id, order_item_id)
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.order_items;

INSERT INTO silver.order_items (
    order_id, order_item_id, product_id, seller_id,
    shipping_limit_ts, price, freight_value
)
SELECT
    order_id,
    CAST(order_item_id AS INT)            AS order_item_id,
    product_id,
    seller_id,
    TRY_CAST(shipping_limit_date AS DATETIME2) AS shipping_limit_ts,
    CAST(price         AS DECIMAL(12,2))  AS price,
    CAST(freight_value AS DECIMAL(12,2))  AS freight_value
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY order_id, order_item_id
                              ORDER BY _ingested_at DESC) AS rn
    FROM bronze.order_items
) x
WHERE rn = 1;

-- ---------------------------------------------------------------------
-- silver.order_payments — installment grain
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.order_payments;

INSERT INTO silver.order_payments (
    order_id, payment_sequential, payment_type,
    payment_installments, payment_value
)
SELECT
    order_id,
    CAST(payment_sequential   AS INT)        AS payment_sequential,
    LOWER(LTRIM(RTRIM(payment_type)))         AS payment_type,
    CAST(payment_installments AS INT)         AS payment_installments,
    CAST(payment_value        AS DECIMAL(12,2)) AS payment_value
FROM bronze.order_payments;

-- ---------------------------------------------------------------------
-- silver.order_reviews
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.order_reviews;

INSERT INTO silver.order_reviews (
    review_id, order_id, review_score,
    review_comment_title, review_comment_message,
    review_creation_ts, review_answer_ts
)
SELECT
    review_id,
    order_id,
    CAST(review_score AS INT) AS review_score,
    review_comment_title,
    review_comment_message,
    TRY_CAST(review_creation_date     AS DATETIME2) AS review_creation_ts,
    TRY_CAST(review_answer_timestamp  AS DATETIME2) AS review_answer_ts
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY _ingested_at DESC) AS rn
    FROM bronze.order_reviews
) x
WHERE rn = 1;

-- ---------------------------------------------------------------------
-- silver.products — join EN translation
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.products;

INSERT INTO silver.products (
    product_id, category_pt, category_en,
    name_length, description_length, photos_qty,
    weight_g, length_cm, height_cm, width_cm
)
SELECT
    p.product_id,
    p.product_category_name AS category_pt,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category_en,
    CAST(p.product_name_lenght        AS INT) AS name_length,
    CAST(p.product_description_lenght AS INT) AS description_length,
    CAST(p.product_photos_qty         AS INT) AS photos_qty,
    CAST(p.product_weight_g           AS INT) AS weight_g,
    CAST(p.product_length_cm          AS INT) AS length_cm,
    CAST(p.product_height_cm          AS INT) AS height_cm,
    CAST(p.product_width_cm           AS INT) AS width_cm
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY _ingested_at DESC) AS rn
    FROM bronze.products
) p
LEFT JOIN bronze.category_translation t
       ON p.product_category_name = t.product_category_name
WHERE p.rn = 1;

-- ---------------------------------------------------------------------
-- silver.sellers
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.sellers;

INSERT INTO silver.sellers (seller_id, seller_zip_prefix, seller_city, seller_state)
SELECT
    seller_id,
    CAST(seller_zip_code_prefix AS INT) AS seller_zip_prefix,
    UPPER(LTRIM(RTRIM(seller_city)))     AS seller_city,
    UPPER(LTRIM(RTRIM(seller_state)))    AS seller_state
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY seller_id ORDER BY _ingested_at DESC) AS rn
    FROM bronze.sellers
) x
WHERE rn = 1;

-- ---------------------------------------------------------------------
-- silver.customers
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.customers;

INSERT INTO silver.customers (
    customer_id, customer_unique_id, customer_zip_prefix,
    customer_city, customer_state
)
SELECT
    customer_id,
    customer_unique_id,
    CAST(customer_zip_code_prefix AS INT) AS customer_zip_prefix,
    UPPER(LTRIM(RTRIM(customer_city)))     AS customer_city,
    UPPER(LTRIM(RTRIM(customer_state)))    AS customer_state
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _ingested_at DESC) AS rn
    FROM bronze.customers
) x
WHERE rn = 1;

-- ---------------------------------------------------------------------
-- silver.geolocation — collapse multi-row zip prefixes to centroid
-- ---------------------------------------------------------------------
TRUNCATE TABLE silver.geolocation;

INSERT INTO silver.geolocation (zip_prefix, lat, lng, city, state)
SELECT
    CAST(geolocation_zip_code_prefix AS INT) AS zip_prefix,
    AVG(geolocation_lat)                      AS lat,
    AVG(geolocation_lng)                      AS lng,
    MAX(UPPER(LTRIM(RTRIM(geolocation_city))))  AS city,
    MAX(UPPER(LTRIM(RTRIM(geolocation_state)))) AS state
FROM bronze.geolocation
GROUP BY CAST(geolocation_zip_code_prefix AS INT);

PRINT 'Silver layer loaded.';
GO

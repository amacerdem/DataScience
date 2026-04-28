-- =====================================================================
-- GOLD LAYER (T-SQL) — star schema for Power BI
-- Reads silver.*, writes gold.* (DimDate / DimCustomer / DimProduct /
-- DimSeller / DimGeography / FactOrderItems / FactPayments / FactReviews)
-- =====================================================================
USE olist;
GO

SET DATEFIRST 7;  -- Sunday=1, Saturday=7 — consistent day_of_week semantics
GO

-- ---------------------------------------------------------------------
-- gold.DimDate — full calendar 2016-01-01 → 2019-12-31 (recursive CTE)
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.DimDate;

;WITH dates AS (
    SELECT CAST('2016-01-01' AS DATE) AS d
    UNION ALL
    SELECT DATEADD(DAY, 1, d) FROM dates WHERE d < '2019-12-31'
)
INSERT INTO gold.DimDate (
    date_key, [date], [year], [quarter], [month], month_name,
    [day], day_of_week, day_name, day_of_year, week_of_year,
    is_weekend, year_quarter, year_month
)
SELECT
    CAST(CONVERT(varchar(8), d, 112) AS INT)         AS date_key,
    d                                                  AS [date],
    DATEPART(year, d)                                 AS [year],
    DATEPART(quarter, d)                              AS [quarter],
    DATEPART(month, d)                                AS [month],
    DATENAME(month, d)                                AS month_name,
    DATEPART(day, d)                                  AS [day],
    DATEPART(weekday, d)                              AS day_of_week,
    DATENAME(weekday, d)                              AS day_name,
    DATEPART(dayofyear, d)                            AS day_of_year,
    DATEPART(week, d)                                 AS week_of_year,
    CASE WHEN DATEPART(weekday, d) IN (1,7) THEN 1 ELSE 0 END AS is_weekend,
    CONCAT(DATEPART(year, d), '-Q', DATEPART(quarter, d)) AS year_quarter,
    LEFT(CONVERT(varchar(10), d, 23), 7)              AS year_month
FROM dates
OPTION (MAXRECURSION 1500);
GO

-- ---------------------------------------------------------------------
-- gold.DimCustomer — conformed at customer_unique_id
-- Olist quirk: customer_id is per-order pseudonym; customer_unique_id is real person.
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.DimCustomer;

;WITH ord_count AS (
    SELECT customer_unique_id,
           COUNT(DISTINCT customer_id) AS n_orders_per_unique
    FROM silver.customers
    GROUP BY customer_unique_id
), latest AS (
    SELECT customer_unique_id, customer_zip_prefix, customer_city, customer_state,
           ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY customer_id DESC) AS rn
    FROM silver.customers
)
INSERT INTO gold.DimCustomer (
    customer_key, customer_unique_id, customer_zip_prefix,
    customer_city, customer_state, n_orders_per_unique, is_repeat_customer
)
SELECT
    DENSE_RANK() OVER (ORDER BY l.customer_unique_id) AS customer_key,
    l.customer_unique_id,
    l.customer_zip_prefix,
    l.customer_city,
    l.customer_state,
    o.n_orders_per_unique,
    CASE WHEN o.n_orders_per_unique > 1 THEN 1 ELSE 0 END AS is_repeat_customer
FROM latest l
JOIN ord_count o ON l.customer_unique_id = o.customer_unique_id
WHERE l.rn = 1;
GO

-- bridge: per-order customer_id → customer_key (for fact joins)
TRUNCATE TABLE gold._bridge_customer;

INSERT INTO gold._bridge_customer (customer_id, customer_key)
SELECT c.customer_id, d.customer_key
FROM silver.customers c
JOIN gold.DimCustomer d ON c.customer_unique_id = d.customer_unique_id;
GO

-- ---------------------------------------------------------------------
-- gold.DimProduct
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.DimProduct;

INSERT INTO gold.DimProduct (
    product_key, product_id, category_pt, category_en,
    photos_qty, weight_g, length_cm, height_cm, width_cm, weight_bucket
)
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
    CASE
        WHEN weight_g IS NULL THEN 'unknown'
        WHEN weight_g < 500    THEN '0-500g'
        WHEN weight_g < 2000   THEN '500g-2kg'
        WHEN weight_g < 10000  THEN '2-10kg'
        ELSE '10kg+'
    END AS weight_bucket
FROM silver.products;
GO

-- ---------------------------------------------------------------------
-- gold.DimSeller
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.DimSeller;

INSERT INTO gold.DimSeller (seller_key, seller_id, seller_zip_prefix, seller_city, seller_state)
SELECT
    DENSE_RANK() OVER (ORDER BY seller_id) AS seller_key,
    seller_id,
    seller_zip_prefix,
    seller_city,
    seller_state
FROM silver.sellers;
GO

-- ---------------------------------------------------------------------
-- gold.DimGeography — Brazilian state → 5 macro-region rollup
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.DimGeography;

;WITH states AS (
    SELECT DISTINCT customer_state AS state FROM silver.customers WHERE customer_state IS NOT NULL
    UNION
    SELECT DISTINCT seller_state   AS state FROM silver.sellers   WHERE seller_state   IS NOT NULL
)
INSERT INTO gold.DimGeography (geography_key, state, region)
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
FROM states;
GO

-- ---------------------------------------------------------------------
-- gold.FactOrderItems — primary fact, grain = 1 line item
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.FactOrderItems;

INSERT INTO gold.FactOrderItems (
    order_id, order_item_id,
    purchase_date_key, delivered_date_key, estimated_date_key,
    customer_key, product_key, seller_key,
    order_status, price, freight_value, total_value,
    delivery_days, delivery_vs_estimate_days, on_time_flag
)
SELECT
    oi.order_id,
    oi.order_item_id,
    CAST(CONVERT(varchar(8), o.order_purchase_ts,           112) AS INT) AS purchase_date_key,
    CAST(CONVERT(varchar(8), o.order_delivered_customer_ts, 112) AS INT) AS delivered_date_key,
    CAST(CONVERT(varchar(8), o.order_estimated_delivery_ts, 112) AS INT) AS estimated_date_key,
    bc.customer_key,
    dp.product_key,
    ds.seller_key,
    o.order_status,
    oi.price,
    oi.freight_value,
    oi.price + oi.freight_value AS total_value,
    DATEDIFF(DAY, o.order_purchase_ts, o.order_delivered_customer_ts)            AS delivery_days,
    DATEDIFF(DAY, o.order_estimated_delivery_ts, o.order_delivered_customer_ts)  AS delivery_vs_estimate_days,
    CASE WHEN o.order_delivered_customer_ts <= o.order_estimated_delivery_ts THEN 1 ELSE 0 END AS on_time_flag
FROM silver.order_items oi
JOIN silver.orders o            ON oi.order_id = o.order_id
LEFT JOIN gold._bridge_customer bc ON o.customer_id = bc.customer_id
LEFT JOIN gold.DimProduct       dp ON oi.product_id = dp.product_id
LEFT JOIN gold.DimSeller        ds ON oi.seller_id  = ds.seller_id;
GO

-- ---------------------------------------------------------------------
-- gold.FactPayments
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.FactPayments;

INSERT INTO gold.FactPayments (
    order_id, payment_sequential, purchase_date_key,
    customer_key, payment_type, payment_installments, payment_value
)
SELECT
    p.order_id,
    p.payment_sequential,
    CAST(CONVERT(varchar(8), o.order_purchase_ts, 112) AS INT) AS purchase_date_key,
    bc.customer_key,
    p.payment_type,
    p.payment_installments,
    p.payment_value
FROM silver.order_payments p
JOIN silver.orders o ON p.order_id = o.order_id
LEFT JOIN gold._bridge_customer bc ON o.customer_id = bc.customer_id;
GO

-- ---------------------------------------------------------------------
-- gold.FactReviews
-- ---------------------------------------------------------------------
TRUNCATE TABLE gold.FactReviews;

INSERT INTO gold.FactReviews (
    review_id, order_id, purchase_date_key, review_date_key,
    customer_key, review_score, response_days
)
SELECT
    r.review_id,
    r.order_id,
    CAST(CONVERT(varchar(8), o.order_purchase_ts, 112) AS INT) AS purchase_date_key,
    CAST(CONVERT(varchar(8), r.review_creation_ts, 112) AS INT) AS review_date_key,
    bc.customer_key,
    r.review_score,
    DATEDIFF(DAY, r.review_creation_ts, r.review_answer_ts) AS response_days
FROM silver.order_reviews r
JOIN silver.orders o ON r.order_id = o.order_id
LEFT JOIN gold._bridge_customer bc ON o.customer_id = bc.customer_id;
GO

PRINT 'Gold layer loaded.';

-- Summary counts
SELECT 'DimDate'         AS [table], COUNT(*) AS [rows] FROM gold.DimDate
UNION ALL SELECT 'DimCustomer',     COUNT(*) FROM gold.DimCustomer
UNION ALL SELECT 'DimProduct',      COUNT(*) FROM gold.DimProduct
UNION ALL SELECT 'DimSeller',       COUNT(*) FROM gold.DimSeller
UNION ALL SELECT 'DimGeography',    COUNT(*) FROM gold.DimGeography
UNION ALL SELECT 'FactOrderItems',  COUNT(*) FROM gold.FactOrderItems
UNION ALL SELECT 'FactPayments',    COUNT(*) FROM gold.FactPayments
UNION ALL SELECT 'FactReviews',     COUNT(*) FROM gold.FactReviews;

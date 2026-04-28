-- =====================================================================
-- OLIST T-SQL INIT — database, schemas, all tables (bronze/silver/gold)
-- Target: SQL Server 2022 / Azure SQL Edge / Azure SQL DB / Fabric SQL
-- =====================================================================

-- Run from master DB to create the olist database
USE master;
GO
IF DB_ID('olist') IS NULL
    CREATE DATABASE olist;
GO

USE olist;
GO

-- Schemas: bronze (raw), silver (cleaned), gold (star schema)
IF SCHEMA_ID('bronze') IS NULL EXEC('CREATE SCHEMA bronze');
IF SCHEMA_ID('silver') IS NULL EXEC('CREATE SCHEMA silver');
IF SCHEMA_ID('gold')   IS NULL EXEC('CREATE SCHEMA gold');
GO

-- ---------------------------------------------------------------------
-- BRONZE — raw, mirrors the CSVs as they arrived (NVARCHAR for safety)
-- ---------------------------------------------------------------------
IF OBJECT_ID('bronze.orders', 'U') IS NOT NULL DROP TABLE bronze.orders;
CREATE TABLE bronze.orders (
    order_id                       NVARCHAR(64),
    customer_id                    NVARCHAR(64),
    order_status                   NVARCHAR(32),
    order_purchase_timestamp       NVARCHAR(32),
    order_approved_at              NVARCHAR(32),
    order_delivered_carrier_date   NVARCHAR(32),
    order_delivered_customer_date  NVARCHAR(32),
    order_estimated_delivery_date  NVARCHAR(32),
    _ingested_at                   DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file                   NVARCHAR(256)
);

IF OBJECT_ID('bronze.order_items', 'U') IS NOT NULL DROP TABLE bronze.order_items;
CREATE TABLE bronze.order_items (
    order_id              NVARCHAR(64),
    order_item_id         INT,
    product_id            NVARCHAR(64),
    seller_id             NVARCHAR(64),
    shipping_limit_date   NVARCHAR(32),
    price                 DECIMAL(12,2),
    freight_value         DECIMAL(12,2),
    _ingested_at          DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file          NVARCHAR(256)
);

IF OBJECT_ID('bronze.order_payments', 'U') IS NOT NULL DROP TABLE bronze.order_payments;
CREATE TABLE bronze.order_payments (
    order_id              NVARCHAR(64),
    payment_sequential    INT,
    payment_type          NVARCHAR(32),
    payment_installments  INT,
    payment_value         DECIMAL(12,2),
    _ingested_at          DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file          NVARCHAR(256)
);

IF OBJECT_ID('bronze.order_reviews', 'U') IS NOT NULL DROP TABLE bronze.order_reviews;
CREATE TABLE bronze.order_reviews (
    review_id                NVARCHAR(64),
    order_id                 NVARCHAR(64),
    review_score             INT,
    review_comment_title     NVARCHAR(256),
    review_comment_message   NVARCHAR(MAX),
    review_creation_date     NVARCHAR(32),
    review_answer_timestamp  NVARCHAR(32),
    _ingested_at             DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file             NVARCHAR(256)
);

IF OBJECT_ID('bronze.products', 'U') IS NOT NULL DROP TABLE bronze.products;
CREATE TABLE bronze.products (
    product_id                    NVARCHAR(64),
    product_category_name         NVARCHAR(128),
    product_name_lenght           INT,
    product_description_lenght    INT,
    product_photos_qty            INT,
    product_weight_g              INT,
    product_length_cm             INT,
    product_height_cm             INT,
    product_width_cm              INT,
    _ingested_at                  DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file                  NVARCHAR(256)
);

IF OBJECT_ID('bronze.sellers', 'U') IS NOT NULL DROP TABLE bronze.sellers;
CREATE TABLE bronze.sellers (
    seller_id                NVARCHAR(64),
    seller_zip_code_prefix   INT,
    seller_city              NVARCHAR(128),
    seller_state             NVARCHAR(8),
    _ingested_at             DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file             NVARCHAR(256)
);

IF OBJECT_ID('bronze.customers', 'U') IS NOT NULL DROP TABLE bronze.customers;
CREATE TABLE bronze.customers (
    customer_id                NVARCHAR(64),
    customer_unique_id         NVARCHAR(64),
    customer_zip_code_prefix   INT,
    customer_city              NVARCHAR(128),
    customer_state             NVARCHAR(8),
    _ingested_at               DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file               NVARCHAR(256)
);

IF OBJECT_ID('bronze.geolocation', 'U') IS NOT NULL DROP TABLE bronze.geolocation;
CREATE TABLE bronze.geolocation (
    geolocation_zip_code_prefix INT,
    geolocation_lat             FLOAT,
    geolocation_lng             FLOAT,
    geolocation_city            NVARCHAR(128),
    geolocation_state           NVARCHAR(8),
    _ingested_at                DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file                NVARCHAR(256)
);

IF OBJECT_ID('bronze.category_translation', 'U') IS NOT NULL DROP TABLE bronze.category_translation;
CREATE TABLE bronze.category_translation (
    product_category_name           NVARCHAR(128),
    product_category_name_english   NVARCHAR(128),
    _ingested_at                    DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    _source_file                    NVARCHAR(256)
);
GO

-- ---------------------------------------------------------------------
-- SILVER — typed, deduplicated, conformed
-- ---------------------------------------------------------------------
IF OBJECT_ID('silver.orders', 'U') IS NOT NULL DROP TABLE silver.orders;
CREATE TABLE silver.orders (
    order_id                       NVARCHAR(64) NOT NULL PRIMARY KEY,
    customer_id                    NVARCHAR(64) NOT NULL,
    order_status                   NVARCHAR(32),
    order_purchase_ts              DATETIME2(0),
    order_approved_ts              DATETIME2(0),
    order_delivered_carrier_ts     DATETIME2(0),
    order_delivered_customer_ts    DATETIME2(0),
    order_estimated_delivery_ts    DATETIME2(0)
);

IF OBJECT_ID('silver.order_items', 'U') IS NOT NULL DROP TABLE silver.order_items;
CREATE TABLE silver.order_items (
    order_id           NVARCHAR(64) NOT NULL,
    order_item_id      INT NOT NULL,
    product_id         NVARCHAR(64),
    seller_id          NVARCHAR(64),
    shipping_limit_ts  DATETIME2(0),
    price              DECIMAL(12,2),
    freight_value      DECIMAL(12,2),
    PRIMARY KEY (order_id, order_item_id)
);

IF OBJECT_ID('silver.order_payments', 'U') IS NOT NULL DROP TABLE silver.order_payments;
CREATE TABLE silver.order_payments (
    order_id              NVARCHAR(64) NOT NULL,
    payment_sequential    INT NOT NULL,
    payment_type          NVARCHAR(32),
    payment_installments  INT,
    payment_value         DECIMAL(12,2),
    PRIMARY KEY (order_id, payment_sequential)
);

IF OBJECT_ID('silver.order_reviews', 'U') IS NOT NULL DROP TABLE silver.order_reviews;
CREATE TABLE silver.order_reviews (
    review_id                NVARCHAR(64) NOT NULL PRIMARY KEY,
    order_id                 NVARCHAR(64) NOT NULL,
    review_score             INT,
    review_comment_title     NVARCHAR(256),
    review_comment_message   NVARCHAR(MAX),
    review_creation_ts       DATETIME2(0),
    review_answer_ts         DATETIME2(0)
);

IF OBJECT_ID('silver.products', 'U') IS NOT NULL DROP TABLE silver.products;
CREATE TABLE silver.products (
    product_id           NVARCHAR(64) NOT NULL PRIMARY KEY,
    category_pt          NVARCHAR(128),
    category_en          NVARCHAR(128),
    name_length          INT,
    description_length   INT,
    photos_qty           INT,
    weight_g             INT,
    length_cm            INT,
    height_cm            INT,
    width_cm             INT
);

IF OBJECT_ID('silver.sellers', 'U') IS NOT NULL DROP TABLE silver.sellers;
CREATE TABLE silver.sellers (
    seller_id          NVARCHAR(64) NOT NULL PRIMARY KEY,
    seller_zip_prefix  INT,
    seller_city        NVARCHAR(128),
    seller_state       NVARCHAR(8)
);

IF OBJECT_ID('silver.customers', 'U') IS NOT NULL DROP TABLE silver.customers;
CREATE TABLE silver.customers (
    customer_id           NVARCHAR(64) NOT NULL PRIMARY KEY,
    customer_unique_id    NVARCHAR(64) NOT NULL,
    customer_zip_prefix   INT,
    customer_city         NVARCHAR(128),
    customer_state        NVARCHAR(8)
);

IF OBJECT_ID('silver.geolocation', 'U') IS NOT NULL DROP TABLE silver.geolocation;
CREATE TABLE silver.geolocation (
    zip_prefix  INT NOT NULL PRIMARY KEY,
    lat         FLOAT,
    lng         FLOAT,
    city        NVARCHAR(128),
    state       NVARCHAR(8)
);
GO

-- ---------------------------------------------------------------------
-- GOLD — star schema (Kimball), surrogate keys, ready for Power BI
-- ---------------------------------------------------------------------
IF OBJECT_ID('gold.DimDate', 'U') IS NOT NULL DROP TABLE gold.DimDate;
CREATE TABLE gold.DimDate (
    date_key      INT NOT NULL PRIMARY KEY,
    [date]        DATE NOT NULL,
    [year]        INT,
    [quarter]     INT,
    [month]       INT,
    month_name    NVARCHAR(16),
    [day]         INT,
    day_of_week   INT,
    day_name      NVARCHAR(16),
    day_of_year   INT,
    week_of_year  INT,
    is_weekend    BIT,
    year_quarter  NVARCHAR(8),
    year_month    NVARCHAR(8)
);

IF OBJECT_ID('gold.DimCustomer', 'U') IS NOT NULL DROP TABLE gold.DimCustomer;
CREATE TABLE gold.DimCustomer (
    customer_key          INT NOT NULL PRIMARY KEY,
    customer_unique_id    NVARCHAR(64) NOT NULL,
    customer_zip_prefix   INT,
    customer_city         NVARCHAR(128),
    customer_state        NVARCHAR(8),
    n_orders_per_unique   INT,
    is_repeat_customer    BIT
);

IF OBJECT_ID('gold._bridge_customer', 'U') IS NOT NULL DROP TABLE gold._bridge_customer;
CREATE TABLE gold._bridge_customer (
    customer_id     NVARCHAR(64) NOT NULL PRIMARY KEY,
    customer_key    INT NOT NULL
);

IF OBJECT_ID('gold.DimProduct', 'U') IS NOT NULL DROP TABLE gold.DimProduct;
CREATE TABLE gold.DimProduct (
    product_key    INT NOT NULL PRIMARY KEY,
    product_id     NVARCHAR(64) NOT NULL,
    category_pt    NVARCHAR(128),
    category_en    NVARCHAR(128),
    photos_qty     INT,
    weight_g       INT,
    length_cm      INT,
    height_cm      INT,
    width_cm       INT,
    weight_bucket  NVARCHAR(16)
);

IF OBJECT_ID('gold.DimSeller', 'U') IS NOT NULL DROP TABLE gold.DimSeller;
CREATE TABLE gold.DimSeller (
    seller_key         INT NOT NULL PRIMARY KEY,
    seller_id          NVARCHAR(64) NOT NULL,
    seller_zip_prefix  INT,
    seller_city        NVARCHAR(128),
    seller_state       NVARCHAR(8)
);

IF OBJECT_ID('gold.DimGeography', 'U') IS NOT NULL DROP TABLE gold.DimGeography;
CREATE TABLE gold.DimGeography (
    geography_key  INT NOT NULL PRIMARY KEY,
    state          NVARCHAR(8) NOT NULL UNIQUE,
    region         NVARCHAR(16)
);

IF OBJECT_ID('gold.FactOrderItems', 'U') IS NOT NULL DROP TABLE gold.FactOrderItems;
CREATE TABLE gold.FactOrderItems (
    order_id                    NVARCHAR(64) NOT NULL,
    order_item_id               INT NOT NULL,
    purchase_date_key           INT,
    delivered_date_key          INT,
    estimated_date_key          INT,
    customer_key                INT,
    product_key                 INT,
    seller_key                  INT,
    order_status                NVARCHAR(32),
    price                       DECIMAL(12,2),
    freight_value               DECIMAL(12,2),
    total_value                 DECIMAL(12,2),
    delivery_days               INT,
    delivery_vs_estimate_days   INT,
    on_time_flag                BIT,
    PRIMARY KEY (order_id, order_item_id)
);

IF OBJECT_ID('gold.FactPayments', 'U') IS NOT NULL DROP TABLE gold.FactPayments;
CREATE TABLE gold.FactPayments (
    order_id              NVARCHAR(64) NOT NULL,
    payment_sequential    INT NOT NULL,
    purchase_date_key     INT,
    customer_key          INT,
    payment_type          NVARCHAR(32),
    payment_installments  INT,
    payment_value         DECIMAL(12,2),
    PRIMARY KEY (order_id, payment_sequential)
);

IF OBJECT_ID('gold.FactReviews', 'U') IS NOT NULL DROP TABLE gold.FactReviews;
CREATE TABLE gold.FactReviews (
    review_id          NVARCHAR(64) NOT NULL PRIMARY KEY,
    order_id           NVARCHAR(64) NOT NULL,
    purchase_date_key  INT,
    review_date_key    INT,
    customer_key       INT,
    review_score       INT,
    response_days      INT
);
GO

-- Indexes for fact joins (boost Power BI / Copilot query performance)
CREATE INDEX IX_FactOrderItems_purchase_date ON gold.FactOrderItems(purchase_date_key);
CREATE INDEX IX_FactOrderItems_customer      ON gold.FactOrderItems(customer_key);
CREATE INDEX IX_FactOrderItems_product       ON gold.FactOrderItems(product_key);
CREATE INDEX IX_FactOrderItems_seller        ON gold.FactOrderItems(seller_key);
CREATE INDEX IX_FactPayments_purchase_date   ON gold.FactPayments(purchase_date_key);
CREATE INDEX IX_FactPayments_customer        ON gold.FactPayments(customer_key);
CREATE INDEX IX_FactReviews_purchase_date    ON gold.FactReviews(purchase_date_key);
CREATE INDEX IX_FactReviews_customer         ON gold.FactReviews(customer_key);
GO

PRINT 'Init complete: olist database with bronze/silver/gold schemas + tables.';

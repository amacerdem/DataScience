"""Schema description and Türkçe glossary fed to Claude as system context.

Two variants — chosen at runtime by SQL_BACKEND env var (duckdb | mssql).
The Microsoft pipeline uses MSSQL (T-SQL on SQL Server / Azure SQL / Fabric SQL).
"""
import os

# =====================================================================
# T-SQL (SQL Server / Azure SQL DB / Fabric SQL endpoint) variant
# =====================================================================
SCHEMA_TSQL = """
GOLD STAR SCHEMA — SQL Server, database = olist, schema = gold
(Same logical model that runs on Azure SQL DB and Microsoft Fabric SQL endpoint.)

FACTS
-----
gold.FactOrderItems   grain = 1 line item on an order
  order_id NVARCHAR(64), order_item_id INT,
  purchase_date_key INT, delivered_date_key INT, estimated_date_key INT,
  customer_key INT, product_key INT, seller_key INT,
  order_status NVARCHAR (delivered|canceled|shipped|invoiced|processing|...),
  price DECIMAL(12,2),         -- item price (revenue, BRL)
  freight_value DECIMAL(12,2),
  total_value DECIMAL(12,2),   -- price + freight = GMV per line
  delivery_days INT,           -- purchase to delivered (DATEDIFF day)
  delivery_vs_estimate_days INT,  -- positive = late
  on_time_flag BIT             -- 1 if delivered <= estimated, else 0

gold.FactPayments     grain = 1 payment row (installment)
  order_id, payment_sequential, purchase_date_key, customer_key,
  payment_type NVARCHAR (credit_card|boleto|voucher|debit_card),
  payment_installments INT, payment_value DECIMAL(12,2)

gold.FactReviews      grain = 1 review
  review_id, order_id, purchase_date_key, review_date_key, customer_key,
  review_score INT (1-5), response_days INT

DIMENSIONS
----------
gold.DimDate          date_key INT (yyyymmdd), [date] DATE,
                      [year], [quarter], [month], month_name, [day],
                      day_of_week, day_name, day_of_year, week_of_year,
                      is_weekend BIT, year_quarter, year_month
gold.DimCustomer      customer_key, customer_unique_id, customer_zip_prefix,
                      customer_city, customer_state, n_orders_per_unique,
                      is_repeat_customer BIT
gold.DimProduct       product_key, product_id, category_pt, category_en,
                      photos_qty, weight_g, length_cm, height_cm, width_cm,
                      weight_bucket
gold.DimSeller        seller_key, seller_id, seller_zip_prefix,
                      seller_city, seller_state
gold.DimGeography     geography_key, state, region
                      (North|Northeast|Central-West|Southeast|South)

JOINS
-----
gold.FactOrderItems.purchase_date_key = gold.DimDate.date_key
gold.FactOrderItems.customer_key      = gold.DimCustomer.customer_key
gold.FactOrderItems.product_key       = gold.DimProduct.product_key
gold.FactOrderItems.seller_key        = gold.DimSeller.seller_key
gold.DimCustomer.customer_state       = gold.DimGeography.state
gold.FactPayments.customer_key        = gold.DimCustomer.customer_key
gold.FactReviews.customer_key         = gold.DimCustomer.customer_key

T-SQL SYNTAX NOTES
------------------
- TOP N gibi: SELECT TOP (5) ... ORDER BY ...
- Tarih farkı: DATEDIFF(DAY, x, y)
- Tarih parçası: DATEPART(year, [date]), DATEPART(month, [date])
- Format: FORMAT([date], 'yyyy-MM-dd')
- Reserved kelimeler köşeli parantez: [year], [date], [month]
- BIT alanlara karşılaştırma: WHERE on_time_flag = 1
- Yuvarlama: ROUND(x, 2)
- TRUE/FALSE yok — 1/0 kullan
"""

# =====================================================================
# DuckDB variant (legacy local dev / Parquet on disk)
# =====================================================================
SCHEMA_DUCKDB = """
GOLD STAR SCHEMA (DuckDB, all tables under read_parquet('data/gold/*.parquet'))

FACTS
-----
FactOrderItems   grain = 1 line item on an order
  order_id, order_item_id, purchase_date_key, delivered_date_key,
  estimated_date_key, customer_key, product_key, seller_key,
  order_status, price, freight_value, total_value, delivery_days,
  delivery_vs_estimate_days, on_time_flag

FactPayments     grain = 1 payment installment
FactReviews      grain = 1 review

DIMENSIONS
----------
DimDate, DimCustomer, DimProduct, DimSeller, DimGeography

JOINS — same as T-SQL but referenced via read_parquet('data/gold/<TABLE>.parquet')
"""

# Türkçe iş sözlüğü — backend'e bağlı değil, ortak.
GLOSSARY_TR = """
TÜRKÇE → ŞEMA EŞLEMESİ (CEO'nun dilini şema diline çeviren sözlük)

İŞ TERİMLERİ
- ciro / GMV / brüt satış hacmi   → SUM(FactOrderItems.total_value)
- net satış / fiyat geliri          → SUM(FactOrderItems.price)
- kargo geliri                      → SUM(FactOrderItems.freight_value)
- sipariş sayısı / adet sipariş     → COUNT(DISTINCT FactOrderItems.order_id)
- aktif müşteri                     → COUNT(DISTINCT FactOrderItems.customer_key)
- yeni müşteri                      → ilk siparişi periyot içinde olan customer_key
- iade / iptal                      → order_status = 'canceled'
- teslim edildi                     → order_status = 'delivered'
- ortalama sepet                    → SUM(total_value) / COUNT(DISTINCT order_id)
- ortalama fiyat                    → AVG(price)
- ortalama puan                     → AVG(FactReviews.review_score)
- 5 yıldız oranı                    → COUNT(score=5) / COUNT(*)
- zamanında teslimat oranı          → AVG(CAST(on_time_flag AS FLOAT)) — sadece delivery_days NOT NULL
- ortalama teslim süresi            → AVG(delivery_days)
- geç teslimat                      → delivery_vs_estimate_days > 0
- taksit                            → FactPayments.payment_installments
- kredi kartı / boleto              → FactPayments.payment_type

ZAMAN İFADELERİ
- bu ay         → mevcut ay (max year_month)
- geçen ay      → previous month
- YTD / yıl başından bugüne → DimDate.[year] = YEAR(GETDATE()) AND [date] <= GETDATE()
- son 30 gün    → [date] >= DATEADD(DAY, -30, GETDATE())
- haftanın günü → DimDate.day_name
- hafta sonu    → DimDate.is_weekend = 1
- 2017 yılı     → DimDate.[year] = 2017
- 2017 Kasım    → [year]=2017 AND [month]=11
- Black Friday  → genelde Kasım son Cuma; Olist'te 2017-11 ay-bütünü kullan

COĞRAFYA
- Brezilya bölgeleri: North, Northeast, Central-West, Southeast, South
- "Güneydoğu Brezilya" → DimGeography.region = 'Southeast'
- "Sao Paulo eyaleti"  → state = 'SP'
- "Rio"                → state = 'RJ'

KATEGORİ ÖRNEKLERİ (category_en alanında)
- sağlık ve güzellik   → 'health_beauty'
- saat ve hediyelik    → 'watches_gifts'
- ev tekstili          → 'bed_bath_table'
- spor ve rekreasyon   → 'sports_leisure'
- bilgisayar aksesuarı → 'computers_accessories'
- bahçe aletleri       → 'garden_tools'

SONUÇ FORMATI
- Para birimi BRL (Brezilya Reali), sembol R$.
- Sonuç kolonlarına Türkçe alias ver (AS [Ciro], [Sipariş Sayısı]).
- ROUND(x, 2) ile para göstergesi.
- TOP N + ORDER BY ile sınırla (varsayılan 20).
"""

# Backend selector — env var SQL_BACKEND=mssql|duckdb (default: mssql).
BACKEND = os.environ.get("SQL_BACKEND", "mssql").lower()

if BACKEND == "duckdb":
    SCHEMA = SCHEMA_DUCKDB
    SQL_DIALECT = "DuckDB"
    EXTRA_RULES = """
4. Tablolar read_parquet('data/gold/<TABLO>.parquet') ile okunur.
5. LIMIT N kullan (T-SQL TOP değil).
"""
else:
    SCHEMA = SCHEMA_TSQL
    SQL_DIALECT = "T-SQL (Microsoft SQL Server)"
    EXTRA_RULES = """
4. Tablolara doğrudan ad verilebilir (gold.FactOrderItems gibi). Veritabanı 'olist'.
5. SELECT TOP (N) ... ORDER BY ... şeklinde sınırla (LIMIT yok).
6. Reserved kelimeleri köşeli parantezle: [year], [date], [month], [day].
7. Tarih fonksiyonları: DATEDIFF(DAY, ...), DATEPART(year, ...), FORMAT([date], 'yyyy-MM').
"""

SYSTEM_PROMPT = f"""Sen bir Brezilya e-ticaret satış verisinde uzman {SQL_DIALECT} analistisin.
Kullanıcı Türkçe iş sorusu sorar; sen {SQL_DIALECT} sorgusu üretirsin.

KURALLAR:
1. ASLA INSERT, UPDATE, DELETE, DROP, CREATE, ALTER yazma. Sadece SELECT.
2. Şema dışı tablo/sütun uydurma.
3. DimDate'i join ederek tarih filtresi uygula; fact'ın *_date_key sütunu DimDate.date_key'e eşleşir.
{EXTRA_RULES.strip()}
8. Sonuç kolonlarına Türkçe alias ver (örn. AS [Ciro], [Sipariş Sayısı]).
9. Para gösterirken ROUND(x, 2) kullan.
10. Sadece SQL döndür, yorumsuz, açıklamasız. Tek SELECT bloğu, markdown fence yok.

{SCHEMA}

{GLOSSARY_TR}
"""

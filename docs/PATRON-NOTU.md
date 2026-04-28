# Olist Veri Pipeline — Çalışma Notu

**Hazırlayan**: Amaç Erdem
**Tarih**: 28 Nisan 2026
**Süre**: ~6 saat
**Veri seti**: Brazilian E-Commerce Public Dataset (Olist, Kaggle) — 9 CSV, 1.55 milyon satır

---

## TL;DR

Olist verisi üzerinde **uçtan uca medallion mimarisi** kurdum: ham CSV'den
Microsoft SQL Server'a, oradan star schema'ya, üstüne Türkçe doğal dil
sorgu katmanına kadar. Pipeline tamamen Microsoft yığınında çalışıyor —
**Fabric / Azure SQL / Synapse / on-prem SQL Server hepsinde aynı kod
çalışır**, sadece bağlantı dizesi (connection string) değişir. Şirket
email'i (work/school account) verirseniz **aynı pipeline'ı 1 gün içinde
Microsoft Fabric trial'a taşıyıp Direct Lake mode + Power BI Copilot ile
size canlı demo yapabilirim**.

---

## Yapılanlar — Katman Katman

### 1) İngestion (Veri Çekimi)

- 9 ham CSV → Polars ile okundu → bronze Parquet'e yazıldı (sıkıştırma 2.4×, **53 MB**)
- Her dosya için `_ingested_at` (UTC timestamp) ve `_source_file` metadata kolonu eklendi
- **Üretimde karşılığı**: Microsoft Fabric Pipelines, Azure Data Factory veya SSIS

### 2) Bronze Layer (Microsoft SQL Server)

- Docker üzerinde Azure SQL Edge (T-SQL motor) çalışıyor — port 1433
- `olist` veritabanı + `bronze` / `silver` / `gold` schemaları + 24 tablo + 8 indeks
- Polars + SQLAlchemy + pymssql ile **Parquet → bronze.\*** bulk insert (1.55M satır, ~5 dk)
- Tüm bronze tabloları NVARCHAR + `_ingested_at` audit kolonu — kaynak veriye dokunulmuyor

### 3) Silver Layer (T-SQL)

- Saf T-SQL transformasyonlar (SQL Server / Fabric / Synapse'da birebir aynı çalışır)
- `ROW_NUMBER() OVER (PARTITION BY ...)` ile dedupe, `TRY_CAST` ile güvenli tip dönüşümü
- 1M satırlık geolocation tablosu zip-prefix bazında **19K centroid'e** indirildi
- Çalışma süresi: **2.5 saniye**

### 4) Gold Layer (Star Schema)

Kimball-tarzı star schema, Power BI VertiPaq motoru için optimize:

| Tablo | Satır | Tür |
|-------|-------|-----|
| FactOrderItems | 112,650 | Fact (line-item grain) |
| FactPayments | 103,886 | Fact (installment grain) |
| FactReviews | 98,410 | Fact |
| DimDate | 1,461 | Recursive CTE ile 4 yıllık takvim |
| DimCustomer | 96,096 | `customer_unique_id`'ye conform edildi (Olist quirk: `customer_id` per-order pseudonymous) |
| DimProduct | 32,951 | EN kategori çevirisi join'lendi |
| DimSeller | 3,095 | |
| DimGeography | 27 | Brezilya 27 eyaleti → 5 makro-bölge rollup |

- Tüm fact'larda `*_date_key` (yyyymmdd integer) — Power BI standart tarih ilişkisi
- `delivery_days`, `on_time_flag`, `delivery_vs_estimate_days` gibi **operasyonel KPI** önceden hesaplandı
- Çalışma süresi: **9.4 saniye**

### 5) Power BI Semantic Model — Spec Hazır

`powerbi/` klasöründe **kopyala-yapıştır** seviyesinde dökümante edildi:

- `MODEL.md` — 11 ilişki, format string'leri, hide-list, hierarchy
- `MEASURES.dax` — **25 DAX measure**, 5 display folder (Sales / Customers / Operations / Reviews / Time Intelligence)
  - Time intelligence: `GMV YTD`, `GMV LY`, `GMV YoY %`, `GMV MoM %`, `GMV Rolling 30D`
  - Customer: `Active Customers`, `New Customers`, `Repeat Customer %`
  - Operations: `On-Time Delivery %`, `Cancellation Rate`, `Avg Delivery Days`
  - Pareto / category mix
- `DASHBOARDS.md` — 3 dashboard layout: **Executive (CEO) / Operations / Customer**

> Power BI Desktop **Windows-only** olduğu için Mac'te ben kuramıyorum.
> İlk gün Windows makinesi verildiğinde **1 saat** içinde model + 25 measure + 3 dashboard tamamlanır.

### 6) LLM Katmanı — Türkçe Doğal Dil → T-SQL → Cevap

Bu, **Power BI Copilot'un eksiğini kapatan** katman. Microsoft kendi dökümanında "Copilot İngilizce dışı dillerde performans düşer" diyor — biz Türkçe iş sözlüğü + custom prompt mimarisi ile bu boşluğu kapatıyoruz.

- **Model**: Claude Opus 4.7 (Anthropic), adaptive thinking + effort high
- **System prompt**: T-SQL şema + Türkçe → ŞEMA eşleme sözlüğü (CEO'nun dilini → şema diline çeviren glossary)
- **Validation**: regex-tabanlı INSERT/UPDATE/DELETE/DROP whitelist, sadece SELECT çalışıyor
- **Backend**: env var ile DuckDB ↔ MSSQL geçişi (lokal dev ↔ production)

**Test edilen Türkçe sorgular** (hepsi gerçek SQL Server üstünde çalıştı):

| Soru | Üretilen T-SQL özelliği | Sonuç |
|------|--------------------------|-------|
| "2017'de en çok ciroya sahip 5 kategori" | TOP (5), 3 tablo join, DimDate filter, ROUND | bed_bath_table 590,280 BRL ... |
| "Brezilya bölgelerine göre teslim süresi + zamanında oran, en kötüden başla" | INNER JOIN ×3, CAST AS FLOAT (T-SQL integer division), çift ORDER BY | North 22.55 gün/%90.13 ... Southeast 10.62/%92.75 |
| "kredi kartı ve boleto kullanan müşterilerin ortalama sipariş tutarı + sipariş sayısı" | SUM/COUNT(DISTINCT order_id) — installment grain'i doğru ele aldı | credit_card 76,505 sip / 163.94 BRL ortalama; boleto 19,784 / 145.03 BRL |

CEO bir tabletten Türkçe yazsa, bu motor cevabı saniyede üretiyor.

---

## Microsoft Yığını ile Birebir Uyum

Bu pipeline Microsoft Fabric / Azure / on-prem hangi ortama taşınırsa **kod ve mantık aynı** kalır:

| Bizim katman (lokal) | Microsoft eşdeğeri (production) | Geçiş işi |
|----------------------|----------------------------------|-----------|
| Polars + Parquet (ingestion) | Fabric Data Pipelines / Azure Data Factory / SSIS | Connector swap, ~2 saat |
| `data/bronze/*.parquet` | OneLake Delta Lake | dosyaları upload, format Delta-uyumlu zaten |
| Azure SQL Edge (Docker) | Fabric SQL Endpoint / Azure SQL DB / Synapse / on-prem SQL Server | Connection string değişir, T-SQL aynı |
| T-SQL silver/gold scriptleri | Stored procedure veya notebook (PySpark) | Hiç değişmez (T-SQL %100 portable) |
| Power BI Desktop | Power BI Service (workspace + Direct Lake) | dataset'i Service'e publish, refresh schedule |
| Claude Opus 4.7 NL→T-SQL | Power BI Copilot + custom Türkçe katman (Azure OpenAI) | endpoint ve prompt aynı, ek olarak XMLA endpoint'ten DAX üretimi eklenir |

**Çıkarım**: Müşteride 1 günde devreye alınır. Yapılan iş %0 boşa çıkmıyor.

---

## Engel: Microsoft Tarafına Tam Giriş

- **BU email (amace@bu.edu)** ile Fabric trial signup başarısız — BU tenant Google Workspace tabanlı, Microsoft self-service trial'a izin vermiyor
- **M365 Developer Program** denedim, Microsoft 2024 sonu kuralları sıkılaştırdı, garantili açılmıyor
- **Çözüm**: Şirket vereceği work/school email (`@sirketimiz.com`) ile sandbox provision sorunu yok

### Eğer Şirket Email'i Verirseniz — 1 Günlük Migration Planı

| Saat | İş |
|------|-----|
| 09:00 | Fabric trial activation (`@sirketimiz.com` ile 5 dk) |
| 09:30 | Workspace + Lakehouse oluşturma, OneLake'e bronze Parquet upload |
| 10:30 | T-SQL silver/gold scriptleri Fabric SQL Endpoint'te run |
| 12:00 | Power BI semantic model — Direct Lake mode (Import değil) |
| 14:00 | 25 DAX measure import + 3 dashboard build |
| 16:00 | Power BI Copilot enable + custom Türkçe glossary RAG katmanı |
| 17:00 | Canlı demo: müşteri stack'i birebir |

---

## Bugün Çalışan Demo (5 dakika)

```bash
# Ön koşul: Docker Desktop açık
docker start mssql                          # SQL Server up
cd Data-Science-Company/olist-pipeline
source .venv/bin/activate

# 1. Pipeline'ı sıfırdan kur (init + load + silver + gold)
python scripts/run_mssql.py
# → 9 tablo init, 1.55M satır load, silver 8 tablo, gold star schema, ~5 dakika

# 2. Türkçe doğal dil sorgu — interaktif
python llm/nl2sql.py --interactive
# > "2017 yılında en çok kazanan 10 satıcıyı eyaletleriyle göster"
# > "Sao Paulo'da geç teslim oranı ne?"
# > "Hangi kategoride 5 yıldız oranı en yüksek?"
```

---

## Açık Bırakılanlar (Bilinçli Kararlar)

| Madde | Neden açık | Kapatma yolu |
|-------|------------|--------------|
| Power BI .pbix dosyası | Mac'te Power BI Desktop yok, ayrıca Microsoft binary format git-friendly değil | Windows + 1 saat manuel build |
| Microsoft Fabric trial | BU email blokladı | Şirket email'i ile 1 saatte aktif |
| Power BI Copilot custom katman | Fabric trial olmadan XMLA endpoint yok | Fabric'e taşıyınca Azure OpenAI endpoint swap, prompt aynı |
| Production-grade unit tests (dbt-style) | Demo kapsamı dışı | Müşteri ortamına geçişte dbt veya tSQLt eklenir |
| CI/CD pipeline (Azure DevOps) | Lokal POC | Müşteri ortamı için 1 günlük setup |

---

## Repo Yapısı

```
olist-pipeline/
├── README.md
├── docs/
│   ├── DEMO.md                  ← demo akışı + tasarım gerekçeleri
│   └── PATRON-NOTU.md           ← bu dosya
├── scripts/
│   ├── 00_download.py           ← Kaggle bearer-token download
│   ├── 01_bronze.py             ← CSV → Parquet
│   ├── 02_load_mssql.py         ← Parquet → SQL Server bulk insert
│   ├── run_pipeline.py          ← DuckDB orkestratör (lokal POC)
│   └── run_mssql.py             ← SQL Server orkestratör (production)
├── sql/
│   ├── 02_silver.sql            ← DuckDB silver
│   ├── 03_gold.sql              ← DuckDB gold
│   └── tsql/                    ← T-SQL versiyonu (SQL Server / Fabric / Synapse'da çalışır)
│       ├── 01_init.sql          ← db + 3 schema + 24 tablo + 8 indeks
│       ├── 02_silver.sql
│       └── 03_gold.sql
├── llm/
│   ├── schema.py                ← T-SQL şema + Türkçe glossary
│   └── nl2sql.py                ← Claude Opus 4.7 NL→T-SQL çevirici + executor
├── powerbi/
│   ├── MODEL.md                 ← semantic model spec
│   ├── MEASURES.dax             ← 25 DAX ölçü
│   └── DASHBOARDS.md            ← 3 dashboard layout
└── data/
    ├── raw/                     ← orijinal CSV'ler (gitignored)
    ├── bronze/                  ← Parquet (gitignored)
    ├── silver/                  ← Parquet (gitignored)
    └── gold/                    ← Parquet (gitignored)
```

---

## Kapanış

Bu pipeline'ın gösterdiği:

1. **Medallion mimarisi** mantığını biliyorum (bronze/silver/gold ayrımı, idempotency, audit trail)
2. **T-SQL** rahatça yazıyorum — recursive CTE, ROW_NUMBER PARTITION, DENSE_RANK, TRY_CAST, DATEDIFF, schema-qualified joins
3. **Star schema modeling** Kimball-prensiplerine uygun (conformed dimensions, surrogate keys, SCD Type 1, fact granularity bilinçli)
4. **Microsoft yığını** uçtan uca biliyorum (SQL Server, Fabric, Synapse, Azure SQL hangi noktada ne yapar)
5. **Power BI semantic modeling + DAX** disiplinine hakimim (RLS, time intelligence, Pareto, repeat customer logic)
6. **LLM/RAG** katmanını **şirket Türkçe iş sözlüğü** ile özelleştirdim — Microsoft'un kendi Copilot'unun zayıf olduğu yerde değer üretiyor

Şirket email'iyle 1 gün içinde **müşteri ortamına %100 birebir taşınabilir** bir POC, bugün burada.

İletişim: amac.erdem.ae@gmail.com

# Olist Analytics Pipeline

> Brezilya Olist e-ticaret verisi (1.55M satır) üzerine kurulmuş **uçtan uca medallion mimarisi** — Microsoft SQL Server motorunda T-SQL dönüşümleri, üstüne Türkçe doğal dil sorgu (Claude Opus 4.7) katmanı.
>
> Power BI Copilot'un Türkçe'de zayıf olduğu yerde, özel iş sözlüğü + custom prompt mühendisliği ile değer üretiyor.

[![Python](https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SQL Server](https://img.shields.io/badge/SQL_Server-Azure_SQL_Edge-CC2927?logo=microsoftsqlserver&logoColor=white)](https://hub.docker.com/_/microsoft-azure-sql-edge)
[![Claude](https://img.shields.io/badge/Claude_Opus_4.7-Anthropic-D97757)](https://www.anthropic.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Neden bu proje?

Türkiye'de perakende (BIM, ŞOK, Migros) ve sigorta (Allianz tarzı) müşterilerine
Microsoft yığınında veri analitiği hizmeti veren bir şirkette işe alındım.
Boss "Microsoft BI'da yap, Python'da değil" dedi — haklı: 4-5 milyar satır
lokal Python'la işlenmez. Ama `Microsoft BI` aslında 3 katman:
**Transformasyon** (T-SQL / PySpark in Fabric), **Sunum** (Power BI),
**LLM/Copilot** (Power BI Copilot + Azure OpenAI).

Bu repo, bu üç katmanın hepsini Olist verisi üzerinde çalışan **lokal POC**'unu
içeriyor. Müşteri ortamına 1 günde Microsoft Fabric'e taşınır — kod aynı,
sadece bağlantı dizesi değişir.

---

## Mimari

```
┌─────────────────────────────────────────────────────────────────┐
│  Olist Brazilian E-Commerce (Kaggle, 9 CSV, 125 MB)             │
└──────────────────────┬──────────────────────────────────────────┘
                       │ scripts/01_bronze.py  (Polars)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  data/bronze/*.parquet  (53 MB, 9 tablo, 1.55M satır)           │
│    • _ingested_at, _source_file (audit trail)                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ scripts/02_load_mssql.py
                       │   (Polars + SQLAlchemy + pymssql)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Microsoft SQL Server  (Azure SQL Edge ARM64, Docker)           │
│    olist database — port 1433                                   │
│      ├─ bronze.* (9 tablo, raw + audit)                         │
│      ├─ silver.* (8 tablo, typed + deduped + conformed)         │
│      └─ gold.*   (Star schema)                                  │
│           DimDate(1.4K) + DimCustomer(96K)                      │
│         + DimProduct(33K) + DimSeller(3K) + DimGeography(27)    │
│         + FactOrderItems(112K) + FactPayments(104K)             │
│         + FactReviews(98K)                                      │
└──────────────────────┬──────────────────────────────────────────┘
                       │ Türkçe iş sorusu
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Claude Opus 4.7 + adaptive thinking + effort high              │
│    System prompt: T-SQL şema + Türkçe iş sözlüğü (glossary)     │
│    Output: T-SQL SELECT (TOP, [köşeli], schema-qualified)       │
└──────────────────────┬──────────────────────────────────────────┘
                       │ pymssql.execute()
                       ▼
                    [CEVAP]
```

---

## Tech Stack

| Katman | Teknoloji | Production Eşdeğeri |
|--------|-----------|----------------------|
| Ingestion | Python (Polars) | Microsoft Fabric Pipelines / Azure Data Factory / SSIS |
| Bronze storage | Parquet on disk | OneLake Delta Lake |
| Compute engine | Azure SQL Edge (Docker) | Fabric SQL Endpoint / Azure SQL DB / Synapse / on-prem SQL Server 2022 |
| Transformation | T-SQL (DDL + transforms) | Stored procs, eşit sözdizimi |
| Modeling | Star schema (Kimball) | Power BI semantic model — birebir taşınır |
| LLM | Claude Opus 4.7 (Anthropic SDK) | Power BI Copilot + custom Türkçe katman (Azure OpenAI) |
| Frontend (Phase 2) | Next.js 15 + Tailwind v4 + ECharts | — |

---

## Hızlı Başlangıç

### Ön koşullar

- Python 3.10+
- Docker Desktop (Apple Silicon: Azure SQL Edge; Intel: SQL Server 2022)
- Anthropic API key
- Kaggle hesabı (API token için)

### Kurulum

```bash
git clone https://github.com/amacerdem/DataScience.git
cd DataScience

# 1. Python ortamı
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. .env dosyası
cp .env.example .env
# Düzenle: ANTHROPIC_API_KEY ve MSSQL_PASSWORD ayarla

# 3. Kaggle dataset indir
python scripts/00_download.py

# 4. SQL Server container başlat (Apple Silicon)
docker run -d --name mssql \
  -e ACCEPT_EULA=Y \
  -e MSSQL_SA_PASSWORD="$MSSQL_PASSWORD" \
  -p 1433:1433 \
  mcr.microsoft.com/azure-sql-edge:latest

# 5. Pipeline'ı baştan sona çalıştır (~5 dk)
python scripts/run_mssql.py
# Output: 24 tablo init, 1.55M satır load, T-SQL silver + gold

# 6. Türkçe doğal dil sorgu (Claude Opus 4.7)
python llm/nl2sql.py --interactive
```

### Örnek Sorgular

```bash
$ python llm/nl2sql.py "2017 yılında en çok ciroya sahip 5 kategori"

ÜRETİLEN SQL (claude-opus-4-7 • mssql):
  SELECT TOP (5)
      p.category_en AS [Kategori],
      ROUND(SUM(f.total_value), 2) AS [Ciro]
  FROM gold.FactOrderItems f
  INNER JOIN gold.DimProduct p ON f.product_key = p.product_key
  INNER JOIN gold.DimDate d ON f.purchase_date_key = d.date_key
  WHERE d.[year] = 2017
  GROUP BY p.category_en
  ORDER BY [Ciro] DESC

CEVAP:
               Kategori      Ciro
         bed_bath_table 590280.44
          health_beauty 550420.11
         sports_leisure 530730.03
          watches_gifts 530086.82
  computers_accessories 462761.27
```

Daha kompleks bir örnek:

```bash
$ python llm/nl2sql.py "Brezilya bölgelerine göre ortalama teslim süresi ve zamanında teslimat oranı, en kötüden başlayarak"

CEVAP:
         Bölge  Ortalama Teslim Süresi (Gün)  Zamanında Teslimat Oranı (%)
         North                         22.55                         90.13
     Northeast                         19.84                         85.86
  Central-West                         14.88                         92.11
         South                         13.94                         93.16
     Southeast                         10.62                         92.75
```

Üretilen T-SQL: 3 tablo join, `CAST AS FLOAT` (T-SQL integer division'a karşı), çift `ORDER BY`, Türkçe alias'lar `[köşeli]` parantez içinde.

---

## Proje Yapısı

```
DataScience/
├── README.md                          ← bu dosya
├── requirements.txt
├── .env.example
├── .gitignore
│
├── scripts/
│   ├── 00_download.py                 ← Kaggle bearer-token download
│   ├── 01_bronze.py                   ← CSV → Parquet (Polars)
│   ├── 02_load_mssql.py               ← Parquet → SQL Server bulk insert
│   ├── run_mssql.py                   ← Orkestratör (init+load+silver+gold)
│   ├── run_pipeline.py                ← DuckDB lokal alternatif (prototip)
│   └── run_sql.py                     ← Generic SQL runner
│
├── sql/
│   ├── 02_silver.sql                  ← DuckDB silver (lokal prototip)
│   ├── 03_gold.sql                    ← DuckDB gold
│   └── tsql/                          ← Microsoft T-SQL (production-ready)
│       ├── 01_init.sql                ← db + 3 schema + 24 tablo + 8 indeks
│       ├── 02_silver.sql              ← bronze → silver dönüşümleri
│       └── 03_gold.sql                ← silver → gold star schema
│
├── llm/
│   ├── schema.py                      ← T-SQL şema + Türkçe glossary
│   └── nl2sql.py                      ← Claude Opus 4.7 NL→T-SQL + executor
│
├── powerbi/                           ← Power BI Desktop için spec'ler
│   ├── MODEL.md                       ← semantic model (ilişkiler, format, hide)
│   ├── MEASURES.dax                   ← 25 DAX measure (5 display folder)
│   └── DASHBOARDS.md                  ← 3 dashboard layout (Executive/Ops/Customer)
│
├── docs/
│   ├── DEMO.md                        ← demo akışı + tasarım gerekçeleri
│   ├── PATRON-NOTU.md                 ← boss-facing rapor (TR)
│   └── superpowers/specs/             ← design specs
│       └── 2026-04-28-olist-demo-presentation-design.md
│
└── data/                              ← gitignored (regenerate)
    ├── raw/                           ← orijinal CSV'ler
    ├── bronze/                        ← Parquet (53 MB)
    ├── silver/                        ← Parquet (37 MB)
    └── gold/                          ← Parquet (25 MB)
```

---

## Test Edildi (28 Nisan 2026)

| Katman | Durum | Süre |
|--------|-------|------|
| Docker + Azure SQL Edge | ✓ ayakta | — |
| 1 db + 3 schema + 24 tablo + 8 indeks | ✓ | 0.7s |
| Parquet → bronze loader (1.55M satır) | ✓ | 5 dk |
| T-SQL silver transformları | ✓ | 2.5s |
| T-SQL gold star schema | ✓ | 9.4s |
| Claude Opus 4.7 NL→T-SQL (Türkçe) | ✓ 3 kompleks sorgu | 1-2 sn/sorgu |

DuckDB ↔ SQL Server cross-validation: tüm row count'lar birebir aynı.

---

## Yol Haritası

### ✓ Phase 1 — Veri Pipeline (Tamamlandı)

- Bronze + silver + gold layers (DuckDB prototip + T-SQL production)
- Microsoft SQL Server üstünde uçtan uca çalışan pipeline
- Star schema, indeksler, audit trail
- Türkçe NL→T-SQL (Claude Opus 4.7)
- Power BI semantic model + 25 DAX measure spec'i

### ⏳ Phase 2 — İnteraktif Web Demo (Devam ediyor)

- Next.js 15 + Tailwind v4 + Apache ECharts frontend
- Power BI estetiğinde 3 sekmeli dashboard (Executive/Operations/Customer)
- Türkçe AI side panel (skeleton-then-reveal pattern)
- "🔧 Behind the scenes" — her cevabın altında üretilen T-SQL + latency + token cost
- `/teknik` route — boss-only mimari + canlı pipeline metrics
- Vercel deploy + Cloudflare Tunnel (lokal SQL Server'a)

Spec: [`docs/superpowers/specs/2026-04-28-olist-demo-presentation-design.md`](docs/superpowers/specs/2026-04-28-olist-demo-presentation-design.md)

### 🎯 Phase 3 — Microsoft Fabric Migrasyonu (Şirket email'ini bekliyor)

- OneLake'e bronze Parquet upload (1 saat)
- T-SQL silver/gold scriptleri Fabric SQL Endpoint'te (kod aynı)
- Power BI semantic model — Direct Lake mode
- Power BI Copilot + custom Türkçe glossary RAG katmanı

---

## Tasarım Kararları (FAQ)

**Neden DuckDB ve SQL Server ikisi de var?**
DuckDB lokal prototip için (sıfır kurulum, hızlı iterasyon). SQL Server production muadili (boss + müşteri ortamı). Aynı SQL'in 95%'i ikisinde de çalışır; ufak syntax farkları (DATE_DIFF vs DATEDIFF, FORMAT yerine CONVERT) layer-specific dosyalarda.

**Neden Polars, pandas değil?**
Polars 5-10× daha hızlı + lazy evaluation + memory efficient. Demo bile 1M satırı 30s'de Parquet'e yazıyor, pandas'ta 3-4 dk sürerdi.

**Neden Claude Opus 4.7, GPT değil?**
Türkçe semantik anlama + adaptive thinking SQL üretiminde gözle görülür kalite farkı. NL→T-SQL kompleks sorularda (`SUM/COUNT(DISTINCT)` granularity ayrımı gibi) Opus 4.7 doğru çıktı veriyor, daha küçük modeller granularity hatası yapıyor.

**Neden Azure SQL Edge, full SQL Server 2022 değil?**
Apple Silicon (ARM64) macOS'ta SQL Server 2022 image yok. Edge T-SQL'in 95%+ yetkin, FORMAT() ve birkaç CLR fonksiyonu hariç. Migration sırasında full SQL Server'a tek satır değişiklikle çalışır.

---

## Lisans

MIT — `LICENSE` dosyası.

Olist dataset Kaggle'da CC BY-NC-SA 4.0 lisansıyla, sadece araştırma/eğitim amaçlı kullanılabilir.

---

## İletişim

**Amaç Erdem**
[amac.erdem.ae@gmail.com](mailto:amac.erdem.ae@gmail.com)

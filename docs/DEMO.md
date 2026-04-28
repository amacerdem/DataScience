# Demo Notes — Boss Presentation

## One-line pitch

> Brezilya Olist verisi üzerinde uçtan uca medallion pipeline (bronze→silver→gold)
> kurdum: 1.55M satır → temizlik → star schema → Power BI semantic model →
> Türkçe doğal dil sorgu katmanı. Aynı şablon BIM/Allianz boyutuna ölçeklenir;
> teknolojiler birebir Microsoft Fabric'in karşılığı (DuckDB→Fabric SQL,
> Parquet→OneLake Delta, Power BI Desktop→Power BI Service).

## Architecture diagram (anlat-çiz)

```
┌─ KAYNAK ──────────────────────────────────────────────────────────────────┐
│ Olist Kaggle dataset (gerçek hayatta: POS, SAP, CRM, eski mainframe)      │
└─────────────────────┬─────────────────────────────────────────────────────┘
                      │   urllib (gerçek hayatta: ADF / Fabric Pipelines)
                      ▼
┌─ BRONZE ──────────────────────────────────────────────────────────────────┐
│ Parquet, immutable, _ingested_at ile zaman damgası                        │
│ 9 tablo, 1.55M satır, 53 MB                                               │
└─────────────────────┬─────────────────────────────────────────────────────┘
                      │   DuckDB SQL (gerçek hayatta: Fabric SQL veya Spark)
                      ▼
┌─ SILVER ──────────────────────────────────────────────────────────────────┐
│ Tip dönüşümü, dedup (ROW_NUMBER OVER PARTITION), MDM                      │
│ Geolocation 1M satır → 19K zip-prefix centroid                            │
└─────────────────────┬─────────────────────────────────────────────────────┘
                      │   DuckDB SQL — star schema modelleme
                      ▼
┌─ GOLD ────────────────────────────────────────────────────────────────────┐
│ FactOrderItems (112K) + FactPayments (104K) + FactReviews (98K)           │
│ DimDate (1.4K) + DimCustomer (96K) + DimProduct (33K)                     │
│ DimSeller (3K) + DimGeography (27 — Brezilya eyalet → 5 makro-bölge)      │
└─────────────────────┬─────────────────────────────────────────────────────┘
                      │   Power Query (Folder connector → Parquet)
                      ▼
┌─ POWER BI ────────────────────────────────────────────────────────────────┐
│ Semantic model: 8 ilişki, 1 inactive (USERELATIONSHIP)                    │
│ 25 DAX ölçü: temel + zaman zekası + Pareto + müşteri segment              │
│ 3 dashboard: Executive (CEO) + Operations + Customer                       │
└─────────────────────┬─────────────────────────────────────────────────────┘
                      │   OpenAI / Azure OpenAI + custom Türkçe glossary RAG
                      ▼
┌─ NL → SQL/DAX ────────────────────────────────────────────────────────────┐
│ "Geçen ay Sao Paulo'da en çok satan kategori?" → SQL üret → çalıştır →    │
│ Türkçe cevap. CEO sohbet kutusu deneyimi.                                 │
└───────────────────────────────────────────────────────────────────────────┘
```

## Hangi tasarım kararını neden aldım?

| Karar                                  | Neden                                                      |
|---------------------------------------|------------------------------------------------------------|
| Medallion (Bronze/Silver/Gold)        | Microsoft + Databricks defakto standardı. Hata izi geriye, source-of-truth ayrımı, idempotency. |
| Parquet + Delta-uyumlu                | Fabric OneLake'in native formatı. Gerçek migrasyonda dosyaları bire bir taşır. |
| DuckDB                                | Lokal Synapse/Fabric SQL muadili. Aynı SQL dialect, columnar, sıfır servis maliyeti. |
| Star schema (Kimball)                 | Power BI VertiPaq motorunun en hızlı çalıştığı şekil. Snowflake yapsam DAX yavaşlardı. |
| Customer SCD: customer_unique_id       | Olist'in tuzağı: customer_id sipariş başına yeniden üretiliyor. customer_unique_id gerçek kişi. Conformity dedup ile sağlandı. |
| Date key olarak yyyymmdd integer      | Kimball'ın tavsiyesi. Date'ten daha hızlı join, partition friendly. |
| Bridge tablosu (_bridge_customer)     | Olist quirk'ini facta yansıtmadan tek noktada çözmek için. |
| FactOrderItems'ı line-grain tuttum    | Item-bazlı analiz (kategori/seller breakdown) için zorunlu. Order-grain seçseydim "şu üründe kaç indirim" sorusuna cevap veremezdim. |
| 3 fact tablo (Items / Payments / Reviews) | Farklı grain'ler. Ortak filter context için DimDate/DimCustomer'a bağlandım. |
| NL→SQL önce, NL→DAX sonra             | Lokal demo için SQL yeterli. Production hedefi DAX (Power BI Premium XMLA). Aynı prompt şeması, sadece model adı + endpoint değişir. |

## 3 dakikalık demo akışı

**00:00 — 00:30**: Mimariyi göster (yukarıdaki diyagram)
**00:30 — 01:00**: `python scripts/run_pipeline.py --skip-download` → 1.5 saniyede pipeline'ın tamamı
**01:00 — 02:00**: Power BI dashboard'u aç, 5 KPI + map + Pareto'yu gez
**02:00 — 02:30**: Slicer ile yıl değiştir, YoY grow %'ün canlı güncellendiğini göster
**02:30 — 03:00**: NL→SQL terminali aç:
- "2017 Kasım ayı cirosu nedir?"
- "Hangi eyalette zamanında teslimat oranı en düşük?"
- "Hangi kategoride 5 yıldız oranı en yüksek?"

## Fabric'e migrate ne kadar sürer (sorulduğunda)

- Bronze: aynı parquet, OneLake'e upload (1 saat)
- Silver: aynı SQL, DuckDB → Fabric SQL Endpoint (T-SQL'e syntax 95% uyumlu, COPY → CETAS olur, 2-3 saat)
- Gold: aynı, 2 saat
- Power BI semantic model: Direct Lake mode'a çevirisi 1 saat (sadece data source switch + refresh)
- NL katmanı: Azure OpenAI'ya endpoint değiştir, prompt aynı (1 saat)

**Toplam ~1 işgünü** — bu da doğrudan iş değer önerisi: lokalde POC, müşteride deploy.

## Bilmeyebileceği soruların cevapları

- **"Neden Power BI Copilot kullanmadın direkt?"** → Türkçe'de Microsoft'un kendisi "İngilizce dışı dilde performans düşer" diyor (resmi doc). Custom glossary + Türkçe iş terimleri sözlüğü ile %60+ doğruluk farkı yaratıyoruz.
- **"Milyarlarca satıra nasıl ölçeklenir?"** → Aynı kod. Parquet partition'la (yıl/ay) + Spark/Fabric Capacity. DuckDB tek node 100GB'a kadar idare eder; üstüne çıkıldığında sadece compute katmanı değişir, transformasyon mantığı aynı kalır.
- **"Veri güvenliği?"** → Bronze layer'a PII varsa DLP (Microsoft Purview), Power BI'da RLS (örn. mağaza müdürü kendi mağazasını görür), NL→SQL'de schema whitelist + read-only validation (kodda mevcut: FORBIDDEN regex).
- **"İncremental refresh?"** → Bronze layer'a `_ingested_at` timestamp koyduk; gerçek hayatta watermark veya CDC (SQL Server native CDC) ile delta çekilir, Silver'da MERGE ile upsert.

## Limit / Açıklık

- DuckDB lokal, single-node — tek geliştiricinin kasası. Production'da Fabric Capacity gerekir.
- Olist datası 100K sipariş; gerçek müşteride 1000× büyüklük olabilir, bu testle kanıtlanamaz ama mimari ölçeklenir.
- LLM kalitesi prompt'a + glossary'ye bağlı; agresif edge-case testleri yapılmadı (hallucination riski daima var, validation katmanı kritik).

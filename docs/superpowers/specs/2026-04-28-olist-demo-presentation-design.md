# Olist Demo Presentation — Design Spec

**Date**: 2026-04-28
**Author**: Amaç Erdem
**Status**: Draft → user review pending
**Goal**: Production-ready interactive web app that doubles as (1) customer-facing data analytics demo and (2) technical credentials demonstration for the boss who hired me at the data analytics company.

---

## 1. Goals and Non-Goals

### Goals

- Replace the static "deck + screenshots" presentation pattern with a **live, interactive web app** running on the actual SQL Server pipeline already built (`olist-pipeline/` repo).
- Use **Power BI's visual language** (white cards, `#118DFF` blue, Segoe UI, Fluent shadows) so enterprise customers see something they recognize.
- Layer modern web polish on top: smooth motion, real-time chart streaming, conversational AI in Turkish.
- Give the **boss a "behind the scenes" path** that exposes T-SQL, latency, token cost, joins used — proving the work and skill behind the surface.
- Be **showable to enterprise customers as-is** after the boss demo. No Olist-specific UX leakage; only the data is from Olist.

### Explicit Non-Goals

- Voice input (Whisper). Deferred to a v2 — Turkish ASR risk outweighs polish for this round.
- Mobile-first design. Desktop is primary; mobile responsive but not a flagship target.
- Multi-tenant authentication / user accounts. This is a single-tenant demo.
- Microsoft Fabric live deployment. Out of scope until boss provides a work/school email.
- Power BI .pbix export. Specs already exist in `powerbi/`; can be built on Day 1 of the job on a Windows machine. Not part of this app.

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  USER BROWSER  (Chrome / Safari / Firefox, desktop primary)        │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────┴─────────────────────────────────────────┐
│  Vercel — Next.js 15 (App Router) + React 19                       │
│    /            → Customer demo (dashboard + AI panel)             │
│    /teknik      → Boss-only technical view (architecture + metrics)│
│  Tailwind v4 + shadcn/ui + Apache ECharts + Framer Motion          │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ Cloudflare Tunnel (cloudflared)
┌──────────────────────────┴─────────────────────────────────────────┐
│  LOCAL MAC  (developer's laptop, where SQL Server runs)            │
│    FastAPI backend (port 8000)                                     │
│      POST /api/ask        — Türkçe sorgu → Claude → T-SQL → result │
│      GET  /api/dashboard  — pre-built KPI/chart payloads (cached)  │
│      GET  /api/health     — pipeline metrics (row counts, latency) │
│      GET  /api/sql/{id}   — for "behind the scenes" — original SQL │
│                                                                    │
│    Anthropic SDK (Claude Opus 4.7, adaptive thinking, effort high) │
│    pymssql + SQLAlchemy → SQL Server                               │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ port 1433
┌──────────────────────────┴─────────────────────────────────────────┐
│  Docker — Azure SQL Edge (Microsoft SQL Server)                    │
│    olist database — bronze (1.55M) + silver + gold star schema     │
└────────────────────────────────────────────────────────────────────┘
```

**Why backend stays local:** Power BI / SQL Server live on the developer's laptop is the most authentic demo to a customer who runs Microsoft on-premise or in their own Azure tenant. Cloudflare Tunnel exposes the local FastAPI to Vercel without opening ports.

### Component boundaries

- **Frontend has no business logic.** It only renders charts from JSON payloads served by the backend. All Türkçe → SQL → result happens server-side.
- **Backend has no presentation logic.** It returns raw data + metadata (chart type hint, axis labels, formatting hints) — frontend decides how to render.
- **Cached vs live answers** are differentiated in the API response (`source: "cache" | "llm"`), so the UI can show appropriate hints.

---

## 3. Frontend Routes

### `/` — Customer Demo (default)

The page the customer sees. Tabbed dashboard + AI conversation side panel.

**Top navigation bar:**
- Logo + brand mark (left)
- Tab selector: 📊 Executive / 🚚 Operations / 👤 Customer (center)
- Filters: Year ▾ + Region ▾ (right)
- "💬 Sor" CTA (right edge) — collapses/expands the AI panel

**Main grid (left/wider column, ~70% width):**
- KPI row: 5 cards (current tab's primary metrics)
- Chart grid: 3-4 charts arranged in 2/3 + 1/3 columns
- Each card has subtle "↗" hover → click for full-screen detail (out of scope for v1; placeholder click handler)

**AI side panel (right, ~30% width, collapsible):**
- "AI" badge + "Türkçe Sor" header
- "Önerilen Sorular" — 3 chips (pre-built questions, instant cached responses)
- Conversation thread (user/AI bubbles, scrolls)
- Input box with send button (auto-focus, Enter to send, Shift+Enter newline)

**Behavior on AI ask:**
1. User sends message (chip click OR typed)
2. Skeleton chart appears in conversation thread (200ms after send)
3. Claude streams text — typewriter effect in the AI bubble
4. SQL executes server-side; when result arrives, skeleton fades into ECharts visual (1-2s animation)
5. Below the chart: small "🔧 Bu nasıl üretildi?" link → expands to show T-SQL + latency + token cost
6. "📥 İndir" link → CSV / Excel / PDF download (Phase 5)

### `/teknik` — Boss View

Single-page technical credentials view. Same layout primitives, different content.

**Sections (vertical scroll):**

1. **Hero**: title "Olist Pipeline — Mimari ve Çalışan Sistemler" + run metrics (live counter)
   - Total rows: 1,550,922 (live from `/api/health`)
   - SQL Server status: ● online (Azure SQL Edge ARM64)
   - Last query latency: 387 ms
   - Pipeline rebuild time: 5 dk 17 sn

2. **Architecture diagram** (animated SVG): Olist CSV → Polars → Bronze Parquet → SQL Server → T-SQL → Gold star schema → Claude Opus 4.7 → Frontend.

3. **Layer-by-layer breakdown** (collapsible cards):
   - Bronze: row counts per table, ingest timestamps, source files
   - Silver: dedup ratios, type cast count, geolocation rollup (1M → 19K)
   - Gold: 8 tables, indexes, surrogate keys, FK relationships
   - LLM: model, system prompt size, glossary terms, last 10 queries with timing
   - Power BI: model spec link, 25 DAX measures (formula display), 3 dashboard layouts

4. **Live query log** (last 20 questions asked with full T-SQL + latency + cost):
   - Sortable table
   - Click a row → expands to show full SQL + result preview

5. **Microsoft Fabric migration plan**: timeline showing what changes when work email arrives.

---

## 4. Visual Design System

### Color palette (Power BI default theme)

| Role | Hex | Use |
|------|-----|-----|
| Primary | `#118DFF` | KPIs, active states, primary buttons, line/bar default |
| Accent | `#FF8C00` | Highlights (Black Friday, anomalies) |
| Success | `#107C10` | Positive trends, ✓ states |
| Warning | `#FDB900` | Warnings, mid-tier states |
| Danger | `#A4262C` | Negative trends, errors |
| Premium | `#5C2D91` | Repeat customers, special segments |
| BG | `#FAFAFA` | Page background |
| Card | `#FFFFFF` | Card surfaces |
| Border | `#E8E8E8` | Card borders, dividers |
| Text strong | `#252525` | Headers, KPI numbers |
| Text medium | `#595959` | Labels, secondary info |
| Text muted | `#8A8A8A` | Tertiary, disabled |

### Typography

- **Font**: Segoe UI Variable (Windows), `-apple-system, BlinkMacSystemFont, system-ui` fallback
- KPI number: 28px / 700
- Section header: 14px / 600
- KPI label: 11px / 600 / uppercase / 0.06em letter-spacing
- Body: 13px / 400 / `#252525`
- Caption: 11px / 400 / `#595959`

### Card style

- White background, 1px `#E8E8E8` border, 8px radius
- Shadow: `0 1px 2px rgba(0,0,0,0.04)`
- Padding: 16px (KPI) / 20px (chart)
- Hover: shadow `0 2px 8px rgba(0,0,0,0.08)`, border `#D0D0D0`

### Motion

- Page transitions: 200ms ease-out (Framer Motion)
- KPI on mount: stagger 60ms, opacity 0→1, translateY 8px → 0
- Chart skeleton → real chart: cross-fade 400ms with chart-specific entrance animation (ECharts native)
- Typewriter: 12ms per character (Anthropic streaming default cadence)
- Tab change: cross-fade 150ms
- "Behind the scenes" expand: 250ms accordion

### Iconography

- Lucide icons (lightweight, consistent stroke)
- Emoji for tab labels and chips (warm, approachable for non-technical users)
- No custom illustrations in v1

---

## 5. Pre-built Dashboards

### Executive Tab — "GMV Cockpit"

**KPIs (row of 5):**
- GMV (BRL) with YoY % delta
- Sipariş Sayısı with YoY %
- AOV (Average Order Value)
- Aktif Müşteri with YoY %
- 5★ Oranı with delta

**Charts (2/3 + 1/3 grid below KPIs):**
- Aylık GMV trend (bar chart, 2017 with Black Friday spike highlighted in `#FF8C00`)
- Top 5 Kategori (horizontal bar)

**Charts (1/3 + 2/3 grid below):**
- Brezilya filled map (state-level GMV, choropleth in `#118DFF` saturation)
- Pareto: Cumulative GMV % (combo bar+line)

### Operations Tab — "Delivery & Fulfillment"

**KPIs (row of 4):**
- Zamanında Teslimat %
- Ortalama Teslim Günü
- İptal Oranı
- Teslim Edilen Sipariş

**Charts:**
- Delivery days histogram (bins: 0-5, 5-10, 10-15, 15-30, 30+)
- On-time % by region (Brezilya filled map)
- Avg delivery days trend (12-month line chart)
- Top 10 slowest sellers (horizontal bar table)

### Customer Tab — "Acquisition & Retention"

**KPIs (row of 4):**
- Aktif Müşteri
- Yeni Müşteri
- Repeat Customer %
- Avg Review Score (with 5-star icons)

**Charts:**
- New vs Returning trend (stacked bar by month)
- Customer count by state (Brezilya filled map)
- Review score distribution (donut, 1-5 stars)
- Top 10 categories by avg review score (table)

---

## 6. AI Conversation Behavior

### Query lifecycle

```
USER ACTION (chip OR typed query)
  │
  ├─ chip → POST /api/ask {q, mode: "cache"}
  │         backend reads cached response (50-100ms total)
  │         response includes pre-computed chart spec
  │
  └─ typed → POST /api/ask/stream  (Server-Sent Events)
            backend stream events in order:
              1. event: skeleton          (immediately)
              2. event: text_delta * N    (Claude streaming, ~12ms cadence)
              3. event: sql               (after Claude emits full SQL)
              4. event: result            (after SQL Server returns rows + chart_spec)
              5. event: done              (metadata: latency, tokens, cost)

FRONTEND RENDERING
  │
  ├─ T+0ms:    user message bubble appears
  ├─ T+200ms:  AI bubble + skeleton placeholder (chart-shaped gray box)
  ├─ T+200ms+: Anthropic stream begins, typewriter text in AI bubble
  ├─ T+~1500ms: SQL result arrives, skeleton fades into ECharts visual
  ├─ T+~3000ms: text stream completes, "🔧 Bu nasıl üretildi?" link appears
  └─ User can click link → SQL + latency + tokens in slide-down panel
```

### Pre-built question chips (3 per tab)

**Executive tab:**
1. 📈 "2017 Black Friday cirosunu göster"
2. 🏆 "En çok satan 10 kategori nedir?"
3. 🇧🇷 "Bölgelere göre ciro karşılaştırması"

**Operations tab:**
1. 🚚 "Brezilya bölgelerine göre teslim performansı"
2. ⏱ "En yavaş teslimat yapan 10 satıcı"
3. ❌ "Hangi eyalette en çok sipariş iptali var?"

**Customer tab:**
1. 🔁 "Repeat customer oranı bölge bazında"
2. ⭐ "Hangi kategoride 5 yıldız oranı en yüksek?"
3. 💳 "Kredi kartı vs boleto kullanan müşteri farkı"

### Chart type inference

LLM is asked to suggest a chart type alongside the SQL. Mapping:
- Single number → KPI card
- Categorical breakdown (≤8 categories) → horizontal bar
- Categorical breakdown (>8) → table or grouped bar
- Time series (date column) → line or area
- Geographic (state/region) → filled map
- Two numerics → scatter
- Cumulative → Pareto combo

Frontend has a `<ChartRenderer />` component that switches on `chart_spec.type`.

### "Bu nasıl üretildi?" panel

Expandable inline section under each AI response:
- Generated T-SQL (syntax highlighted, copy button)
- Tables joined (gold.FactOrderItems, gold.DimDate, ...)
- Indexes used (from SQL Server query plan, optional v2)
- Latency breakdown: LLM 1.2s + SQL 0.3s + render 0.1s = 1.6s
- Token cost: input 1,847 + output 124 = $0.0096 (Opus 4.7 pricing)
- Model: claude-opus-4-7 + adaptive thinking + effort high

---

## 7. Backend API

Two distinct endpoints — cached chip path is synchronous JSON; live LLM path is Server-Sent Events stream.

### `POST /api/ask` — Cached / Chip Path (sync JSON)

Used when the user clicks a pre-built chip with `mode: "cache"`. Returns a single JSON payload, 50–100ms total.

Request:
```json
{
  "question": "2017 yılında en çok ciroya sahip 5 kategori",
  "mode": "cache"
}
```

Response:
```json
{
  "id": "q_abc123",
  "source": "cache",
  "sql": "SELECT TOP (5) p.category_en AS [Kategori], ...",
  "result": {
    "columns": ["Kategori", "Ciro (R$)"],
    "rows": [["bed_bath_table", 590280.44], ...]
  },
  "chart_spec": {
    "type": "horizontal_bar",
    "x": "Ciro (R$)",
    "y": "Kategori",
    "color": "#118DFF",
    "format": "BRL"
  },
  "explanation": "2017 yılında en çok ciro Bed & Bath kategorisinde, ardından Health & Beauty geliyor.",
  "metadata": {
    "model": "claude-opus-4-7",
    "tokens_in": 1847,
    "tokens_out": 124,
    "latency_ms": {"llm": 1247, "sql": 312, "total": 1559},
    "tables_joined": ["gold.FactOrderItems", "gold.DimProduct", "gold.DimDate"],
    "cost_usd": 0.0096
  }
}
```

### `POST /api/ask/stream` — Live LLM Path (Server-Sent Events)

Used when the user types a custom question. Streams SSE events so the frontend can render the skeleton-then-reveal pattern. Events fire in this order:

```
event: skeleton
data: {"id":"q_xyz789","chart_spec_hint":{"type":"unknown"}}

event: text_delta
data: {"text":"2017"}

event: text_delta
data: {"text":" yılında"}

... (Anthropic stream continues, ~12ms cadence)

event: sql
data: {"sql":"SELECT TOP (5) p.category_en ..."}

event: result
data: {"columns":["Kategori","Ciro"],"rows":[...],"chart_spec":{"type":"horizontal_bar",...}}

event: done
data: {"metadata":{"model":"claude-opus-4-7","tokens_in":1847,"tokens_out":124,"latency_ms":{"llm":1247,"sql":312,"total":1559},"tables_joined":[...],"cost_usd":0.0096}}
```

Frontend uses `EventSource` (or `fetch` + `ReadableStream` for POST) to consume these events and update the UI incrementally.

### `GET /api/dashboard?tab=executive`

Returns the pre-built KPI + chart payload for the named tab. Cached in memory (10 min TTL).

### `GET /api/health`

Live pipeline metrics for the `/teknik` page header counter:
```json
{
  "sql_server": {"status": "online", "version": "Azure SQL Edge 15.0.2000"},
  "rows": {"bronze": 1550922, "silver": 1448938, "gold": 348195},
  "last_query": {"id": "q_abc123", "latency_ms": 387, "ts": "..."},
  "uptime_minutes": 142
}
```

### `GET /api/queries`

Last 20 queries with full metadata, for the `/teknik` query log section.

---

## 8. Implementation Phases

### Phase 1 — Backend (FastAPI on top of existing nl2sql.py)
- Wrap existing `llm/nl2sql.py` logic in FastAPI endpoints
- Add chart-type inference to Claude prompt (return JSON with sql + chart_spec)
- Build `/api/dashboard` with cached pre-computed KPI + chart payloads
- Build `/api/health` and `/api/queries`
- CORS for Vercel frontend
- Cloudflare Tunnel setup script

### Phase 2 — Frontend scaffold
- `npx create-next-app@latest olist-app --typescript --app --tailwind`
- shadcn/ui init + install card, button, tabs, sheet, badge, skeleton
- ECharts via `echarts-for-react`
- Brazil GeoJSON map (one-time, public domain)
- Tailwind theme override → Power BI palette + Segoe UI

### Phase 3 — Customer demo (`/`)
- Tabbed dashboard with 3 tabs (Executive / Operations / Customer)
- KPI cards from `/api/dashboard`
- Chart components (`<KPICard />`, `<ChartCard />`, `<ChartRenderer />`)
- AI side panel: chips + conversation + skeleton-then-reveal
- Streaming integration via Anthropic SDK on backend, EventSource on frontend
- "Bu nasıl üretildi?" expandable

### Phase 4 — Boss view (`/teknik`)
- Hero with live counter (polls `/api/health` every 5s)
- Animated SVG architecture diagram
- Layer-by-layer collapsible cards
- Live query log table with expansion
- Migration plan timeline

### Phase 5 — Polish
- Motion: Framer Motion stagger + page transitions
- Skeleton states for all loading
- Error boundaries (graceful fallback if backend offline)
- "📥 İndir" CSV/Excel/PDF export
- Keyboard shortcuts (`/` to focus AI input, `g` then `e/o/c` to switch tabs)

### Phase 6 — Deploy
- Vercel deploy with custom domain (`olist.show` or similar)
- Cloudflare Tunnel running on Mac → Vercel calls local FastAPI
- README with "demo running" instructions for boss

---

## 9. File Layout (target)

```
olist-pipeline/
├── (existing — backend/SQL/LLM)
├── api/                          ← new: FastAPI app
│   ├── main.py
│   ├── ask.py                    ← Claude integration + chart spec
│   ├── dashboard.py              ← pre-built tab payloads
│   ├── health.py
│   └── chart_inference.py        ← LLM picks chart type
├── app/                          ← new: Next.js frontend
│   ├── (root)/
│   │   ├── page.tsx              ← customer demo
│   │   ├── components/
│   │   │   ├── DashboardTabs.tsx
│   │   │   ├── KPICard.tsx
│   │   │   ├── ChartCard.tsx
│   │   │   ├── ChartRenderer.tsx
│   │   │   ├── AIPanel.tsx
│   │   │   ├── ChatBubble.tsx
│   │   │   └── BehindScenes.tsx
│   │   └── lib/
│   │       ├── api.ts
│   │       └── echarts-theme.ts
│   ├── teknik/
│   │   ├── page.tsx
│   │   └── components/
│   │       ├── ArchitectureDiagram.tsx
│   │       ├── LayerCard.tsx
│   │       ├── LiveCounter.tsx
│   │       └── QueryLog.tsx
│   └── globals.css               ← Power BI theme
├── infrastructure/
│   ├── tunnel.sh                 ← Cloudflare Tunnel start script
│   └── start-all.sh              ← docker + api + tunnel + frontend
└── docs/superpowers/specs/
    └── 2026-04-28-olist-demo-presentation-design.md  ← THIS FILE
```

---

## 10. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| LLM returns broken SQL | Existing regex validator (`FORBIDDEN`); graceful error in chat ("Sorun var, tekrar sor") |
| Chart type misinference | Fall back to table view; user can switch chart type from a small icon row |
| SQL Server offline during demo | `/api/health` shows red status; all chips fall back to cached responses |
| Cloudflare Tunnel drops | Vercel uses `localhost` fallback when accessed from same Mac; "Local mode" banner appears |
| Claude API rate limit | Cache by question hash for 1h; identical questions return cached response |
| Token cost runaway | `max_tokens: 2048` cap; cost displayed per query for boss transparency |
| Power BI map of Brazil missing | Use public-domain GeoJSON (IBGE 2022, included in repo) |

---

## 11. Success Criteria

The demo passes when:

1. Boss opens `/` from his laptop → sees Executive dashboard within 3 seconds (after first warmup; cold-start tunnel may add ~1s).
2. Boss clicks "📈 Black Friday" chip → chart appears within 200ms (cached).
3. Boss types a custom Türkçe question → answer + chart appears within 3 seconds.
4. Boss clicks "🔧 Bu nasıl üretildi?" → sees actual T-SQL that ran on SQL Server.
5. Boss navigates to `/teknik` → sees live row counts, architecture, last 20 queries.
6. Demo runs end-to-end without any hard refresh or error toast for the planned 5-minute walkthrough.

If all 6 work, the demo is shippable to enterprise customers (BIM, Allianz, ŞOK class) with only branding swap.

---

## 12. Out of Scope (explicit)

- User accounts / authentication
- Persistent chat history (per-session only)
- Multi-language UI (Türkçe only — boss demo language; v2 EN toggle is trivial later)
- Real-time data refresh (data is the static Olist snapshot)
- Power BI .pbix file generation
- Microsoft Fabric live deployment
- Voice input
- Mobile-first (responsive but not optimized)
- A/B test infrastructure
- SSO / RLS / row-level security

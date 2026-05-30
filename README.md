# AMFI Mutual Fund NAV API

A **FastAPI** backend that fetches live Net Asset Value (NAV) data for all Indian mutual funds from [AMFI India](https://portal.amfiindia.com) and exposes clean REST endpoints with JSON responses.

Built with **[uv](https://github.com/astral-sh/uv)** — the fast Python package manager.

---

## Features

- Lookup by **Scheme Code** or **ISIN**
- **Bulk lookup** — up to 50 scheme codes or ISINs in one request
- **Search & filter** by scheme name, fund house, category, and scheme type with pagination
- **Meta endpoint** — discover all valid fund houses, categories, and scheme types
- **SQLite-backed persistent cache** — survives process restarts; re-fetches from AMFI only when stale
- **Per-IP rate limiting** (via slowapi)

---

## Project Structure

```
amfi-api/
├── main.py            # FastAPI app and route definitions
├── models.py          # Pydantic request/response models
├── data_fetcher.py    # AMFI data downloader, parser, and SQLite cache
├── pyproject.toml     # Project metadata and dependencies (uv)
├── uv.lock            # Lockfile (commit this for reproducible installs)
├── amfi_cache.db      # SQLite cache (auto-created, do not commit)
└── README.md
```

---

## Getting Started

### 1. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Run the development server

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Run in production

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Configuration

All configuration is via environment variables.

| Variable    | Default              | Description                                                   |
|-------------|----------------------|---------------------------------------------------------------|
| `DB_PATH`   | `./amfi_cache.db`    | Path to the SQLite cache database.                            |

Cache TTL and the AMFI source URL are constants in `data_fetcher.py`.

| Setting         | File              | Default |
|-----------------|-------------------|---------|
| Cache TTL       | `data_fetcher.py` → `CACHE_TTL` | 3600 seconds (1 hour) |
| AMFI source URL | `data_fetcher.py` → `AMFI_URL`  | `https://portal.amfiindia.com/spages/NAVAll.txt` |

---

## API Endpoints

### Rate Limits (per IP)

| Endpoint group         | Limit       |
|------------------------|-------------|
| `/fund/scheme`, `/fund/isin` | 100 / minute |
| `/fund/search`         | 60 / minute |
| `/fund/bulk/*`, `/meta`| 30 / minute |

Exceeding a limit returns **HTTP 429**.

### `GET /fund/scheme/{scheme_code}`

Fetch a single fund by its AMFI Scheme Code.

```bash
curl http://localhost:8000/fund/scheme/119551
```

**Response:**
```json
{
  "data": {
    "scheme_code": "119551",
    "isin_div_payout_growth": "INF209KA12Z1",
    "isin_div_reinvestment": "INF209KA13Z9",
    "scheme_name": "Aditya Birla Sun Life Banking & PSU Debt Fund - DIRECT - IDCW",
    "nav": 104.5269,
    "nav_date": "26-May-2026",
    "fund_house": "Aditya Birla Sun Life Mutual Fund",
    "category": "Debt Scheme - Banking and PSU Fund",
    "scheme_type": "Open Ended"
  },
  "source": "amfiindia.com",
  "cached": true
}
```

---

### `GET /fund/isin/{isin}`

Fetch a single fund by its ISIN (Growth, Dividend Payout, or Dividend Reinvestment).

```bash
curl http://localhost:8000/fund/isin/INF209KA12Z1
```

---

### `GET /fund/search`

Search and filter funds with pagination. All parameters are optional and can be combined freely.

```bash
curl "http://localhost:8000/fund/search?fund_house=axis&scheme_type=Open+Ended&limit=10&page=2"
```

| Query Param   | Type    | Default | Description |
|---------------|---------|---------|-------------|
| `q`           | string  | —       | Partial scheme name (min 3 chars, case-insensitive) |
| `fund_house`  | string  | —       | Partial AMC / fund house name filter |
| `category`    | string  | —       | Partial category filter |
| `scheme_type` | string  | —       | `Open Ended`, `Close Ended`, or `Interval` |
| `page`        | integer | `1`     | Page number (1-indexed) |
| `limit`       | integer | `20`    | Results per page (1–100) |

**Response includes pagination fields:**
```json
{
  "query": null,
  "fund_house": "axis",
  "category": null,
  "scheme_type": "Open Ended",
  "page": 2,
  "limit": 10,
  "total_results": 397,
  "total_pages": 40,
  "data": [ ... ],
  "source": "amfiindia.com",
  "cached": true
}
```

Use `/meta` to discover all valid filter values.

---

### `GET /fund/bulk/scheme?codes={code1,code2,...}`

Fetch up to **50 funds** by scheme code in a single request.

```bash
curl "http://localhost:8000/fund/bulk/scheme?codes=119551,120503,149205"
```

**Response:**
```json
{
  "found": [ ... ],
  "not_found": ["999999"],
  "total_requested": 3,
  "total_found": 2,
  "source": "amfiindia.com",
  "cached": true
}
```

---

### `GET /fund/bulk/isin?isins={isin1,isin2,...}`

Fetch up to **50 funds** by ISIN in a single request.

```bash
curl "http://localhost:8000/fund/bulk/isin?isins=INF209KA12Z1,INF209KA13Z9"
```

Response format is the same as bulk scheme lookup.

---

### `GET /meta`

Returns all distinct fund houses, categories, and scheme types present in the current dataset. Use these as inputs to `/fund/search`.

```bash
curl http://localhost:8000/meta
```

```json
{
  "fund_houses": ["Aditya Birla Sun Life Mutual Fund", "Axis Mutual Fund", ...],
  "categories": ["Debt Scheme - Banking and PSU Fund", "Equity Scheme - Large Cap Fund", ...],
  "scheme_types": ["Close Ended", "Interval", "Open Ended"],
  "total_records": 14364
}
```

---

### `GET /cache/status`

Check the current state of the in-memory and SQLite cache.

```json
{
  "cached": true,
  "total_records": 14364,
  "last_fetched_at": "2026-05-27T06:17:06Z",
  "cache_age_seconds": 42.3,
  "cache_ttl_seconds": 3600,
  "persistence": "SQLite",
  "db_path": "./amfi_cache.db",
  "source": "https://portal.amfiindia.com/spages/NAVAll.txt"
}
```

---

### `GET /cache/refresh`

Force a fresh fetch of AMFI NAV data from source, bypassing the TTL.

---

## Interactive Docs

Once the server is running, open:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Data Source

All NAV data is sourced directly from **AMFI India**:
`https://portal.amfiindia.com/spages/NAVAll.txt`

Data is updated by AMFI every business day by ~9 PM IST.

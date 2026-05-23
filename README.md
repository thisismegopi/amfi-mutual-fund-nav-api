# AMFI Mutual Fund NAV API

A **FastAPI** backend that fetches live Net Asset Value (NAV) data for all Indian mutual funds from [AMFI India](https://portal.amfiindia.com) and exposes clean REST endpoints with JSON responses.

Built with **[uv](https://github.com/astral-sh/uv)** — the fast Python package manager.

---

## Project Structure

```
amfi-api/
├── main.py            # FastAPI app and route definitions
├── models.py          # Pydantic request/response models
├── data_fetcher.py    # AMFI data downloader, parser, and cache
├── pyproject.toml     # Project metadata and dependencies (uv)
├── uv.lock            # Lockfile (commit this for reproducible installs)
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

## API Endpoints

### `GET /fund/scheme/{scheme_code}`
Fetch a fund by its AMFI Scheme Code.

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
    "nav": 104.3467,
    "nav_date": "22-May-2026",
    "fund_house": "Aditya Birla Sun Life Mutual Fund",
    "category": "Debt Scheme - Banking and PSU Fund"
  },
  "source": "amfiindia.com",
  "cached": true
}
```

---

### `GET /fund/isin/{isin}`
Fetch a fund by ISIN (Growth, Dividend Payout, or Dividend Reinvestment).

```bash
curl http://localhost:8000/fund/isin/INF209KA12Z1
```

---

### `GET /fund/search?q={name}&limit={n}`
Search funds by partial scheme name (case-insensitive).

```bash
curl "http://localhost:8000/fund/search?q=axis+bluechip&limit=5"
```

| Query Param | Type    | Default | Description |
|-------------|---------|---------|-------------|
| `q`         | string  | —       | Partial or full scheme name (min 3 chars) |
| `limit`     | integer | 20      | Max results returned (1–100) |

---

### `GET /cache/status`
Check the current state of the in-memory cache.

---

### `GET /cache/refresh`
Force a fresh fetch of AMFI NAV data, bypassing the 1-hour TTL.

---

## Interactive Docs

Once the server is running, open:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Configuration

| Setting         | File              | Default |
|-----------------|-------------------|---------|
| Cache TTL       | `data_fetcher.py` → `CACHE_TTL` | 3600 seconds (1 hour) |
| AMFI source URL | `data_fetcher.py` → `AMFI_URL`  | `https://portal.amfiindia.com/spages/NAVAll.txt` |

---

## Data Source

All NAV data is sourced directly from **AMFI India**:
`https://portal.amfiindia.com/spages/NAVAll.txt`

Data is updated by AMFI every business day by ~9 PM IST.

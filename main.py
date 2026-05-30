"""
AMFI Mutual Fund NAV API
Fetches live NAV data from AMFI India and exposes lookup, search, filter,
bulk, and meta endpoints with per-IP rate limiting.
"""

import math
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from data_fetcher import AMFIDataFetcher
from models import BulkLookupResponse, SearchResponse, SingleFundResponse

# ---------------------------------------------------------------------------
# Rate limiter (per IP)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(
    title="AMFI Mutual Fund NAV API",
    description=(
        "Fetch live Net Asset Value (NAV) data for Indian mutual funds from AMFI India. "
        "Supports lookup by Scheme Code / ISIN, bulk lookups, filtered search with pagination, "
        "and a meta endpoint listing all fund houses, categories, and scheme types."
    ),
    version="2.0.0",
    contact={"name": "AMFI NAV API", "url": "https://portal.amfiindia.com"},
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

fetcher = AMFIDataFetcher()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "AMFI Mutual Fund NAV API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "by_scheme_code": "/fund/scheme/{scheme_code}",
            "by_isin": "/fund/isin/{isin}",
            "search": "/fund/search",
            "bulk_by_codes": "/fund/bulk/scheme?codes=xxx,yyy",
            "bulk_by_isins": "/fund/bulk/isin?isins=INF...,INF...",
            "meta": "/meta",
            "cache_status": "/cache/status",
            "refresh_cache": "/cache/refresh",
        },
    }


@app.get(
    "/fund/scheme/{scheme_code}",
    response_model=SingleFundResponse,
    summary="Get fund by Scheme Code",
    tags=["Fund Lookup"],
)
@limiter.limit("100/minute")
async def get_by_scheme_code(request: Request, scheme_code: str):
    """
    Fetch a single mutual fund record using its **AMFI Scheme Code**.

    Example: `/fund/scheme/119551`
    """
    await fetcher.ensure_data_loaded()
    record = fetcher.get_by_scheme_code(scheme_code.strip())
    if not record:
        raise HTTPException(
            status_code=404, detail=f"No fund found with Scheme Code '{scheme_code}'."
        )
    return SingleFundResponse(
        data=record, source="amfiindia.com", cached=fetcher.is_cached()
    )


@app.get(
    "/fund/isin/{isin}",
    response_model=SingleFundResponse,
    summary="Get fund by ISIN",
    tags=["Fund Lookup"],
)
@limiter.limit("100/minute")
async def get_by_isin(request: Request, isin: str):
    """
    Fetch a single mutual fund record using its **ISIN** (Growth, Dividend Payout,
    or Dividend Reinvestment ISIN).

    Example: `/fund/isin/INF209KA12Z1`
    """
    await fetcher.ensure_data_loaded()
    record = fetcher.get_by_isin(isin.strip().upper())
    if not record:
        raise HTTPException(
            status_code=404, detail=f"No fund found with ISIN '{isin}'."
        )
    return SingleFundResponse(
        data=record, source="amfiindia.com", cached=fetcher.is_cached()
    )


@app.get(
    "/fund/search",
    response_model=SearchResponse,
    summary="Search and filter funds",
    tags=["Fund Lookup"],
)
@limiter.limit("60/minute")
async def search_funds(
    request: Request,
    q: Optional[str] = Query(
        None, min_length=3, description="Partial scheme name (min 3 chars)"
    ),
    fund_house: Optional[str] = Query(
        None, description="Partial AMC / fund house name filter"
    ),
    category: Optional[str] = Query(None, description="Partial category filter"),
    scheme_type: Optional[str] = Query(
        None,
        description="Scheme type filter: 'Open Ended', 'Close Ended', or 'Interval'",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page (max 100)"),
):
    """
    Search and filter funds with optional pagination. All parameters are optional
    and can be combined freely.

    - **q** — partial scheme name (case-insensitive)
    - **fund_house** — partial AMC name (e.g. `axis`, `sbi`)
    - **category** — partial category (e.g. `large cap`, `debt`)
    - **scheme_type** — `Open Ended`, `Close Ended`, or `Interval`
    - **page** / **limit** — pagination controls

    Use `/meta` to discover all valid fund houses, categories, and scheme types.
    """
    await fetcher.ensure_data_loaded()
    results, total = fetcher.search(
        query=q,
        fund_house=fund_house,
        category=category,
        scheme_type=scheme_type,
        page=page,
        limit=limit,
    )
    return SearchResponse(
        query=q,
        fund_house=fund_house,
        category=category,
        scheme_type=scheme_type,
        page=page,
        limit=limit,
        total_results=total,
        total_pages=math.ceil(total / limit) if total else 0,
        data=results,
        source="amfiindia.com",
        cached=fetcher.is_cached(),
    )


@app.get(
    "/fund/bulk/scheme",
    response_model=BulkLookupResponse,
    summary="Bulk lookup by Scheme Codes",
    tags=["Bulk Lookup"],
)
@limiter.limit("30/minute")
async def bulk_by_scheme_codes(
    request: Request,
    codes: str = Query(..., description="Comma-separated AMFI scheme codes (max 50)"),
):
    """
    Fetch up to **50 funds** by their AMFI Scheme Codes in a single request.

    Example: `/fund/bulk/scheme?codes=119551,120503,149205`

    Returns two lists: `found` (matched records) and `not_found` (unrecognised codes).
    """
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:50]
    if not code_list:
        raise HTTPException(status_code=400, detail="Provide at least one scheme code.")
    await fetcher.ensure_data_loaded()
    found, not_found = fetcher.get_bulk_by_scheme_codes(code_list)
    return BulkLookupResponse(
        found=found,
        not_found=not_found,
        total_requested=len(code_list),
        total_found=len(found),
        source="amfiindia.com",
        cached=fetcher.is_cached(),
    )


@app.get(
    "/fund/bulk/isin",
    response_model=BulkLookupResponse,
    summary="Bulk lookup by ISINs",
    tags=["Bulk Lookup"],
)
@limiter.limit("30/minute")
async def bulk_by_isins(
    request: Request,
    isins: str = Query(..., description="Comma-separated ISINs (max 50)"),
):
    """
    Fetch up to **50 funds** by their ISINs in a single request.

    Example: `/fund/bulk/isin?isins=INF209KA12Z1,INF209KA13Z9`

    Returns two lists: `found` (matched records) and `not_found` (unrecognised ISINs).
    """
    isin_list = [i.strip() for i in isins.split(",") if i.strip()][:50]
    if not isin_list:
        raise HTTPException(status_code=400, detail="Provide at least one ISIN.")
    await fetcher.ensure_data_loaded()
    found, not_found = fetcher.get_bulk_by_isins(isin_list)
    return BulkLookupResponse(
        found=found,
        not_found=not_found,
        total_requested=len(isin_list),
        total_found=len(found),
        source="amfiindia.com",
        cached=fetcher.is_cached(),
    )


@app.get(
    "/meta",
    summary="List all filter values",
    tags=["Meta"],
)
@limiter.limit("30/minute")
async def meta(request: Request):
    """
    Returns all distinct **fund houses**, **categories**, and **scheme types**
    present in the current dataset. Use these values as inputs to `/fund/search`.
    """
    await fetcher.ensure_data_loaded()
    return {
        "fund_houses": fetcher.get_all_fund_houses(),
        "categories": fetcher.get_all_categories(),
        "scheme_types": fetcher.get_all_scheme_types(),
        "total_records": fetcher.total_records(),
    }


@app.get(
    "/cache/status",
    summary="Check cache status",
    tags=["Cache"],
)
async def cache_status():
    """Returns information about the in-memory and SQLite cache of AMFI NAV data."""
    return {
        "cached": fetcher.is_cached(),
        "total_records": fetcher.total_records(),
        "last_fetched_at": fetcher.last_fetched_at(),
        "cache_age_seconds": fetcher.cache_age_seconds(),
        "cache_ttl_seconds": fetcher.CACHE_TTL,
        "persistence": "SQLite",
        "db_path": fetcher._db_path,
        "source": "https://portal.amfiindia.com/spages/NAVAll.txt",
    }


@app.get(
    "/cache/refresh",
    summary="Force refresh NAV data from AMFI",
    tags=["Cache"],
)
async def refresh_cache():
    """Forces a fresh fetch of NAV data from AMFI, bypassing the cache TTL."""
    count = await fetcher.force_refresh()
    return {
        "message": "Cache refreshed successfully.",
        "total_records": count,
        "last_fetched_at": fetcher.last_fetched_at(),
    }

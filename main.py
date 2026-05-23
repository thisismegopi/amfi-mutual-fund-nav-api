"""
AMFI Mutual Fund NAV API
Fetches live NAV data from AMFI India and exposes lookup endpoints
by Scheme Code, ISIN, and Scheme Name.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx
import time
from typing import Optional
from models import FundRecord, SearchResponse, SingleFundResponse, ErrorResponse
from data_fetcher import AMFIDataFetcher

app = FastAPI(
    title="AMFI Mutual Fund NAV API",
    description=(
        "Fetch live Net Asset Value (NAV) data for Indian mutual funds "
        "from AMFI India. Supports lookup by Scheme Code, ISIN, and Scheme Name."
    ),
    version="1.0.0",
    contact={
        "name": "AMFI NAV API",
        "url": "https://portal.amfiindia.com",
    },
)

# Singleton data fetcher with caching
fetcher = AMFIDataFetcher()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "AMFI Mutual Fund NAV API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "by_scheme_code": "/fund/scheme/{scheme_code}",
            "by_isin":        "/fund/isin/{isin}",
            "search_by_name": "/fund/search?q=<name>",
            "cache_status":   "/cache/status",
            "refresh_cache":  "/cache/refresh",
        },
    }


@app.get(
    "/fund/scheme/{scheme_code}",
    response_model=SingleFundResponse,
    summary="Get fund by Scheme Code",
    tags=["Fund Lookup"],
)
async def get_by_scheme_code(scheme_code: str):
    """
    Fetch a single mutual fund record using its **AMFI Scheme Code**.

    Example: `/fund/scheme/119551`
    """
    await fetcher.ensure_data_loaded()
    record = fetcher.get_by_scheme_code(scheme_code.strip())
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No fund found with Scheme Code '{scheme_code}'.",
        )
    return SingleFundResponse(data=record, source="amfiindia.com", cached=fetcher.is_cached())


@app.get(
    "/fund/isin/{isin}",
    response_model=SingleFundResponse,
    summary="Get fund by ISIN",
    tags=["Fund Lookup"],
)
async def get_by_isin(isin: str):
    """
    Fetch a single mutual fund record using its **ISIN** (Growth, Dividend Payout,
    or Dividend Reinvestment ISIN).

    Example: `/fund/isin/INF209KA12Z1`
    """
    await fetcher.ensure_data_loaded()
    record = fetcher.get_by_isin(isin.strip().upper())
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No fund found with ISIN '{isin}'.",
        )
    return SingleFundResponse(data=record, source="amfiindia.com", cached=fetcher.is_cached())


@app.get(
    "/fund/search",
    response_model=SearchResponse,
    summary="Search funds by Scheme Name",
    tags=["Fund Lookup"],
)
async def search_by_name(
    q: str = Query(..., min_length=3, description="Partial or full scheme name to search"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results to return"),
):
    """
    Search mutual funds by **Scheme Name** (case-insensitive, partial match supported).

    Example: `/fund/search?q=axis+bluechip&limit=10`
    """
    await fetcher.ensure_data_loaded()
    results = fetcher.search_by_name(q.strip(), limit=limit)
    return SearchResponse(
        query=q,
        total_results=len(results),
        limit=limit,
        data=results,
        source="amfiindia.com",
        cached=fetcher.is_cached(),
    )


@app.get(
    "/cache/status",
    summary="Check cache status",
    tags=["Cache"],
)
async def cache_status():
    """Returns information about the current in-memory cache of AMFI NAV data."""
    return {
        "cached": fetcher.is_cached(),
        "total_records": fetcher.total_records(),
        "last_fetched_at": fetcher.last_fetched_at(),
        "cache_age_seconds": fetcher.cache_age_seconds(),
        "cache_ttl_seconds": fetcher.CACHE_TTL,
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

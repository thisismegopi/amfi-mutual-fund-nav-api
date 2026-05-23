"""
AMFIDataFetcher
---------------
Downloads and parses the AMFI NAVAll.txt file, builds lookup indexes,
and provides a simple cache with a configurable TTL.
"""

import httpx
import time
from typing import Optional, Dict, List
from models import FundRecord


AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"


class AMFIDataFetcher:
    CACHE_TTL = 3600  # 1 hour

    def __init__(self):
        self._records: List[FundRecord] = []
        # Indexes for O(1) lookup
        self._by_scheme_code: Dict[str, FundRecord] = {}
        self._by_isin: Dict[str, FundRecord] = {}
        self._fetched_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def is_cached(self) -> bool:
        return self._fetched_at is not None

    def total_records(self) -> int:
        return len(self._records)

    def last_fetched_at(self) -> Optional[str]:
        if self._fetched_at is None:
            return None
        import datetime
        return datetime.datetime.utcfromtimestamp(self._fetched_at).strftime("%Y-%m-%dT%H:%M:%SZ")

    def cache_age_seconds(self) -> Optional[float]:
        if self._fetched_at is None:
            return None
        return round(time.time() - self._fetched_at, 1)

    # ------------------------------------------------------------------
    # Lookup methods
    # ------------------------------------------------------------------

    def get_by_scheme_code(self, code: str) -> Optional[FundRecord]:
        return self._by_scheme_code.get(code)

    def get_by_isin(self, isin: str) -> Optional[FundRecord]:
        return self._by_isin.get(isin)

    def search_by_name(self, query: str, limit: int = 20) -> List[FundRecord]:
        q = query.lower()
        return [r for r in self._records if q in r.scheme_name.lower()][:limit]

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def ensure_data_loaded(self):
        """Load data if not cached or cache has expired."""
        if self._fetched_at is None or (time.time() - self._fetched_at) > self.CACHE_TTL:
            await self._fetch_and_parse()

    async def force_refresh(self) -> int:
        await self._fetch_and_parse()
        return len(self._records)

    # ------------------------------------------------------------------
    # Internal: fetch & parse
    # ------------------------------------------------------------------

    async def _fetch_and_parse(self):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(AMFI_URL)
            response.raise_for_status()
            raw_text = response.text

        records, by_code, by_isin = self._parse(raw_text)
        self._records = records
        self._by_scheme_code = by_code
        self._by_isin = by_isin
        self._fetched_at = time.time()

    @staticmethod
    def _parse(raw: str):
        records: List[FundRecord] = []
        by_code: Dict[str, FundRecord] = {}
        by_isin: Dict[str, FundRecord] = {}

        current_category = None
        current_fund_house = None

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # ---- Category header (e.g. "Open Ended Schemes(Equity Scheme - Large Cap Fund)")
            if line.startswith("Open Ended") or line.startswith("Close Ended") or line.startswith("Interval"):
                # Extract category name between parentheses if present
                if "(" in line and ")" in line:
                    current_category = line[line.index("(") + 1 : line.index(")")]
                else:
                    current_category = line
                continue

            # ---- Column header row
            if line.startswith("Scheme Code;"):
                continue

            # ---- Fund house name (single token without semicolons)
            if ";" not in line:
                current_fund_house = line
                continue

            # ---- Data row
            parts = line.split(";")
            if len(parts) < 5:
                continue

            scheme_code = parts[0].strip()
            isin_growth = parts[1].strip() or None
            isin_reinvest = parts[2].strip() or None
            scheme_name = parts[3].strip()
            nav_raw = parts[4].strip()
            nav_date = parts[5].strip() if len(parts) > 5 else None

            # Sanitise ISIN dashes
            if isin_growth == "-":
                isin_growth = None
            if isin_reinvest == "-":
                isin_reinvest = None

            # Parse NAV to float
            try:
                nav_value = float(nav_raw) if nav_raw and nav_raw != "N.A." else None
            except ValueError:
                nav_value = None

            record = FundRecord(
                scheme_code=scheme_code,
                isin_div_payout_growth=isin_growth,
                isin_div_reinvestment=isin_reinvest,
                scheme_name=scheme_name,
                nav=nav_value,
                nav_date=nav_date,
                fund_house=current_fund_house,
                category=current_category,
            )

            records.append(record)
            by_code[scheme_code] = record

            if isin_growth:
                by_isin[isin_growth.upper()] = record
            if isin_reinvest:
                by_isin[isin_reinvest.upper()] = record

        return records, by_code, by_isin

"""
AMFIDataFetcher
---------------
Downloads and parses the AMFI NAVAll.txt file, builds in-memory lookup indexes,
and persists parsed data to SQLite so the cache survives process restarts.
"""

import httpx
import time
import datetime
import os
import aiosqlite
from typing import Optional, Dict, List, Tuple
from models import FundRecord


AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
DEFAULT_DB_PATH = os.getenv("DB_PATH", "./amfi_cache.db")


class AMFIDataFetcher:
    CACHE_TTL = 3600  # 1 hour

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path
        self._records: List[FundRecord] = []
        self._by_scheme_code: Dict[str, FundRecord] = {}
        self._by_isin: Dict[str, FundRecord] = {}
        self._fetched_at: Optional[float] = None
        self._db_initialized = False

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

    def search(
        self,
        query: Optional[str] = None,
        fund_house: Optional[str] = None,
        category: Optional[str] = None,
        scheme_type: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[FundRecord], int]:
        results = self._records

        if query:
            q = query.lower()
            results = [r for r in results if q in r.scheme_name.lower()]
        if fund_house:
            fh = fund_house.lower()
            results = [r for r in results if r.fund_house and fh in r.fund_house.lower()]
        if category:
            cat = category.lower()
            results = [r for r in results if r.category and cat in r.category.lower()]
        if scheme_type:
            st = scheme_type.lower()
            results = [r for r in results if r.scheme_type and st in r.scheme_type.lower()]

        total = len(results)
        offset = (page - 1) * limit
        return results[offset : offset + limit], total

    def get_bulk_by_scheme_codes(self, codes: List[str]) -> Tuple[List[FundRecord], List[str]]:
        found, not_found = [], []
        for code in codes:
            record = self._by_scheme_code.get(code.strip())
            if record:
                found.append(record)
            else:
                not_found.append(code.strip())
        return found, not_found

    def get_bulk_by_isins(self, isins: List[str]) -> Tuple[List[FundRecord], List[str]]:
        found, not_found = [], []
        for isin in isins:
            record = self._by_isin.get(isin.strip().upper())
            if record:
                found.append(record)
            else:
                not_found.append(isin.strip())
        return found, not_found

    def get_all_fund_houses(self) -> List[str]:
        return sorted({r.fund_house for r in self._records if r.fund_house})

    def get_all_categories(self) -> List[str]:
        return sorted({r.category for r in self._records if r.category})

    def get_all_scheme_types(self) -> List[str]:
        return sorted({r.scheme_type for r in self._records if r.scheme_type})

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def ensure_data_loaded(self):
        if self._fetched_at is not None and (time.time() - self._fetched_at) <= self.CACHE_TTL:
            return
        await self._ensure_db()
        db_ts = await self._get_db_timestamp()
        if db_ts and (time.time() - db_ts) <= self.CACHE_TTL:
            await self._load_from_db()
            self._fetched_at = db_ts
        else:
            await self._fetch_and_parse()

    async def force_refresh(self) -> int:
        await self._ensure_db()
        await self._fetch_and_parse()
        return len(self._records)

    # ------------------------------------------------------------------
    # SQLite persistence
    # ------------------------------------------------------------------

    async def _ensure_db(self):
        if self._db_initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cache_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    fetched_at REAL NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS nav_records (
                    scheme_code TEXT PRIMARY KEY,
                    isin_div_payout_growth TEXT,
                    isin_div_reinvestment TEXT,
                    scheme_name TEXT NOT NULL,
                    nav REAL,
                    nav_date TEXT,
                    fund_house TEXT,
                    category TEXT,
                    scheme_type TEXT
                )
            """)
            await db.commit()
        self._db_initialized = True

    async def _get_db_timestamp(self) -> Optional[float]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT fetched_at FROM cache_meta WHERE id = 1") as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def _load_from_db(self):
        records: List[FundRecord] = []
        by_code: Dict[str, FundRecord] = {}
        by_isin: Dict[str, FundRecord] = {}

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT * FROM nav_records") as cur:
                async for row in cur:
                    r = FundRecord(
                        scheme_code=row[0],
                        isin_div_payout_growth=row[1],
                        isin_div_reinvestment=row[2],
                        scheme_name=row[3],
                        nav=row[4],
                        nav_date=row[5],
                        fund_house=row[6],
                        category=row[7],
                        scheme_type=row[8],
                    )
                    records.append(r)
                    by_code[r.scheme_code] = r
                    if r.isin_div_payout_growth:
                        by_isin[r.isin_div_payout_growth.upper()] = r
                    if r.isin_div_reinvestment:
                        by_isin[r.isin_div_reinvestment.upper()] = r

        self._records = records
        self._by_scheme_code = by_code
        self._by_isin = by_isin

    async def _save_to_db(self, records: List[FundRecord], fetched_at: float):
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM nav_records")
            await db.executemany(
                "INSERT INTO nav_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        r.scheme_code,
                        r.isin_div_payout_growth,
                        r.isin_div_reinvestment,
                        r.scheme_name,
                        r.nav,
                        r.nav_date,
                        r.fund_house,
                        r.category,
                        r.scheme_type,
                    )
                    for r in records
                ],
            )
            await db.execute(
                "INSERT OR REPLACE INTO cache_meta (id, fetched_at) VALUES (1, ?)", (fetched_at,)
            )
            await db.commit()

    # ------------------------------------------------------------------
    # Internal: fetch & parse
    # ------------------------------------------------------------------

    async def _fetch_and_parse(self):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(AMFI_URL)
            response.raise_for_status()
            raw_text = response.text

        records, by_code, by_isin = self._parse(raw_text)
        fetched_at = time.time()

        self._records = records
        self._by_scheme_code = by_code
        self._by_isin = by_isin
        self._fetched_at = fetched_at

        await self._save_to_db(records, fetched_at)

    @staticmethod
    def _parse(raw: str):
        records: List[FundRecord] = []
        by_code: Dict[str, FundRecord] = {}
        by_isin: Dict[str, FundRecord] = {}

        current_category = None
        current_fund_house = None
        current_scheme_type = None

        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            # Scheme-type / category header lines
            if line.startswith("Open Ended"):
                current_scheme_type = "Open Ended"
                current_category = line[line.index("(") + 1 : line.index(")")] if "(" in line else line
                continue
            if line.startswith("Close Ended"):
                current_scheme_type = "Close Ended"
                current_category = line[line.index("(") + 1 : line.index(")")] if "(" in line else line
                continue
            if line.startswith("Interval"):
                current_scheme_type = "Interval"
                current_category = line[line.index("(") + 1 : line.index(")")] if "(" in line else line
                continue

            if line.startswith("Scheme Code;"):
                continue

            # Fund house name (no semicolons)
            if ";" not in line:
                current_fund_house = line
                continue

            parts = line.split(";")
            if len(parts) < 5:
                continue

            scheme_code = parts[0].strip()
            isin_growth = parts[1].strip() or None
            isin_reinvest = parts[2].strip() or None
            scheme_name = parts[3].strip()
            nav_raw = parts[4].strip()
            nav_date = parts[5].strip() if len(parts) > 5 else None

            if isin_growth == "-":
                isin_growth = None
            if isin_reinvest == "-":
                isin_reinvest = None

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
                scheme_type=current_scheme_type,
            )

            records.append(record)
            by_code[scheme_code] = record

            if isin_growth:
                by_isin[isin_growth.upper()] = record
            if isin_reinvest:
                by_isin[isin_reinvest.upper()] = record

        return records, by_code, by_isin

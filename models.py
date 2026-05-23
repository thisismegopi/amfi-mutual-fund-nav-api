"""
Pydantic models for the AMFI NAV API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class FundRecord(BaseModel):
    scheme_code: str = Field(..., description="AMFI Scheme Code")
    isin_div_payout_growth: Optional[str] = Field(None, description="ISIN for Dividend Payout / Growth option")
    isin_div_reinvestment: Optional[str] = Field(None, description="ISIN for Dividend Reinvestment option")
    scheme_name: str = Field(..., description="Full name of the mutual fund scheme")
    nav: Optional[float] = Field(None, description="Net Asset Value (NAV) in INR")
    nav_date: Optional[str] = Field(None, description="Date of the NAV (DD-MMM-YYYY)")
    fund_house: Optional[str] = Field(None, description="Name of the Asset Management Company (AMC)")
    category: Optional[str] = Field(None, description="Scheme category (e.g., Equity, Debt, Hybrid)")

    class Config:
        json_schema_extra = {
            "example": {
                "scheme_code": "119551",
                "isin_div_payout_growth": "INF209KA12Z1",
                "isin_div_reinvestment": "INF209KA13Z9",
                "scheme_name": "Aditya Birla Sun Life Banking & PSU Debt Fund - DIRECT - IDCW",
                "nav": 104.3467,
                "nav_date": "22-May-2026",
                "fund_house": "Aditya Birla Sun Life Mutual Fund",
                "category": "Debt Scheme - Banking and PSU Fund",
            }
        }


class SingleFundResponse(BaseModel):
    data: FundRecord
    source: str
    cached: bool


class SearchResponse(BaseModel):
    query: str
    total_results: int
    limit: int
    data: List[FundRecord]
    source: str
    cached: bool


class ErrorResponse(BaseModel):
    detail: str

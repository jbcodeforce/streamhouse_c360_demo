"""FastAPI router for the /analytics endpoints (C360 dashboard)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from analytics import service
from analytics.models import DataAnalytics, CustomerProfile

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/c360-profile", response_model=DataAnalytics, status_code=200)
def get_c360_profile() -> DataAnalytics:
    """Cross-customer analytics for the C360 dashboard.

    Reads the five ``fct_crm_*`` data products with concurrent snapshot
    queries and assembles them. Always 200
    with a well-formed payload: when a live query is unconfigured or fails, the
    payload is simply empty (``row_count == 0``).
    """
    return service.get_data_analytics()


@router.get("/c360-profile/customer/{customer_id}", response_model=CustomerProfile, status_code=200)
def get_customer_profile(customer_id: str) -> CustomerProfile:
    """One customer's metrics via a ``WHERE customer_id = …`` snapshot query."""
    profile = service.get_customer_profile(customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return profile


# --- RTCE / Lightning Query API variants (current-state point lookups) ----


@router.get("/c360-profile/rtce/customers", response_model=list[CustomerProfile], status_code=200)
def search_customer_profiles_rtce(
    name: str = Query(..., min_length=1, max_length=100, description="Customer name substring"),
) -> list[CustomerProfile]:
    """Name → profile(s) in one call: resolve ``customer_id``s from the operational
    database, then read each from the ``fct_c360_profile`` Lightning table.

    Empty list when nothing matches (or no match has a profile row yet).
    """
    return service.get_customer_profiles_rtce_by_name(name)


@router.get("/c360-profile/rtce/customer/{customer_id}", response_model=CustomerProfile, status_code=200)
def get_customer_profile_rtce(customer_id: str) -> CustomerProfile:
    """One customer's current-state metrics via an RTCE Lightning point lookup."""
    profile = service.get_customer_profile_rtce(customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return profile

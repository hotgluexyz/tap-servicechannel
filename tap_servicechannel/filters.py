"""Helpers for user-configurable stream filters (Hotglue selected filters)."""

from __future__ import annotations

from typing import Any, Optional, Set


def parse_vendor_filter_selection(selected_filters: Optional[dict]) -> Set[str]:
    """Extract the vendor payee id allow-list from Hotglue selected filter config.

    Supports both a flat shape (``{"vendor_payee_id": [...]}``) and the clause
    shape (``{"clauses": [{"field": "vendor_payee_id", "values": [...]}]}``).
    """
    vendor_payee_ids: Set[str] = set()
    if not selected_filters:
        return vendor_payee_ids

    for key in ("vendor_payee_id", "vendor_id"):
        values = selected_filters.get(key)
        if values:
            vendor_payee_ids.update(_as_list(values))

    for clause in selected_filters.get("clauses", []):
        field = clause.get("field") or clause.get("filter_name") or clause.get("name")
        values = clause.get("values") or clause.get("value")
        if field in ("vendor_payee_id", "vendor_id"):
            vendor_payee_ids.update(_as_list(values))

    return vendor_payee_ids


def record_matches_vendor_filters(
    record: dict[str, Any],
    vendor_payee_ids: Set[str],
) -> bool:
    """Return True when the record passes the vendor filter (or none is set)."""
    if not vendor_payee_ids:
        return True

    payee_id = record.get("VendorPayeeId")
    if payee_id is None:
        return False
    return str(payee_id) in vendor_payee_ids


def build_vendor_odata_filter(vendor_payee_ids: Set[str]) -> Optional[str]:
    """Build an OData ``$filter`` clause to push vendor filtering server-side.

    ``VendorPayeeId`` is numeric, so only integer-like values are pushed down;
    any non-numeric values are still enforced client-side by
    :func:`record_matches_vendor_filters`.
    """
    numeric_ids = sorted({v for v in vendor_payee_ids if str(v).lstrip("-").isdigit()})
    if not numeric_ids:
        return None
    clause = " or ".join(f"VendorPayeeId eq {v}" for v in numeric_ids)
    return f"({clause})"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]

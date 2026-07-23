"""Helpers for user-configurable stream filters (Hotglue selected filters)."""

from __future__ import annotations

from typing import Any, Optional, Set


def parse_provider_filter_selection(selected_filters: Optional[dict]) -> Set[str]:
    """Extract the provider id allow-list from Hotglue selected filter config.

    The stream's selected filters use numbered clauses, e.g.::

        {
          "clause_1": {
            "field": "Provider/Id",
            "operator": "IN",
            "value": ["Provider Name (2000045779)", ...]
          }
        }

    Every numbered clause contributes its ``value`` (a single string for ``EQ``
    or a list for ``IN``). Option values are ``"<name> (id)"`` display strings,
    so the trailing id in parentheses is extracted; raw id values are also
    accepted.
    """
    provider_ids: Set[str] = set()
    if not selected_filters:
        return provider_ids

    for clause in selected_filters.values():
        if not isinstance(clause, dict):
            continue

        values = clause.get("value")
        if values is None:
            values = clause.get("values")
        for raw in _as_list(values):
            provider_id = _extract_provider_id(raw)
            if provider_id:
                provider_ids.add(provider_id)

    return provider_ids

def _extract_provider_id(value: Any) -> Optional[str]:
    """Pull the provider id out of a ``"<name> (id)"`` option, else return as-is."""
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(")") and "(" in text:
        text = text.rsplit("(", 1)[-1].rstrip(")").strip()
    return text or None


def build_provider_odata_filter(provider_ids: Set[str]) -> Optional[str]:
    """Build an OData ``$filter`` clause to push provider filtering server-side.

    ``Provider/Id`` is numeric, so only integer-like values are pushed down;
    any non-numeric values are ignored.
    """
    numeric_ids = sorted({v for v in provider_ids if str(v).lstrip("-").isdigit()})
    if not numeric_ids:
        return None
    
    if len(numeric_ids) == 1:
        return f"Provider/Id eq {numeric_ids[0]}"

    clause = " or ".join(f"Provider/Id eq {v}" for v in numeric_ids)
    return f"({clause})"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]

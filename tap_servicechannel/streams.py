"""Stream type classes for tap-servicechannel."""

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import unquote, urlparse

import requests
from hotglue_singer_sdk import typing as th

from tap_servicechannel.client import ServiceChannelStream
from tap_servicechannel.filters import (
    build_provider_odata_filter,
    parse_provider_filter_selection,
)


class TradesStream(ServiceChannelStream):
    """Subscriber trades.

    Used as the parent of :class:`VendorsStream` (vendors are only listable
    per-trade). It is a plain REST endpoint that returns a bare JSON array and
    is not paginated, so the OData query params and pagination are disabled.
    """

    name = "trades"
    path = "/v3/trades"
    replication_key = None
    records_jsonpath = "$[*]"

    schema = th.PropertiesList(
        th.Property("Id", th.IntegerType),
        th.Property("Name", th.StringType),
        th.Property("SubscriberId", th.IntegerType),
    ).to_dict()

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        return {}

    def get_next_page_token(
        self, response: requests.Response, previous_token: Optional[Any]
    ) -> None:
        return None

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        return {"trade_id": record["Id"]}


class VendorsStream(ServiceChannelStream):
    """Vendors (ServiceChannel "providers").

    ServiceChannel exposes no usable ``/odata/providers`` collection endpoint
    (a plain ``GET`` there returns a server-side 500 due to ambiguous routing),
    and there is no "list all providers" route. Providers are only listable per
    trade via ``/v3/providers/getbytradeid``, so this stream is a child of
    :class:`TradesStream`: it fetches the providers for each trade and emits the
    distinct providers (de-duplicated by ``Id`` across trades within a run).

    Only ``Id``/``Name``/``DoNotDispatch`` are available from this endpoint; the
    richer provider fields are not exposed by any working list/detail route.
    """

    name = "vendors"
    path = "/v3/providers/getbytradeid"
    parent_stream_type = TradesStream
    replication_key = None
    records_jsonpath = "$.Providers[*]"

    schema = th.PropertiesList(
        th.Property("Id", th.IntegerType),
        th.Property("Name", th.StringType),
        th.Property("DoNotDispatch", th.BooleanType),
    ).to_dict()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._seen_ids: Set[Any] = set()

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        return {"tradeId": (context or {})["trade_id"]}

    def get_next_page_token(
        self, response: requests.Response, previous_token: Optional[Any]
    ) -> None:
        return None

    def post_process(self, row: dict, context: Optional[dict] = None) -> Optional[dict]:
        row = super().post_process(row, context) or row
        provider_id = row.get("Id")
        if provider_id in self._seen_ids:
            return None
        self._seen_ids.add(provider_id)
        return row

    def get_available_filters_reference_data(
        self, fields_to_include: Set[str]
    ) -> List[Dict[str, Any]]:
        """Return the distinct vendors used to populate invoice filter options.

        Backs the ``reference_data.vendors.Name(Id)`` options declared by
        :meth:`InvoicesStream.get_available_filters_metadata`. Vendors
        (ServiceChannel "providers") are only listable per trade, so this walks
        the same Trades -> providers path this stream syncs on: it lists every
        trade via ``/v3/trades`` then collects the providers for each trade via
        ``/v3/providers/getbytradeid``, de-duplicating by provider ``Id``. Each
        entry exposes the raw ``Id``/``Name`` plus a combined ``"Name (Id)"``
        display label so callers get a compact vendor pick-list.
        """
        trades_url = f"{self.url_base}/v3/trades"
        trades_request = self.build_prepared_request("GET", trades_url)
        trades_response = self.request_decorator(self._request)(trades_request, None)
        trades = trades_response.json() or []

        providers_url = f"{self.url_base}{self.path}"
        seen: Set[Any] = set()
        reference_data: List[Dict[str, Any]] = []
        for trade in trades:
            trade_id = trade.get("Id")
            if trade_id is None:
                continue
            request = self.build_prepared_request(
                "GET", providers_url, params={"tradeId": trade_id}
            )
            response = self.request_decorator(self._request)(request, None)
            providers = response.json().get("Providers", []) or []
            for provider in providers:
                provider_id = provider.get("Id")
                if provider_id is None or provider_id in seen:
                    continue
                seen.add(provider_id)
                reference_data.append(
                    {
                        "Id": provider_id,
                        "Name": provider.get("Name"),
                        "Name(Id)": f"{provider.get('Name')} ({provider_id})",
                    }
                )

        return reference_data


class InvoicesStream(ServiceChannelStream):

    name = "invoices"
    path = "/odata/invoices"    
    expand_fields = "Provider"

    def __init__(self, *args, **kwargs) -> None:
        # Initialize before super().__init__(), which may call
        # setup_selected_filters() during construction.
        self._provider_ids: Set[str] = set()
        super().__init__(*args, **kwargs)
        
    schema = th.PropertiesList(
        th.Property("Id", th.IntegerType),
        th.Property("Number", th.StringType),
        th.Property("BatchNumber", th.StringType),
        th.Property("InvoiceTax", th.NumberType),
        th.Property("PostedTaxRate", th.NumberType),
        th.Property("PostedTax2Rate", th.NumberType),
        th.Property("VendorPayeeId", th.IntegerType),
        th.Property("InvoiceTotal", th.NumberType),
        th.Property("InvoiceBalance", th.NumberType),
        th.Property("ApprovedDate", th.DateTimeType),
        th.Property("ApprovalCode", th.StringType),
        th.Property("EditableAdditionalApprovalCode", th.StringType),
        th.Property("PostedDate", th.DateTimeType),
        th.Property("PostedBy", th.StringType),
        th.Property("Subtotal", th.NumberType),
        th.Property("Status", th.StringType),
        th.Property("Trade", th.StringType),
        th.Property(
            "InvoiceAmountsDetails",
            th.ObjectType(
                th.Property("LaborAmount", th.NumberType),
                th.Property("MaterialAmount", th.NumberType),
                th.Property("TravelAmount", th.NumberType),
                th.Property("FreightAmount", th.NumberType),
                th.Property("OtherAmount", th.NumberType),
                th.Property("OtherDescription", th.StringType),
            ),
        ),
        th.Property(
            "InvoiceTaxesDetails",
            th.ObjectType(
                th.Property("LaborTax", th.NumberType),
                th.Property("MaterialTax", th.NumberType),
                th.Property("TravelTax", th.NumberType),
                th.Property("FreightTax", th.NumberType),
                th.Property("OtherTax", th.NumberType),
            ),
        ),
        th.Property(
            "Tax2Details",
            th.ObjectType(
                th.Property("Tax2Amount", th.NumberType),
                th.Property("Tax2Name", th.StringType),
            ),
        ),
        th.Property("WithMismatchedRates", th.BooleanType),
        th.Property("IsOutsourced", th.BooleanType),
        th.Property("StarredBy", th.StringType),
        th.Property("IsStarred", th.BooleanType),
        th.Property("StarredDate", th.DateTimeType),
        th.Property("Description", th.StringType),
        th.Property("InvoiceDate", th.DateTimeType),
        th.Property("LaborTaxIncluded", th.BooleanType),
        th.Property("TravelTaxIncluded", th.BooleanType),
        th.Property("MaterialsTaxIncluded", th.BooleanType),
        th.Property("FreightTaxIncluded", th.BooleanType),
        th.Property("OtherTaxIncluded", th.BooleanType),
        th.Property("NonTaxableLabor", th.NumberType),
        th.Property("NonTaxableTravel", th.NumberType),
        th.Property("NonTaxableMaterial", th.NumberType),
        th.Property("NonTaxableFreight", th.NumberType),
        th.Property("NonTaxableOther", th.NumberType),
        th.Property("StatusChangeDate", th.DateTimeType),
        th.Property("StatusChangeUser", th.StringType),
        th.Property("StatusChangeUserid", th.StringType),
        th.Property("IsDuplicate", th.BooleanType),
        th.Property("WoTrackingNumber", th.IntegerType),
        th.Property("Terms", th.StringType),
        th.Property("Comments", th.StringType),
        th.Property("PaidDate", th.DateTimeType),
        th.Property("TransferredDate", th.DateTimeType),
        th.Property("LastActionDate", th.DateTimeType),
        th.Property("UpdatedDate", th.DateTimeType),
        th.Property(
            "StatusHistoryShort",
            th.ArrayType(
                th.ObjectType(
                    th.Property("CreatedBy", th.StringType),
                    th.Property("CreatedById", th.IntegerType),
                    th.Property("Status", th.StringType),
                    th.Property("InvId", th.IntegerType),
                    th.Property("ActionDate", th.StringType),
                )
            ),
        ),
        th.Property("WoAssignedTo", th.StringType),
        th.Property("IsChargesApprovalCodesDefault", th.BooleanType),
        th.Property("StoredFeatures", th.ArrayType(th.StringType)),
        th.Property("Provider", th.ObjectType(
            th.Property("@odata.type", th.StringType),
            th.Property("Id", th.IntegerType),
            th.Property("Name", th.StringType),
            th.Property("DoNotDispatch", th.BooleanType),
            th.Property("Phone", th.StringType),
            th.Property("FullName", th.StringType),
            th.Property("Address1", th.StringType),
            th.Property("Address2", th.StringType),
            th.Property("City", th.StringType),
            th.Property("State", th.StringType),
            th.Property("Zip", th.StringType),
            th.Property("Country", th.StringType),
            th.Property("MainContact", th.StringType),
            th.Property("DateCreated", th.DateTimeType),
            th.Property("LastUserDate", th.DateTimeType),
            th.Property("SuperUser", th.StringType),
            th.Property("WebSite", th.StringType),
            th.Property("Email", th.StringType),
            th.Property("TaxId", th.StringType),
            th.Property("Trade", th.StringType),
            th.Property("ProcessingEmail", th.StringType),
            th.Property("FaxNumber", th.StringType),
            th.Property("SuiteFloor", th.StringType),
            th.Property("MailInfo", th.StringType),
            th.Property("ImageFile", th.StringType),
            th.Property("ReturnMail", th.StringType),
            th.Property("MailFrequency", th.StringType),
            th.Property("FormId", th.StringType),
            th.Property("Pager", th.StringType),
            th.Property("NightRequest", th.BooleanType),
            th.Property("ShortFormatEmail", th.StringType),
            th.Property("LastTrainingDate", th.DateTimeType),
            th.Property("LastTrainingDateStr", th.StringType),
            th.Property("IsInternal", th.BooleanType),
            th.Property("IsOnOffShoreFeatureEnabled", th.BooleanType),
        )),
    ).to_dict()

    def setup_selected_filters(self) -> None:
        self._provider_ids |= parse_provider_filter_selection(self._selected_filters)

    def get_available_filters_metadata(self) -> Dict[str, Any]:
        return {
            "supported_operators": ["AND", "OR"],
            "supports_nesting_clauses": False,
            "filters": {
                "provider_id": {
                    "label": "Vendor",
                    "supported_operators": ["IN", "EQ"],
                    "target_field": "Provider/Id",
                    "options": "reference_data.vendors.Name(Id)",
                },
            },
        }

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        provider_clause = build_provider_odata_filter(self._provider_ids)
        if provider_clause:
            existing = params.get("$filter")
            params["$filter"] = (
                f"{existing} and {provider_clause}" if existing else provider_clause
            )
        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        return {
            "wo_tracking_number": record.get("WoTrackingNumber"),
            "invoice_id": record.get("Id"),
        }


class AttachmentsStream(ServiceChannelStream):

    name = "attachments"
    path = "/v3/odata/workorders({wo_tracking_number})/attachments"
    parent_stream_type = InvoicesStream
    replication_key = None

    schema = th.PropertiesList(
        th.Property("Id", th.IntegerType),
        th.Property("Description", th.StringType),
        th.Property("Name", th.StringType),
        th.Property("TimeStamp", th.DateTimeType),
        th.Property("Uri", th.StringType),
        th.Property("NoteId", th.IntegerType),
        th.Property("Visibility", th.IntegerType),
        th.Property("IsInvoiceDigitalCopy", th.BooleanType),
        th.Property("UploadBy", th.StringType),
        th.Property("wo_tracking_number", th.IntegerType),
        th.Property("attachment_path", th.StringType),
    ).to_dict()

    def get_records(self, context: Optional[dict]) -> Iterable[dict]:
        if not context or context.get("wo_tracking_number") is None:
            return
        yield from super().get_records(context)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Strip path separators / unsafe characters from a file name."""
        name = os.path.basename(name.strip())
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name) or "attachment"

    def _resolve_filename(self, row: dict) -> str:
        """Pick a stable, unique file name for the attachment record."""
        name = row.get("Name") or row.get("Description")
        if not name:
            # Fall back to the name encoded in the pre-signed URI.
            path = urlparse(row.get("Uri") or "").path
            name = unquote(os.path.basename(path)) if path else None
        if not name:
            name = "attachment"
        name = self._sanitize_filename(name)
        # Prefix with the attachment Id (the primary key) so multiple
        # attachments on the same invoice that share a display name don't
        # overwrite each other.
        attachment_id = row.get("Id")
        if attachment_id is not None:
            name = f"{attachment_id}_{name}"
        return name

    def _download_attachment(self, row: dict, context: Optional[dict]) -> Optional[str]:
        """Download the attachment file and return its path relative to sync-output."""
        uri = row.get("Uri")
        if not uri:
            return None

        invoice_id = (context or {}).get("invoice_id") or "unknown_invoice"
        # Path relative to the sync-output folder, e.g.
        # ``attachments/171367500/347326792_IMG_20260401_124316.jpeg``.
        relative_path = os.path.join(
            "attachments", str(invoice_id), self._resolve_filename(row)
        )
        target_path = os.path.join(self.get_sync_output_folder(), relative_path)

        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with requests.get(uri, stream=True, timeout=60) as response:
                response.raise_for_status()
                with open(target_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
            self.logger.info("Downloaded attachment to %s", target_path)
            return relative_path
        except Exception as ex:
            self.logger.warning("Failed to download attachment %s from %s: %s", row.get("Id"), uri, ex)
            return None

    def post_process(self, row: dict, context: Optional[dict] = None) -> Optional[dict]:
        row = super().post_process(row, context) or row
        # The API response omits the work-order link; carry it over from the
        # parent context so downstream joins back to invoices/work orders work.
        row["wo_tracking_number"] = (context or {}).get("wo_tracking_number")
        if self.config.get("download_attachments"):
            row["attachment_path"] = self._download_attachment(row, context)
        return row

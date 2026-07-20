"""Stream type classes for tap-servicechannel."""

import os
import re
from typing import Any, Dict, Iterable, Optional, Set
from urllib.parse import unquote, urlparse

import requests
from hotglue_singer_sdk import typing as th

from tap_servicechannel.client import ServiceChannelStream
from tap_servicechannel.filters import (
    build_vendor_odata_filter,
    parse_vendor_filter_selection,
    record_matches_vendor_filters,
)


class InvoicesStream(ServiceChannelStream):

    name = "invoices"
    path = "/odata/invoices"

    def __init__(self, *args, **kwargs) -> None:
        # Initialize before super().__init__(), which may call
        # setup_selected_filters() during construction.
        self._vendor_payee_ids: Set[str] = set()
        super().__init__(*args, **kwargs)
        # Config fallback so filtering also works without a selected-filters file.
        config_vendors = self.config.get("vendor_payee_ids")
        if config_vendors is not None:
            values = (
                config_vendors if isinstance(config_vendors, list) else [config_vendors]
            )
            self._vendor_payee_ids.update(str(v) for v in values)

    def setup_selected_filters(self) -> None:
        self._vendor_payee_ids |= parse_vendor_filter_selection(self._selected_filters)

    def get_available_filters_metadata(self) -> Dict[str, Any]:
        return {
            "supported_operators": ["AND", "OR"],
            "supports_nesting_clauses": False,
            "filters": {
                "vendor_payee_id": {
                    "label": "Vendor",
                    "supported_operators": ["IN", "EQ"],
                    "target_field": "VendorPayeeId",
                    "options": "reference_data.invoices.VendorPayeeId",
                },
            },
        }

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        vendor_clause = build_vendor_odata_filter(self._vendor_payee_ids)
        if vendor_clause:
            existing = params.get("$filter")
            params["$filter"] = (
                f"{existing} and {vendor_clause}" if existing else vendor_clause
            )
        return params

    def post_process(self, row: dict, context: Optional[dict] = None) -> Optional[dict]:
        row = super().post_process(row, context) or row
        if not record_matches_vendor_filters(row, self._vendor_payee_ids):
            return None
        return row

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
    ).to_dict()

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
        """Pick a stable file name for the attachment record."""
        name = row.get("Name") or row.get("Description")
        if not name:
            # Fall back to the name encoded in the pre-signed URI, then the Id.
            path = urlparse(row.get("Uri") or "").path
            name = unquote(os.path.basename(path)) if path else None
        if not name:
            name = f"attachment_{row.get('Id')}"
        return self._sanitize_filename(name)

    def _output_folder(self, invoice_id: str) -> str:
        job_id = os.environ.get("JOB_ID")
        base = os.path.join("/home/hotglue", job_id, "sync-output") if job_id else "."
        folder = os.path.join(base, "attachments", invoice_id)
        os.makedirs(folder, exist_ok=True)
        return folder

    def _download_attachment(self, row: dict, context: Optional[dict]) -> None:
        uri = row.get("Uri")
        if not uri:
            return

        invoice_id = (context or {}).get("invoice_id") or "unknown_invoice"
        target_dir = self._output_folder(str(invoice_id))

        filename = self._resolve_filename(row)
        target_path = os.path.join(target_dir, filename)

        try:
            with requests.get(uri, stream=True, timeout=60) as response:
                response.raise_for_status()
                with open(target_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
            self.logger.info("Downloaded attachment to %s", target_path)
        except Exception as ex:  # noqa: BLE001
            self.logger.warning(
                "Failed to download attachment %s from %s: %s",
                row.get("Id"),
                uri,
                ex,
            )

    def post_process(self, row: dict, context: Optional[dict] = None) -> Optional[dict]:
        row = super().post_process(row, context) or row
        if self.config.get("download_attachments"):
            self._download_attachment(row, context)
        return row

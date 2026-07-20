"""ServiceChannel tap class."""

from typing import List

from hotglue_singer_sdk import Stream, Tap
from hotglue_singer_sdk import typing as th

from tap_servicechannel.streams import (
    AttachmentsStream,
    InvoicesStream,
    TradesStream,
    VendorsStream,
)

STREAM_TYPES = [
    InvoicesStream,
    AttachmentsStream,
    TradesStream,
    VendorsStream,
]


class TapServiceChannel(Tap):
    """ServiceChannel tap class."""

    name = "tap-servicechannel"

    config_jsonschema = th.PropertiesList(
        th.Property("client_id", th.StringType, required=True),
        th.Property("client_secret", th.StringType, required=True),
        th.Property("access_token", th.StringType, required=False),
        th.Property("refresh_token", th.StringType, required=False),
        th.Property("username", th.StringType),
        th.Property("password", th.StringType),
        th.Property("start_date", th.DateTimeType, description="The earliest record date to sync"),
        th.Property(
            "download_attachments",
            th.BooleanType,
            default=False,
            description="If true, download attachment files to the local output path",
        ),
        th.Property(
            "vendor_payee_ids",
            th.ArrayType(th.StringType),
            description=(
                "Optional allow-list of VendorPayeeId values; only invoices for "
                "these vendors (and their attachments) are synced"
            ),
        ),
    ).to_dict()

    def discover_streams(self) -> List[Stream]:
        """Return a list of discovered streams."""
        return [stream_class(tap=self) for stream_class in STREAM_TYPES]


if __name__ == "__main__":
    TapServiceChannel.cli()

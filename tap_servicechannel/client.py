import os
from datetime import timedelta, timezone
from typing import Any, Dict, Optional
from hotglue_singer_sdk.streams import RESTStream
from memoization import cached

from tap_servicechannel.auth import ServiceChannelAuthenticator


class ServiceChannelStream(RESTStream):

    url_base = "https://api.servicechannel.com"
    primary_keys = ["Id"]
    replication_key = "UpdatedDate"
    replication_format = "%Y-%m-%dT%H:%M:%S%z"
    # Timezone used when emitting the replication filter value (UTC-04:00).
    replication_tz = timezone(timedelta(hours=-4))
    records_jsonpath = "$.value[*]"
    page_size = 50
    expand_fields = None

    @property
    @cached
    def authenticator(self) -> ServiceChannelAuthenticator:
        """Return a new authenticator object."""
        return ServiceChannelAuthenticator.create_for_stream(self)

    def get_next_page_token(
        self, response, previous_token: Optional[Any]
    ) -> Optional[int]:
        records = response.json().get("value", [])
        if len(records) < self.page_size:
            return None
        return (previous_token or 0) + len(records)

    def get_url_params(
        self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params: dict = {"$top": self.page_size}
        if next_page_token:
            params["$skip"] = next_page_token
        if self.expand_fields:
            params["$expand"] = self.expand_fields
        if self.replication_key:
            params["$orderby"] = f"{self.replication_key} asc"
            start_date = self.get_starting_timestamp(context)
            if start_date:
                value = start_date.astimezone(self.replication_tz).strftime(
                    self.replication_format
                )
                # strftime renders %z as "-0400"; OData wants "-04:00".
                value = f"{value[:-2]}:{value[-2:]}"
                params["$filter"] = f"{self.replication_key} ge {value}"
        return params
    
    def get_sync_output_folder(self) -> str:
        """Return the base folder under which output files (attachments) are written.

        In the hotglue runtime ``JOB_ID`` is set and files are uploaded from
        ``/home/hotglue/{job_id}/sync-output``. Locally we fall back to a
        ``sync-output`` directory (overridable via the ``output_dir`` config).
        """
        job_id = os.environ.get("JOB_ID")
        if job_id:
            return f"/home/hotglue/{job_id}/sync-output"
        return self.config.get("output_dir", "sync-output")

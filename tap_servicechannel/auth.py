"""ServiceChannel Authentication."""

import requests
from requests.auth import HTTPBasicAuth

from hotglue_singer_sdk.authenticators import OAuthAuthenticator, SingletonMeta
from hotglue_singer_sdk.helpers._util import utc_now


class ServiceChannelAuthenticator(OAuthAuthenticator, metaclass=SingletonMeta):
   
    @property
    def oauth_request_body(self) -> dict:
        if self.config.get("refresh_token") is not None:
            return {
                "grant_type": "refresh_token",
                "refresh_token": self.config["refresh_token"],
            }
            
        elif self.config.get("username") is not None and self.config.get("password") is not None:
            return {
                "grant_type": "password",
                "username": self.config["username"],
                "password": self.config["password"],
            }
        else:
            raise ValueError("Either refresh_token or username/password must be provided in the config")

    def update_access_token(self) -> None:
        request_time = utc_now()
        token_response = requests.post(
            self.auth_endpoint,
            data=self.oauth_request_payload,
            auth=HTTPBasicAuth(self.config["client_id"], self.config["client_secret"]),
        )
        try:
            token_response.raise_for_status()
            self.logger.info("OAuth authorization attempt was successful.")
        except Exception as ex:
            raise RuntimeError(
                f"Failed OAuth login, response was '{token_response.json()}'. {ex}"
            )
        token_json = token_response.json()
        self.access_token = token_json["access_token"]
        self.expires_in = token_json.get("expires_in", self._default_expiration)
        if self.expires_in is not None:
            self.expires_in = int(self.expires_in) + int(request_time.timestamp())
        self.last_refreshed = request_time

    @classmethod
    def create_for_stream(cls, stream) -> "ServiceChannelAuthenticator":
        return cls(
            stream=stream,
            auth_endpoint="https://login.servicechannel.com/oauth/token",
        )

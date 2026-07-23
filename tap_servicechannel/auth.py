"""ServiceChannel Authentication."""

import requests
from requests.auth import HTTPBasicAuth
import json
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

    def update_access_token_locally(self) -> None:
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
                f"Failed OAuth login, response was '{token_response.text}'. {ex}"
            )
        token_json = token_response.json()
        self.access_token = token_json["access_token"]
        expires_in = token_json.get("expires_in", self._default_expiration)
        if expires_in is None:
            self.logger.debug(
                "No expires_in receied in OAuth response and no "
                "default_expiration set. Token will be treated as if it never "
                "expires."
            )
            self.expires_in = None
        else:
            self.expires_in = int(expires_in) + int(request_time.timestamp())

        self.last_refreshed = request_time
        # Update the tap config with the new access_token and refresh_token
        self._tap._config["access_token"] = token_json["access_token"]
        self._tap._config["expires_in"] = self.expires_in
        if token_json.get("refresh_token"):
            # Log the refresh_token
            self._tap.logger.info(f"Latest refresh token: {token_json.get('refresh_token')}")
            self._tap._config["refresh_token"] = token_json["refresh_token"]

        # Write the updated config back to the file (only when config was loaded from a path)
        if self._tap.config_file is not None:
            with open(self._tap.config_file, "w") as outfile:
                json.dump(self._tap._config, outfile, indent=4)

    @classmethod
    def create_for_stream(cls, stream) -> "ServiceChannelAuthenticator":
        return cls(
            stream=stream,
            auth_endpoint="https://login.servicechannel.com/oauth/token",
        )

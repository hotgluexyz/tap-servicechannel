"""Tests standard tap features using the built-in SDK tests library."""

import datetime

from hotglue_singer_sdk.testing import get_standard_tap_tests

from tap_servicechannel.tap import TapServiceChannel

SAMPLE_CONFIG = {
    "client_id": "test_client_id",
    "client_secret": "test_client_secret",
    "username": "test_username",
    "password": "test_password",
    "start_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
}


# Run standard built-in tap tests from the SDK:
def test_standard_tap_tests():
    """Run standard tap tests from the SDK."""
    tests = get_standard_tap_tests(TapServiceChannel, config=SAMPLE_CONFIG)
    for test in tests:
        test()


# TODO: Create additional tests as appropriate for your tap.

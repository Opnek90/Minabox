"""Shared setup for the test run across all services."""

import pytest
import structlog


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Start every test with an untouched structlog configuration.

    structlog.configure() acts globally on the whole process. A service that
    does it at import time thereby configures the tests of every other service
    too - and a make_filtering_bound_logger(INFO) stops
    structlog.testing.capture_logs() from seeing debug events. That is exactly
    what test_a_disabled_led_never_claims_its_pin failed on, but only in the
    full run, never on its own: the order of the test files decided it.

    The root cause is fixed in media-downloader-service. This fixture makes sure
    the next service that configures at import time does not cause days of
    unfindable failures again.
    """
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()

"""Gemeinsame Vorkehrungen fuer den Testlauf ueber alle Dienste hinweg."""

import pytest
import structlog


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Jeden Test mit unveraenderter structlog-Konfiguration beginnen lassen.

    structlog.configure() wirkt global auf den ganzen Prozess. Ein Dienst, der
    das beim Import tut, richtet damit auch die Tests aller anderen Dienste
    ein - und ein make_filtering_bound_logger(INFO) laesst
    structlog.testing.capture_logs() keine debug-Ereignisse mehr sehen. Genau
    daran ist test_a_disabled_led_never_claims_its_pin gescheitert, aber nur im
    Gesamtlauf, nie allein: die Reihenfolge der Testdateien entschied darueber.

    Die Ursache ist im media-downloader-service behoben. Diese Vorkehrung
    stellt sicher, dass der naechste Dienst, der beim Import konfiguriert,
    nicht wieder tagelang unauffindbare Fehlschlaege verursacht.
    """
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()

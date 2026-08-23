"""Tests for the mock reader's simulated tag rhythm."""

from __future__ import annotations

from rfid_service.config_schema import MockReaderConfig
from rfid_service.infrastructure.hardware.mock_reader import MockReader


def _reads(reader: MockReader, count: int) -> list[str | None]:
    return [reader.read_tag_uid() for _ in range(count)]


def test_uninitialised_reader_reports_nothing() -> None:
    reader = MockReader("i2c", config=MockReaderConfig(tags=["AABB"]))

    assert reader.read_tag_uid() is None


def test_tag_is_held_for_the_configured_number_of_reads() -> None:
    """A mock that changed tag on every read made the scan loop untestable."""
    reader = MockReader(
        "i2c", config=MockReaderConfig(tags=["AABB"], hold_reads=3, gap_reads=2)
    )
    reader.initialize()

    assert _reads(reader, 5) == ["AABB", "AABB", "AABB", None, None]


def test_tags_are_cycled_with_gaps_between_them() -> None:
    reader = MockReader(
        "i2c",
        config=MockReaderConfig(tags=["AABB", "CCDD"], hold_reads=2, gap_reads=1),
    )
    reader.initialize()

    assert _reads(reader, 6) == ["AABB", "AABB", None, "CCDD", "CCDD", None]


def test_no_tags_configured_means_always_empty() -> None:
    reader = MockReader("i2c", config=MockReaderConfig(tags=[]))
    reader.initialize()

    assert _reads(reader, 3) == [None, None, None]


def test_zero_gap_keeps_the_reader_occupied() -> None:
    reader = MockReader(
        "i2c",
        config=MockReaderConfig(tags=["AABB", "CCDD"], hold_reads=1, gap_reads=0),
    )
    reader.initialize()

    assert _reads(reader, 4) == ["AABB", "CCDD", "AABB", "CCDD"]


def test_cleanup_stops_reporting_tags() -> None:
    reader = MockReader("i2c", config=MockReaderConfig(tags=["AABB"]))
    reader.initialize()
    reader.cleanup()

    assert reader.read_tag_uid() is None


def test_reader_id_defaults_to_the_interface() -> None:
    assert MockReader("spi", config=MockReaderConfig()).reader_id == "mock_spi"

"""Tests for the debug export.

The focus is on the promises the export makes to the user: no secret leaves the
box, a broken collector does not break the archive, and the option tiers cannot
be talked past.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from backend_service.core.debug_export import framework as fw
from backend_service.core.debug_export.redaction import (
    REDACTED,
    SecretTripwire,
    pseudonymize,
    scrub,
    scrub_text,
)

# ── Redaction ────────────────────────────────────────────────────────────────


def test_scrub_removes_secret_keys_but_keeps_diagnostics():
    payload = {
        "api_key": "supergeheim1234",
        "web_password_hash": "$2b$12$abcdefghijklmno",
        "device_id": "box1",
        "keyboard_layout": "de",
        "nested": {"token": "abcdef123456", "temperature": 42},
    }
    result = scrub(payload)
    assert result["api_key"] == REDACTED
    assert result["web_password_hash"] == REDACTED
    assert result["nested"]["token"] == REDACTED
    # Diagnostics must survive - a redactor that eats the useful half is useless.
    assert result["device_id"] == "box1"
    assert result["keyboard_layout"] == "de"
    assert result["nested"]["temperature"] == 42


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer abcdef0123456789abcdef",
        "X-Api-Key: 0123456789abcdef0123",
        "psk=meinWlanPasswort",
        "https://user:passwort@example.com/feed.xml",
        "kontakt@example.com",
    ],
)
def test_scrub_text_masks_credentials(text):
    assert REDACTED in scrub_text(text)


def test_scrub_text_keeps_short_hashes():
    """A 40-char SHA is a bootloader/git revision, not a secret."""
    revision = "57db150d63864d47e6c9071f6b086a5401eb4e92"
    assert revision in scrub_text(f"bootloader {revision}")


def test_scrub_text_masks_long_hex_blobs():
    key = "a" * 64
    assert key not in scrub_text(f"HOST_HELPER_API_KEY war {key}")


def test_pseudonymize_is_stable_within_salt_and_differs_across_salts():
    first = pseudonymize("MeinWLAN", "salt-a")
    assert first == pseudonymize("MeinWLAN", "salt-a")
    assert first != pseudonymize("MeinWLAN", "salt-b")
    assert "MeinWLAN" not in (first or "")


def test_tripwire_finds_and_removes_real_values():
    tripwire = SecretTripwire({"env:HOST_HELPER_API_KEY": "geheimer-schluessel-1234"})
    payload = "config sagt key=geheimer-schluessel-1234 ende"
    assert tripwire.find(payload) == ["env:HOST_HELPER_API_KEY"]
    cleaned, found = tripwire.redact(payload)
    assert found == ["env:HOST_HELPER_API_KEY"]
    assert "geheimer-schluessel-1234" not in cleaned


def test_tripwire_ignores_short_values():
    """Short values produce false positives and are not worth protecting."""
    tripwire = SecretTripwire({"env:PORT": "1883"})
    assert tripwire.find("mqtt runs on 1883") == []


# ── Options ──────────────────────────────────────────────────────────────────


def test_options_presets():
    minimal = fw.ExportOptions.from_payload({"preset": "minimal"})
    assert minimal.logs is False
    assert minimal.media == fw.MEDIA_OFF

    full = fw.ExportOptions.from_payload({"preset": "full"})
    assert full.history is True
    assert full.media == fw.MEDIA_FILENAMES


def test_options_system_block_cannot_be_switched_off():
    options = fw.ExportOptions.from_payload({"system": False})
    assert options.system is True


def test_options_reject_unknown_values():
    options = fw.ExportOptions.from_payload(
        {"preset": "gibtsnicht", "media": "alles", "log_tail": "viele"}
    )
    assert options.preset == "recommended"
    assert options.media == fw.MEDIA_COUNTS
    assert options.log_tail == fw.DEFAULT_LOG_TAIL


def test_options_log_tail_is_clamped():
    assert (
        fw.ExportOptions.from_payload({"log_tail": 999999}).log_tail == fw.MAX_LOG_TAIL
    )
    assert fw.ExportOptions.from_payload({"log_tail": 1}).log_tail == 50


def test_restrict_to_standard_drops_the_elevated_tiers():
    options = fw.ExportOptions.from_payload(
        {"preset": "full", "include_db": True, "sound_test": True}
    )
    options.restrict_to_standard()
    assert options.history is False
    assert options.include_db is False
    assert options.sound_test is False
    assert options.media == fw.MEDIA_COUNTS


def test_options_sound_test_is_off_in_every_preset():
    """Audible side effect: only a deliberate tick may turn it on, never a preset."""
    for preset in ("minimal", "recommended", "full"):
        assert fw.ExportOptions.from_payload({"preset": preset}).sound_test is False


# ── Collector runner ─────────────────────────────────────────────────────────


@pytest.fixture
def clean_registry():
    """The registry is module-level state; keep tests independent."""
    original = dict(fw.REGISTRY)
    fw.REGISTRY.clear()
    yield fw.REGISTRY
    fw.REGISTRY.clear()
    fw.REGISTRY.update(original)


def _context(**kwargs):
    from pathlib import Path

    defaults = {
        "options": fw.ExportOptions(),
        "salt": "test-salt",
        "data_path": Path("/tmp"),
        "device_id": "box1",
    }
    defaults.update(kwargs)
    return fw.ExportContext(**defaults)


@pytest.mark.asyncio
async def test_a_failing_collector_does_not_break_the_export(clean_registry):
    @fw.register("test.broken", fw.BLOCK_SYSTEM)
    def broken(ctx):
        raise RuntimeError("Kaputt")

    @fw.register("test.works", fw.BLOCK_SYSTEM)
    def works(ctx):
        return {"system/ok.json": {"value": 1}}

    outcomes = await fw.run_collectors(_context())
    by_name = {o.name: o for o in outcomes}
    assert by_name["test.broken"].status == "failed"
    assert "Kaputt" in by_name["test.broken"].error
    assert by_name["test.works"].status == "ok"


@pytest.mark.asyncio
async def test_collector_timeout_is_recorded_not_raised(clean_registry):
    import asyncio

    @fw.register("test.slow", fw.BLOCK_SYSTEM, timeout=0.05)
    async def slow(ctx):
        await asyncio.sleep(5)
        return {}

    outcomes = await fw.run_collectors(_context())
    assert outcomes[0].status == "failed"
    assert "Timed out" in outcomes[0].error


@pytest.mark.asyncio
async def test_collector_returning_only_an_error_is_failed_not_ok(clean_registry):
    """The 2026-08-18 package had system/docker.json = {"error": ...} at status "ok".

    The triage checks the manifest, saw "ok", and reported "kein Befund" while
    restart counts and OOM kills were in fact missing.
    """

    @fw.register("test.caught_its_own_error", fw.BLOCK_SYSTEM)
    def caught(ctx):
        return {
            "system/docker.json": {
                "error": "DockerException: Permission denied",
            }
        }

    outcomes = await fw.run_collectors(_context())
    assert outcomes[0].status == "failed"
    assert "Permission denied" in outcomes[0].error
    # The error file still travels with the archive - it is evidence.
    assert "system/docker.json" in outcomes[0].files


@pytest.mark.asyncio
async def test_partial_result_with_a_side_error_stays_ok(clean_registry):
    """Real data plus a sub-error is a partial result, not a failure."""

    @fw.register("test.partial", fw.BLOCK_SYSTEM)
    def partial(ctx):
        return {
            "system/docker.json": {
                "server_version": "29.7.2",
                "df_error": "TimeoutError",
            }
        }

    outcomes = await fw.run_collectors(_context())
    assert outcomes[0].status == "ok"


@pytest.mark.asyncio
async def test_one_good_file_beside_an_error_file_stays_ok(clean_registry):
    @fw.register("test.mixed", fw.BLOCK_SYSTEM)
    def mixed(ctx):
        return {
            "system/a.json": {"error": "nope"},
            "system/b.json": {"value": 1},
        }

    outcomes = await fw.run_collectors(_context())
    assert outcomes[0].status == "ok"


@pytest.mark.asyncio
async def test_manifest_carries_the_failed_status(clean_registry):
    """Whatever the collector did, the manifest must not claim success."""

    @fw.register("system.docker", fw.BLOCK_SYSTEM)
    def docker_collector(ctx):
        return {"system/docker.json": {"error": "DockerException: Permission denied"}}

    outcomes = await fw.run_collectors(_context())
    entry = outcomes[0].as_manifest()
    assert entry["status"] == "failed"
    assert "Permission denied" in entry["error"]


@pytest.mark.asyncio
async def test_deselected_blocks_are_reported_as_skipped(clean_registry):
    @fw.register("test.history", fw.BLOCK_HISTORY)
    def history(ctx):  # pragma: no cover - must not run
        raise AssertionError("must not run")

    options = fw.ExportOptions.from_payload({"history": False})
    outcomes = await fw.run_collectors(_context(options=options))
    assert outcomes[0].status == "skipped_by_user"


# ── Archive ──────────────────────────────────────────────────────────────────


def _read_archive(payload: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(payload))


def test_archive_blocks_a_leaked_secret_and_records_it_loudly():
    tripwire = SecretTripwire({"env:HOST_HELPER_API_KEY": "streng-geheim-4711"})
    outcome = fw.CollectorOutcome(
        "test.leaky",
        "ok",
        1,
        files={"config/leak.json": {"irgendwas": "streng-geheim-4711"}},
    )
    archive, manifest = fw.build_archive(_context(), [outcome], tripwire)

    content = _read_archive(archive).read("config/leak.json").decode()
    assert "streng-geheim-4711" not in content
    blocked = manifest["secret_tripwire"]["blocked"]
    assert blocked and blocked[0]["collector"] == "test.leaky"


def test_archive_always_contains_manifest_and_readme():
    archive, _ = fw.build_archive(_context(), [], SecretTripwire())
    names = _read_archive(archive).namelist()
    assert "manifest.json" in names
    assert "README.txt" in names


def test_readme_lists_only_what_was_selected():
    options = fw.ExportOptions.from_payload({"preset": "minimal"})
    archive, _ = fw.build_archive(_context(options=options), [], SecretTripwire())
    readme = _read_archive(archive).read("README.txt").decode()
    assert "Netzwerk-Zustand" in readme
    assert "Abspielverlauf" not in readme


def test_size_budget_truncates_logs_before_dropping_essentials(clean_registry):
    @fw.register("test.logs", fw.BLOCK_LOGS, bulky=True)
    def logs(ctx):  # pragma: no cover - registered for the bulky flag only
        return {}

    essential = fw.CollectorOutcome(
        "test.essential", "ok", 1, files={"system/state.json": {"wichtig": True}}
    )
    bulky = fw.CollectorOutcome(
        "test.logs",
        "ok",
        1,
        files={"services/audio/logs.txt": "\n".join(f"zeile {i}" for i in range(5000))},
    )
    archive, manifest = fw.build_archive(
        _context(), [essential, bulky], SecretTripwire(), max_total_bytes=8000
    )

    names = _read_archive(archive).namelist()
    assert "system/state.json" in names  # essentials survive
    assert manifest["truncations"], "the truncation has to be recorded in the manifest"
    truncated = manifest["truncations"][0]
    assert truncated["path"] == "services/audio/logs.txt"
    assert truncated["status"] == "truncated"
    # The tail is what matters in a log - the last lines must be the ones kept.
    kept = _read_archive(archive).read("services/audio/logs.txt").decode()
    assert "zeile 4999" in kept


def test_manifest_records_every_collector_outcome():
    outcomes = [
        fw.CollectorOutcome("a.ok", "ok", 5, files={"a.json": {}}),
        fw.CollectorOutcome("b.failed", "failed", 7, error="kaputt"),
        fw.CollectorOutcome("c.skipped", "skipped_by_user", 0),
    ]
    _, manifest = fw.build_archive(_context(), outcomes, SecretTripwire())
    statuses = {c["name"]: c["status"] for c in manifest["collectors"]}
    assert statuses == {
        "a.ok": "ok",
        "b.failed": "failed",
        "c.skipped": "skipped_by_user",
    }
    assert manifest["schema_version"] == fw.SCHEMA_VERSION


def test_json_files_are_scrubbed_on_the_way_into_the_archive():
    outcome = fw.CollectorOutcome(
        "test.config",
        "ok",
        1,
        files={"config/x.json": {"api_key": "abc123", "port": 8080}},
    )
    archive, _ = fw.build_archive(_context(), [outcome], SecretTripwire())
    payload = json.loads(_read_archive(archive).read("config/x.json"))
    assert payload["api_key"] == REDACTED
    assert payload["port"] == 8080


# ── Endpoint guards ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "address,expected",
    [
        ("192.168.1.50", True),
        ("10.0.0.5", True),
        ("172.17.0.2", True),
        ("127.0.0.1", True),
        ("169.254.10.1", True),
        ("fd00::1", True),
        ("8.8.8.8", False),
        ("93.184.216.34", False),
        # Python counts the documentation and benchmark ranges as private,
        # because they are not routable. For the question this check asks -
        # "did the call come from the internet?" - that is the right answer,
        # even though the names suggest otherwise.
        ("203.0.113.7", True),
        ("kein-ip", False),
        (None, False),
    ],
)
def test_private_network_check(address, expected):
    from backend_service.api.routes_debug import _is_private_client

    assert _is_private_client(address) is expected

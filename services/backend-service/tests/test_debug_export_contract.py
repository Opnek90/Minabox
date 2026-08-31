"""Contract test: the export must match what the analysis skill expects.

The skill reads a fixed layout (references/export-schema.md). If someone adds a
collector and forgets the documentation, the analysis side silently goes blind
on that data - so this test fails instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend_service.core.debug_export import REGISTRY, SCHEMA_VERSION

# The references live outside the service; run-tests.sh mounts them at /w. When
# they are absent (a bare service checkout) the test skips rather than lying.
SCHEMA_RELATIVE = ".claude/skills/minabox-debug-analyze/references/export-schema.md"


def _schema_candidates() -> list[Path]:
    candidates = [Path("/w/references/export-schema.md")]
    # Walk up from the test file until the repository root turns up. The depth
    # differs between the mounted test container and a checkout.
    here = Path(__file__).resolve()
    candidates.extend(parent / SCHEMA_RELATIVE for parent in here.parents)
    return candidates


def _schema_text() -> str:
    for candidate in _schema_candidates():
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    pytest.skip("export-schema.md not available")


def test_every_collector_is_documented():
    schema = _schema_text()
    undocumented = sorted(name for name in REGISTRY if name not in schema)
    assert not undocumented, (
        "These collectors are missing from references/export-schema.md: "
        f"{undocumented}. Without an entry the analysis knows nothing about them."
    )


def test_no_documented_collector_disappeared():
    """The other direction: a removed collector leaves the skill looking for ghosts."""
    schema = _schema_text()
    section = schema.split("### Collector names")[1].split("### Files")[0]
    documented = {
        token.strip().strip("`,")
        for token in section.replace("\n", " ").split()
        if "." in token
    }
    documented = {
        name.strip("`,.")
        for name in documented
        if name.startswith(
            (
                "system.",
                "services.",
                "logs.",
                "config.",
                "db.",
                "media.",
                "client.",
                "settings.",
                "network.",
                "history.",
                "database.",
                "audio.",
            )
        )
    }
    missing = sorted(name for name in documented if name not in REGISTRY)
    assert not missing, f"Documented but not in the code: {missing}"


def test_schema_version_is_documented():
    schema = _schema_text()
    assert f"## schema_version {SCHEMA_VERSION}" in schema


def test_collector_blocks_are_known():
    """Every collector belongs to a block the dialog can actually offer."""
    from backend_service.core.debug_export.framework import ExportOptions

    options = ExportOptions()
    for name, collector in REGISTRY.items():
        assert collector.block in {
            "system",
            "logs",
            "settings",
            "network",
            "media",
            "history",
            "client",
            "database",
            "sound_test",
        }, f"{name} declares an unknown block: {collector.block}"
        # block_enabled must have an answer for it, otherwise it would never run.
        assert isinstance(options.block_enabled(collector.block), bool)

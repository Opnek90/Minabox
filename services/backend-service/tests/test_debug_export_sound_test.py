"""The sound-test collector: opt-in, admin-only, and never silent about failure."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend_service.core.debug_export.collectors.audio import collect_sound_test
from backend_service.core.debug_export.framework import ExportContext, ExportOptions


def _context(**kwargs) -> ExportContext:
    defaults = {
        "options": ExportOptions(),
        "salt": "test-salt",
        "data_path": Path("/tmp"),
        "device_id": "box1",
    }
    defaults.update(kwargs)
    return ExportContext(**defaults)


@pytest.mark.asyncio
async def test_collect_sound_test_records_the_chain_result(monkeypatch):
    async def fake_chain():
        return {
            "steps": [{"id": "sink_level", "ok": True, "fixed": True, "detail": "5% -> 60%"}],
            "fixed": ["sink_level"],
            "cause": "sink_level",
            "tone_played": True,
            "host_checks_available": True,
            "timestamp": "2026-08-26T10:00:00+00:00",
        }

    monkeypatch.setattr(
        "backend_service.api.routes_audio.run_sound_test_chain", fake_chain
    )

    files = await collect_sound_test(_context())
    result = files["audio/sound_test.json"]
    assert result["tone_played"] is True
    assert result["cause"] == "sink_level"


@pytest.mark.asyncio
async def test_collect_sound_test_reports_a_failed_chain_as_an_error_file(monkeypatch):
    async def fake_chain():
        raise RuntimeError("audio service unavailable")

    monkeypatch.setattr(
        "backend_service.api.routes_audio.run_sound_test_chain", fake_chain
    )

    files = await collect_sound_test(_context())
    assert "audio service unavailable" in files["audio/sound_test.json"]["error"]

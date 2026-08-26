"""Sound-test collector: opt-in only, and the one with a physical side effect.

Runs the same chain as "Fix sound problem" (docs/services/Offene-Punkte.md
1.7) and records what it found - including whether the test tone actually
played. Everything else in the export only *reads* the box; this one makes it
play a tone through the speaker, which is why it is admin-only and never part
of a preset (see BLOCK_SOUND_TEST in framework.py).
"""

from __future__ import annotations

from typing import Any

import structlog

from backend_service.core.debug_export.framework import (
    BLOCK_SOUND_TEST,
    ExportContext,
    register,
)

logger = structlog.get_logger(__name__)


@register("audio.sound_test", BLOCK_SOUND_TEST, timeout=60.0)
async def collect_sound_test(ctx: ExportContext) -> dict[str, Any]:
    """Run the sound-repair chain once and keep its result for the export."""
    from backend_service.api.routes_audio import run_sound_test_chain

    try:
        result = await run_sound_test_chain()
    except Exception as e:
        logger.warning("debug_export_sound_test_failed", error=str(e))
        return {"audio/sound_test.json": {"error": f"{type(e).__name__}: {e}"}}
    return {"audio/sound_test.json": result}

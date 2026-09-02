"""Synthesis against a stand-in for Piper.

The real binary is not in the test image, and it is not what these tests are
about. What matters is that the long-lived process behaves: that a half-written
clip never becomes visible, that a Piper which fails, hangs or dies is reported
rather than handed on as a valid file, and that a broken one is dropped instead
of reused - a stream that might carry a stale answer is worse than a cold
start.
"""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path

import pytest

from tts_service.synthesizer import PiperProcess, SynthesisError, VoicePool

# A stand-in for Piper in --json-input mode: reads one JSON line, writes the
# file it names, and echoes the path back on stdout - which is the completion
# signal the real one gives.
FAKE_PIPER = r"""#!/bin/sh
while IFS= read -r line; do
  out=$(printf '%s' "$line" | sed 's/.*"output_file": *"\([^"]*\)".*/\1/')
  printf 'RIFFdummy' > "$out"
  echo "$out"
done
"""


def _binary(tmp_path: Path, body: str = FAKE_PIPER) -> Path:
    script = tmp_path / "piper"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _process(binary: Path, *, timeout: float = 5.0) -> PiperProcess:
    return PiperProcess(
        binary=binary,
        model=Path("/voices/de.onnx"),
        espeak_data=Path("/espeak"),
        timeout_sec=timeout,
    )


@pytest.mark.asyncio
async def test_a_finished_clip_lands_under_its_own_name(tmp_path):
    piper = _process(_binary(tmp_path))
    output = tmp_path / "clip.wav"

    assert await piper.synthesize("Hallo", output) == output
    assert output.read_bytes() == b"RIFFdummy"
    # Nothing half-written left behind.
    assert list(tmp_path.glob("*.part")) == []
    await piper.close()


@pytest.mark.asyncio
async def test_the_process_survives_between_phrases(tmp_path):
    """The whole point: the 63 MB model is loaded once, not per phrase."""
    piper = _process(_binary(tmp_path))

    await piper.synthesize("eins", tmp_path / "a.wav")
    first = piper._process
    await piper.synthesize("zwei", tmp_path / "b.wav")

    assert piper._process is first
    assert (tmp_path / "b.wav").exists()
    await piper.close()


@pytest.mark.asyncio
async def test_a_piper_that_dies_is_reported_and_dropped(tmp_path):
    piper = _process(_binary(tmp_path, '#!/bin/sh\necho "boom" >&2\nexit 3\n'))

    with pytest.raises(SynthesisError, match="stopped"):
        await piper.synthesize("Hallo", tmp_path / "clip.wav")

    assert not (tmp_path / "clip.wav").exists()
    assert list(tmp_path.glob("*.part")) == []
    # Dropped, so the next request starts a fresh one rather than reading a
    # stale line off a dead stream.
    assert piper._process is None


@pytest.mark.asyncio
async def test_an_empty_result_counts_as_a_failure(tmp_path):
    """A zero-byte WAV would be cached and played as silence forever."""
    body = (
        "#!/bin/sh\n"
        "while IFS= read -r line; do\n"
        "  out=$(printf '%s' \"$line\" | sed 's/.*\"output_file\": *\"\\([^\"]*\\)\".*/\\1/')\n"
        '  : > "$out"\n'
        '  echo "$out"\n'
        "done\n"
    )
    piper = _process(_binary(tmp_path, body))

    with pytest.raises(SynthesisError, match="no audio"):
        await piper.synthesize("Hallo", tmp_path / "clip.wav")

    assert not (tmp_path / "clip.wav").exists()


@pytest.mark.asyncio
async def test_a_hanging_piper_is_killed(tmp_path):
    piper = _process(_binary(tmp_path, "#!/bin/sh\nsleep 30\n"), timeout=0.3)

    with pytest.raises(SynthesisError, match="did not finish"):
        await piper.synthesize("Hallo", tmp_path / "clip.wav")

    assert not (tmp_path / "clip.wav").exists()
    assert piper._process is None


@pytest.mark.asyncio
async def test_a_missing_binary_is_reported_not_raised_raw(tmp_path):
    piper = _process(tmp_path / "nowhere")
    with pytest.raises(SynthesisError, match="not available"):
        await piper.synthesize("Hallo", tmp_path / "clip.wav")


@pytest.mark.asyncio
async def test_the_text_travels_as_json_not_on_the_command_line(tmp_path):
    """Card names are arbitrary user text, quotes and newlines included."""
    body = (
        "#!/bin/sh\n"
        "while IFS= read -r line; do\n"
        '  printf "%s" "$line" >> /dev/stdout.seen\n'
        "  out=$(printf '%s' \"$line\" | sed 's/.*\"output_file\": *\"\\([^\"]*\\)\".*/\\1/')\n"
        '  printf "%s" "$line" > "$out".json\n'
        '  printf RIFF > "$out"\n'
        '  echo "$out"\n'
        "done\n"
    )
    piper = _process(_binary(tmp_path, body))

    await piper.synthesize('Die "Maus"\nund der Elefant', tmp_path / "clip.wav")

    seen = next(iter(tmp_path.glob("*.json")))
    import json as _json

    payload = _json.loads(seen.read_text())
    assert payload["text"] == 'Die "Maus"\nund der Elefant'
    await piper.close()


@pytest.mark.asyncio
async def test_the_output_directory_is_created(tmp_path):
    piper = _process(_binary(tmp_path))
    output = tmp_path / "fresh" / "clip.wav"

    await piper.synthesize("Hallo", output)

    assert output.exists()
    await piper.close()


@pytest.mark.asyncio
async def test_concurrent_phrases_do_not_share_a_pipe(tmp_path):
    """Two answers down one stdin would arrive in an order nobody can match."""
    piper = _process(_binary(tmp_path))

    await asyncio.gather(
        piper.synthesize("eins", tmp_path / "a.wav"),
        piper.synthesize("zwei", tmp_path / "b.wav"),
    )

    assert (tmp_path / "a.wav").read_bytes() == b"RIFFdummy"
    assert (tmp_path / "b.wav").read_bytes() == b"RIFFdummy"
    await piper.close()


# --- the pool ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_pool_keeps_one_process_per_voice(tmp_path):
    pool = VoicePool(
        binary=_binary(tmp_path), espeak_data=Path("/espeak"), timeout_sec=5.0
    )
    de, en = Path("/voices/de.onnx"), Path("/voices/en.onnx")

    assert pool.for_model(de) is pool.for_model(de)
    assert pool.for_model(de) is not pool.for_model(en)
    await pool.close()


@pytest.mark.asyncio
async def test_the_pool_starts_nothing_it_is_not_asked_for(tmp_path):
    """A box has one announcement language; the other model must not be read
    into memory for nothing."""
    pool = VoicePool(
        binary=_binary(tmp_path), espeak_data=Path("/espeak"), timeout_sec=5.0
    )
    await pool.synthesize("Hallo", model=Path("/voices/de.onnx"), output=tmp_path / "a.wav")

    assert list(pool._processes) == ["de.onnx"]
    await pool.close()

"""Turning a sentence into a WAV file, with Piper.

Piper is driven as a **long-lived subprocess**, one per voice, fed one line of
JSON per phrase. That is the whole reason this file is more than a
``create_subprocess_exec`` call:

Starting ``piper`` per phrase means loading a 63 MB ONNX model per phrase.
Measured end to end on a Raspberry Pi 4:

============================================  ========
one phrase, process started for it            4 - 5 s
one phrase, process already running           1.5 - 2.3 s
the first phrase after the container started  ~7 s
a phrase that is already in the cache         ~70 ms
============================================  ========

So the load costs more than the synthesis does. Keeping the process alive pays
it once per container instead of once per card, and leaves only the inference -
which is what an announcement can live with. Everything after the first time a
phrase is said is a cache hit and never reaches this module at all.

Piper is a subprocess rather than a Python binding on purpose: the published
Linux build is one self-contained tarball - executable, ONNX runtime, espeak
phoneme data - and needs neither a compiler nor a wheel that happens to exist
for this Python version on arm64.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections import deque
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

#: How much of Piper's own logging is kept for an error message. It writes a
#: handful of lines per phrase, so this is a few phrases' worth - enough to say
#: what went wrong, bounded so a long-running process cannot grow into it.
_STDERR_LINES = 20


class SynthesisError(RuntimeError):
    """Piper could not produce a clip."""


class PiperProcess:
    """One Piper, kept running, speaking one voice.

    Started on first use and never on startup: a box has one announcement
    language, so the second voice's model normally never has to be read into
    memory at all.
    """

    def __init__(
        self,
        *,
        binary: Path,
        model: Path,
        espeak_data: Path,
        timeout_sec: float,
    ) -> None:
        self._binary = binary
        self._model = model
        self._espeak_data = espeak_data
        self._timeout_sec = timeout_sec
        self._process: asyncio.subprocess.Process | None = None
        self._stderr: deque[str] = deque(maxlen=_STDERR_LINES)
        self._drain: asyncio.Task[None] | None = None
        # One phrase at a time down one pipe. The caller serialises too, but a
        # shared process that relies on its callers for that is a trap.
        self._lock = asyncio.Lock()

    @property
    def model_name(self) -> str:
        return self._model.name

    async def _start(self) -> asyncio.subprocess.Process:
        cmd = [
            str(self._binary),
            "--json-input",
            "--model",
            str(self._model),
            "--espeak_data",
            str(self._espeak_data),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as exc:
            raise SynthesisError(f"Piper is not available: {exc}") from exc

        self._process = process
        self._stderr.clear()
        # Piper logs a few lines per phrase. Nobody reading them would fill the
        # pipe buffer and wedge the process mid-sentence, so they are drained
        # continuously and the last of them kept for error messages.
        self._drain = asyncio.create_task(self._drain_stderr(process))
        logger.info("piper_started", voice=self.model_name, pid=process.pid)
        return process

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> None:
        assert process.stderr is not None
        while True:
            line = await process.stderr.readline()
            if not line:
                return
            self._stderr.append(line.decode(errors="replace").rstrip())

    def _recent_errors(self) -> str:
        return " | ".join(list(self._stderr)[-3:])

    async def _stop(self) -> None:
        """Drop the process. The next request starts a fresh one.

        Used after every failure, deliberately: a phrase that timed out may
        still be on its way down the pipe, and a stream that might carry a
        stale answer is worse than a cold start.
        """
        process, self._process = self._process, None
        drain, self._drain = self._drain, None
        if drain and not drain.done():
            drain.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await drain
        if process is None or process.returncode is not None:
            return
        try:
            process.kill()
        except ProcessLookupError:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=5.0)

    async def synthesize(self, text: str, output: Path) -> Path:
        """Speak *text* into *output*.

        Piper is given a temporary name next to the target and the file is
        renamed into place afterwards. The cache directory is shared with the
        audio service, and the rename is the only way to be sure the reader
        never opens a half-written clip - a truncated announcement sounds like
        a fault in the box.
        """
        output.parent.mkdir(parents=True, exist_ok=True)
        # A random suffix, so two requests for the same phrase cannot write
        # into each other's partial file. The rename makes the loser harmless -
        # both wrote the same audio.
        tmp = output.with_name(f"{output.name}.{uuid.uuid4().hex[:8]}.part")

        async with self._lock:
            try:
                await self._run(text, tmp)
            except SynthesisError:
                tmp.unlink(missing_ok=True)
                await self._stop()
                raise

        if not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            await self._stop()
            raise SynthesisError("Piper produced no audio")

        try:
            tmp.replace(output)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise SynthesisError(f"Could not store the clip: {exc}") from exc

        logger.debug(
            "clip_synthesized", path=str(output), bytes=output.stat().st_size
        )
        return output

    async def _run(self, text: str, tmp: Path) -> None:
        """One line in, one line out. Raises SynthesisError on anything else."""
        process = self._process
        if process is None or process.returncode is not None:
            process = await self._start()

        assert process.stdin is not None and process.stdout is not None
        # json.dumps also does the escaping that keeps this one line: a card
        # name is arbitrary user text and may contain quotes or newlines.
        line = json.dumps({"text": text, "output_file": str(tmp)}) + "\n"

        try:
            process.stdin.write(line.encode("utf-8"))
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            raise SynthesisError(f"Piper is gone: {exc}") from exc

        try:
            # Piper writes the finished file's path on stdout when a line is
            # done. That, not the file appearing, is the completion signal -
            # the file exists from the moment it starts writing it.
            done = await asyncio.wait_for(
                process.stdout.readline(), timeout=self._timeout_sec
            )
        except TimeoutError:
            raise SynthesisError(
                f"Piper did not finish within {self._timeout_sec:.0f} s"
            ) from None

        if not done:
            raise SynthesisError(
                f"Piper stopped ({process.returncode}): {self._recent_errors()}"
            )

    async def close(self) -> None:
        """Shut the process down - for the service's own shutdown."""
        await self._stop()


class VoicePool:
    """The running Piper processes, one per voice, started on demand."""

    def __init__(
        self, *, binary: Path, espeak_data: Path, timeout_sec: float
    ) -> None:
        self._binary = binary
        self._espeak_data = espeak_data
        self._timeout_sec = timeout_sec
        self._processes: dict[str, PiperProcess] = {}

    def for_model(self, model: Path) -> PiperProcess:
        process = self._processes.get(model.name)
        if process is None:
            process = PiperProcess(
                binary=self._binary,
                model=model,
                espeak_data=self._espeak_data,
                timeout_sec=self._timeout_sec,
            )
            self._processes[model.name] = process
        return process

    async def synthesize(self, text: str, *, model: Path, output: Path) -> Path:
        return await self.for_model(model).synthesize(text, output)

    async def close(self) -> None:
        for process in self._processes.values():
            await process.close()
        self._processes.clear()

"""Noise filtering and honest truncation for log files in the export.

The 2026-08-18 package showed why this matters: logs/syslog-kernel.txt held
799 lines and practically all of it was Docker veth churn ("entered blocking
state", "entered promiscuous mode", "renamed from eth0"). The window started
two hours after the last boot, so the boot messages -- and with them any
under-voltage or mmc error -- had fallen out of the tail entirely.

Two rules follow from that:

1. Filter *before* truncating. Dropping noise first means the same line budget
   buys real history instead of bridge chatter.
2. Say what was cut. A truncated log without a header invites the reader to
   mistake absence of evidence for evidence of absence, which is exactly the
   wrong conclusion on a box that is failing intermittently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Container networking churn. Every container start/stop writes a handful of
# these, they carry no diagnostic value, and on a box that restarts services
# they crowd out everything else.
NOISE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"entered (blocking|forwarding|disabled|listening|learning) state",
        r"(entered|left) promiscuous mode",
        r"renamed from eth\d+",
        r"\bveth[0-9a-f]{4,}\b",
        r"\bbr-[0-9a-f]{10,}\b",
        r"docker0: port \d+",
        r"link becomes ready",
        r"IPv6: ADDRCONF\(NETDEV_(UP|CHANGE)\)",
    )
)

# Lines that must never be dropped, whatever the budget. These are the ones an
# intermittent-fault triage actually reads.
KEEP_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # Power: the Pi's classic failure mode
        r"under-?voltage",
        r"voltage normalised",
        r"throttl",
        # SD card / storage
        r"\bmmcblk\d",
        r"\bmmc\d+:",
        r"\bsdhci\b",
        r"\bEXT4-fs (error|warning)",
        r"I/O error",
        r"buffer I/O error",
        r"blk_update_request",
        r"critical (medium|target) error",
        r"\bread-only\b.*\bfilesystem\b",
        # Memory pressure
        r"out of memory",
        r"oom[-_]kill",
        r"oom_reaper",
        r"killed process \d+",
        # Boot: without these you cannot tell how far back the file reaches
        r"booting linux",
        r"linux version",
        r"kernel command line",
        r"\bwatchdog\b.*\b(reset|timeout)\b",
    )
)

# journalctl -o short-iso: "2026-08-18T13:45:01+0200 host kernel: ..."
_ISO_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:[+-]\d{2}:?\d{2}|Z)?)")
# /var/log/syslog: "Aug 18 13:45:01 host kernel: ..."
_SYSLOG_TS = re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})")


def _timestamp(line: str) -> str | None:
    for pattern in (_ISO_TS, _SYSLOG_TS):
        match = pattern.match(line.strip())
        if match:
            return match.group(1)
    return None


def is_noise(line: str) -> bool:
    """True if the line is container-networking churn and nothing else."""
    if any(pattern.search(line) for pattern in KEEP_PATTERNS):
        return False  # a keep-rule always wins over a noise-rule
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def is_always_keep(line: str) -> bool:
    return any(pattern.search(line) for pattern in KEEP_PATTERNS)


@dataclass
class FilterResult:
    lines: list[str] = field(default_factory=list)
    total_in: int = 0
    dropped_noise: int = 0
    dropped_budget: int = 0
    kept_important: int = 0
    period_start: str | None = None
    period_end: str | None = None

    @property
    def dropped_total(self) -> int:
        return self.dropped_noise + self.dropped_budget

    @property
    def truncated(self) -> bool:
        return self.dropped_total > 0


def filter_log_lines(lines: list[str], limit: int) -> FilterResult:
    """Drop noise, then trim to ``limit`` lines without losing important ones.

    Important lines (:data:`KEEP_PATTERNS`) survive the budget even when they
    are the oldest in the file -- otherwise a boot-time under-voltage warning
    is the first thing to go, which is precisely what happened.
    """
    result = FilterResult(total_in=len(lines))

    surviving: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if is_noise(line):
            result.dropped_noise += 1
        else:
            surviving.append((index, line))

    important = [(i, ln) for i, ln in surviving if is_always_keep(ln)]
    ordinary = [(i, ln) for i, ln in surviving if not is_always_keep(ln)]
    result.kept_important = len(important)

    if limit > 0 and len(surviving) > limit:
        room = max(limit - len(important), 0)
        kept_ordinary = ordinary[-room:] if room else []
        result.dropped_budget = len(ordinary) - len(kept_ordinary)
        chosen = sorted(important + kept_ordinary, key=lambda pair: pair[0])
    else:
        chosen = surviving

    result.lines = [line for _, line in chosen]

    stamps = [ts for ts in (_timestamp(line) for line in result.lines) if ts]
    if stamps:
        result.period_start, result.period_end = stamps[0], stamps[-1]

    return result


def build_header(result: FilterResult, *, source: str | None = None) -> str:
    """A header that keeps the reader from over-reading an empty log."""
    period = (
        f"{result.period_start} bis {result.period_end}"
        if result.period_start and result.period_end
        else "unbekannt (keine lesbaren Zeitstempel)"
    )
    parts = [
        f"# Abgedeckter Zeitraum: {period}",
        f"# Zeilen: {len(result.lines)} von {result.total_in} behalten, "
        f"{result.dropped_total} verworfen "
        f"(Rauschen: {result.dropped_noise}, Kuerzung: {result.dropped_budget})",
    ]
    if source:
        parts.insert(0, f"# Quelle: {source}")
    if result.kept_important:
        parts.append(
            f"# Immer behalten: {result.kept_important} Zeile(n) zu Unterspannung, "
            "Drosselung, mmc/SD, E/A-Fehler, OOM oder Boot"
        )
    parts.append(
        "# Hinweis: Diese Datei ist gefiltert und gekuerzt. Fehlt hier ein "
        "Hinweis, ist das kein Beleg dafuer, dass es das Problem nicht gab."
    )
    return "\n".join(parts)


def render_filtered_log(
    lines: list[str], limit: int, *, source: str | None = None
) -> str:
    """Filter, truncate and prepend the header. The header is always present."""
    result = filter_log_lines(lines, limit)
    return build_header(result, source=source) + "\n#\n" + "\n".join(result.lines)


def render_truncated_text(text: str, limit: int, *, source: str | None = None) -> str:
    """Header + tail for logs we only truncate (container logs), no noise filter."""
    lines = text.splitlines()
    kept = lines[-limit:] if limit > 0 and len(lines) > limit else lines
    result = FilterResult(
        lines=kept,
        total_in=len(lines),
        dropped_budget=max(len(lines) - len(kept), 0),
    )
    stamps = [ts for ts in (_timestamp(line) for line in kept) if ts]
    if stamps:
        result.period_start, result.period_end = stamps[0], stamps[-1]
    if not result.truncated:
        return text
    return build_header(result, source=source) + "\n#\n" + "\n".join(kept)

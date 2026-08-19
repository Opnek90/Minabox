"""Tests for kernel-log noise filtering and truncation headers.

Modelled on logs/syslog-kernel.txt from the 2026-08-18 package: 799 lines,
practically all Docker veth churn, window starting two hours after the last
boot so the boot messages were gone.
"""

from __future__ import annotations

from backend_service.core.debug_export import logfilter

VETH_NOISE = [
    "2026-08-18T11:20:{:02d}+0200 box1 kernel: veth1a2b3c4: renamed from eth0",
    "2026-08-18T11:20:{:02d}+0200 box1 kernel: br-9f8e7d6c5b4a: port 3(veth1a2b3c4) entered blocking state",
    "2026-08-18T11:20:{:02d}+0200 box1 kernel: br-9f8e7d6c5b4a: port 3(veth1a2b3c4) entered forwarding state",
    "2026-08-18T11:20:{:02d}+0200 box1 kernel: device veth1a2b3c4 entered promiscuous mode",
    "2026-08-18T11:20:{:02d}+0200 box1 kernel: docker0: port 2(vethabcdef1) entered disabled state",
]

BOOT_LINES = [
    "2026-08-18T09:00:01+0200 box1 kernel: Booting Linux on physical CPU 0x0000000000 [0x412fd050]",
    "2026-08-18T09:00:01+0200 box1 kernel: Linux version 6.12.62+rpt-rpi-v8",
    "2026-08-18T09:00:02+0200 box1 kernel: Kernel command line: console=serial0,115200",
]

TROUBLE_LINES = [
    "2026-08-18T09:14:33+0200 box1 kernel: hwmon hwmon1: Undervoltage detected!",
    "2026-08-18T09:15:00+0200 box1 kernel: mmc0: card at address 0001 error -110",
    "2026-08-18T10:02:11+0200 box1 kernel: EXT4-fs error (device mmcblk0p2): ext4_find_entry",
    "2026-08-18T10:30:00+0200 box1 kernel: Out of memory: Killed process 1234 (python3)",
    "2026-08-18T10:31:00+0200 box1 kernel: blk_update_request: I/O error, dev mmcblk0, sector 42",
]


def _noisy_log(noise_count: int = 780) -> list[str]:
    """Boot + trouble at the front, then a flood of veth churn, as observed."""
    lines = list(BOOT_LINES) + list(TROUBLE_LINES)
    for i in range(noise_count):
        lines.append(VETH_NOISE[i % len(VETH_NOISE)].format(i % 60))
    return lines


# ── Noise classification ─────────────────────────────────────────────────────


def test_veth_and_bridge_lines_are_noise():
    for template in VETH_NOISE:
        assert logfilter.is_noise(template.format(1)), template


def test_boot_and_trouble_lines_are_never_noise():
    for line in BOOT_LINES + TROUBLE_LINES:
        assert not logfilter.is_noise(line), line
        assert logfilter.is_always_keep(line), line


def test_a_keep_rule_beats_a_noise_rule():
    """An under-voltage warning that mentions a veth is still an under-voltage warning."""
    line = "... veth1a2b3c4 entered blocking state ... Undervoltage detected!"
    assert not logfilter.is_noise(line)


# ── Filtering before truncating ──────────────────────────────────────────────


def test_noise_is_dropped_before_the_line_budget_applies():
    result = logfilter.filter_log_lines(_noisy_log(), limit=100)
    assert result.dropped_noise >= 780
    text = "\n".join(result.lines)
    assert "entered blocking state" not in text
    assert "renamed from eth0" not in text


def test_boot_messages_survive_a_tight_budget():
    """The regression: boot and under-voltage fell out of the tail."""
    result = logfilter.filter_log_lines(_noisy_log(), limit=5)
    text = "\n".join(result.lines)
    assert "Booting Linux" in text
    assert "Undervoltage detected!" in text
    assert "Out of memory" in text
    assert "EXT4-fs error" in text
    assert "mmc0" in text


def test_important_lines_are_kept_even_beyond_the_limit():
    result = logfilter.filter_log_lines(_noisy_log(), limit=1)
    assert result.kept_important == len(BOOT_LINES) + len(TROUBLE_LINES)
    assert len(result.lines) >= result.kept_important


def test_ordinary_lines_are_tailed_not_headed():
    lines = [f"2026-08-18T10:00:{i:02d}+0200 box1 kernel: ordinary {i}" for i in range(50)]
    result = logfilter.filter_log_lines(lines, limit=5)
    assert result.lines[-1].endswith("ordinary 49")
    assert result.dropped_budget == 45


def test_original_order_is_preserved():
    result = logfilter.filter_log_lines(_noisy_log(), limit=20)
    assert result.lines == sorted(result.lines, key=lambda ln: _noisy_log().index(ln))


def test_nothing_is_dropped_when_it_fits():
    lines = list(BOOT_LINES)
    result = logfilter.filter_log_lines(lines, limit=100)
    assert result.lines == lines
    assert not result.truncated


# ── The header ───────────────────────────────────────────────────────────────


def test_header_reports_period_and_dropped_count():
    rendered = logfilter.render_filtered_log(_noisy_log(), 100, source="journalctl kernel")
    header = rendered.split("\n#\n")[0]
    assert "Abgedeckter Zeitraum" in header
    assert "2026-08-18T09:00:01+0200" in header
    assert "verworfen" in header
    assert "journalctl kernel" in header


def test_header_warns_against_reading_absence_as_evidence():
    rendered = logfilter.render_filtered_log(_noisy_log(), 100)
    assert "kein Beleg" in rendered.split("\n#\n")[0]


def test_header_handles_unparseable_timestamps():
    result = logfilter.filter_log_lines(["no timestamp here", "nor here"], limit=1)
    header = logfilter.build_header(result)
    assert "unbekannt" in header


def test_truncated_container_log_gets_a_header():
    text = "\n".join(f"2026-08-18T10:00:{i % 60:02d}+0200 line {i}" for i in range(500))
    rendered = logfilter.render_truncated_text(text, 100, source="container audio")
    assert rendered.startswith("# Quelle: container audio")
    assert "400 verworfen" in rendered
    assert rendered.rstrip().endswith("line 499")


def test_untruncated_container_log_is_returned_unchanged():
    text = "line a\nline b"
    assert logfilter.render_truncated_text(text, 100) == text

"""Reading the host's sound card and mixer.

Steps 1 and 7 of the sound-repair chain. Everything here is parsing of real
`/proc/asound/cards` and `amixer` output, taken off a Raspberry Pi with a
wm8960 hat - which is exactly where the parsing has to be right, because a
misread level makes the button turn a speaker up that nobody asked it to.
"""

from __future__ import annotations

from types import SimpleNamespace

from host_helper.api.routes import audio

# Real output, `cat /proc/asound/cards` on the box.
CARDS = """ 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 1 [vc4hdmi1       ]: vc4-hdmi - vc4-hdmi-1
                      vc4-hdmi-1
 2 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones
                      bcm2835 Headphones
 3 [wm8960soundcard]: simple-card - wm8960-soundcard
                      wm8960-soundcard"""

# Real output, `amixer -c 3 scontrols`.
SCONTROLS = """Simple mixer control 'Headphone',0
Simple mixer control 'Headphone Playback ZC',0
Simple mixer control 'Speaker',0
Simple mixer control 'Speaker AC',0
Simple mixer control 'Speaker DC',0
Simple mixer control 'Speaker Playback ZC',0
Simple mixer control 'PCM Playback -6dB',0
Simple mixer control 'Mono Output Mixer Left',0"""

# Real output, `amixer -c 3 sget Speaker`.
SGET_HEALTHY = """Simple mixer control 'Speaker',0
  Capabilities: pvolume
  Playback channels: Front Left - Front Right
  Limits: Playback 0 - 127
  Mono:
  Front Left: Playback 109 [86%] [-12.00dB]
  Front Right: Playback 109 [86%] [-12.00dB]"""


def _run(stdout: str, returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_the_card_numbers_are_read_off_the_real_listing(monkeypatch):
    monkeypatch.setattr(audio, "_run_on_host_via_nsenter", lambda *a, **k: _run(CARDS))
    cards, listing = audio._sound_cards()
    assert cards == ["0", "1", "2", "3"], "the indented second line was counted too"
    assert "wm8960" in listing


def test_no_sound_card_leaves_no_card_numbers(monkeypatch):
    """The actual fault: the codec failed to probe and the card is simply gone."""
    monkeypatch.setattr(audio, "_run_on_host_via_nsenter", lambda *a, **k: _run(""))
    cards, _ = audio._sound_cards()
    assert cards == []


def test_only_controls_that_are_volumes_are_touched(monkeypatch):
    """"Speaker AC", "Speaker DC" and "Speaker Playback ZC" are switches, not
    levels. Setting them to 80 % is meaningless at best."""
    monkeypatch.setattr(audio, "_amixer", lambda *a, **k: _run(SCONTROLS))
    assert audio._controls_of("3") == ["Speaker", "Headphone"]


def test_a_healthy_level_is_read_as_healthy(monkeypatch):
    monkeypatch.setattr(audio, "_amixer", lambda *a, **k: _run(SGET_HEALTHY))
    level, muted = audio._control_level("3", "Speaker")
    assert level == 86
    assert muted is False


def test_a_capture_channel_at_zero_is_not_the_speaker(monkeypatch):
    """A control that does both prints both. A microphone at 0 % must not make
    the button turn the speaker up."""
    both = (
        "Simple mixer control 'PCM',0\n"
        "  Front Left: Playback 109 [86%] [-12.00dB] Capture 0 [0%] [off]\n"
        "  Front Right: Playback 109 [86%] [-12.00dB] Capture 0 [0%] [off]"
    )
    monkeypatch.setattr(audio, "_amixer", lambda *a, **k: _run(both))
    level, muted = audio._control_level("3", "PCM")
    assert level == 86, "read the capture level as the playback level"
    assert muted is False, "read the capture switch as the playback switch"


def test_a_playback_switch_that_is_off_counts_as_muted(monkeypatch):
    off = (
        "Simple mixer control 'Speaker',0\n"
        "  Front Left: Playback 0 [0%] [-73.00dB] [off]\n"
        "  Front Right: Playback 0 [0%] [-73.00dB] [off]"
    )
    monkeypatch.setattr(audio, "_amixer", lambda *a, **k: _run(off))
    level, muted = audio._control_level("3", "Speaker")
    assert level == 0
    assert muted is True


def test_a_healthy_box_is_left_alone(monkeypatch):
    calls: list[list[str]] = []

    def _amixer(args, timeout=10):
        calls.append(args)
        if "scontrols" in args:
            return _run(SCONTROLS)
        return _run(SGET_HEALTHY)

    monkeypatch.setattr(audio, "_run_on_host_via_nsenter", lambda *a, **k: _run(CARDS))
    monkeypatch.setattr(audio, "_amixer", _amixer)

    step = audio._repair_mixer()

    assert step["fixed"] is False
    assert not any("sset" in a for a in calls), "wrote to a mixer that was fine"


def test_a_mixer_at_zero_is_raised(monkeypatch):
    zero = (
        "Simple mixer control 'Speaker',0\n"
        "  Front Left: Playback 0 [0%] [-73.00dB]\n"
        "  Front Right: Playback 0 [0%] [-73.00dB]"
    )
    written: list[list[str]] = []

    def _amixer(args, timeout=10):
        if "scontrols" in args:
            return _run(SCONTROLS)
        if "sset" in args:
            written.append(args)
            return _run("")
        return _run(zero)

    monkeypatch.setattr(audio, "_run_on_host_via_nsenter", lambda *a, **k: _run(CARDS))
    monkeypatch.setattr(audio, "_amixer", _amixer)

    step = audio._repair_mixer()

    assert step["fixed"] is True
    assert written, "found a mixer at zero and left it there"
    assert f"{audio._MIXER_REPAIR_PERCENT}%" in written[0]
    assert "unmute" in written[0]

#!/usr/bin/env python3
"""Tests for select_services.select().

There is no Python job in CI (checks.yml only runs the webui/Node checks), so
this runs standalone:

    python3 .github/scripts/test_select_services.py

It also works under pytest if invoked explicitly:

    python3 -m pytest .github/scripts/test_select_services.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from select_services import SERVICES, SHARED_LIB_DEPENDENTS, select  # noqa: E402


def test_no_version_change_builds_nothing() -> None:
    files = [
        "services/rfid-service/Dockerfile",
        "services/rfid-service/src/rfid_service/main.py",
        "services/backend-service/README.md",
        ".github/workflows/build-images.yml",
        "docs/services/audio/README.md",
    ]
    names, _ = select(files)
    assert names == []


def test_version_bump_builds_only_that_service() -> None:
    names, reasons = select(
        ["services/rfid-service/VERSION", "services/rfid-service/Dockerfile"]
    )
    assert names == ["rfid"]
    assert reasons == ["rfid: VERSION bumped"]


def test_several_version_bumps() -> None:
    names, _ = select(
        [
            "services/webui-service/VERSION",
            "services/backend-service/VERSION",
            "CHANGELOG.md",
        ]
    )
    assert names == ["backend", "webui"]


def test_shared_lib_version_bump_fans_out_to_dependents() -> None:
    names, reasons = select(["services/shared-lib/VERSION"])
    assert names == sorted(SHARED_LIB_DEPENDENTS)
    assert "webui" not in names
    assert reasons == ["shared-lib VERSION bumped - all services except webui"]


def test_shared_lib_source_change_without_bump_builds_nothing() -> None:
    names, _ = select(["services/shared-lib/shared_lib/mqtt/base_client.py"])
    assert names == []


def test_selection_is_a_subset_of_known_services() -> None:
    names, _ = select([f"services/{n}-service/VERSION" for n in SERVICES])
    assert set(names) == set(SERVICES)


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())

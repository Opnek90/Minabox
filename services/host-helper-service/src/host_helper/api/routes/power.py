"""Reboot, shutdown, and restarting the Minabox containers."""

from __future__ import annotations

import subprocess

import structlog
from fastapi import APIRouter, Depends, HTTPException

from host_helper.api.routes.deps import (
    _check_api_key,
    _nsenter_bin,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/reboot")
def reboot_host(_: None = Depends(_check_api_key)) -> dict:
    """Reboot the host (Pi). Runs on the host via nsenter."""
    try:
        nsenter_bin = _nsenter_bin()
        # Run in background so we can return before the host goes down
        subprocess.Popen(
            [str(nsenter_bin), "-t", "1", "-n", "-m", "--", "/sbin/reboot"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter not available on host"
        ) from e
    except Exception as e:
        logger.exception("reboot_failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    logger.info("reboot_initiated")
    return {"ok": True, "message": "Reboot initiated"}


@router.post("/shutdown")
def shutdown_host(_: None = Depends(_check_api_key)) -> dict:
    """Shutdown the host (Pi). Runs on the host via nsenter."""
    try:
        nsenter_bin = _nsenter_bin()
        subprocess.Popen(
            [
                str(nsenter_bin),
                "-t",
                "1",
                "-n",
                "-m",
                "--",
                "/sbin/shutdown",
                "-h",
                "now",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter not available on host"
        ) from e
    except Exception as e:
        logger.exception("shutdown_failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    logger.info("shutdown_initiated")
    return {"ok": True, "message": "Shutdown initiated"}


@router.post("/restart")
def restart_services(_: None = Depends(_check_api_key)) -> dict:
    """Restart the Minabox containers via docker compose on the host."""
    try:
        nsenter_bin = _nsenter_bin()
        # On the host: read the compose project directory from a container
        # label, then restart from there.
        sh_cmd = (
            "WORKDIR=$(docker inspect minabox-backend --format "
            "'{{index .Config.Labels \"com.docker.compose.project.working_dir\"}}' 2>/dev/null); "
            '[ -n "$WORKDIR" ] && cd "$WORKDIR" && docker compose restart'
        )
        result = subprocess.run(
            [str(nsenter_bin), "-t", "1", "-n", "-m", "--", "/bin/sh", "-c", sh_cmd],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise HTTPException(
                status_code=502, detail=(out or "Restart failed")[-1000:]
            )
        logger.info("restart_services_done")
        return {"ok": True, "message": "Services restart initiated"}
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503, detail="nsenter or docker not available on host"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Restart timed out") from e
    except Exception as e:
        logger.exception("restart_services_failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

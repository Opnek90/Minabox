"""REST API for Host-Helper proxy: audio path, move."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend_service.config import get_config

logger = structlog.get_logger(__name__)
router = APIRouter()

HOST_HELPER_TIMEOUT = 10.0


def _host_helper_url() -> str:
    return os.environ.get("HOST_HELPER_URL", "http://host-helper:8000").rstrip("/")


def _host_helper_api_key() -> str | None:
    return os.environ.get("HOST_HELPER_API_KEY", "").strip() or None


def _allowed_audio_paths() -> list[str]:
    raw = os.environ.get("ALLOWED_AUDIO_PATHS", "/media,/mnt,/home/pi")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _validate_path(path: str) -> None:
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="path required")
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")
    p = Path(path).resolve()
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be absolute")
    allowed = _allowed_audio_paths()
    for base in allowed:
        try:
            p.relative_to(Path(base).resolve())
            return
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="Path not under allowed base paths")


class AudioPathBody(BaseModel):
    path: str


class MoveAudioBody(BaseModel):
    source: str
    destination: str


@router.get("/host-status")
async def get_host_status() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"hostname": None, "ip": None, "memory": None, "cpu": None, "disk": None}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/host-status",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_host_status_failed", error=str(e))
    return {"hostname": None, "ip": None, "memory": None, "cpu": None, "disk": None}


@router.get("/audio-path")
async def get_audio_path() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        config = get_config()
        return {"path": config.env.audio_storage_path}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/audio-path",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                data = r.json()
                saved = data.get("audio_files_path")
                if saved:
                    return {"path": saved}
        config = get_config()
        return {"path": config.env.audio_storage_path}
    except Exception as e:
        logger.debug("host_helper_get_audio_path_failed", error=str(e))
        config = get_config()
        return {"path": config.env.audio_storage_path}


@router.put("/audio-path")
async def put_audio_path(body: AudioPathBody) -> dict:
    path = body.path.strip()
    _validate_path(path)
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.post(
                f"{url}/apply-audio-path",
                json={"audio_files_path": path},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code == 400:
                raise HTTPException(status_code=400, detail=r.json().get("detail", "Invalid path"))
            if r.status_code != 200:
                raise HTTPException(status_code=503, detail="Host-Helper request failed")
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_apply_audio_path_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Host-Helper unreachable. Restart stack after adding host-helper.",
        ) from e


@router.post("/move-audio")
async def move_audio(body: MoveAudioBody):
    _validate_path(body.source)
    _validate_path(body.destination)
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.post(
                f"{url}/move",
                json={"source": body.source, "destination": body.destination},
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code == 409:
                raise HTTPException(status_code=409, detail="Move already in progress")
            if r.status_code in (400, 404):
                detail = r.json().get("detail", "Move failed") if r.content else "Move failed"
                raise HTTPException(status_code=r.status_code, detail=detail)
            if r.status_code not in (200, 202):
                raise HTTPException(status_code=503, detail="Host-Helper request failed")
            return JSONResponse(content=r.json(), status_code=r.status_code)
    except httpx.RequestError as e:
        logger.warning("host_helper_move_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Host-Helper unreachable.") from e


@router.get("/move-status")
async def get_move_status() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        return {"status": "idle", "total": 0, "current": 0, "error": None}
    try:
        async with httpx.AsyncClient(timeout=HOST_HELPER_TIMEOUT) as client:
            r = await client.get(
                f"{url}/move-status",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("host_helper_move_status_failed", error=str(e))
    return {"status": "idle", "total": 0, "current": 0, "error": None}


@router.post("/reboot")
async def reboot_host() -> dict:
    url = _host_helper_url()
    api_key = _host_helper_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Host-Helper not configured (HOST_HELPER_API_KEY missing)",
        )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{url}/reboot",
                headers={"X-Api-Key": api_key},
            )
            if r.status_code == 401:
                raise HTTPException(status_code=503, detail="Host-Helper authentication failed")
            if r.status_code >= 400:
                try:
                    detail = (r.json() or {}).get("detail", "Reboot failed") if r.content else "Reboot failed"
                except Exception:
                    detail = (r.text or "Reboot failed")[:500]
                raise HTTPException(status_code=min(r.status_code, 502), detail=detail)
            return r.json()
    except httpx.RequestError as e:
        logger.warning("host_helper_reboot_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Host-Helper unreachable: {e!s}",
        ) from e

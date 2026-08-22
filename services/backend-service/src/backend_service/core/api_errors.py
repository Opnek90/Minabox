"""HTTP-Fehler mit stabilem, uebersetzbarem Code fuer die WebUI.

`detail` bleibt ein englischer, entwicklerorientierter Text (Logs, curl,
GitHub Issues). `code` ist das, was die WebUI dem Nutzer tatsaechlich zeigt -
uebersetzt ueber den `errors`-i18n-Namespace, mit `generic_error` als
Fallback fuer unbekannte Codes. Ein Tippfehler in `detail` ist damit folgenlos
fuer die Anzeige; ein Tippfehler in `code` faellt lediglich auf den
generischen Text zurueck statt eine falsche Sprache oder ein rohes JSON
anzuzeigen.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """HTTPException, die zusaetzlich einen stabilen `code` traegt.

    `extra` haengt weitere Felder an den JSON-Body (z. B. `retry_after` bei
    Rate-Limits) - fuer die uebersetzte Anzeige selbst reicht `code`.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.extra = extra or {}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code, **exc.extra},
        headers=exc.headers,
    )

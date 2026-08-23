"""HTTP errors carrying a stable, translatable code for the WebUI.

`detail` stays English and developer-facing - logs, curl, issue reports.
`code` is what the WebUI actually shows the user, translated through the
`errors` i18n namespace with `generic_error` as the fallback for unknown codes.
A typo in `detail` therefore has no effect on what anyone sees; a typo in
`code` merely falls back to the generic text, rather than showing the wrong
language or raw JSON.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """An HTTPException that also carries a stable `code`.

    `extra` adds further fields to the JSON body (``retry_after`` on a rate
    limit, say). For the translated message itself, `code` is all it takes.
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

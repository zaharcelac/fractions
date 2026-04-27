"""
FastAPI web service: form to set worksheet options, download generated PDF.
Set ROOT_PATH in production when the app is mounted behind a reverse proxy
(e.g. served at https://host/app/  ?  ROOT_PATH=/app).

PDFs are built in memory only and streamed in the HTTP response; nothing is written to
server disk. Rate limits and MAX_WEB_PAGES reduce abuse.
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from fraction_practice import (
    MAX_RANGE_DEFAULT,
    MIN_RANGE_DEFAULT,
    PAGE_HEADER_TEXT,
    write_fractions_pdf,
)


def _get_forwarded_trusted_proxies() -> list[str] | str:
    """
    Hosts that may set X-Forwarded-Proto (and friends). Uvicorn defaults to 127.0.0.1 only,
    so a Docker or LAN reverse proxy is often *not* trusted and scheme stays http. Default *
    (override with FORWARDED_TRUSTED_PROXIES, e.g. 10.0.0.0/8) so url_for and base_url use https
    when the front proxy sets X-Forwarded-Proto: https.
    """
    raw = os.environ.get("FORWARDED_TRUSTED_PROXIES", "*").strip()
    if not raw:
        return "*"
    if raw == "*":
        return "*"
    return [h.strip() for h in raw.split(",") if h.strip()]


def _env_limit_str(name: str, default: str) -> str:
    v = os.environ.get(name, default).strip()
    return v if v else default


# Per-IP limits (slowapi / limits). Tune via env for public traffic.
# Examples: "60/minute", "10/hour", "100/day"
RATE_LIMIT_INDEX = _env_limit_str("RATE_LIMIT_INDEX", "60/minute")
RATE_LIMIT_GENERATE = _env_limit_str("RATE_LIMIT_GENERATE", "30/minute")

# Cap total worksheet "pages" from the web form (CLI has no such cap)
try:
    _MAX_WEB_PAGES = max(1, int(os.environ.get("MAX_WEB_PAGES", "20")))
except ValueError:
    _MAX_WEB_PAGES = 20

limiter = Limiter(key_func=get_remote_address)


def _get_root_path() -> str:
    p = os.environ.get("ROOT_PATH", "").strip()
    if not p or p == "/":
        return ""
    p = p.rstrip("/")
    if not p.startswith("/"):
        p = f"/{p}"
    return p


class _RootPathStripMiddleware(BaseHTTPMiddleware):
    """
    When the proxy forwards a path prefix (e.g. /fractions) to this app, routing uses / and
    /generate. Strip ROOT_PATH from the path so /fractions and /fractions/ both work without
    a 307 from Starlette redirect_slashes handling.
    """

    def __init__(self, app, root_getter) -> None:
        super().__init__(app)
        self._root_getter = root_getter

    async def dispatch(self, request: Request, call_next):
        pfx = (self._root_getter() or "").rstrip("/")
        if pfx:
            p = request.scope.get("path", "")
            if p == pfx or p.startswith(pfx + "/"):
                suffix = p[len(pfx) :] or "/"
                if not suffix.startswith("/"):
                    suffix = f"/{suffix}"
                request.scope["path"] = suffix
        return await call_next(request)


app = FastAPI(
    title="Fraction practice PDF",
    root_path=_get_root_path(),
    redirect_slashes=False,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(_RootPathStripMiddleware, _get_root_path)
# After RootPath so stack is: ... -> proxy headers -> root strip -> routes (see Starlette add_middleware order)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=_get_forwarded_trusted_proxies())

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _public_ui_url_for_pdf(request: Request) -> str | None:
    """Prefer FRACTIONS_PUBLIC_URL; else use the request base URL (full URL is fine; PDF strips scheme)."""
    env = os.environ.get("FRACTIONS_PUBLIC_URL", "").strip()
    if env:
        return env
    return str(request.base_url).rstrip("/")


def _parse_seed(raw: str) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    v = int(s, 10)
    if v < 0 or v > 999:
        raise ValueError("Seed must be between 0 and 999 (inclusive).")
    return v


def _index_context(
    request: Request,
    *,
    error: str | None,
    pages: int,
    frange: int,
    max_problems: int,
    seed_display: str,
) -> dict:
    return {
        "request": request,
        "form_action": str(request.url_for("generate")),
        "min_range": MIN_RANGE_DEFAULT,
        "max_range": MAX_RANGE_DEFAULT,
        "max_web_pages": _MAX_WEB_PAGES,
        "error": error,
        "pages": pages,
        "frange": frange,
        "max_problems": max_problems,
        "seed": seed_display,
    }


@app.get("/", name="index")
@limiter.limit(RATE_LIMIT_INDEX)
async def form_get(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        _index_context(
            request,
            error=None,
            pages=1,
            frange=4,
            max_problems=10,
            seed_display=str(random.randint(100, 999)),
        ),
    )


@app.post("/generate", name="generate")
@limiter.limit(RATE_LIMIT_GENERATE)
async def generate(
    request: Request,
    pages: int = Form(1, ge=1, le=_MAX_WEB_PAGES),
    frange: int = Form(4, ge=MIN_RANGE_DEFAULT, le=MAX_RANGE_DEFAULT),
    max_problems: int = Form(10, ge=1, le=10),
    seed: str = Form(""),
) -> Response:
    try:
        seed_val = _parse_seed(seed)
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "index.html",
            _index_context(
                request,
                error=str(e),
                pages=pages,
                frange=frange,
                max_problems=max_problems,
                seed_display=(seed.strip() or str(random.randint(100, 999))),
            ),
            status_code=400,
        )
    try:
        buf = BytesIO()
        write_fractions_pdf(
            buf,
            pages=pages,
            frange=frange,
            max_problems=max_problems,
            header=PAGE_HEADER_TEXT,
            seed=seed_val,
            public_ui_url=_public_ui_url_for_pdf(request),
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "index.html",
            _index_context(
                request,
                error=str(e),
                pages=pages,
                frange=frange,
                max_problems=max_problems,
                seed_display=seed.strip() or str(random.randint(100, 999)),
            ),
            status_code=400,
        )
    # Single in-memory buffer; not written to server filesystem
    data = buf.getvalue()
    fn = f"fractions_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fn}"',
            "Cache-Control": "no-store",
        },
    )

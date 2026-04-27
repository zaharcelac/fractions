"""
FastAPI web service: form to set worksheet options, download generated PDF.
Set ROOT_PATH in production when the app is mounted behind a reverse proxy
(e.g. served at https://host/app/  ?  ROOT_PATH=/app).
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

from fraction_practice import (
    MAX_RANGE_DEFAULT,
    MIN_RANGE_DEFAULT,
    PAGE_HEADER_TEXT,
    write_fractions_pdf,
)


def _get_root_path() -> str:
    p = os.environ.get("ROOT_PATH", "").strip()
    if not p or p == "/":
        return ""
    return p.rstrip("/")


app = FastAPI(
    title="Fraction practice PDF",
    root_path=_get_root_path(),
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


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
        "error": error,
        "pages": pages,
        "frange": frange,
        "max_problems": max_problems,
        "seed": seed_display,
    }


@app.get("/", name="index")
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
async def generate(
    request: Request,
    pages: int = Form(1, ge=1),
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
    data = buf.getvalue()
    fn = f"fractions_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fn}"',
        },
    )

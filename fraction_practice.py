#!/usr/bin/env python3
"""
Generate US Letter PDF worksheets: circle (pie) model + three fraction choices.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from math import cos, sin, pi
from pathlib import Path
from typing import Any, BinaryIO

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


# Max denominator for --range: at least 3, up to 8 (see MIN/MAX below).
MIN_RANGE_DEFAULT = 3
MAX_RANGE_DEFAULT = 8

# Single header on every page (overridable with --header); centered, bold, large.
PAGE_HEADER_TEXT: str = "FRACTIONS 101"
PAGE_HEADER_FONT: str = "Helvetica-Bold"
PAGE_HEADER_FONT_SIZE: float = 20.0

# Footer: regular monospace, multi-line, centered; drawn on every physical page.
FOOTER_FONT: str = "Courier"
FOOTER_FONT_SIZE: float = 9.0

# Multiple-choice rows to the right of each pie: empty circles + fraction (students mark a circle)
ANSWERS_FONT: str = "Helvetica-Bold"
ANSWERS_FONT_SIZE: float = 18.0
# Vertical step between each answer line; keep ≥ font size so lines do not overlap.
ANSWERS_LINE_SPACING: float = 28.0
ANSWERS_BUBBLE_RADIUS_PT: float = 6.5
ANSWERS_BUBBLE_STROKE_PT: float = 1.0
ANSWERS_BUBBLE_TO_TEXT_GAP_PT: float = 8.0
# Horizontal distance (pt) from the pie’s right rim to the left edge of the first answer bubble.
PIE_RIM_TO_ANSWERS_GAP_PT: float = 30.0

# US Letter: two columns of pies, at most 5 rows per column (10 per physical PDF page).
_LETTER_PAGE_W, _LETTER_PAGE_H = letter
_LETTER_MARGIN = 0.6 * inch
_LETTER_BELOW_TITLE = 0.4 * inch
_LETTER_CONTENT_BOTTOM_PAD = 0.3 * inch
# Reserve space for one centered mono footer line below the main pie area.
_FOOTER_RESERVE = 0.22 * inch
_LETTER_TITLE_Y = _LETTER_PAGE_H - _LETTER_MARGIN
_LETTER_CONTENT_TOP = _LETTER_TITLE_Y - _LETTER_BELOW_TITLE
_LETTER_CONTENT_BOTTOM = _LETTER_MARGIN + _LETTER_CONTENT_BOTTOM_PAD + _FOOTER_RESERVE
_LETTER_CONTENT_USABLE = _LETTER_CONTENT_TOP - _LETTER_CONTENT_BOTTOM
# One vertical slot = 1/5 of the content height (max 5 circles stacked per column).
PIE_ROW_HEIGHT: float = _LETTER_CONTENT_USABLE / 5.0
PIE_NUM_COLUMNS: int = 2
MAX_PIES_PER_COLUMN: int = 5
MAX_PIES_PER_PDF_PAGE: int = PIE_NUM_COLUMNS * MAX_PIES_PER_COLUMN
# Horizontal layout: two equal content columns with a gutter.
_CONTENT_INNER_W: float = _LETTER_PAGE_W - 2.0 * _LETTER_MARGIN
_COLUMN_GUTTER: float = 0.28 * inch
_COLUMN_WIDTH: float = (_CONTENT_INNER_W - _COLUMN_GUTTER) / 2.0
_PIE_INSET: float = 0.2 * inch
_ANSWERS_TEXT_W: float = 64.0  # pt, reserve: bubble + gap + longest fraction
_CIRCLE_R_MIN = 0.2 * inch
_CIRCLE_R_MAX = 0.6 * inch
# Column must fit: inset + 2r + rim-to-answers gap + bubbles + fraction text
R_CAP_FROM_COLUMN: float = max(
    _CIRCLE_R_MIN,
    (
        _COLUMN_WIDTH
        - _PIE_INSET
        - PIE_RIM_TO_ANSWERS_GAP_PT
        - 2.0 * ANSWERS_BUBBLE_RADIUS_PT
        - ANSWERS_BUBBLE_TO_TEXT_GAP_PT
        - _ANSWERS_TEXT_W
    )
    / 2.0,
)
# Single fixed radius: fits 5 rows vertically and pie+answers within one column; not resized on page.
DEFAULT_CIRCLE_RADIUS_PT: float = min(
    _CIRCLE_R_MAX,
    R_CAP_FROM_COLUMN,
    max(_CIRCLE_R_MIN, 0.36 * PIE_ROW_HEIGHT),
)
# Shaded pie sectors (solid); each component 0-1. Unshaded sectors stay white (1, 1, 1).
PIE_SHADED_FILL_RGB: tuple[float, float, float] = (0.82, 0.82, 0.82)
# Stroke width in points for the pie chart: hub-to-rim sector dividers and the outer ring.
PIE_DIVIDERS_STROKE_PT: float = 1.5
PIE_OUTLINE_CIRCLE_STROKE_PT: float = 1.5


@dataclass(frozen=True)
class Problem:
    """
    A proper fraction in **display** form (n, d): the pie and label use n and d as given,
    so 1/2 and 2/4 are different (two vs four sectors, etc.). Comparing the amount uses ``value``.
    """
    n: int
    d: int

    def __post_init__(self) -> None:
        if not (self.d >= 2 and 0 < self.n < self.d):
            raise ValueError(f"invalid proper fraction: {self.n}/{self.d}")

    @property
    def value(self) -> Fraction:
        return Fraction(self.n, self.d)

    @property
    def num(self) -> int:
        return self.n

    @property
    def den(self) -> int:
        return self.d

    def as_str(self) -> str:
        return f"{self.n}/{self.d}"


def _proper_fractions(max_denominator: int) -> list[Problem]:
    """
    All proper (n, d) with 1 <= n < d and 2 <= d <= max_denominator — one problem per
    **pair** (1/2 and 2/4 both appear, with different diagrams).
    """
    out: list[Problem] = []
    for d in range(2, max_denominator + 1):
        for n in range(1, d):
            out.append(Problem(n, d))
    return out


def _choose_wrong(correct: Problem, pool: set[Problem], rng: random.Random) -> list[Problem]:
    """
    Pick two wrong options with **different** rational values from the correct answer,
    so we never list two answer choices with the same amount (e.g. 1/2 and 2/4) at once.
    """
    by_val: dict[Fraction, list[Problem]] = defaultdict(list)
    for p in pool:
        if p.value == correct.value:
            continue
        by_val[p.value].append(p)
    value_keys = list(by_val.keys())
    if len(value_keys) < 2:
        raise ValueError("Need at least two distinct values for wrong answers")
    v1, v2 = rng.sample(value_keys, 2)
    return [rng.choice(by_val[v1]), rng.choice(by_val[v2])]


def _draw_pie(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    radius: float,
    denominator: int,
    numerator: int,
    rng: random.Random,
) -> None:
    """Draw a circle split into `denominator` equal sectors; shade `numerator` adjacent wedges in light grey."""
    c.setStrokeColorRGB(0, 0, 0)

    n = denominator
    if n < 2:
        raise ValueError("denominator must be at least 2")
    m = numerator
    if m < 0 or m > n:
        raise ValueError("invalid numerator for pie")

    # Shaded sectors form one contiguous block (adjacent wedges, wrapping on the circle).
    if m == 0:
        shaded: set[int] = set()
    elif m == n:
        shaded = set(range(n))
    else:
        start = rng.randrange(n)
        shaded = {(start + j) % n for j in range(m)}

    start_ang = pi / 2  # 12 o'clock
    for i in range(n):
        t0 = start_ang - 2 * pi * i / n
        t1 = start_ang - 2 * pi * (i + 1) / n
        path = c.beginPath()
        path.moveTo(cx, cy)
        for s in range(0, 17):
            t = t0 + (t1 - t0) * s / 16.0
            path.lineTo(cx + radius * cos(t), cy + radius * sin(t))
        path.close()
        if i in shaded:
            c.setFillColorRGB(*PIE_SHADED_FILL_RGB)
        else:
            c.setFillColorRGB(1, 1, 1)
        c.drawPath(path, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)

    # Radial lines: one spoke per sector boundary (denominator n → n divisions visible).
    c.setLineWidth(PIE_DIVIDERS_STROKE_PT)
    c.setStrokeColorRGB(0, 0, 0)
    for k in range(n):
        t = start_ang - 2 * pi * k / n
        xe = cx + radius * cos(t)
        ye = cy + radius * sin(t)
        c.line(cx, cy, xe, ye)

    c.setLineWidth(PIE_OUTLINE_CIRCLE_STROKE_PT)
    c.circle(cx, cy, radius, fill=0, stroke=1)


def _draw_problem_block(
    c: canvas.Canvas,
    x0: float,
    y0: float,
    row_height: float,
    correct: Problem,
    choices: list[Problem],
    rng: random.Random,
) -> None:
    """y0 = top of row. choices are shuffled; each line is an empty mark circle and a fraction. row_height is PIE_ROW_HEIGHT."""
    r = DEFAULT_CIRCLE_RADIUS_PT
    row_mid = y0 - 0.5 * row_height
    cx = x0 + r + _PIE_INSET
    cy = row_mid
    _draw_pie(c, cx, cy, r, correct.den, correct.num, rng)

    text_x = x0 + _PIE_INSET + 2.0 * r + PIE_RIM_TO_ANSWERS_GAP_PT
    line_h = ANSWERS_LINE_SPACING
    ty = row_mid + line_h
    bubble_r = ANSWERS_BUBBLE_RADIUS_PT
    fr_x = text_x + 2.0 * bubble_r + ANSWERS_BUBBLE_TO_TEXT_GAP_PT
    c.setFont(ANSWERS_FONT, ANSWERS_FONT_SIZE)
    c.setFillColorRGB(0, 0, 0)
    a_desc = pdfmetrics.getAscentDescent(ANSWERS_FONT, ANSWERS_FONT_SIZE)
    # From text baseline, visual center = baseline + (ascent + descent) / 2 (descent is ≤ 0 in user space).
    baseline_to_vcenter = (a_desc[0] + a_desc[1]) / 2.0
    for p in choices:
        bubble_cx = text_x + bubble_r
        bubble_cy = ty + baseline_to_vcenter
        c.setLineWidth(ANSWERS_BUBBLE_STROKE_PT)
        c.setStrokeColorRGB(0, 0, 0)
        c.circle(bubble_cx, bubble_cy, bubble_r, fill=0, stroke=1)
        c.setFont(ANSWERS_FONT, ANSWERS_FONT_SIZE)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(fr_x, ty, p.as_str())
        ty -= line_h


def normalize_public_url_for_footer(raw: str | None) -> str:
    """
    Return host[/path] with no http:// or https:// (trailing slash stripped).
    Empty or whitespace-only input yields a short placeholder (PDF built-in font safe).
    """
    if raw is None:
        return "-"
    s = raw.strip()
    if not s:
        return "-"
    for prefix in ("https://", "http://"):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :]
            break
    return s.rstrip("/") or "-"


def _draw_page_footer(
    c: canvas.Canvas,
    *,
    set_w: int,
    set_z: int,
    page_x: int,
    page_y: int,
    denominator: int,
    max_problems_actual: int,
    public_url_display: str,
) -> None:
    """Draw centered one-line footer (regular Courier), fields separated by |."""
    line = " | ".join(
        [
            f"SET {set_w} of {set_z}",
            f"PAGE {page_x} of {page_y}",
            f"DENOMINATOR: {denominator}",
            f"MAX-PROBLEMS: {max_problems_actual}",
            f"URL: {public_url_display}",
        ]
    )
    c.setFont(FOOTER_FONT, FOOTER_FONT_SIZE)
    c.setFillColorRGB(0, 0, 0)
    y = _LETTER_MARGIN + FOOTER_FONT_SIZE * 0.2
    w = c.stringWidth(line, FOOTER_FONT, FOOTER_FONT_SIZE)
    c.drawString((_LETTER_PAGE_W - w) / 2, y, line)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate US Letter PDFs with simple fraction practice (circle model + 3 choices)."
    )
    p.add_argument(
        "--pages",
        type=int,
        default=1,
        metavar="N",
        help="How many worksheet pages to generate (default: 1).",
    )
    p.add_argument(
        "--range",
        type=int,
        default=4,
        dest="frange",
        metavar="N",
        choices=range(MIN_RANGE_DEFAULT, MAX_RANGE_DEFAULT + 1),
        help=(
            f"Maximum denominator: proper fractions use denominators from 2 through N "
            f"(default: 4, allowed: {MIN_RANGE_DEFAULT}–{MAX_RANGE_DEFAULT})."
        ),
    )
    p.add_argument(
        "--max-problems",
        type=int,
        default=10,
        metavar="N",
        help=(
            "Requested problems per worksheet (default: 10). Two columns × up to 5 rows (10) per PDF page, "
            "then continue on the next page (may be lowered if the fraction pool is too small for unique problems)."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Output PDF path. Default: output/fractions_YYYY-MM-DD_HH-mm-SS.pdf "
            "(timestamp at run time; output directory is created if missing)."
        ),
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible output.",
    )
    p.add_argument(
        "--test",
        action="store_true",
        help="Write to output/test.pdf (ignored if --output is set).",
    )
    p.add_argument(
        "--header",
        default=PAGE_HEADER_TEXT,
        metavar="TEXT",
        help=f'Plain text at the top of each page (default: {PAGE_HEADER_TEXT!r}).',
    )
    p.add_argument(
        "--public-url",
        default=None,
        metavar="URL",
        help=(
            "Public web UI URL for the PDF footer (scheme optional; shown without http(s)://). "
            "If omitted, uses env FRACTIONS_PUBLIC_URL or the footer URL line shows a placeholder."
        ),
    )
    return p.parse_args()


def write_fractions_pdf(
    out_file: BinaryIO,
    *,
    pages: int,
    frange: int,
    max_problems: int,
    header: str = PAGE_HEADER_TEXT,
    seed: int | None = None,
    public_ui_url: str | None = None,
) -> dict[str, Any]:
    """
    Write a US Letter PDF to ``out_file`` (path-like opened by caller, or e.g. :class:`io.BytesIO`).
    Raises :exc:`ValueError` if options are invalid for generation.

    ``public_ui_url`` is displayed in the footer with http(s) stripped; if unset/empty,
    the footer still includes a URL line with a placeholder.
    """
    if pages < 1:
        raise ValueError("--pages must be at least 1")
    if max_problems < 1:
        raise ValueError("--max-problems must be at least 1")
    if frange < MIN_RANGE_DEFAULT or frange > MAX_RANGE_DEFAULT:
        raise ValueError(
            f"--range must be between {MIN_RANGE_DEFAULT} and {MAX_RANGE_DEFAULT}"
        )

    pool = _proper_fractions(frange)
    pool_set = set(pool)
    n_forms = len(pool)
    n_distinct_values = len({p.value for p in pool})
    if n_distinct_values < 3:
        raise ValueError(
            "Need at least 3 distinct rational values in the pool for A/B/C (increase --range)."
        )

    per_page = min(max_problems, n_forms)
    rng = random.Random(seed)

    sub_pages_per_worksheet = (per_page + MAX_PIES_PER_PDF_PAGE - 1) // MAX_PIES_PER_PDF_PAGE
    total_pdf_pages = pages * sub_pages_per_worksheet

    margin = _LETTER_MARGIN
    title_y = _LETTER_TITLE_Y
    content_top = _LETTER_CONTENT_TOP
    row_h = PIE_ROW_HEIGHT
    col_left = margin
    col_right = margin + _COLUMN_WIDTH + _COLUMN_GUTTER

    c = canvas.Canvas(out_file, pagesize=letter)
    c.setTitle(header)
    public_display = normalize_public_url_for_footer(public_ui_url)

    pdf_page_num = 0
    for pnum in range(pages):
        picked: list[Problem] = rng.sample(pool, per_page)
        for start in range(0, per_page, MAX_PIES_PER_PDF_PAGE):
            chunk = picked[start : start + MAX_PIES_PER_PDF_PAGE]

            c.setFont(PAGE_HEADER_FONT, PAGE_HEADER_FONT_SIZE)
            c.setFillColorRGB(0, 0, 0)
            w_header = c.stringWidth(header, PAGE_HEADER_FONT, PAGE_HEADER_FONT_SIZE)
            c.drawString((_LETTER_PAGE_W - w_header) / 2, title_y, header)

            for idx, pr in enumerate(chunk):
                row = idx // PIE_NUM_COLUMNS
                col = idx % PIE_NUM_COLUMNS
                x0 = col_left if col == 0 else col_right
                y0 = content_top - row * row_h
                wrong = _choose_wrong(pr, pool_set, rng)
                choices = [pr, wrong[0], wrong[1]]
                order = list(range(3))
                rng.shuffle(order)
                shuffled = [choices[j] for j in order]
                _draw_problem_block(
                    c,
                    x0,
                    y0,
                    row_h,
                    pr,
                    shuffled,
                    rng,
                )
            pdf_page_num += 1
            _draw_page_footer(
                c,
                set_w=pnum + 1,
                set_z=pages,
                page_x=pdf_page_num,
                page_y=total_pdf_pages,
                denominator=frange,
                max_problems_actual=per_page,
                public_url_display=public_display,
            )
            c.showPage()

    c.save()
    return {
        "per_page": per_page,
        "total_pdf_pages": total_pdf_pages,
        "n_forms": n_forms,
        "worksheets": pages,
        "max_requested": max_problems,
    }


def main() -> int:
    args = _parse_args()

    rmax = args.frange

    if args.output is not None:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.test:
            output_path: Path = out_dir / "test.pdf"
        else:
            out_name = datetime.now().strftime("fractions_%Y-%m-%d_%H-%M-%S.pdf")
            output_path = out_dir / out_name

    try:
        with open(output_path, "wb") as f:
            public = args.public_url
            if public is None:
                public = os.environ.get("FRACTIONS_PUBLIC_URL", "").strip() or None
            meta = write_fractions_pdf(
                f,
                pages=args.pages,
                frange=rmax,
                max_problems=args.max_problems,
                header=args.header,
                seed=args.seed,
                public_ui_url=public,
            )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(
        f"Wrote {output_path} ({meta['total_pdf_pages']} PDF page(s), {meta['per_page']} problem(s) per "
        f"worksheet, {meta['worksheets']} worksheet(s), "
        f"2×{MAX_PIES_PER_COLUMN} layout, pie radius {DEFAULT_CIRCLE_RADIUS_PT:.1f} pt).",
        file=sys.stderr,
    )
    if meta["per_page"] < meta["max_requested"]:
        print(
            f"Note: using {meta['per_page']} problem(s) per worksheet (max (n/d) forms in pool: {meta['n_forms']}).",
            file=sys.stderr,
        )
    if meta["per_page"] > MAX_PIES_PER_PDF_PAGE:
        n_phys = (meta["per_page"] + MAX_PIES_PER_PDF_PAGE - 1) // MAX_PIES_PER_PDF_PAGE
        print(
            f"Note: {meta['per_page']} problem(s) per worksheet are split across {n_phys} PDF page(s) "
            f"(2×{MAX_PIES_PER_COLUMN} layout, {MAX_PIES_PER_PDF_PAGE} per page).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

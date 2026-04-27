# Fraction practice worksheets

Generates **US Letter** PDF worksheets with ReportLab. Each item has a **pie chart** (sectors shaded in one contiguous block) and **three** answer rows: a **marking circle** plus the **fraction** you print (not “A / B / C” labels). Students pick one bubble.

## Requirements

- Python 3.10+ (3.12+ or 3.14+ recommended; see [`.python-version`](.python-version) if you use pyenv)
- See [`requirements.txt`](requirements.txt) (ReportLab, FastAPI, Uvicorn, and dependencies)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

All arguments are optional except where noted; **defaults** are given below.

```text
python3 fraction_practice.py [--pages N] [--range N] [--max-problems N] [-o PATH] [--header TEXT]
                             [--seed SEED] [--test]
```

| Argument | Default | Meaning |
|----------|---------|--------|
| `--pages` | `1` | How many **worksheet** passes to generate; each can span multiple physical PDF pages if needed. |
| `--range` | `4` | Largest **denominator** `R`; problems use all proper pairs `(n, d)` with `1 ≤ n < d` and `2 ≤ d ≤ R`. **Allowed:** `3`–`8` (enforced at parse time). |
| `--max-problems` | `10` | How many problems per **worksheet**; capped by the number of **(n, d) forms** in the pool. |
| `-o` / `--output` | (see below) | Output PDF path. |
| `--header` | `FRACTIONS 101` | Single line of plain text, centered, bold, at the top of each page. |
| `--seed` | (none) | Reproducible shuffling. |
| `--test` | off | If set (and `--output` is not), writes `output/test.pdf` instead of a timestamped name. |

### Layout and content rules

- **Two columns** of problems, up to **5 rows** per column (**10** pies per **physical** PDF page). The pie size is **fixed** (not shrunk when you ask for fewer problems). More than 10 problems in one worksheet **continue on the next PDF page**.
- **Display form** matters: e.g. **1/2** (two parts, one shaded) and **2/4** (four parts, two shaded) are **different** items in the pool. The tool lists every proper `(n, d)` in range, with **no** value-only deduplication.
- The pool must have at least **three distinct rational values** (so the three options can differ in amount). In rare small pools, use a higher `--range` or a lower `--max-problems`. Wrong-answer options are always **two other values** than the correct one (so you never get both 1/2 and 2/4 as two choices in the same problem).

### Default output

If you **omit** `-o` / `--output`:

- Normally: `output/fractions_YYYY-MM-DD_HH-mm-SS.pdf`
- With `--test` (and no `-o`): `output/test.pdf`

The `output/` directory is created if needed. A custom path also has parent directories created when needed. Generated `*.pdf` files under `output/` are **git-ignored**; `output/.gitkeep` keeps the folder in the repo.

### Examples

```bash
# All defaults: 1 worksheet, max denominator 4, 10 problems (or fewer if the pool is smaller)
python3 fraction_practice.py

# Explicit, same as many defaults
python3 fraction_practice.py --pages 1 --range 4 --max-problems 10

# Eighths, 12 problems on one logical worksheet (spills to a second PDF page after 10)
python3 fraction_practice.py --range 8 --max-problems 12
```

## Web service (optional)

Run [`app.py`](app.py) with Uvicorn to get a small HTML form (same options as the CLI) and download the generated PDF in the browser.

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
# Open http://127.0.0.1:8000/ — submit to download a PDF
```

**Behind a reverse proxy** (e.g. public URL is `https://example.com/fractions/…`), set **`ROOT_PATH`** to the path prefix the proxy strips before forwarding (no trailing slash), for example:

```bash
export ROOT_PATH=/fractions
uvicorn app:app --host 0.0.0.0 --port 8000
```

This sets FastAPI’s `root_path` so link helpers (e.g. the form’s post URL) use the right prefix. Your proxy should still be configured to forward to the app and set `X-Forwarded-Proto` / `Host` as usual.

| Path | Description |
|------|-------------|
| `app.py` | FastAPI app: `GET /` form, `POST /generate` returns `application/pdf` |

## Tuning the PDF (code constants)

Most visual settings live at the top of [`fraction_practice.py`](fraction_practice.py), including:

- **Header:** `PAGE_HEADER_TEXT`, `PAGE_HEADER_FONT`, `PAGE_HEADER_FONT_SIZE`
- **Pies:** `PIE_SHADED_FILL_RGB`, `PIE_DIVIDERS_STROKE_PT`, `PIE_OUTLINE_CIRCLE_STROKE_PT`, `PIE_RIM_TO_ANSWERS_GAP_PT`
- **Answer bubbles and labels:** `ANSWERS_*` (font, spacing, bubble size, stroke, gap to fraction text, etc.)

## Project layout

| Path | Description |
|------|-------------|
| `fraction_practice.py` | CLI, PDF engine (`write_fractions_pdf` for reuse) |
| `app.py` | Optional FastAPI form + download |
| `requirements.txt` | Python dependencies |
| `output/` | Default location for CLI PDFs |

## License

Add a license if you publish this project.

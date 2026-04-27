# Fraction practice worksheets

Generates **US Letter** PDF worksheets with ReportLab. Each item has a **pie chart** (sectors shaded in one contiguous block) and **three** answer rows: a **marking circle** plus the **fraction** you print (not “A / B / C” labels). Students pick one bubble.

## Requirements

- Python 3.10+ (3.12+ or 3.14+ recommended; see [`.python-version`](.python-version) if you use pyenv)
- See [`requirements.txt`](requirements.txt) (ReportLab, FastAPI, Uvicorn, Jinja2, `python-multipart`, and dependencies)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage (CLI)

All arguments are optional except where noted; **defaults** are given below.

```text
python3 fraction_practice.py [--pages N] [--range N] [--max-problems N] [-o PATH] [--header TEXT]
                             [--seed SEED] [--public-url URL] [--test]
```

| Argument | Default | Meaning |
|----------|---------|--------|
| `--pages` | `1` | How many **worksheet** passes to generate; each can span multiple physical PDF pages if needed. |
| `--range` | `4` | Largest **denominator** `R`; problems use all proper pairs `(n, d)` with `1 ≤ n < d` and `2 ≤ d ≤ R`. **Allowed:** `3`–`8` (enforced at parse time). |
| `--max-problems` | `10` | How many problems per **worksheet**; capped by the number of **(n, d) forms** in the pool. |
| `-o` / `--output` | (see below) | Output PDF path. |
| `--header` | `FRACTIONS 101` | Single line of plain text, centered, bold, at the top of each page. |
| `--seed` | (none) | Reproducible shuffling. |
| `--public-url` | (see below) | Public web UI URL for the **PDF footer** (scheme optional). If omitted, uses env **`FRACTIONS_PUBLIC_URL`**; if still unset, the footer shows a placeholder for the URL segment. |
| `--test` | off | If set (and `--output` is not), writes `output/test.pdf` instead of a timestamped name. |

### PDF footer

Every **physical** page includes a **single** centered line in **regular Courier**, with fields separated by **` | `**:

`SET W of Z | PAGE X of Y | DENOMINATOR: R | MAX-PROBLEMS: N | URL: host…`

- **SET** — worksheet index **W** of **Z** total worksheets (`--pages`).
- **PAGE** — physical PDF page **X** of **Y** (extra pages when a worksheet has more than 10 problems, or multiple worksheets).
- **DENOMINATOR** — `--range` value `R` (largest denominator in the pool).
- **MAX-PROBLEMS** — actual problems per worksheet after capping to the pool size (may be below what you requested).
- **URL** — `http://` / `https://` stripped; trailing `/` removed. Use **`--public-url`** or **`FRACTIONS_PUBLIC_URL`** so generated PDFs point at your real web UI.

### Layout and content rules

- **Two columns** of problems, up to **5 rows** per column (**10** pies per **physical** PDF page). The pie size is **fixed** (not shrunk when you ask for fewer problems). More than 10 problems in one worksheet **continue on the next PDF page**.
- **Display form** matters: e.g. **1/2** (two parts, one shaded) and **2/4** (four parts, two shaded) are **different** items in the pool. The tool lists every proper `(n, d)` in range, with **no** value-only deduplication.
- The pool must have at least **three distinct rational values** (so the three options can differ in amount). In rare small pools, use a higher `--range` or a lower `--max-problems`. Wrong-answer options are always **two other values** than the correct one (so you never get both 1/2 and 2/4 as two choices in the same problem).

### Default output

If you **omit** `-o` / `--output`:

- Normally: `output/fractions_YYYY-MM-DD_HH-mm-SS.pdf`
- With `--test` (and no `-o`): `output/test.pdf`

The `output/` directory is created if needed. A custom path also has parent directories created when needed. Generated `*.pdf` files under `output/` are **git-ignored** (see [`.gitignore`](.gitignore); add `output/.gitkeep` if you want the empty folder tracked).

### Examples

```bash
# All defaults: 1 worksheet, max denominator 4, 10 problems (or fewer if the pool is smaller)
python3 fraction_practice.py

# Explicit, same as many defaults
python3 fraction_practice.py --pages 1 --range 4 --max-problems 10

# Eighths, 12 problems on one logical worksheet (spills to a second PDF page after 10)
python3 fraction_practice.py --range 8 --max-problems 12

# Footer URL (also: export FRACTIONS_PUBLIC_URL=https://example.com/fractions)
python3 fraction_practice.py --public-url https://example.com/fractions
```

## Web service (optional)

Run [`app.py`](app.py) with Uvicorn: HTML form in [`templates/index.html`](templates/index.html), **POST** to download a PDF (same generator as the CLI: `write_fractions_pdf`).

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
# Open http://127.0.0.1:8000/ — submit to download a PDF
```

The form uses **range** `3`–`8`, **max problems** `1`–`10`, optional **seed** (`0`–`999`), and the fixed page **header** from code (not edited in the form). Set **`FRACTIONS_PUBLIC_URL`** to the public UI base (e.g. `https://example.com/fractions`) so PDF footers show the right **URL** segment; if unset, the app falls back to **`request.base_url`** (fine for local dev).

**Behind a reverse proxy** (e.g. public URL is `https://example.com/fractions…`), set **`ROOT_PATH`** to the URL path prefix: no trailing slash, leading slash is optional in the env (e.g. `fractions` and `/fractions` are the same), for example:

```bash
export ROOT_PATH=/fractions
uvicorn app:app --host 0.0.0.0 --port 8000
```

This sets FastAPI’s `root_path` so link helpers (e.g. the form’s post URL) use the right prefix. If the proxy forwards the **full** public path to Uvicorn (e.g. `GET /fractions` and `GET /fractions/` with no further rewrite), the app **strips** that prefix on each request, and **`redirect_slashes`** is off so you do not get a **307** to add a trailing slash. Your proxy should still be configured to forward to the app and set `X-Forwarded-Proto` / `Host` as usual. Prefer **`FRACTIONS_PUBLIC_URL`** for the footer so it shows the **public** hostname, not the internal service URL.

**HTTPS and the form `action` URL:** the HTML form uses `request.url_for("generate")`, which follows the request **scheme** (`http` vs `https`). The browser loads your site over **TLS**, but Uvicorn often sees only **HTTP** from the next hop (Nginx, Traefik, a load balancer). If **`X-Forwarded-Proto: https`** is not applied to the ASGI scope, the server builds **`http://…`** for the form, and the browser may warn about mixed content or “insecure” submission. The app includes **`ProxyHeadersMiddleware`** (same idea as Uvicorn’s) with **`FORWARDED_TRUSTED_PROXIES`** (default `*`, meaning: trust the connecting client to send forwarded headers; in production, set this to your proxy’s IP range, e.g. `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` or a single Nginx address). Your reverse proxy should send at least `X-Forwarded-Proto: https` when the client used HTTPS. You can also run Uvicorn with `--forwarded-allow-ips` if you prefer that path only.

| Path | Description |
|------|-------------|
| `GET /` | Form |
| `POST /generate` | Returns `application/pdf` |

## Docker

Build the image (see [`Makefile`](Makefile)):

```bash
make build
# Optional: make build IMAGE_NAME=myorg/fractions
```

Run:

```bash
docker run --rm -p 8000:8000 fractions
# Optional: -e ROOT_PATH=/fractions -e FRACTIONS_PUBLIC_URL=https://example.com/fractions
```

The image runs **Uvicorn** on port **8000** (see [`Dockerfile`](Dockerfile)).

## Tuning the PDF (code constants)

Most visual settings live at the top of [`fraction_practice.py`](fraction_practice.py), including:

- **Header:** `PAGE_HEADER_TEXT`, `PAGE_HEADER_FONT`, `PAGE_HEADER_FONT_SIZE`
- **Footer:** `FOOTER_FONT`, `FOOTER_FONT_SIZE` (plus bottom margin / reserved space near `_FOOTER_RESERVE`)
- **Pies:** `PIE_SHADED_FILL_RGB`, `PIE_DIVIDERS_STROKE_PT`, `PIE_OUTLINE_CIRCLE_STROKE_PT`, `PIE_RIM_TO_ANSWERS_GAP_PT`
- **Answer bubbles and labels:** `ANSWERS_*` (font, spacing, bubble size, stroke, gap to fraction text, etc.)

## Project layout

| Path | Description |
|------|-------------|
| `fraction_practice.py` | CLI, PDF engine (`write_fractions_pdf` for reuse) |
| `app.py` | Optional FastAPI app |
| `templates/` | Jinja2 HTML for the web form |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image (Uvicorn, port 8000) |
| `Makefile` | `make build` → `docker build` |
| `output/` | Default location for CLI PDFs |

## License

Add a license if you publish this project.

# Bootstrap Bench

A standalone, client-side what-if tool for Scheme 3 (monotone-cubic) curve
bootstrapping. Move par-rate sliders and a short-rate anchor (r0) and it
redraws the implied instantaneous forward, spot, and discount curves out to
360 months, with a live round-trip fit check. Includes an "Export 30Y
forward curves" button that builds an .xlsx workbook of forward-implied par
yield / spot / discount grids (quarterly, 0-30Y), and a paste-in importer
for Treasury.gov's daily par yield curve table.

The bootstrap math (`bootstrapScheme2`/`bootstrapScheme3`, root-finding,
discount/forward evaluation) is a direct JS port of `src/cmt_bootstrap.py`'s
Scheme 2/3 logic, verified against the Python implementation to match to
10 decimal places. If `cmt_bootstrap.py`'s Scheme 2/3 math changes, this
file should be re-verified against it (see the parent repo's history for
the verification approach used when this was first ported).

## Running it

It's a single self-contained HTML file — no build step, no server, no
dependencies beyond two public CDN scripts (Google Fonts, SheetJS for the
Excel export). Open `index.html` directly in a browser, or:

- **GitHub Pages (recommended for sharing a stable link):** this repo ships
  a workflow (`.github/workflows/deploy-pages.yml`) that deploys this
  folder to Pages on every push to `main` that touches it. One-time setup:
  in the repo's **Settings → Pages**, set **Source** to **GitHub Actions**
  — after that it deploys automatically. Once enabled, it's served at
  `https://<owner>.github.io/<repo>/`.
- **CodeSandbox:** use "Import from GitHub" and point it at this
  repo/branch/path (`web/bootstrap-bench`) — CodeSandbox will serve
  `index.html` directly. Better if you want visitors to fork/edit the code
  in-browser rather than just run it; for just sharing the running tool,
  prefer Pages above.
- Any other static host (Netlify, a plain `python -m http.server`) works
  the same way — it's dependency-free besides the two CDN scripts.

## Notes

- All state (slider positions, an imported curve) lives only in that
  browser tab — nothing here talks to this repo or persists anywhere.
- The Excel export tries a Claude-Artifact-only download API first and
  falls back to a normal browser download when that API isn't present
  (i.e., everywhere this file is hosted outside a Claude Artifact).

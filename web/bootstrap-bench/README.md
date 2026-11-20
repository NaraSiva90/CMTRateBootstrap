# Bootstrap Bench

A standalone, client-side what-if tool for Scheme 3 (monotone-cubic) curve
bootstrapping. Move par-rate sliders and a short-rate anchor (r0) and it
redraws the implied instantaneous forward, spot, and discount curves out to
360 months, with a live round-trip fit check. Includes an "Export 30Y
forward curves" button that builds an .xlsx workbook of forward-implied par
yield / spot / discount grids (quarterly, 0-30Y), and a paste-in importer
for Treasury.gov's daily par yield curve table.

## Shock scenario tab

The second tab overlays a shocked curve on the base curve from the first tab,
in the same three charts (the base curve is drawn dashed). The hover readout
gives base, shocked and change for each measure.

- **How the shock is applied:** each row's shock in basis points is added to
  that par rate, and to r0, and the shocked curve is then bootstrapped again
  from those inputs. Par rates therefore move by exactly the shock; forward
  and spot rates move by roughly, not exactly, that amount.
- **Specifying it:** one parallel shift (default +100 bp) fills every row.
  Typing in a row sets that tenor's shock on its own; it then ignores later
  changes to the parallel shift until cleared with its × button. "Reset to
  +100 bp parallel" clears every row.
- **Export:** the workbook always includes the shocked curve as three more
  sheets (`Shocked Par Yield fwd %`, `Shocked Spot Rate fwd %`,
  `Shocked Discount Factor fwd`) in the same layout as the base sheets. The
  `Inputs` sheet records the base, shock and shocked value for every row.

The bootstrap math (`bootstrapScheme2`/`bootstrapScheme3`, root-finding,
discount/forward evaluation) is a direct JS port of `src/cmt_bootstrap.py`'s
Scheme 2/3 logic, verified against the Python implementation to match to
10 decimal places. If `cmt_bootstrap.py`'s Scheme 2/3 math changes, this
file should be re-verified against it (see the parent repo's history for
the verification approach used when this was first ported).

## Try it

No install needed. Both links serve this folder from the `main` branch, so
they show the same version.

- **Run it: <https://narasiva90.github.io/CMTRateBootstrap/>** (GitHub
  Pages). Use this one to open or share the tool. It is the page on its own,
  with no editor around it and no account needed.
- **See the code beside it:
  <https://codesandbox.io/p/sandbox/github/NaraSiva90/CMTRateBootstrap/tree/main/web/bootstrap-bench>**
  (CodeSandbox). Use this one to read the source next to the running page,
  or to fork a private copy to experiment with. It is a read-only view of
  this repository; a fork is a snapshot and does not follow later changes
  here.

## Running it yourself

It's a single self-contained HTML file with no build step and no server. Its
only outside dependencies are two public CDN resources (Google Fonts, and
SheetJS for the Excel export). Open `index.html` directly in a browser, or
serve the folder from any static host (for example `python -m http.server`).

## How the hosted copies stay current

- **GitHub Pages:** `.github/workflows/deploy-pages.yml` redeploys this
  folder on every push to `main` that touches it. This relies on the
  repository setting **Settings → Pages → Source → GitHub Actions**. A fork
  of this repository needs the same setting before its own deployment works.
- **CodeSandbox:** the link above reads this folder from `main` each time it
  is opened, so there is nothing to deploy. Edits can't be made through it;
  changes go through this repository.

## Notes

- All state (slider positions, an imported curve) lives only in that
  browser tab — nothing here talks to this repo or persists anywhere.
- The Excel export tries a Claude-Artifact-only download API first and
  falls back to a normal browser download when that API isn't present
  (i.e., everywhere this file is hosted outside a Claude Artifact).

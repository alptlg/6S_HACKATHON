# NYC EMS Response Time Dashboard
**Cornell SYSEN 5300 · Six Sigma Hackathon · Team Chiblings**

Interactive Six Sigma / SPC dashboard for analysing NYC EMS response times.  
Single self-contained HTML file — no server, no dependencies to install.

---

## Quick Start

```bash
# 1. Open the dashboard (no build needed)
open index.html        # macOS
xdg-open index.html    # Linux

# Or just drag index.html into any browser.
```

To rebuild from source after changing data or template:

```bash
# Re-pack CSVs into compact JS arrays (4,800 stratified rows per scenario)
python pack_data.py --all

# Splice data + borough map images into the HTML template
python build_page.py
```

---

## Repository Layout

```
.
├── index.html              # ← Deliverable: open this in a browser
│
├── qc.py                   # Statistical QC functions (lognormal I-MR, Cpk, CI)
├── main.py                 # CLI: load CSV → print SPC report
├── pack_data.py            # Stratified sample + pack CSVs → compact JS arrays
├── build_page.py           # Splice template + data + maps → index.html
│
├── data/
│   ├── codebook.md         # Column definitions, encodings, statistical methods
│   ├── stable_operations_2026_24000_synthetic.csv
│   ├── highDelay_2026_24000_synthetic.csv
│   └── noDelay_2026_24000_synthetic.csv
│
└── scratchpad/             # Build artefacts (not committed)
    ├── index_v9.html       # HTML template with __DATA_BLOB__ placeholder
    ├── data_all_v4.js      # Packed data blob (4,800 rows × 3 scenarios)
    └── map_images_block.txt  # Base64 borough map PNGs (9 MB)
```

---

## CLI Analysis

```bash
# Print SPC report for stable scenario, all boroughs, full year
python main.py --scenario stable

# Manhattan only, last month
python main.py --scenario delay --borough Manhattan --window 1mo

# Per-borough breakdown table
python main.py --scenario fast --borough all --breakdown

# Custom CSV
python main.py --csv data/my_data.csv --window 6mo
```

---

## Statistics

All formulas live in `qc.py::compute_stats()` and are mirrored exactly in the JS dashboard.

| Quantity | Formula |
|---|---|
| Geometric mean | `exp(mean(ln RT))` |
| 95% CI | `[exp(μ_log ± t_{n-1} · σ_log/√n)]` back-transformed |
| I-MR UCL (log) | `μ_log + 2.660 × MR̄` |
| MR UCL | `3.267 × MR̄` |
| Process capability | `Cpu = (ln(8.0) − μ_log) / (3 σ_log)` |

Run `python qc.py` to execute the known-answer self-test suite.

---

## Dashboard Features

- **3 built-in scenarios**: Stable Operations, High Delay, No Delay/Fast
- **Custom CSV upload**: drag-and-drop any CSV matching the codebook schema
- **Time windows**: Full Year · Last 6 Mo · Last 1 Mo · Last Week · Last Day
- **Per-borough drilldown**: I-MR control chart, MR chart, Cpk, good/fair/bad breakdown
- **Centerline toggle**: Geometric mean (lognormal) ↔ Arithmetic mean
- **NFPA 1710 USL** reference line at 8.0 min
- **OOC highlighting**: Out-of-control points flagged red on I-chart
- **Borough map view**: Base64-embedded PNG maps coloured by response-time zone

---

## Security

- No secrets, API keys, or server URLs in any file
- No network requests at runtime (100% offline after page load)
- Test data lives in `data/` with `data/codebook.md`
- `python qc.py` must pass before any UI changes are made

---

## Data

Synthetic data generated to simulate EMS response patterns.  
Not real FDNY / NYC EMS records.  
See `data/codebook.md` for full schema documentation.

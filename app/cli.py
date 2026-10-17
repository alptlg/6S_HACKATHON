#!/usr/bin/env python3
"""
cli.py — CLI entry point for NYC EMS Response Time Analysis
Cornell SYSEN 5300 · Six Sigma Hackathon · Team Chiblings

Usage:
    python app/cli.py --scenario stable
    python app/cli.py --scenario delay --borough Manhattan
    python app/cli.py --scenario fast  --borough all --window 1mo
    python app/cli.py --csv data/my_custom_file.csv --borough Queens
    python app/cli.py --report pdf --out reports/
"""

import argparse
import csv
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from types import SimpleNamespace

try:
    from qc import NFPA_USL_MIN as NFPA_USL, run_qc
except ModuleNotFoundError:
    from app.qc import NFPA_USL_MIN as NFPA_USL, run_qc


# ── Constants ─────────────────────────────────────────────────────────────
BOROUGHS = ["Queens", "Brooklyn", "Manhattan", "Bronx", "Staten Island"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCENARIOS = {
    "stable": str(DATA_DIR / "stable_operations_2026_24000_synthetic.csv"),
    "delay":  str(DATA_DIR / "highDelayAlex_2026_24000_synthetic.csv"),
    "fast":   str(DATA_DIR / "noDelayAlexData_2026_24000_synthetic.csv"),
}
WINDOWS = {"all", "6mo", "1mo", "week", "day"}

EPOCH = datetime(2026, 1, 1)  # day_offset reference point


# ── Data loading ──────────────────────────────────────────────────────────
def load_csv(path: str) -> list[dict]:
    """
    Load a response-time CSV and return normalised row dicts.

    Accepted schemas (mirrors JS parseCustomCSV):
      - Schema A (no_delay / high_delay):
          incident_id, call_received, dispatch_time, on_scene_time,
          borough, zone, response_time_min, traffic_level,
          available_units, priority, simulated_special_cause
      - Schema B (stable_operations):
          incident_id, call_received, dispatch_time, on_scene_time,
          zone [used as borough], traffic_level, available_units,
          priority, simulated_special_cause
          (no borough or response_time_min columns)

    Returns list of dicts with keys:
        zone, rt, priority, traffic, units, day, hour
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = [h.strip().lower().replace(" ", "_") for h in reader.fieldnames or []]

        for raw in reader:
            row = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in raw.items()}

            # Borough / zone
            zone_raw = (row.get("borough") or row.get("zone") or "").strip()
            zone = next((b for b in BOROUGHS if b.lower() == zone_raw.lower()), None)
            if not zone:
                continue

            # Response time
            if "response_time_min" in header and row.get("response_time_min"):
                try:
                    rt = float(row["response_time_min"])
                except ValueError:
                    continue
            else:
                try:
                    t0 = datetime.fromisoformat(row["call_received"])
                    t1 = datetime.fromisoformat(row["on_scene_time"])
                    rt = (t1 - t0).total_seconds() / 60
                except (KeyError, ValueError):
                    continue

            if rt <= 0 or rt > 300:
                continue

            # Day offset & hour
            try:
                call_dt = datetime.fromisoformat(row["call_received"])
                day = (call_dt.date() - EPOCH.date()).days
                hour = call_dt.hour
            except (KeyError, ValueError):
                day, hour = 0, 0

            # Traffic
            trf_raw = (row.get("traffic_level") or "").lower()
            if "gridlock" in trf_raw or "high" in trf_raw:
                traffic = "High"
            elif "medium" in trf_raw or "moderate" in trf_raw:
                traffic = "Medium"
            else:
                traffic = "Low"

            # Priority
            pri_raw = (row.get("priority") or "").lower()
            if "high" in pri_raw or pri_raw == "1":
                priority = 1
            elif "medium" in pri_raw or "moderate" in pri_raw or pri_raw == "3":
                priority = 3
            else:
                priority = 6

            # Units
            try:
                units = int(float(row.get("available_units", 1)))
            except (ValueError, TypeError):
                units = 1

            rows.append({
                "zone": zone,
                "rt": rt,
                "priority": priority,
                "traffic": traffic,
                "units": units,
                "day": day,
                "hour": hour,
            })

    return rows


def filter_by_window(rows: list[dict], window: str) -> list[dict]:
    """Return rows within the requested time window relative to max day_offset."""
    if window == "all" or not rows:
        return rows
    max_day = max(r["day"] for r in rows)
    delta = {"6mo": 182, "1mo": 30, "week": 7, "day": 1}.get(window, 0)
    min_day = max(0, max_day - delta)
    return [r for r in rows if r["day"] >= min_day]


def filter_by_borough(rows: list[dict], borough: str) -> list[dict]:
    """Return rows for a specific borough (or all if borough == 'all')."""
    if borough.lower() == "all":
        return rows
    target = next((b for b in BOROUGHS if b.lower() == borough.lower()), None)
    if not target:
        raise ValueError(f"Unknown borough '{borough}'. Choose from: {BOROUGHS}")
    return [r for r in rows if r["zone"] == target]


# ── Summary (statistics come from qc.run_qc; nothing is computed here) ──
def compute_stats(rt_vals: list[float]) -> SimpleNamespace | None:
    """Flatten qc.run_qc into the fields the reports print. None if n < 4."""
    if len(rt_vals) < 4:
        return None
    q = run_qc(rt_vals)
    n = q.descriptive.n
    good = sum(1 for v in rt_vals if v < 8)
    bad = sum(1 for v in rt_vals if v >= 15)
    fair = n - good - bad
    imr = SimpleNamespace(
        log_cl=q.imr.log_cl, log_ucl=q.imr.log_ucl, log_lcl=q.imr.log_lcl,
        ucl_min=q.imr.ucl_min, lcl_min=q.imr.lcl_min,
        ooc_high=q.imr.n_above_ucl, ooc_low=q.imr.n_below_lcl,
        ooc_total=q.imr.n_above_ucl + q.imr.n_below_lcl,
    )
    return SimpleNamespace(
        n=n, arith_mean=q.descriptive.mean, geo_mean=q.ci.geo_mean,
        geo_ci_low=q.ci.geo_ci_low, geo_ci_high=q.ci.geo_ci_high,
        p90=q.descriptive.p90, cpk=q.capability.cpk, imr=imr,
        good=good, fair=fair, bad=bad,
        good_pct=100 * good / n, fair_pct=100 * fair / n, bad_pct=100 * bad / n,
    )


# ── Reporting ─────────────────────────────────────────────────────────────
def _bar(value: float, total: int, width: int = 20) -> str:
    """Simple ASCII bar chart element."""
    filled = round(value / 100 * width) if total else 0
    return "█" * filled + "░" * (width - filled)


def print_report(rows: list[dict], label: str) -> None:
    """Print a formatted SPC summary to stdout."""
    rt_vals = [r["rt"] for r in rows]
    s = compute_stats(rt_vals)

    print(f"\n{'═'*60}")
    print(f"  NYC EMS Response Time — {label}")
    print(f"{'═'*60}")

    if s is None:
        print(f"  ⚠  Insufficient data (n={len(rt_vals)}, need ≥4)")
        return

    # Overview
    print(f"\n  Observations : {s.n:,}")
    print(f"  Arithmetic μ : {s.arith_mean:.2f} min")
    print(f"  Geometric  μ : {s.geo_mean:.2f} min  "
          f"[95% CI: {s.geo_ci_low:.2f} – {s.geo_ci_high:.2f}]")
    print(f"  p90          : {s.p90:.2f} min")
    print(f"  Cpk (log)    : {s.cpk:.3f}  "
          f"({'✅ capable' if s.cpk >= 1.33 else '⚠ marginal' if s.cpk >= 1.0 else '❌ not capable'})")
    print(f"  NFPA 1710 USL: {NFPA_USL:.1f} min")

    # I-MR summary
    imr = s.imr
    print(f"\n  ── I-MR Control Chart (log scale) ──")
    print(f"  CL  = {math.exp(imr.log_cl):.2f} min  (ln={imr.log_cl:.4f})")
    print(f"  UCL = {imr.ucl_min:.2f} min  (ln={imr.log_ucl:.4f})")
    print(f"  LCL = {imr.lcl_min:.2f} min  (ln={imr.log_lcl:.4f})")
    print(f"  OOC : {imr.ooc_total} points  "
          f"({imr.ooc_high} above UCL, {imr.ooc_low} below LCL)")

    # Category breakdown
    print(f"\n  ── Response Time Categories ──")
    print(f"  Good  (<8 min) : {s.good:>5,}  {_bar(s.good_pct, s.n)}  {s.good_pct:5.1f}%")
    print(f"  Fair  (8–15)   : {s.fair:>5,}  {_bar(s.fair_pct, s.n)}  {s.fair_pct:5.1f}%")
    print(f"  Bad   (≥15)    : {s.bad:>5,}  {_bar(s.bad_pct, s.n)}  {s.bad_pct:5.1f}%")

    print()


def print_borough_breakdown(rows: list[dict], scenario_label: str) -> None:
    """Print per-borough stats table."""
    print(f"\n{'─'*80}")
    print(f"  PER-BOROUGH BREAKDOWN — {scenario_label}")
    print(f"{'─'*80}")
    print(f"  {'Borough':<16} {'n':>5}  {'Geo μ':>7}  {'p90':>6}  {'Cpk':>6}  "
          f"{'Good%':>6}  {'Fair%':>6}  {'Bad%':>5}  {'OOC':>4}")
    print(f"  {'─'*16} {'─'*5}  {'─'*7}  {'─'*6}  {'─'*6}  "
          f"{'─'*6}  {'─'*6}  {'─'*5}  {'─'*4}")

    for borough in BOROUGHS:
        br = [r for r in rows if r["zone"] == borough]
        s  = compute_stats([r["rt"] for r in br])
        if s is None:
            print(f"  {borough:<16} {'—':>5}")
            continue
        cpk_str = f"{s.cpk:.2f}" if s.cpk < 99 else ">99"
        print(
            f"  {borough:<16} {s.n:>5,}  {s.geo_mean:>7.2f}  {s.p90:>6.2f}  "
            f"{cpk_str:>6}  {s.good_pct:>5.1f}%  {s.fair_pct:>5.1f}%  "
            f"{s.bad_pct:>4.1f}%  {s.imr.ooc_total:>4}"
        )
    print()


# ── CLI ───────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="NYC EMS Response Time — Six Sigma Analysis CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/cli.py --scenario stable
  python app/cli.py --scenario delay  --borough Manhattan --window 1mo
  python app/cli.py --csv data/custom.csv --window 6mo
  python app/cli.py --scenario fast   --borough all      --breakdown
""",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--scenario", choices=["stable", "delay", "fast"],
                     help="Built-in scenario CSV (stable / delay / fast)")
    src.add_argument("--csv", metavar="FILE",
                     help="Path to a custom CSV file")

    p.add_argument("--borough", default="all",
                   help="Borough to analyse ('all' or e.g. 'Manhattan')")
    p.add_argument("--window", default="all", choices=list(WINDOWS),
                   help="Time window (all / 6mo / 1mo / week / day)")
    p.add_argument("--breakdown", action="store_true",
                   help="Print per-borough breakdown table")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Locate CSV
    if args.scenario:
        csv_path = SCENARIOS[args.scenario]
        label_base = {"stable": "Stable Operations", "delay": "High Delay",
                      "fast": "No Delay / Fast"}[args.scenario]
    else:
        csv_path = args.csv
        label_base = Path(args.csv).stem

    if not os.path.exists(csv_path):
        print(f"Error: CSV not found at '{csv_path}'", file=sys.stderr)
        print("  Put your CSVs in the data/ directory and re-run.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {csv_path} …", end=" ", flush=True)
    rows = load_csv(csv_path)
    print(f"{len(rows):,} valid rows loaded.")

    # Apply filters
    rows = filter_by_window(rows, args.window)
    window_label = {"all": "Full Year", "6mo": "Last 6 Mo", "1mo": "Last 1 Mo",
                    "week": "Last Week", "day": "Last Day"}.get(args.window, args.window)

    borough_label = args.borough if args.borough.lower() != "all" else "All Boroughs"
    label = f"{label_base} · {borough_label} · {window_label}"

    analysis_rows = filter_by_borough(rows, args.borough)
    print_report(analysis_rows, label)

    if args.breakdown:
        print_borough_breakdown(rows, f"{label_base} · {window_label}")


if __name__ == "__main__":
    main()

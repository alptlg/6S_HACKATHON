#!/usr/bin/env python3
"""
pack_data.py — Convert raw CSVs into the compact JS array format for index.html

Cornell SYSEN 5300 · Six Sigma Hackathon · Team Chiblings

Packed row format (7 integers per call):
    [zone_idx, rt×10, priority_int, traffic_idx, units, day_offset, hour]

  zone_idx   : Queens=0, Brooklyn=1, Manhattan=2, Bronx=3, Staten Island=4
  rt×10      : response_time_min × 10, rounded to int (÷10 in JS → minutes)
  priority   : High=1, Medium=3, Low=6
  traffic_idx: Low=0, Medium=1, High=2  (Gridlock → 2)
  day_offset : days since 2026-01-01
  hour       : 0–23

Stratified sample: 80 rows per zone per calendar month = 4,800 rows/scenario.
This keeps the JS payload under ~300 KB while covering the full year.

Usage:
    python pack_data.py                           # uses defaults in PATHS dict
    python pack_data.py --stable  path/stable.csv
    python pack_data.py --delay   path/delay.csv
    python pack_data.py --fast    path/fast.csv
    python pack_data.py --all                     # re-pack all three
    python pack_data.py --out     data_all_v5.js  # custom output filename

Output goes to: scratchpad/data_all_vN.js  (or --out path)
"""

import argparse
import csv
import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from cli import load_csv  # reuse the normalised loader

# ── Configuration ─────────────────────────────────────────────────────────
ROWS_PER_ZONE_MONTH = 80   # 80 × 5 zones × 12 months = 4,800 rows per scenario
RANDOM_SEED = 42

ZONE_IDX = {
    "Queens":       0,
    "Brooklyn":     1,
    "Manhattan":    2,
    "Bronx":        3,
    "Staten Island":4,
}
PRIORITY_INT = {1: 1, 3: 3, 6: 6}
TRAFFIC_IDX  = {"Low": 0, "Medium": 1, "High": 2}

EPOCH = datetime(2026, 1, 1)

# Default CSV paths — override with CLI flags
SCRATCHPAD = Path("/tmp/claude-0/-home-claude/ef6604ec-0032-5929-afa8-84749fa2f3ab/scratchpad")
PATHS = {
    "stable": "data/stable_operations_2026_24000_synthetic.csv",
    "delay":  "data/highDelay_2026_24000_synthetic.csv",
    "fast":   "data/noDelay_2026_24000_synthetic.csv",
}
DEFAULT_OUT = SCRATCHPAD / "data_all_v5.js"


# ── Packing helpers ───────────────────────────────────────────────────────
def row_month(row: dict) -> int:
    """Return 1-based calendar month from day_offset."""
    d = EPOCH + __import__("datetime").timedelta(days=row["day"])
    return d.month


def pack_row(r: dict) -> list[int]:
    """Convert a normalised row dict to the 7-integer packed format."""
    zone_i   = ZONE_IDX.get(r["zone"], 0)
    rt_int   = max(1, round(r["rt"] * 10))        # ×10, min 1
    pri_int  = PRIORITY_INT.get(r["priority"], 3)
    trf_i    = TRAFFIC_IDX.get(r["traffic"], 0)
    units    = max(1, min(r["units"], 9))          # clamp 1–9
    day      = int(r["day"])
    hour     = int(r["hour"])
    return [zone_i, rt_int, pri_int, trf_i, units, day, hour]


def stratified_sample(rows: list[dict], n_per_zone_month: int, seed: int) -> list[dict]:
    """
    Stratified random sample: n_per_zone_month rows per (zone, month) bucket.
    If a bucket has fewer rows, all are taken.
    """
    rng = random.Random(seed)
    buckets: dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = (r["zone"], row_month(r))
        buckets[key].append(r)

    sampled = []
    for key in sorted(buckets):
        bucket = buckets[key]
        rng.shuffle(bucket)
        sampled.extend(bucket[:n_per_zone_month])

    # Sort by day then hour so the I-MR chart runs chronologically
    sampled.sort(key=lambda r: (r["day"], r["hour"]))
    return sampled


def pack_scenario(csv_path: str, label: str, seed: int = RANDOM_SEED) -> str:
    """
    Load a CSV, stratified-sample it, pack to int arrays.

    Returns a JS const declaration string:
        const RAW_STABLE=[[...],[...],...];
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    print(f"  Loading {csv_path} …", end=" ", flush=True)
    rows = load_csv(csv_path)
    print(f"{len(rows):,} rows loaded.")

    sampled = stratified_sample(rows, ROWS_PER_ZONE_MONTH, seed)
    print(f"  Stratified sample: {len(sampled):,} rows "
          f"({ROWS_PER_ZONE_MONTH}/zone/month × 5 zones × 12 months)")

    # Validate coverage
    buckets: dict[tuple, int] = defaultdict(int)
    for r in sampled:
        buckets[(r["zone"], row_month(r))] += 1
    sparse = [(z, m, c) for (z, m), c in buckets.items() if c < ROWS_PER_ZONE_MONTH]
    if sparse:
        print(f"  ⚠  Sparse buckets (fewer than {ROWS_PER_ZONE_MONTH} rows):")
        for z, m, c in sorted(sparse):
            print(f"       {z} month {m:02d}: {c} rows")

    packed = [pack_row(r) for r in sampled]
    var_name = f"RAW_{label.upper()}"
    rows_js = ",".join(f"[{','.join(map(str, p))}]" for p in packed)
    print(f"  Packed {len(packed)} rows → {var_name}  "
          f"({len(rows_js)//1024} KB)")
    return f"const {var_name}=[{rows_js}];"


def compute_preview(rows_js: str, var: str) -> None:
    """Quick sanity print — parse the JS literal back to Python."""
    import ast
    inner = rows_js[len(f"const {var}=["):-2]  # strip const X=[ and ];
    arrays = ast.literal_eval(f"[{inner}]")
    rts = [a[1] / 10 for a in arrays]
    geo = math.exp(sum(math.log(max(v, 0.01)) for v in rts) / len(rts))
    good = sum(1 for v in rts if v < 8)
    bad  = sum(1 for v in rts if v >= 15)
    print(f"  Preview: n={len(arrays)}, geo_mean={geo:.2f} min, "
          f"good={good/len(arrays)*100:.0f}%, bad={bad/len(arrays)*100:.0f}%")


# ── CLI ───────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pack raw CSVs into compact JS arrays for index.html",
    )
    p.add_argument("--stable", metavar="CSV",
                   help="Stable operations CSV (default: data/stable_operations…)")
    p.add_argument("--delay",  metavar="CSV",
                   help="High delay CSV (default: data/highDelay…)")
    p.add_argument("--fast",   metavar="CSV",
                   help="No delay / fast CSV (default: data/noDelay…)")
    p.add_argument("--all", action="store_true",
                   help="Re-pack all three scenarios using defaults")
    p.add_argument("--out", metavar="FILE", default=str(DEFAULT_OUT),
                   help=f"Output JS file (default: {DEFAULT_OUT})")
    p.add_argument("--seed", type=int, default=RANDOM_SEED,
                   help=f"Random seed for sampling (default: {RANDOM_SEED})")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve which scenarios to pack
    to_pack: dict[str, str] = {}
    if args.stable:
        to_pack["stable"] = args.stable
    if args.delay:
        to_pack["delay"] = args.delay
    if args.fast:
        to_pack["fast"] = args.fast
    if args.all or not to_pack:
        to_pack = dict(PATHS)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    blobs: dict[str, str] = {}

    # Pack each requested scenario
    for key, csv_path in to_pack.items():
        print(f"\n── {key.upper()} ──────────────────────────────")
        blob = pack_scenario(csv_path, key, seed=args.seed)
        compute_preview(blob, f"RAW_{key.upper()}")
        blobs[key] = blob

    # If we're not repacking all three, read existing file to preserve others
    existing: dict[str, str] = {}
    if out_path.exists() and len(blobs) < 3:
        print(f"\nReading existing {out_path} to preserve un-modified scenarios …")
        with open(out_path) as f:
            content = f.read()
        for key in ("stable", "delay", "fast"):
            var = f"RAW_{key.upper()}"
            start = content.find(f"const {var}=[")
            if start >= 0:
                end = content.find("];", start) + 2
                existing[key] = content[start:end]

    # Merge: new blobs take priority
    final: dict[str, str] = {**existing, **blobs}

    # Write JS file
    lines = [
        "// Auto-generated by pack_data.py — do not edit by hand",
        f"// Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"// Rows per zone/month: {ROWS_PER_ZONE_MONTH} | Seed: {args.seed}",
        "",
    ]
    for key in ("stable", "delay", "fast"):
        if key in final:
            lines.append(final[key])
    lines.append(f"const STABLE_IS_PLACEHOLDER={'false' if 'stable' in final else 'true'};")
    lines.append("")

    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    size = out_path.stat().st_size
    print(f"\n✅ Written to {out_path}  ({size:,} bytes / {size//1024} KB)")
    print("\nNext step:")
    print("  python build_page.py")
    print("  # which splices the data blob + map images into index.html")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
build_page.py — Splice data blob + map images into the HTML template.

Cornell SYSEN 5300 · Six Sigma Hackathon · Team Chiblings

Pipeline:
    pack_data.py  →  data_all_vN.js
                  ↘
    map_images_block.txt  →  build_page.py  →  index.html
                  ↗
    index_template.html

Usage:
    python build_page.py                      # uses paths below
    python build_page.py --data data_all.js   # custom data blob
    python build_page.py --maps /tmp/maps.txt # custom map images file
    python build_page.py --out  /var/www/index.html

Template placeholders replaced:
    __DATA_BLOB__   → contents of the data JS file (RAW_* arrays)
    __MAP_IMAGES__  → contents of map_images_block.txt (base64 PNGs)
"""

import argparse
import os
import sys
from pathlib import Path

# ── Default paths ─────────────────────────────────────────────────────────
SCRATCHPAD  = Path("/tmp/claude-0/-home-claude/ef6604ec-0032-5929-afa8-84749fa2f3ab/scratchpad")
TEMPLATE    = SCRATCHPAD / "index_v9.html"
DATA_FILE   = SCRATCHPAD / "data_all_v4.js"
MAPS_FILE   = Path("/tmp/map_images_block.txt")
OUT         = Path("/home/claude/index.html")

# Sanity-check strings that must / must not appear in the final file
MUST_CONTAIN = [
    "RAW_STABLE",
    "RAW_DELAY",
    "RAW_FAST",
    "STABLE_IS_PLACEHOLDER",
    "MAP_IMAGES",
    "computeStats",
    "selfTest",
    "NFPA_USL",
    "Chart.js",
    "parseCustomCSV",
]
MUST_NOT_CONTAIN = [
    "__DATA_BLOB__",
    "__MAP_IMAGES__",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build index.html from template + data + maps",
    )
    p.add_argument("--template", default=str(TEMPLATE),
                   help=f"HTML template file (default: {TEMPLATE})")
    p.add_argument("--data", default=str(DATA_FILE),
                   help=f"Packed JS data blob (default: {DATA_FILE})")
    p.add_argument("--maps", default=str(MAPS_FILE),
                   help=f"Map images JS block (default: {MAPS_FILE})")
    p.add_argument("--out", default=str(OUT),
                   help=f"Output HTML file (default: {OUT})")
    return p.parse_args()


def load(path: str, label: str) -> str:
    if not os.path.exists(path):
        print(f"ERROR: {label} not found at '{path}'", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return f.read()


def main() -> None:
    args = parse_args()

    print("Building index.html …\n")
    print(f"  Template : {args.template}")
    print(f"  Data     : {args.data}")
    print(f"  Maps     : {args.maps}")
    print(f"  Output   : {args.out}\n")

    html      = load(args.template, "Template")
    data_blob = load(args.data,     "Data blob")

    if os.path.exists(args.maps):
        maps_block = load(args.maps, "Map images")
    else:
        maps_block = "const MAP_IMAGES = {};"
        print(f"  ⚠  Map images not found at {args.maps} — using empty MAP_IMAGES\n"
              "      Borough map tabs will show a blank area.\n"
              "      To fix: run generate_maps.py or provide the maps file.\n")

    # Splice
    html = html.replace("__DATA_BLOB__",  data_blob)
    html = html.replace("__MAP_IMAGES__", maps_block)

    # ── Sanity checks ─────────────────────────────────────────────────────
    errors = []
    for token in MUST_CONTAIN:
        if token not in html:
            errors.append(f"MISSING in output: '{token}'")
    for token in MUST_NOT_CONTAIN:
        if token in html:
            errors.append(f"PLACEHOLDER still present: '{token}'")

    if errors:
        print("Build FAILED — sanity checks:", file=sys.stderr)
        for e in errors:
            print(f"  ✗  {e}", file=sys.stderr)
        sys.exit(1)

    print("  Sanity checks:")
    for token in MUST_CONTAIN:
        print(f"  ✅ {token}")
    for token in MUST_NOT_CONTAIN:
        print(f"  ✅ {token!r} absent")

    # Write output
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size = out_path.stat().st_size
    print(f"\n✅ Built {args.out}")
    print(f"   Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
    print("\nDone. Open index.html in a browser to verify.")


if __name__ == "__main__":
    main()

"""Command-line entry point.

Usage (from repository root):

    python -m pipeline.cli inventory
    python -m pipeline.cli extract
    python -m pipeline.cli reconcile
    python -m pipeline.cli map
    python -m pipeline.cli vocab
    python -m pipeline.cli validate
    python -m pipeline.cli all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python -m pipeline.cli` from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="NMAA Archives EAD → CIDOC CRM pipeline")
    parser.add_argument(
        "stage",
        choices=["inventory", "extract", "reconcile", "map", "validate", "slideshow", "vocab", "all"],
    )
    parser.add_argument("--live", action="store_true", help="Optional live vocabulary lookups")
    parser.add_argument("--probe-iiif", action="store_true", help="HTTP-probe derived IIIF URLs")
    parser.add_argument(
        "--fetch-slideshow",
        action="store_true",
        help="Harvest EDAN slideshow page IDS ids (also implied by stage slideshow)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Map only the first N components")
    parser.add_argument(
        "--ead",
        default=None,
        help="EAD XML path (default srcdata/FSA.A.04-ead.xml; use FSA.A.06-ead.xml for Herzfeld)",
    )
    args = parser.parse_args(argv)
    ead_path = args.ead

    if args.stage in {"inventory", "all"}:
        from pipeline.inventory import run as inventory

        report = inventory(ead_path)
        print("inventory components:", report["components"])
        print("digitized:", report["digitized_components"])
    if args.stage in {"extract", "all"}:
        from pipeline.extract_entities import extract

        ents = extract(ead_path)
        print("entities:", {k: len(v) for k, v in ents.items()})
    if args.stage in {"reconcile", "all"}:
        from pipeline.reconcile import run as reconcile
        from pipeline.paths import CACHE_DIR

        reconcile(live=args.live)
        print((CACHE_DIR / "reconciliation-summary.json").read_text(encoding="utf-8"))
    if args.stage == "slideshow" or args.fetch_slideshow:
        from pipeline.ead_parser import parse_ead, walk
        from pipeline.iiif import harvest_from_ead, load_slideshow_cache
        from pipeline.paths import SRCDATA

        data = parse_ead(ead_path or SRCDATA)
        nodes = [n for n, _ in walk(data["collection"])]
        harvest_from_ead(nodes, resume=True, limit=args.limit if args.stage == "slideshow" else None)
        cache = load_slideshow_cache()
        filled = sum(1 for v in cache.values() if v.get("ids_ids"))
        print(f"slideshow cache: {filled}/{len(cache)} with page lists")
    if args.stage in {"vocab", "all"}:
        from pipeline.seed import run as seed_vocab

        print(json.dumps(seed_vocab(), indent=2))
    if args.stage in {"map", "all"}:
        from pipeline.map_crm import run as map_crm

        result = map_crm(path=ead_path, probe_iiif=args.probe_iiif, limit=args.limit)
        print(json.dumps(result, indent=2))
    if args.stage in {"validate", "all"}:
        from pipeline.validate import run as validate

        print(json.dumps(validate(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

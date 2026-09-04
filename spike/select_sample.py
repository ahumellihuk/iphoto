"""Pick the PhotoKit spike sample from the Photos database and write spike/scratch/sample.json.

The sandboxed spike app can only read inside the scratch folder it was granted,
so the sample lives there.

Run from a terminal with Full Disk Access:

    uv run python spike/select_sample.py [--seed 42] [--per-band 10] [--controls 5] [--exclude spike/scratch/sample.json] [--out ...]

Bands (spec docs/specs/2026-09-04-photokit-spike.md): small (<200 MB), medium
(200 MB to 1 GB), large (>1 GB, always including the largest video), plus local
controls. Ten iCloud-only videos are marked `paired` for AppleScript ground truth.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iphoto.scanner import _scan_videos_sqlite  # noqa: E402

MB = 1024 * 1024
GB = 1024 * MB


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--per-band", type=int, default=10)
    ap.add_argument("--controls", type=int, default=5)
    ap.add_argument("--library", default=None)
    ap.add_argument("--out", default=str(Path(__file__).parent / "scratch" / "sample.json"))
    ap.add_argument("--exclude", action="append", default=[],
                    help="sample.json file(s) whose videos must not be chosen again (their originals are now cached)")
    args = ap.parse_args()

    excluded: set[str] = set()
    for path in args.exclude:
        excluded |= {v["uuid"] for v in json.loads(Path(path).read_text())["videos"]}

    videos = [v for v in _scan_videos_sqlite(library_path=args.library) if v.uuid not in excluded]
    icloud = [v for v in videos if not v.is_local]
    local = [v for v in videos if v.is_local]
    bands = {
        "small": [v for v in icloud if v.size_bytes < 200 * MB],
        "medium": [v for v in icloud if 200 * MB <= v.size_bytes < GB],
        "large": [v for v in icloud if v.size_bytes >= GB],
    }
    rng = random.Random(args.seed)
    chosen: dict[str, list] = {}
    for name, pool in bands.items():
        pool = sorted(pool, key=lambda v: v.uuid)
        if name == "large" and pool:
            largest = max(pool, key=lambda v: v.size_bytes)
            rest = [v for v in pool if v.uuid != largest.uuid]
            chosen[name] = [largest] + rng.sample(rest, min(args.per_band - 1, len(rest)))
        else:
            chosen[name] = rng.sample(pool, min(args.per_band, len(pool)))
    chosen["local"] = rng.sample(sorted(local, key=lambda v: v.uuid), min(args.controls, len(local)))

    # Paired subset: 3 small, 3 medium, 4 large (largest always included).
    paired: set[str] = set()
    for name, n in (("small", 3), ("medium", 3), ("large", 4)):
        for v in chosen[name][:n]:
            paired.add(v.uuid)

    out = {
        "created": datetime.now(UTC).isoformat(),
        "library_path": args.library,
        "videos": [
            {
                "uuid": v.uuid,
                "original_filename": v.original_filename,
                "size_bytes": v.size_bytes,
                "is_local": v.is_local,
                "band": band,
                "paired": v.uuid in paired,
                "moment_name": v.moment_name,
                "reference_sha256": None,
                "reference_size": None,
            }
            for band, vids in chosen.items()
            for v in vids
        ],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))

    total = sum(v["size_bytes"] for v in out["videos"])
    print(f"library: {len(videos)} videos, {len(icloud)} iCloud-only, {len(local)} local")
    for name, vids in chosen.items():
        print(f"  {name:6s} {len(vids):2d} chosen of {len(bands.get(name, local)):4d}  "
              f"{sum(v.size_bytes for v in vids) / GB:6.2f} GB")
    print(f"total {total / GB:.2f} GB, paired {len(paired)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

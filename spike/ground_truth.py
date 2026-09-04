"""Export the paired subset through today's AppleScript path and record SHA-256 references.

Run from a terminal with Automation permission for Photos, when `iphoto archive`
is NOT running:

    uv run python spike/ground_truth.py [--sample spike/scratch/sample.json] [--scratch spike/scratch/ground_truth]

Writes reference_sha256 and reference_size back into sample.json. Videos that
already have a reference are skipped, so the script is safe to re-run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iphoto.applescript_exporter import export_via_applescript  # noqa: E402
from iphoto.config import ICLOUD_MIN_TIMEOUT  # noqa: E402
from iphoto.exporter import compute_sha256  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=str(Path(__file__).parent / "scratch" / "sample.json"))
    ap.add_argument("--scratch", default=str(Path(__file__).parent / "scratch" / "ground_truth"))
    ap.add_argument("--keep", action="store_true", help="keep exported files after hashing")
    args = ap.parse_args()

    if subprocess.run(["pgrep", "-f", "iphoto archive"], capture_output=True).returncode == 0:
        print("refusing: 'iphoto archive' is running")
        return 1

    sample_path = Path(args.sample)
    sample = json.loads(sample_path.read_text())
    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)

    for v in sample["videos"]:
        if not v["paired"] or v.get("reference_sha256"):
            continue
        out_dir = scratch / v["uuid"]
        out_dir.mkdir(exist_ok=True)
        start = time.time()
        ok, path, err = export_via_applescript(
            uuid=v["uuid"],
            filename=v["original_filename"],
            output_dir=out_dir,
            timeout=ICLOUD_MIN_TIMEOUT,
            post_export_wait_seconds=90,
            post_export_poll_seconds=2.0,
        )
        elapsed = time.time() - start
        if not ok or not path:
            print(f"FAIL {v['uuid'][:8]} {v['original_filename']}: {err}")
            v["reference_error"] = err
            sample_path.write_text(json.dumps(sample, indent=2))
            continue
        size = path.stat().st_size
        sha = compute_sha256(path)
        v["reference_sha256"] = sha
        v["reference_size"] = size
        v["reference_elapsed_s"] = round(elapsed, 1)
        v["reference_mbps"] = round(size / elapsed / 1024 / 1024, 2) if elapsed else None
        sample_path.write_text(json.dumps(sample, indent=2))
        print(f"ok   {v['uuid'][:8]} {v['original_filename']} {size} B {elapsed:.0f}s sha={sha[:12]} db_size_match={size == v['size_bytes']}")
        if not args.keep:
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

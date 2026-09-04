"""Summarize PhotoKit spike JSONL results against the spec thresholds.

    uv run python spike/summarize.py spike/scratch/results/A1-*.jsonl

Prints one table per threshold (docs/specs/2026-09-04-photokit-spike.md) and a
failure taxonomy by error domain and code. Paste the output into the results
record under docs/research.
"""

from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path


def load(paths: list[str]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}% ({n}/{d})" if d else "n/a"


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    rows = load(paths)
    videos = {r["uuid"] for r in rows if r["uuid"] != "-"}
    # Videos the probe found already local (--only-cloud) are not iCloud measurements.
    skipped_local = {r["uuid"] for r in rows if r["step"] == "download" and (r.get("note") or "").startswith("skipped")}
    icloud = {r["uuid"] for r in rows if r["uuid"] != "-" and r["band"] != "local"} - skipped_local
    by_step = collections.defaultdict(list)
    for r in rows:
        by_step[r["step"]].append(r)

    def ok_set(step: str, uuids: set[str]) -> set[str]:
        return {r["uuid"] for r in by_step[step] if r["ok"] and r["uuid"] in uuids}

    start = next((r for r in by_step["run_start"]), {})
    print(f"runs: {len(paths)}  videos: {len(videos)}  iCloud-only: {len(icloud)}  {start.get('note', '')}")
    print()
    print("threshold                          result           pass")
    print("-" * 62)

    enum_ok = ok_set("enumerate", icloud)
    print(f"enumeration (iCloud-only)          {pct(len(enum_ok), len(icloud))}   {'PASS' if len(icloud) and len(enum_ok) / len(icloud) >= 0.95 else 'FAIL'}")

    size_ok = ok_set("size", icloud)
    print(f"public size == db (iCloud-only)    {pct(len(size_ok), len(icloud))}   {'PASS' if len(icloud) and len(size_ok) / len(icloud) >= 0.95 else 'FAIL'}")

    loc_ok = ok_set("locality", videos)
    print(f"locality agrees with db            {pct(len(loc_ok), len(videos))}   {'PASS' if len(videos) and len(loc_ok) / len(videos) >= 0.95 else 'FAIL'}  (db flag = MAX over all resources; see results record)")
    if skipped_local:
        print(f"skipped as already local           {len(skipped_local)} (excluded from iCloud-only denominators)")

    verified = ok_set("verify", icloud)
    print(f"byte-exact download (iCloud-only)  {pct(len(verified), len(icloud))}   {'PASS' if len(icloud) and len(verified) / len(icloud) >= 0.95 else 'FAIL'}")

    stalled = {r["uuid"] for r in by_step["download"] if (r.get("stalls") or 0) > 0}
    unrecovered = stalled - ok_set("download", videos)
    print(f"stall recovery                     stalled={len(stalled)} unrecovered={len(unrecovered)}   {'PASS' if not unrecovered else 'FAIL'}")

    paired_hash = [r for r in by_step["verify"] if "hash_ok=true" in (r.get("note") or "")]
    paired_fail = [r for r in by_step["verify"] if "hash_ok=false" in (r.get("note") or "")]
    print(f"paired hashes identical            ok={len(paired_hash)} mismatch={len(paired_fail)}   {'PASS' if paired_hash and not paired_fail else ('n/a' if not paired_hash and not paired_fail else 'FAIL')}")

    speeds = [r["mbps"] for r in by_step["download"] if r["ok"] and r.get("mbps")]
    if speeds:
        print(f"throughput MB/s                    median={statistics.median(speeds):.1f} min={min(speeds):.1f} max={max(speeds):.1f}")

    cached = collections.Counter((r.get("note") or "?") for r in by_step["cache"])
    if cached:
        print(f"cache side effect                  {dict(cached)}")

    print()
    print("failure taxonomy (step, domain:code, count, example)")
    tax: dict[tuple, list] = collections.defaultdict(list)
    for r in rows:
        if not r["ok"] and r["uuid"] != "-":
            tax[(r["step"], f"{r.get('error_domain') or '-'}:{r.get('error_code') if r.get('error_code') is not None else '-'}")].append(r)
    for (step, code), rs in sorted(tax.items(), key=lambda kv: -len(kv[1])):
        ex = rs[0]
        print(f"  {step:10s} {code:28s} {len(rs):3d}  {(ex.get('error_desc') or ex.get('note') or '')[:70]}")
    if not tax:
        print("  none")

    attempts = collections.Counter(r["attempt"] for r in by_step["download"] if r["ok"])
    if attempts:
        print()
        print(f"successful downloads by attempt: {dict(sorted(attempts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

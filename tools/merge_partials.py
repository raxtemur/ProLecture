#!/usr/bin/env python3
"""Close a video: merge the proposer's files of one video into data/annotations/<VIDEO_ID>.jsonl.

The coordinator works on ``data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl`` in place,
from the end-to-end ids to the last status, and merges the files only when the video is
closed: every sample ``validated`` or ``rejected``, the validator green on the whole video,
the operational log passing ``check --final``. The merged file is written once, in the order
of the ids, and the parts are removed. A ``data/annotations/<VIDEO_ID>.jsonl`` that already
exists is an earlier annotation of the video: a new run never overwrites it.

After the merge the log still names the parts its launches were prepared from;
``coordinator_log.py`` then finds each record in the merged file.

    /home/user/conda/bin/python3 tools/merge_partials.py <VIDEO_ID>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("COORDINATOR_LOG_ROOT", REPO)).resolve()
CLOSED = ("validated", "rejected")


def tool(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "tools" / script), *args],
                          capture_output=True, text=True, check=False)


def id_order(sample_id: str) -> tuple:
    """q2 before q10, q07 before q07b."""
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", sample_id))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("video_id")
    args = parser.parse_args()
    video = args.video_id
    base = ROOT / "data" / "annotations"
    parts = sorted((base / "partial").glob(f"{video}.*.jsonl"))
    target = base / f"{video}.jsonl"
    if not parts:
        print(f"no data/annotations/partial/{video}.*.jsonl: nothing to merge", file=sys.stderr)
        return 2
    if target.exists():
        print(f"data/annotations/{video}.jsonl already exists: it is an earlier annotation of "
              f"this video, and a new run never overwrites it. Leave the parts in partial/ and "
              f"say so in your final report", file=sys.stderr)
        return 2

    texts = {part: part.read_text(encoding="utf-8") for part in parts}
    records, seen, problems = [], {}, []
    prefix = f"3b1b__{video}__"
    for part, text in texts.items():
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            sample_id = record.get("id") or ""
            where = f"{part.name}:{line_number}"
            if sample_id in seen:
                problems.append(f"{where}: id {sample_id!r} is also in {seen[sample_id]}")
            seen[sample_id] = where
            if not sample_id.startswith(prefix):
                problems.append(f"{where}: id {sample_id!r} is not an end-to-end id "
                                f"{prefix}q<NN>: give every sample one before its first review")
            status = (record.get("validation") or {}).get("status")
            if status not in CLOSED:
                problems.append(f"{where}: {sample_id} is {status}: close it first — validated, "
                                f"or rejected with its reason in its coordinator.<ROUND>.md")
            records.append(record)
    if problems:
        print("not merged:\n" + "\n".join(f"  {p}" for p in problems), file=sys.stderr)
        return 1

    validated = tool("validate_samples.py", *map(str, parts))
    if validated.returncode != 0:
        print(f"not merged: the validator fails on the parts — fix what it says, then merge "
              f"again\n{validated.stdout}{validated.stderr}", file=sys.stderr)
        return 1
    checked = tool("coordinator_log.py", video, "check", "--final")
    if checked.returncode != 0:
        print(f"not merged: coordinator_log.py {video} check --final fails — do what it says, "
              f"then merge again\n{checked.stderr}", file=sys.stderr)
        return 1

    records.sort(key=lambda r: id_order(r["id"]))
    target.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                      encoding="utf-8")
    for part in parts:
        part.unlink()
    rechecked = tool("coordinator_log.py", video, "check", "--final")
    if rechecked.returncode != 0:
        for part, text in texts.items():
            part.write_text(text, encoding="utf-8")
        target.unlink()
        print(f"not merged: check --final passed on the parts and fails on the merged file; "
              f"the parts are restored. This is a defect of the tools, not of the "
              f"annotation: report it\n{rechecked.stderr}", file=sys.stderr)
        return 1

    statuses = [r["validation"]["status"] for r in records]
    print(f"merged {len(records)} samples ({statuses.count('validated')} validated, "
          f"{statuses.count('rejected')} rejected) from {len(parts)} file(s) into "
          f"data/annotations/{video}.jsonl; removed "
          + ", ".join(f"partial/{part.name}" for part in parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The output of the journal checks on every real journal, saved and compared.

A change of tools/coordinator_log.py must not change how a journal written before it reads.
The unit tests cannot say that: the old journals hold forms of rows no test writes any more
(a window review with no index, an adjudication with no window, an edit with no kind). So
before such a change:

    python3 tests/journal_baseline.py --save <DIR>

and after it:

    python3 tests/journal_baseline.py --compare <DIR>
    python3 tests/journal_baseline.py --compare <DIR> --mixed <COPY>

Saved per journal: stdout, stderr and the exit code of `check`, `check --final` and `open`,
and of tools/validate_samples.py on every annotation file. `open` prints the age of a launch
in minutes; the number is masked. data/ is not under version control, so the baseline lives
outside the repository, next to whoever makes the change.

`--mixed` asks the same of a journal that goes on: the rules that depend on the format of a
row (data/reviews/README.md, "Formats of a row") must read the old rows as before when new
ones follow them. It copies the reviews, the annotations and the workspace notes to <COPY>
(which must not exist), appends one row of the current format to every journal there — a
note — and compares `check`, `check --final` and `open` on the copy with the baseline, whose
count of notes is one less. The real data is not touched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGE = re.compile(r", \d+ min: ")
NOTES = re.compile(r"(\d+) notes")


def run(*args: str, root: Path = ROOT) -> str:
    env = {**os.environ, "COORDINATOR_LOG_ROOT": str(root)} if root != ROOT else None
    result = subprocess.run([sys.executable, "-B", *args], cwd=ROOT, capture_output=True,
                            text=True, check=False, env=env)
    return (f"exit {result.returncode}\n--- stdout\n{result.stdout}--- stderr\n{result.stderr}")


def journal_outputs(root: Path = ROOT) -> dict[str, str]:
    found = {}
    for log in sorted((root / "data" / "reviews").glob("*/coordinator.log")):
        video = log.parent.name
        tool = "tools/coordinator_log.py"
        found[f"{video}.check"] = run(tool, video, "check", root=root)
        found[f"{video}.final"] = run(tool, video, "check", "--final", root=root)
        found[f"{video}.open"] = AGE.sub(", N min: ", run(tool, video, "open", root=root))
    return found


def outputs() -> dict[str, str]:
    found = journal_outputs()
    base = ROOT / "data" / "annotations"
    for file in sorted(base.glob("*.jsonl")) + sorted((base / "partial").glob("*.jsonl")):
        found[f"validate.{file.name}"] = run("tools/validate_samples.py", str(file.relative_to(ROOT)))
    return found


def mixed_copy(copy: Path) -> None:
    """A copy of what the journal checks read, with one row of the current format appended to
    every journal."""
    shutil.copytree(ROOT / "data" / "reviews", copy / "data" / "reviews", copy_function=shutil.copy2)
    for folder in ("data/annotations", "data/annotations/partial"):
        (copy / folder).mkdir(parents=True, exist_ok=True)
        for file in (ROOT / folder).glob("*.jsonl"):
            shutil.copy2(file, copy / folder / file.name)
    for note in (ROOT / ".review_ws").glob("*/**/*.inputs.json"):
        target = copy / note.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(note, target)
    for log in sorted((copy / "data" / "reviews").glob("*/coordinator.log")):
        rows = len(log.read_text(encoding="utf-8").splitlines())
        said = run("tools/coordinator_log.py", log.parent.name, "note", "--text",
                   "a row of the current format after the rows written before it", root=copy)
        after = log.read_text(encoding="utf-8").splitlines()
        if len(after) != rows + 1 or "v" not in json.loads(after[-1]):
            raise SystemExit(f"{log}: the note was not appended\n{said}")


def compare(saved: dict[str, str], found: dict[str, str], where: Path) -> int:
    differs = sorted(n for n in saved.keys() & found.keys() if saved[n] != found[n])
    gone, new = sorted(saved.keys() - found.keys()), sorted(found.keys() - saved.keys())
    for name in differs:
        print(f"DIFFERS: {name}  (saved: {where / (name + '.txt')})")
        old, now = saved[name].splitlines(), found[name].splitlines()
        for line in [l for l in old if l not in now][:5]:
            print(f"  - {line[:300]}")
        for line in [l for l in now if l not in old][:5]:
            print(f"  + {line[:300]}")
    for name in gone:
        print(f"GONE: {name}")
    for name in new:
        print(f"NEW: {name}")
    print(f"{len(saved)} saved, {len(found)} now: {len(differs)} differ, {len(gone)} gone, "
          f"{len(new)} new")
    return 1 if differs or gone else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--save", type=Path, metavar="DIR")
    how.add_argument("--compare", type=Path, metavar="DIR")
    ap.add_argument("--mixed", type=Path, metavar="COPY",
                    help="with --compare: compare on a copy of the data (made in COPY, which "
                         "must not exist) with a row of the current format appended to every "
                         "journal")
    args = ap.parse_args()
    if args.mixed is not None:
        if args.save:
            ap.error("--mixed goes with --compare")
        if args.mixed.exists():
            ap.error(f"{args.mixed} exists: name a folder that does not")
        mixed_copy(args.mixed.resolve())
        saved = {p.name[:-4]: NOTES.sub(lambda m: f"{int(m.group(1)) + 1} notes",
                                        p.read_text(encoding="utf-8"))
                 for p in args.compare.glob("*.txt") if not p.name.startswith("validate.")}
        return compare(saved, journal_outputs(args.mixed.resolve()), args.compare)
    found = outputs()
    if args.save:
        args.save.mkdir(parents=True, exist_ok=True)
        for name, text in found.items():
            (args.save / f"{name}.txt").write_text(text, encoding="utf-8")
        print(f"saved {len(found)} outputs to {args.save}")
        return 0
    saved = {p.name[:-4]: p.read_text(encoding="utf-8") for p in args.compare.glob("*.txt")}
    return compare(saved, found, args.compare)


if __name__ == "__main__":
    raise SystemExit(main())

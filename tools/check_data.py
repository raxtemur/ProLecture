#!/usr/bin/env python3
"""Is a data folder complete and ready to be measured on? What tools/validate_samples.py does
not look at: the files a record needs and what the evaluation makes of it.

For whoever assembles the data: after closing a video, after restoring the videos by id on
another machine, after downloading the records from somewhere.

    $BASE tools/check_data.py               # exit 1 and the list of problems, or the counts
    $BASE tools/check_data.py --expect 34   # also fail unless exactly 34 videos are closed
    $BASE tools/check_data.py --records-only   # the records alone, before the videos are there
    PROLECTURE_DATA=/path/to/data $BASE tools/check_data.py    # a data folder kept elsewhere

Checked, over every `annotations/*.jsonl` of the folder: tools/validate_samples.py passes; ids
are unique and name their video; a closed file holds no draft; every validated record has its
measured flags (`blind_solved`, `audio_dependency`), a required window with a rubric item,
windows inside the video and not before the question; the video file is there, has sound and
the duration the records state; the subtitles and the transcript are there; the stream the
evaluation would show (eval_common.stream_bounds) lies inside the video.

`--records-only` leaves out what needs the files (the video, its sound and duration, the
subtitles, the transcript) and takes the duration the records state: the check of records that
were downloaded on their own. A video whose records are still in `annotations/partial/` and not
merged is not counted: it is named in a warning. Needs the base interpreter (the validator
needs jsonschema) and, unless `--records-only`, ffprobe in PATH.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_common as ec  # noqa: E402

MEASURED_FLAGS = ("blind_solved", "audio_dependency")
AXES = ("act", "reasoning_level", "temporal_rel", "audio_dependency")


def probe(path: Path) -> dict | None:
    """Duration and whether there is sound, by ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=False)
    try:
        found = json.loads(out.stdout)
        kinds = [s["codec_type"] for s in found["streams"]]
        if "video" not in kinds:
            return None
        return {"duration": float(found["format"]["duration"]), "audio": "audio" in kinds}
    except (ValueError, KeyError):
        return None


def subtitles(video_id: str) -> Path:
    return ec.VIDEOS / video_id / f"{video_id}.en.vtt"


def bundle(video_id: str) -> Path:
    return ec.BUNDLES / video_id / "bundle.json"


def unmerged(videos: list[str]) -> list[str]:
    """Videos with a proposer's file in partial/ and no closed file: still in work."""
    partial = {p.name.split(".")[0] for p in (ec.ANNOTATIONS / "partial").glob("*.jsonl")}
    return sorted(partial - set(videos))


def check(videos: list[str], files_too: bool = True) -> tuple[list[str], dict]:
    """The problems found, and the counts: per video and in all. Without `files_too` the
    videos, subtitles and transcripts are not looked at."""
    problems: list[str] = []
    seen: Counter = Counter()
    per_video: dict[str, dict] = {}
    cube = {axis: Counter() for axis in AXES}
    primary = 0

    files = [str(ec.ANNOTATIONS / f"{v}.jsonl") for v in videos]
    validator = subprocess.run([sys.executable, "-B", str(ec.ROOT / "tools" / "validate_samples.py"), *files],
                               cwd=ec.ROOT, capture_output=True, text=True, check=False)
    if validator.returncode:
        problems.append("tools/validate_samples.py fails (it needs jsonschema: run this with the base "
                        "interpreter):\n" + (validator.stdout + validator.stderr).strip()[-2000:])

    for video_id in videos:
        records = ec.read_records(video_id)
        statuses = Counter((r.get("validation") or {}).get("status") for r in records)
        video = ec.VIDEOS / video_id / f"{video_id}.mp4"
        found = probe(video) if files_too and video.exists() else None
        if not files_too:
            pass
        elif found is None:
            problems.append(f"{video_id}: no readable video at {video}. Download it: "
                            f"tools/fetch_video.py {video_id}")
        elif not found["audio"]:
            problems.append(f"{video_id}: the video has no sound. Download it again: "
                            f"tools/fetch_video.py {video_id} --force")
        if files_too and not subtitles(video_id).exists():
            problems.append(f"{video_id}: no subtitles ({subtitles(video_id).name}); "
                            f"tools/fetch_video.py {video_id} writes them")
        if files_too and (not bundle(video_id).exists()
                          or not json.loads(bundle(video_id).read_text(encoding="utf-8")).get("transcript")):
            problems.append(f"{video_id}: no transcript in {bundle(video_id)}, and the offline run reads "
                            f"it. Build it: tools/make_bundle.py {video_id} --no-frames")
        if statuses.get("draft"):
            problems.append(f"{video_id}: {statuses['draft']} draft record(s) in a closed file: the "
                            "video was merged before its review ended")
        stated = sorted({float(r["video"]["duration"]) for r in records})
        if found and any(abs(d - found["duration"]) > 2 for d in stated):
            problems.append(f"{video_id}: the records state a duration of {', '.join(f'{d:g}' for d in stated)} s "
                            f"but the file runs {found['duration']:.1f} s: this is not the upload that "
                            "was annotated, and the timecodes may be off")
        per_video[video_id] = {"validated": statuses.get("validated", 0), "rejected": statuses.get("rejected", 0),
                               "duration": round(found["duration"], 1) if found else
                               (max(stated) if stated and not files_too else None)}
        for record in records:
            sample_id = record["id"]
            seen[sample_id] += 1
            if record["video"]["youtube_id"] != video_id or f"__{video_id}__" not in sample_id:
                problems.append(f"{sample_id}: the id or video.youtube_id does not name the file's video")
            if record["validation"]["status"] != "validated":
                continue
            duration = found["duration"] if found else float(record["video"]["duration"])
            if record["validation"].get("blind_solved") is None or record.get("audio_dependency") is None:
                problems.append(f"{sample_id}: validated without {' or '.join(MEASURED_FLAGS)}: the "
                                "probes that measure them have not all answered")
            if not 0 <= record["question_time"] <= duration:
                problems.append(f"{sample_id}: question_time outside the video")
            if not any(t["required"] for t in record["triggers"]):
                problems.append(f"{sample_id}: no required window, so nothing of it is scored")
            for trigger in record["triggers"]:
                where = f"{sample_id} window {trigger['idx']}"
                if not 0 <= trigger["t_start"] < trigger["t_end"] <= duration + 0.5:
                    problems.append(f"{where}: outside the video")
                if trigger["t_start"] < record["question_time"]:
                    problems.append(f"{where}: starts before the question")
                if trigger["required"] and not ec.rubric_items(trigger)[0]:
                    problems.append(f"{where}: required, but no rubric item to credit")
            start, end = ec.stream_bounds(record)
            if not start < end <= duration + 0.5 or end < record["question_time"]:
                problems.append(f"{sample_id}: the stream the evaluation shows ({start:.0f}-{end:.0f} s) is off")
            for axis in AXES:
                cube[axis][record[axis]] += 1
            primary += not record["validation"]["blind_solved"]
    problems += [f"{sample_id}: the id is used {n} times" for sample_id, n in seen.items() if n > 1]

    validated = sum(v["validated"] for v in per_video.values())
    totals = {"videos": len(videos), "validated": validated,
              "rejected": sum(v["rejected"] for v in per_video.values()),
              "primary": primary, "blind_solved": validated - primary,
              "hours": round(sum(v["duration"] or 0 for v in per_video.values()) / 3600, 2),
              **{axis: dict(sorted(count.items())) for axis, count in cube.items()}}
    return problems, {"totals": totals, "videos": per_video}


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--expect", type=int, metavar="N", help="fail unless exactly N videos are closed")
    parser.add_argument("--records-only", action="store_true",
                        help="check the records alone: no video, subtitles or transcript is looked for")
    args = parser.parse_args()

    videos = ec.annotation_videos()
    if not videos:
        print(f"no records in {ec.ANNOTATIONS}: the data is not in the repository. Set PROLECTURE_DATA "
              "to a data/ folder that has it (docs/evaluation.md)", file=sys.stderr)
        return 1
    if not args.records_only and shutil.which("ffprobe") is None:
        print("ffprobe is not in PATH (it comes with ffmpeg) and the videos cannot be read without "
              "it. Install it, or pass --records-only to check the records alone", file=sys.stderr)
        return 1
    problems, held = check(videos, files_too=not args.records_only)
    totals = held["totals"]
    if args.expect is not None and len(videos) != args.expect:
        problems.append(f"{len(videos)} closed videos, {args.expect} expected")
    print(f"{ec.DATA}: {totals['videos']} videos, {totals['hours']} h: {totals['validated']} validated "
          f"({totals['primary']} in the primary set), {totals['rejected']} rejected")
    for axis in AXES:
        print(f"  {axis}: " + ", ".join(f"{name} {n}" for name, n in totals[axis].items()))
    waiting = unmerged(videos)
    if waiting:
        print(f"warning: not counted, still in annotations/partial/: {', '.join(waiting)}",
              file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s):", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        if ec.DATA != ec.ROOT / "data":
            print(f"note: fetch_video.py and make_bundle.py write into {ec.ROOT / 'data'}, not into "
                  "the folder PROLECTURE_DATA names: run them where that folder is the checkout's own "
                  "data/, or move what they write", file=sys.stderr)
        return 1
    print("the checks pass" + (" (the records alone: no video, subtitles or transcript was looked for)"
                               if args.records_only else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

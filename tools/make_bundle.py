#!/usr/bin/env python3
"""Assembles the annotation bundle for a video: what an annotator actually works with.

The output is data/bundles/<id>/:
    bundle.json     — machine-readable: chapters, transcript, formulas from the source
    transcript.md   — the transcript with timecodes, broken up by chapter
    formulas.md     — the LaTeX strings from the manim source (scene, file, line)
    frames/         — frames by scene change detection (tools/detect_scenes.py)

There is no uniform grid here any more. On manim videos it errs in two directions at
once: on a static stretch it produces several identical frames, while a scene that
lived ten seconds between the nodes of the grid is not shown at all. The measurements
and the discussion are in docs/scene_detection.md. OpenCV is needed (base conda).

Usage:
    python tools/make_bundle.py l6DKRf-fAAM
    python tools/make_bundle.py l6DKRf-fAAM --scene-threshold 0.008
    python tools/make_bundle.py l6DKRf-fAAM --no-frames     # keep the cut as it is
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_scenes  # noqa: E402  (it sits next door, in tools/)

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "data" / "videos"
BUNDLES_DIR = ROOT / "data" / "bundles"
VENDOR_VIDEOS = ROOT / "vendor" / "videos"
MAPPING = ROOT / "data" / "3b1b_mapping.json"

TEX_CALLS = ("OldTex", "OldTexText", "MathTex", "TexText", "Tex", "Text")
TEX_RE = re.compile(
    r"\b(" + "|".join(TEX_CALLS) + r")\s*\(\s*([rRfFbB]{0,2})(['\"])(.*?)\3",
    re.DOTALL,
)
# every call site — so as to count honestly how many could not be parsed
TEX_CALL_SITE_RE = re.compile(r"\b(" + "|".join(TEX_CALLS) + r")\s*\(")
CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(")


# ---------------------------------------------------------------- the transcript

def ts_to_sec(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(path: Path) -> list[dict]:
    """Returns a list of {start, end, text}. Merges duplicates of consecutive utterances."""
    cues: list[dict] = []
    block: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw.rstrip()
        if line:
            block.append(line)
            continue
        if block:
            times = [l for l in block if "-->" in l]
            if times:
                start_s, end_s = [p.strip() for p in times[0].split("-->")[:2]]
                end_s = end_s.split()[0]
                text = " ".join(
                    l for l in block
                    if "-->" not in l and not l.isdigit() and not l.startswith("WEBVTT")
                    and not l.startswith("Kind:") and not l.startswith("Language:")
                ).strip()
                # 3b1b's service note about editing the subtitles
                text = re.sub(r"\[Submit subtitle corrections at [^\]]*\]", "", text).strip()
                if text:
                    cues.append({"start": ts_to_sec(start_s), "end": ts_to_sec(end_s), "text": text})
            block = []
    # merging exact duplicates (3b1b's vtt contains repeats of the same utterance)
    merged: list[dict] = []
    for c in cues:
        if merged and c["text"] == merged[-1]["text"]:
            merged[-1]["end"] = c["end"]
        else:
            merged.append(c)
    return merged


# ---------------------------------------------------------------- the sources

def iter_source_files(source: str) -> list[Path]:
    if not source:
        return []
    p = VENDOR_VIDEOS / source
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(p.rglob("*.py"))
    return []


def extract_formulas(source: str) -> tuple[list[dict], int]:
    """LaTeX/text strings from the manim source, tied to a scene.

    Returns (strings, how many call sites could not be parsed). Not every call carries
    a literal: the argument is sometimes a variable, a concatenation or the result of
    a function.
    """
    out: list[dict] = []
    call_sites = 0
    for f in iter_source_files(source):
        text = f.read_text(encoding="utf-8", errors="replace")
        call_sites += len(TEX_CALL_SITE_RE.findall(text))
        lines = text.splitlines()
        # a map: line number -> the name of the nearest class above
        class_at: list[str] = []
        current = ""
        for line in lines:
            m = CLASS_RE.match(line)
            if m:
                current = m.group(1)
            class_at.append(current)
        for m in TEX_RE.finditer(text):
            lineno = text.count("\n", 0, m.start())
            body = m.group(4)
            if len(body) < 2 or body.isspace():
                continue
            out.append({
                "file": str(f.relative_to(VENDOR_VIDEOS)),
                "line": lineno + 1,
                "scene": class_at[lineno] if lineno < len(class_at) else "",
                "call": m.group(1),
                "text": body[:300],
            })
    return out, max(call_sites - len(out), 0)


# ---------------------------------------------------------------- the frames

def wipe_frames(out_dir: Path) -> None:
    """Removes every frame before a new cut.

    Removing the frames of a different mode is not enough: with `scenes` the capture
    times depend on the detector's parameters, and a run with a different threshold
    leaves its files next to the new ones. The annotator then sees a mixture of two
    cuts, and `bundle.json` only the half the last run wrote. The frames directory is
    reproduced from the mp4 in full, so there is nothing to lose there.
    """
    if not out_dir.exists():
        return
    stale = list(out_dir.glob("t*.jpg"))
    if stale:
        print(f"[info] {out_dir} holds {len(stale)} frames of a previous cut — removing them")
        for f in stale:
            f.unlink()
    # We do not touch subdirectories: `frames/exact/` is the overview notebook's cache
    # (`data/data_overview.ipynb` cuts fractional times into it on demand), not a
    # leftover of somebody else's cut. But it is worth a warning: the frames there use
    # a different name format and have nothing to do with the list in bundle.json.
    for sub in sorted(d for d in out_dir.iterdir() if d.is_dir()):
        inner = list(sub.glob("t*.jpg"))
        if inner:
            print(f"[info] {sub} holds {len(inner)} frames outside the bundle.json list "
                  f"(the notebook's cache) — leaving them as they are")


# ---------------------------------------------------------------- assembly

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("--scene-threshold", type=float, default=detect_scenes.THRESHOLD,
                    help=f"the scene detector's threshold (default {detect_scenes.THRESHOLD})")
    ap.add_argument("--no-frames", action="store_true")
    args = ap.parse_args()

    vid = args.video_id
    vdir = VIDEOS_DIR / vid
    info_path = vdir / f"{vid}.info.json"
    if not info_path.exists():
        sys.exit(f"no {info_path}; run tools/fetch_video.py {vid} first")
    info = json.loads(info_path.read_text(encoding="utf-8"))

    vtt = vdir / f"{vid}.en.vtt"
    if not vtt.exists():
        sys.exit(f"no {vtt}: the subtitles were not downloaded. Re-run tools/fetch_video.py {vid} --force")
    cues = parse_vtt(vtt)
    if not cues:
        sys.exit(f"{vtt} was parsed but yielded not a single utterance — check the format of the file")
    chapters = info.get("chapters") or []
    duration = float(info["duration"])

    row = next(
        (r for r in json.loads(MAPPING.read_text(encoding="utf-8"))
         if r["youtube_id"] == vid),
        None,
    )
    source = (row or {}).get("source", "")
    if source and not iter_source_files(source):
        guess = (row or {}).get("source_guess", "")
        if guess and iter_source_files(guess):
            print(f"[warn] the path {source} does not exist, taking the fuzzy guess {guess}")
            source = guess
        else:
            print(f"[warn] the source path {source!r} does not exist, there will be no formulas")
    formulas, unparsed = extract_formulas(source)

    bdir = BUNDLES_DIR / vid
    bdir.mkdir(parents=True, exist_ok=True)

    bundle_path = bdir / "bundle.json"
    frames = []
    if args.no_frames and bundle_path.exists():
        # do not wipe the already assembled list of frames
        prev = json.loads(bundle_path.read_text(encoding="utf-8"))
        frames = prev.get("frames", [])
    if not args.no_frames:
        fdir = bdir / "frames"
        # First we make sure the cut is possible at all, and only then remove the old
        # one: otherwise, on a machine without the mp4 or without OpenCV,
        # `make_bundle.py <id>` deletes 437 frames, dies, and leaves a bundle.json
        # listing paths that no longer exist. The former grid deleted nothing, so this
        # would be a regression rather than an inheritance.
        mp4 = vdir / f"{vid}.mp4"
        if not mp4.exists():
            raise SystemExit(f"no {mp4}: there is nothing to cut frames from "
                             f"(download it: tools/fetch_video.py {vid})")
        detect_scenes.require_cv2()
        wipe_frames(fdir)
        cuts = detect_scenes.detect(
            mp4,
            threshold=args.scene_threshold,
            out_dir=fdir,
        )
        frames = [{"t": c["t"], "path": c["path"], "reason": c["reason"]} for c in cuts]

    bundle = {
        "video_id": vid,
        "title": info["title"],
        "duration": duration,
        "upload_date": info.get("upload_date"),
        "source_code": source,
        "chapters": [
            {"start": c["start_time"], "end": c["end_time"], "title": c["title"]}
            for c in chapters
        ],
        "transcript": cues,
        "formulas": formulas,
        "frames": frames,
    }
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # transcript.md — by chapter
    def chapter_of(t: float) -> str:
        for c in chapters:
            if c["start_time"] <= t < c["end_time"]:
                return c["title"]
        return "—"

    lines = [f"# {info['title']}", "", f"Duration {duration:.0f} s. "
             f"Utterances {len(cues)}. Chapters {len(chapters)}.", ""]
    prev_ch = None
    for c in cues:
        ch = chapter_of(c["start"])
        if ch != prev_ch:
            lines += ["", f"## [{c['start']:.0f}s] {ch}", ""]
            prev_ch = ch
        lines.append(f"`{c['start']:7.1f}` {c['text']}")
    (bdir / "transcript.md").write_text("\n".join(lines), encoding="utf-8")

    # formulas.md
    flines = [f"# Strings from the manim source `{source}`", "",
              f"{len(formulas)} strings parsed; another {unparsed} call sites contain "
              f"a non-literal (a variable, a concatenation, the result of a function) and were not extracted.", ""]
    cur_file = None
    for f in formulas:
        if f["file"] != cur_file:
            flines += ["", f"## {f['file']}", ""]
            cur_file = f["file"]
        flines.append(f"- `{f['line']:5d}` **{f['scene'] or '-'}** · {f['call']} · `{f['text']}`")
    (bdir / "formulas.md").write_text("\n".join(flines), encoding="utf-8")

    if not args.no_frames:
        print(f"  ffmpeg    : {shutil.which('ffmpeg') or 'NOT FOUND'}")
    print(f"bundle → {bdir}")
    print(f"  chapters  : {len(chapters)}")
    print(f"  utterances: {len(cues)}")
    print(f"  formulas  : {len(formulas)} of {len(formulas) + unparsed} call sites "
          f"({unparsed} non-literals), files {len(iter_source_files(source))}")
    print(f"  frames    : {len(frames)}"
          + (f" ({len(frames) / duration * 60:.1f} per minute)" if duration else ""))


if __name__ == "__main__":
    main()

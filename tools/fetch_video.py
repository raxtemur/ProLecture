#!/usr/bin/env python3
"""Downloads a 3b1b video from YouTube into data/videos/<id>/.

Cookies are not needed, but an explicit player_client is: the default android_vr
returns URLs on which the CDN answers 403. --download-sections does not work either
(it passes the URL to an external ffmpeg) — we download whole and cut locally.

Without a PO token only format 18 is available (640x360 progressive h264+aac).

Usage:
    python tools/fetch_video.py l6DKRf-fAAM
    python tools/fetch_video.py --slug reinventing-entropy
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "data" / "videos"
MAPPING = ROOT / "data" / "3b1b_mapping.json"

PLAYER_CLIENT = "android"
FORMAT = "18"

# yt-dlp is not installed in every interpreter: in this project it is in the conda
# environment rah_manim, while the notebook and the validator run under base conda.
# So we look for a suitable python ourselves.
CANDIDATE_PYTHONS = [
    sys.executable,
    "/home/jovyan/.mlspace/envs/rah_manim/bin/python",
]


def find_python_with_ytdlp() -> str:
    for py in CANDIDATE_PYTHONS:
        if not py or not Path(py).exists():
            continue
        probe = subprocess.run(
            [py, "-c", "import yt_dlp"], capture_output=True, text=True
        )
        if probe.returncode == 0:
            return py
    sys.exit(
        "could not find an interpreter with yt_dlp. Install it:\n"
        "    /home/jovyan/.mlspace/envs/rah_manim/bin/python -m pip install -U yt-dlp\n"
        "or add your own path to CANDIDATE_PYTHONS in tools/fetch_video.py"
    )


def resolve_slug(slug: str) -> str:
    rows = json.loads(MAPPING.read_text(encoding="utf-8"))
    for r in rows:
        if r["slug"] == slug:
            if not r["youtube_id"]:
                sys.exit(f"lesson {slug} has no youtube_id")
            return r["youtube_id"]
    sys.exit(f"lesson {slug} not found in {MAPPING}")


def fetch(video_id: str, subs_langs: str = "en", force: bool = False) -> Path:
    out_dir = VIDEOS_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4 = out_dir / f"{video_id}.mp4"

    needed = [mp4, out_dir / f"{video_id}.info.json", out_dir / f"{video_id}.en.vtt"]
    missing = [f.name for f in needed if not f.exists()]
    if not missing and not force:
        print(f"[skip] everything in place: {mp4.name} ({mp4.stat().st_size / 2**20:.1f} MB), info.json, en.vtt")
        return out_dir
    if mp4.exists() and missing:
        print(f"[warn] the mp4 is there but these are missing: {', '.join(missing)} — fetching them")

    py = find_python_with_ytdlp()
    if py != sys.executable:
        print(f"[env] yt_dlp found in {py}")
    cmd = [
        py, "-m", "yt_dlp",
        "--no-warnings",
        "--extractor-args", f"youtube:player_client={PLAYER_CLIENT}",
        "-f", FORMAT,
        "--write-info-json",
        "--write-subs", "--sub-langs", subs_langs, "--sub-format", "vtt",
        "--write-description",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    print("[run]", " ".join(cmd[:6]), "...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout[-2000:], file=sys.stderr)
        print(res.stderr[-2000:], file=sys.stderr)
        sys.exit(f"yt-dlp failed with code {res.returncode}")
    return out_dir


def report(out_dir: Path, video_id: str) -> None:
    info_path = out_dir / f"{video_id}.info.json"
    if not info_path.exists():
        print("!! info.json was not downloaded")
        return
    info = json.loads(info_path.read_text(encoding="utf-8"))
    chapters = info.get("chapters") or []
    auto = info.get("automatic_captions") or {}
    manual = info.get("subtitles") or {}
    print(f"\n{info['title']}")
    print(f"  duration     : {info['duration']} s ({info['duration']/60:.1f} min)")
    print(f"  uploaded     : {info.get('upload_date')}")
    print(f"  chapters     : {len(chapters)}")
    print(f"  subtitles    : manual={sorted(manual)[:6]}… auto-en={'en' in auto}")
    if not (out_dir / f"{video_id}.en.vtt").exists():
        print("!! the .en.vtt was not downloaded — the video may have no manual subtitles. "
              "make_bundle will not work without a transcript.")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name:36} {f.stat().st_size/2**20:8.2f} MB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="a YouTube id, or a lesson slug with --slug")
    ap.add_argument("--slug", action="store_true", help="treat the argument as a lesson slug")
    ap.add_argument("--subs", default="en", help="subtitle languages (comma-separated)")
    ap.add_argument("--force", action="store_true", help="re-download even if the file is there")
    args = ap.parse_args()

    video_id = resolve_slug(args.video) if args.slug else args.video
    out_dir = fetch(video_id, args.subs, args.force)
    report(out_dir, video_id)


if __name__ == "__main__":
    main()

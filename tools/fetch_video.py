#!/usr/bin/env python3
"""Скачивает видео 3b1b с YouTube в data/videos/<id>/.

Куки не нужны, но нужен явный player_client: дефолтный android_vr отдаёт URL,
на которых CDN возвращает 403. --download-sections тоже не работает (передаёт URL
внешнему ffmpeg) — качаем целиком, режем локально.

Без PO-токена доступен только формат 18 (640x360 progressive h264+aac).

Использование:
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

# yt-dlp стоит не во всяком интерпретаторе: в этом проекте он есть в conda-окружении
# rah_manim, а ноутбук и валидатор работают под base conda. Ищем подходящий питон сами.
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
        "не нашёл интерпретатор с yt_dlp. Поставь его:\n"
        "    /home/jovyan/.mlspace/envs/rah_manim/bin/python -m pip install -U yt-dlp\n"
        "или добавь свой путь в CANDIDATE_PYTHONS в tools/fetch_video.py"
    )


def resolve_slug(slug: str) -> str:
    rows = json.loads(MAPPING.read_text(encoding="utf-8"))
    for r in rows:
        if r["slug"] == slug:
            if not r["youtube_id"]:
                sys.exit(f"у урока {slug} нет youtube_id")
            return r["youtube_id"]
    sys.exit(f"урок {slug} не найден в {MAPPING}")


def fetch(video_id: str, subs_langs: str = "en", force: bool = False) -> Path:
    out_dir = VIDEOS_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4 = out_dir / f"{video_id}.mp4"

    needed = [mp4, out_dir / f"{video_id}.info.json", out_dir / f"{video_id}.en.vtt"]
    missing = [f.name for f in needed if not f.exists()]
    if not missing and not force:
        print(f"[skip] всё на месте: {mp4.name} ({mp4.stat().st_size / 2**20:.1f} МБ), info.json, en.vtt")
        return out_dir
    if mp4.exists() and missing:
        print(f"[warn] mp4 есть, но не хватает: {', '.join(missing)} — докачиваю")

    py = find_python_with_ytdlp()
    if py != sys.executable:
        print(f"[env] yt_dlp найден в {py}")
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
        sys.exit(f"yt-dlp упал с кодом {res.returncode}")
    return out_dir


def report(out_dir: Path, video_id: str) -> None:
    info_path = out_dir / f"{video_id}.info.json"
    if not info_path.exists():
        print("!! info.json не скачался")
        return
    info = json.loads(info_path.read_text(encoding="utf-8"))
    chapters = info.get("chapters") or []
    auto = info.get("automatic_captions") or {}
    manual = info.get("subtitles") or {}
    print(f"\n{info['title']}")
    print(f"  длительность : {info['duration']} с ({info['duration']/60:.1f} мин)")
    print(f"  выложено     : {info.get('upload_date')}")
    print(f"  чаптеров     : {len(chapters)}")
    print(f"  субтитры     : ручные={sorted(manual)[:6]}… авто-en={'en' in auto}")
    if not (out_dir / f"{video_id}.en.vtt").exists():
        print("!! .en.vtt не скачался — у ролика может не быть ручных субтитров. "
              "make_bundle без транскрипта работать не будет.")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name:36} {f.stat().st_size/2**20:8.2f} МБ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="YouTube id, либо slug урока с --slug")
    ap.add_argument("--slug", action="store_true", help="трактовать аргумент как slug урока")
    ap.add_argument("--subs", default="en", help="языки субтитров (через запятую)")
    ap.add_argument("--force", action="store_true", help="перекачать, даже если файл есть")
    args = ap.parse_args()

    video_id = resolve_slug(args.video) if args.slug else args.video
    out_dir = fetch(video_id, args.subs, args.force)
    report(out_dir, video_id)


if __name__ == "__main__":
    main()

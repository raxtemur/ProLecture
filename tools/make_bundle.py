#!/usr/bin/env python3
"""Собирает annotation bundle по видео: то, с чем реально работает разметчик.

На выходе data/bundles/<id>/:
    bundle.json     — машиночитаемо: чаптеры, транскрипт, формулы из исходника
    transcript.md   — транскрипт с таймкодами, разбитый по чаптерам
    formulas.md     — LaTeX-строки из manim-исходника (сцена, файл, строка)
    frames/         — кадры по детекции смены сцен (tools/detect_scenes.py)

Равномерной сетки здесь больше нет. На manim-видео она ошибается сразу в две
стороны: на статичном куске выдаёт несколько одинаковых кадров, а сцену, прожившую
десять секунд между узлами сетки, не показывает вовсе. Замер и разбор —
в docs/scene_detection.md. Нужен OpenCV (base conda).

Использование:
    python tools/make_bundle.py l6DKRf-fAAM
    python tools/make_bundle.py l6DKRf-fAAM --scene-threshold 0.008
    python tools/make_bundle.py l6DKRf-fAAM --no-frames     # оставить нарезку как есть
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_scenes  # noqa: E402  (лежит рядом, в tools/)

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
# все места вызова — чтобы честно посчитать, сколько не удалось разобрать
TEX_CALL_SITE_RE = re.compile(r"\b(" + "|".join(TEX_CALLS) + r")\s*\(")
CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(")


# ---------------------------------------------------------------- транскрипт

def ts_to_sec(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(path: Path) -> list[dict]:
    """Возвращает список {start, end, text}. Склеивает дубли подряд идущих реплик."""
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
                # служебная плашка 3b1b про правку субтитров
                text = re.sub(r"\[Submit subtitle corrections at [^\]]*\]", "", text).strip()
                if text:
                    cues.append({"start": ts_to_sec(start_s), "end": ts_to_sec(end_s), "text": text})
            block = []
    # склейка точных дублей (в vtt 3b1b встречаются повторы одной реплики)
    merged: list[dict] = []
    for c in cues:
        if merged and c["text"] == merged[-1]["text"]:
            merged[-1]["end"] = c["end"]
        else:
            merged.append(c)
    return merged


# ---------------------------------------------------------------- исходники

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
    """LaTeX/текстовые строки из manim-исходника с привязкой к сцене.

    Возвращает (строки, сколько мест вызова разобрать не удалось). Не всякий вызов
    несёт литерал: аргументом бывает переменная, конкатенация или результат функции.
    """
    out: list[dict] = []
    call_sites = 0
    for f in iter_source_files(source):
        text = f.read_text(encoding="utf-8", errors="replace")
        call_sites += len(TEX_CALL_SITE_RE.findall(text))
        lines = text.splitlines()
        # карта: номер строки -> имя ближайшего класса выше
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


# ---------------------------------------------------------------- кадры

def wipe_frames(out_dir: Path) -> None:
    """Сносит все кадры перед новой нарезкой.

    Мало снести кадры чужого режима: у `scenes` времена съёма зависят от
    параметров детектора, и прогон с другим порогом оставляет свои файлы рядом
    с новыми. Разметчик тогда видит смесь двух нарезок, а `bundle.json` —
    только половину, которую записал последний прогон. Каталог кадров целиком
    воспроизводится из mp4, терять там нечего.
    """
    if not out_dir.exists():
        return
    stale = list(out_dir.glob("t*.jpg"))
    if stale:
        print(f"[info] в {out_dir} {len(stale)} кадров прошлой нарезки — удаляю")
        for f in stale:
            f.unlink()
    # Подкаталоги не трогаем: `frames/exact/` — это кеш ноутбука обзора
    # (`data/data_overview.ipynb` режет туда дробные времена по требованию),
    # а не остаток чужой нарезки. Но предупредить стоит: кадры там лежат
    # в другом формате имени и к списку в bundle.json отношения не имеют.
    for sub in sorted(d for d in out_dir.iterdir() if d.is_dir()):
        inner = list(sub.glob("t*.jpg"))
        if inner:
            print(f"[info] в {sub} {len(inner)} кадров вне списка bundle.json "
                  f"(кеш ноутбука) — оставляю как есть")


# ---------------------------------------------------------------- сборка

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("--scene-threshold", type=float, default=detect_scenes.THRESHOLD,
                    help=f"порог детектора сцен (по умолчанию {detect_scenes.THRESHOLD})")
    ap.add_argument("--no-frames", action="store_true")
    args = ap.parse_args()

    vid = args.video_id
    vdir = VIDEOS_DIR / vid
    info_path = vdir / f"{vid}.info.json"
    if not info_path.exists():
        sys.exit(f"нет {info_path}; сначала tools/fetch_video.py {vid}")
    info = json.loads(info_path.read_text(encoding="utf-8"))

    vtt = vdir / f"{vid}.en.vtt"
    if not vtt.exists():
        sys.exit(f"нет {vtt}: субтитры не скачались. Перезапусти tools/fetch_video.py {vid} --force")
    cues = parse_vtt(vtt)
    if not cues:
        sys.exit(f"{vtt} разобран, но не дал ни одной реплики — проверь формат файла")
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
            print(f"[warn] путь {source} не существует, беру фаззи-догадку {guess}")
            source = guess
        else:
            print(f"[warn] путь к исходнику {source!r} не существует, формул не будет")
    formulas, unparsed = extract_formulas(source)

    bdir = BUNDLES_DIR / vid
    bdir.mkdir(parents=True, exist_ok=True)

    bundle_path = bdir / "bundle.json"
    frames = []
    if args.no_frames and bundle_path.exists():
        # не затирать уже собранный список кадров
        prev = json.loads(bundle_path.read_text(encoding="utf-8"))
        frames = prev.get("frames", [])
    if not args.no_frames:
        fdir = bdir / "frames"
        # Сначала убеждаемся, что нарезка вообще возможна, и только потом сносим
        # старую: иначе на машине без mp4 или без OpenCV `make_bundle.py <id>`
        # удаляет 437 кадров, падает и оставляет bundle.json со списком путей,
        # которых больше нет. Прежняя сетка ничего не удаляла, так что это
        # был бы регресс, а не наследство.
        mp4 = vdir / f"{vid}.mp4"
        if not mp4.exists():
            raise SystemExit(f"нет {mp4}: кадры резать нечем "
                             f"(скачать: tools/fetch_video.py {vid})")
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

    # transcript.md — по чаптерам
    def chapter_of(t: float) -> str:
        for c in chapters:
            if c["start_time"] <= t < c["end_time"]:
                return c["title"]
        return "—"

    lines = [f"# {info['title']}", "", f"Длительность {duration:.0f} с. "
             f"Реплик {len(cues)}. Чаптеров {len(chapters)}.", ""]
    prev_ch = None
    for c in cues:
        ch = chapter_of(c["start"])
        if ch != prev_ch:
            lines += ["", f"## [{c['start']:.0f}s] {ch}", ""]
            prev_ch = ch
        lines.append(f"`{c['start']:7.1f}` {c['text']}")
    (bdir / "transcript.md").write_text("\n".join(lines), encoding="utf-8")

    # formulas.md
    flines = [f"# Строки из manim-исходника `{source}`", "",
              f"Разобрано {len(formulas)} строк; ещё {unparsed} мест вызова содержат "
              f"не литерал (переменная, конкатенация, результат функции) и не извлечены.", ""]
    cur_file = None
    for f in formulas:
        if f["file"] != cur_file:
            flines += ["", f"## {f['file']}", ""]
            cur_file = f["file"]
        flines.append(f"- `{f['line']:5d}` **{f['scene'] or '-'}** · {f['call']} · `{f['text']}`")
    (bdir / "formulas.md").write_text("\n".join(flines), encoding="utf-8")

    if not args.no_frames:
        print(f"  ffmpeg    : {shutil.which('ffmpeg') or 'НЕ НАЙДЕН'}")
    print(f"bundle → {bdir}")
    print(f"  чаптеров  : {len(chapters)}")
    print(f"  реплик    : {len(cues)}")
    print(f"  формул    : {len(formulas)} из {len(formulas) + unparsed} мест вызова "
          f"({unparsed} не литералы), файлов {len(iter_source_files(source))}")
    print(f"  кадров    : {len(frames)}"
          + (f" ({len(frames) / duration * 60:.1f} на минуту)" if duration else ""))


if __name__ == "__main__":
    main()

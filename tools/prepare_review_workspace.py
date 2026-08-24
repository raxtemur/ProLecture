#!/usr/bin/env python3
"""Рабочая папка для субагента-ревьюера: транскрипт и кадры, и ничего лишнего.

Ревьюер не должен иметь доступа к data/annotations — там лежат эталонные ответы
на его же вопрос и ответы соседних вопросов. Поэтому ему готовится отдельный
каталог, куда кладётся только то, что можно видеть.

    # слепой режим: всё, что было в ролике до момента T
    prepare_review_workspace.py <video_id> --until 957 --out /tmp/rev_q07_blind

    # досемплировать участок частой сеткой в ту же папку
    prepare_review_workspace.py <video_id> --dense 930 960 --step 2 --out /tmp/rev_q07_blind

    # папки зондов: одна модальность вместо двух
    prepare_review_workspace.py <video_id> --until 992 --only transcript --out /tmp/probe_text
    prepare_review_workspace.py <video_id> --until 992 --only frames    --out /tmp/probe_vision
    prepare_review_workspace.py <video_id> --frame 946                  --out /tmp/probe_frame

Кадры именуются по таймкоду (t000946.jpg), так что агент видит время прямо
в имени файла и не должен ничего пересчитывать.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def frame_name(t: float) -> str:
    return f"t{int(round(t)):06d}.jpg"


def load_bundle(vid: str) -> dict:
    path = ROOT / "data" / "bundles" / vid / "bundle.json"
    if not path.exists():
        sys.exit(f"нет бандла {path}; сначала tools/make_bundle.py {vid}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_transcript(bundle: dict, out: Path, t0: float, t1: float) -> tuple[int, float]:
    """Реплики, целиком лежащие внутри [t0, t1).

    Пересекающую границу реплику приходится выбрасывать целиком: пословных
    таймингов у нас нет, и обрезать её по t1 нечем. Иначе слепому ревьюеру
    достаётся до нескольких секунд речи из-за его границы — а там, как правило,
    и лежит ответ: 19 из 25 значений t_start пилота попадают внутрь реплики.
    Ошибаться тут можно только в одну сторону: пусть слепой увидит меньше,
    чем мог бы, чем на секунду больше, чем должен.
    """
    cues = [c for c in bundle["transcript"] if c["start"] >= t0 and c["end"] <= t1]
    actual = cues[-1]["end"] if cues else t0
    lines = [f"# Транскрипт {bundle['video_id']}: {t0:.0f}–{t1:.0f} с",
             f"# последняя реплика кончается на {actual:.1f} с; всё, что пересекает "
             f"границу {t1:.0f} с, выброшено целиком", ""]
    lines += [f"[{c['start']:.1f}–{c['end']:.1f}] {c['text']}" for c in cues]
    (out / "transcript.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(cues), actual


def copy_sparse(bundle: dict, out: Path, t0: float, t1: float, cap: int) -> int:
    dst = out / "frames"
    dst.mkdir(exist_ok=True)
    picked = [fr for fr in bundle["frames"] if t0 <= fr["t"] < t1]
    # редкая сетка бандла частая: на получасовом участке её надо проредить,
    # иначе «дешёвая» операция съест весь бюджет кадров
    if len(picked) > cap:
        step = len(picked) / cap
        picked = [picked[int(i * step)] for i in range(cap)]
    n = 0
    for fr in picked:
        src = ROOT / fr["path"]
        if src.exists():
            shutil.copy2(src, dst / frame_name(fr["t"]))
            n += 1
    return n


def check_mode(out: Path, mode: str, force: bool) -> None:
    """Не дать смешать материал двух режимов в одной папке.

    Иначе изоляция зондов держится только на аккуратности координатора: два вызова
    подряд с --only frames и --only transcript в один каталог оставляют там и кадры,
    и транскрипт, причём второй вызов бодро печатает «кадры не кладутся намеренно»
    про папку, где сорок кадров уже лежат. Зонд vision получает текст речи, его
    ответ перестаёт что-либо мерить, а из этого ответа выводится метка зависимости
    от звука — то есть ломается ровно то, ради честности чего всё построено.
    """
    if not out.exists() or not any(out.iterdir()):
        return
    stamp = out / "mode.json"
    was = json.loads(stamp.read_text(encoding="utf-8"))["mode"] if stamp.exists() else None
    if was == mode:
        return
    if force:
        print(f"каталог был режима {was!r}, перезаписывается под {mode!r} (--force)")
        for name in ("transcript.md", "limits.json", "mode.json"):
            (out / name).unlink(missing_ok=True)
        shutil.rmtree(out / "frames", ignore_errors=True)
        return
    sys.exit(f"каталог {out} непуст и собран режимом {was!r}, а сейчас запрошен {mode!r}. "
             f"Разные зонды обязаны получать разные папки — иначе изоляция по модальностям "
             f"не работает. Возьмите другой --out или, если это осознанная пересборка, "
             f"добавьте --force")


def check_dense_allowed(out: Path, force: bool) -> None:
    """Не дать `--dense` пронести кадры в папку, куда кадры класть запрещено.

    `check_mode` вызывался только для `--until` и `--frame`: у `--dense` режима нет,
    поэтому проверка пропускалась, а `extract_dense` создавал `frames/` сам. Итог —
    два вызова подряд, `--until --only transcript` и `--dense`, оставляли в папке
    текстового зонда пятнадцать кадров, причём `mode.json` продолжал утверждать
    `"transcript"`. Зонд text получал картинку, `textonly_solved` переставал
    что-либо мерить, а из него выводится `solvable` и метка зависимости от речи.

    Та же дыра закрывала и `frame`: у frozen-frame-папки нет `limits.json`,
    поэтому `clamp_to_workspace` пропускал любой участок, и зонд «один кадр без
    истории» получал десяток кадров из другого места лекции.
    """
    if not out.exists() or not any(out.iterdir()):
        return
    stamp = out / "mode.json"
    if not stamp.exists():
        if force:
            print(f"каталог {out} непуст и без mode.json, досемплирование по --force")
            return
        sys.exit(f"каталог {out} непуст, но собран не этим скриптом (нет mode.json). "
                 f"--dense досемплирует чужую папку вслепую; возьмите другой --out "
                 f"или добавьте --force")
    was = json.loads(stamp.read_text(encoding="utf-8"))["mode"]
    if was in ("frames", "both"):
        return
    reason = {
        "transcript": "это папка текстового зонда — кадры в ней отменяют весь смысл "
                      "замера textonly_solved",
        "frame": "это папка зонда frozen-frame — он обязан видеть ровно один кадр "
                 "и ничего вокруг",
    }[was]
    sys.exit(f"каталог {out} собран режимом {was!r}: {reason}. Возьмите другой --out")


def clamp_to_workspace(out: Path, t0: float, t1: float) -> tuple[float, float]:
    """Не выпускать досемплирование за границы, с которыми папка была создана.

    Иначе слепой ревьюер, попросив участок «с запасом», увидит кадры после своей
    верхней границы — то есть ровно то, что от него скрыто.
    """
    limits = out / "limits.json"
    if not limits.exists():
        return t0, t1
    lim = json.loads(limits.read_text(encoding="utf-8"))
    a, b = max(t0, lim["from"]), min(t1, lim["until"])
    if (a, b) != (t0, t1):
        print(f"участок обрезан по границам рабочей папки: {a:.0f}-{b:.0f} с")
    if a >= b:
        sys.exit("запрошенный участок целиком вне рабочей папки")
    return a, b


def extract_dense(vid: str, out: Path, t0: float, t1: float, step: float, cap: int) -> int:
    mp4 = ROOT / "data" / "videos" / vid / f"{vid}.mp4"
    if not mp4.exists():
        sys.exit(f"нет видео {mp4}")
    dst = out / "frames"
    dst.mkdir(parents=True, exist_ok=True)

    times, t = [], t0
    while t < t1:
        times.append(round(t, 2))
        t += step
    if len(times) > cap:
        sys.exit(
            f"запрошено {len(times)} кадров при потолке {cap}: сузьте участок "
            f"или увеличьте --step (сейчас {step} с)"
        )

    n = 0
    for t in times:
        target = dst / frame_name(t)
        if target.exists():
            continue
        subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4),
             "-frames:v", "1", "-q:v", "4", str(target), "-y"],
            check=False,
        )
        n += target.exists()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_id")
    ap.add_argument("--out", required=True, help="каталог рабочей папки ревьюера")
    ap.add_argument("--until", type=float, help="подготовить всё от начала до этого момента")
    ap.add_argument("--from", dest="t_from", type=float, default=0.0,
                    help="левая граница для --until (по умолчанию 0)")
    ap.add_argument("--dense", nargs=2, type=float, metavar=("A", "B"),
                    help="досемплировать участок частой сеткой")
    ap.add_argument("--step", type=float, default=2.0,
                    help="шаг --dense, с (по умолчанию 2; меньше 1 не бывает — имена "
                         "кадров округляются до секунды, и половина сетки склеилась бы молча)")
    ap.add_argument("--force", action="store_true",
                    help="пересобрать непустой каталог под другой режим")
    ap.add_argument("--max-frames", type=int, default=60,
                    help="потолок кадров на один вызов --dense")
    ap.add_argument("--max-sparse", type=int, default=40,
                    help="потолок кадров редкой сетки при --until")
    ap.add_argument("--frame", type=float, metavar="T",
                    help="папка ровно из одного кадра (зонд frozen-frame)")
    ap.add_argument("--only", choices=("both", "transcript", "frames"), default="both",
                    help="что класть в папку при --until: обе модальности "
                         "(по умолчанию), только транскрипт (зонд text) или "
                         "только кадры (зонд vision)")
    args = ap.parse_args()

    modes = [args.until is not None, args.dense is not None, args.frame is not None]
    if sum(modes) != 1:
        sys.exit("укажите ровно одно из --until, --dense или --frame")
    if args.only != "both" and args.until is None:
        sys.exit("--only имеет смысл только вместе с --until")
    if args.step < 1.0:
        sys.exit(f"--step {args.step}: имена кадров округляются до целой секунды, "
                 f"поэтому сетка мельче секунды молча склеится и вернёт вдвое меньше "
                 f"кадров, чем покажет счётчик")

    out = Path(args.out)
    mode = "frame" if args.frame is not None else (args.only if args.until is not None else None)
    if mode is not None:
        check_mode(out, mode, args.force)
    out.mkdir(parents=True, exist_ok=True)
    if mode is not None:
        (out / "mode.json").write_text(json.dumps({"mode": mode}), encoding="utf-8")
    bundle = load_bundle(args.video_id)

    if args.frame is not None:
        # Зонду frozen-frame нельзя дать даже границы: limits.json сам по себе
        # сообщает, до какого момента идёт материал, а он должен видеть один кадр
        # и ничего вокруг.
        n = extract_dense(args.video_id, out, args.frame, args.frame + 0.01,
                          1.0, 1)
        print(f"рабочая папка : {out}")
        print(f"  кадр        : {n} шт. на {args.frame:.0f} с")
        print("  ни транскрипта, ни соседних кадров, ни limits.json")
    elif args.until is not None:
        # Пересборка той же папки обязана быть идемпотентной (9.3): copy_sparse
        # только добавляет, поэтому повторный вызов с меньшим --until оставлял
        # кадры за новой границей, а limits.json переписывался и начинал врать.
        if args.only in ("both", "frames"):
            shutil.rmtree(out / "frames", ignore_errors=True)
        if args.only in ("both", "transcript"):
            (out / "transcript.md").unlink(missing_ok=True)
        (out / "limits.json").write_text(
            json.dumps({"from": args.t_from, "until": args.until}), encoding="utf-8")
        cues = frames = 0
        actual = args.until
        if args.only in ("both", "transcript"):
            cues, actual = write_transcript(bundle, out, args.t_from, args.until)
        if args.only in ("both", "frames"):
            frames = copy_sparse(bundle, out, args.t_from, args.until, args.max_sparse)
        print(f"рабочая папка : {out}  (--only {args.only})")
        if args.only in ("both", "transcript"):
            print(f"  транскрипт  : {cues} реплик, {args.t_from:.0f}–{actual:.0f} с "
                  f"(запрошено до {args.until:.0f})")
        else:
            print("  транскрипт  : не кладётся намеренно")
        if args.only in ("both", "frames"):
            print(f"  кадры       : {frames} шт. (редкая сетка из бандла)")
        else:
            print("  кадры       : не кладутся намеренно")
        print("  разметки в папке нет и быть не должно")
    else:
        check_dense_allowed(out, args.force)
        a, b = clamp_to_workspace(out, *args.dense)
        n = extract_dense(args.video_id, out, a, b, args.step, args.max_frames)
        print(f"добавлено кадров: {n} ({a:.0f}–{b:.0f} с, шаг {args.step} с) -> {out}/frames")


if __name__ == "__main__":
    main()

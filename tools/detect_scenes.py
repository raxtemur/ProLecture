#!/usr/bin/env python3
"""Детекция смены сцен в видео 3Blue1Brown: кадры там, где меняется картинка.

Зачем своё, а не сетка ffmpeg: ролики manim — это редкий яркий контент на чёрном
фоне, где сцена держится десятки секунд, а потом за секунду перерисовывается.
Равномерная сетка одновременно дублирует статику и проскакивает смены. Готовые
детекторы (`ffmpeg -vf select='gt(scene,...)'`, PySceneDetect ContentDetector)
сравнивают кадр с ПРЕДЫДУЩИМ, поэтому плавные переезды manim (объект едет через
экран три секунды) для них — цепочка мелких разностей ниже любого порога.

Алгоритм:

1. Опрашиваем видео `probe-fps` раз в секунду (по умолчанию 4).
2. Кадр ужимаем до 192x108 и режем на сетку 9x12 = 108 блоков.
3. Считаем НАКОПЛЕННЫЙ дрейф — поблочную разницу с последним СНЯТЫМ кадром,
   а не с предыдущим просмотренным. Медленный переезд копит дрейф и рано или
   поздно перешагивает порог; статика не копит ничего.
4. Вычитаем шумовой пол: для каждого блока держим медиану разницы соседних
   опрошенных кадров по скользящему окну. Это нужно ровно из-за 3b1b: у него
   поверх сцены часто крутится лента случайных бит, которая меняется каждый кадр
   и не значит ничего. Такой блок получает высокий пол и перестаёт голосовать.
5. Скор кадра = степенное среднее очищенного дрейфа по блокам (`--agg-power`).
   При степени 1 это просто доля изменившейся площади, и тогда одна дописанная
   строка формулы тонет: она занимает один блок из 108. Степень 2 смещает вес
   к немногим сильно изменившимся блокам, и «дописали строку» попадает
   в тот же порог, что и «переехала вся картинка».
6. Перешагнул порог — снимаем кадр, он становится новым опорным. Снимаем не
   в момент срабатывания, а когда анимация УЛЕГЛАСЬ (`--settle-max`): иначе
   в выборку систематически попадают наполовину дописанные формулы.

Подбор порога и сверка по кадрам — в docs/scene_detection.md.

Использование:
    python tools/detect_scenes.py l6DKRf-fAAM                 # только времена
    python tools/detect_scenes.py l6DKRf-fAAM --write-frames  # ещё и кадры
    python tools/detect_scenes.py path/to/video.mp4 --threshold 0.02 --json cuts.json
"""

import argparse
import json
import shutil
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "data" / "videos"

# --- значения по умолчанию, подобранные на трёх роликах 3b1b -----------------
# (см. docs/scene_detection.md: 2026-06, 2026-07 и контрольный 2017-05)
PROBE_FPS = 4.0        # опросов в секунду
THRESHOLD = 0.010      # порог по среднему очищенному дрейфу (доля площади кадра)
MIN_GAP = 2.0          # секунд между соседними снятыми кадрами
MAX_GAP = 45.0         # принудительный кадр, если картинка не менялась так долго
GRID = (9, 12)         # блоков по вертикали и горизонтали (108 блоков)
SMALL = (192, 108)     # размер, до которого ужимается кадр (ширина, высота)
NOISE_WINDOW = 8.0     # секунд скользящего окна для оценки шумового пола
NOISE_K = 1.5          # во сколько раз дрейф должен перекрыть шум блока
AGG_POWER = 2.0        # степень усреднения по блокам (>1 — в пользу локальных правок)
SETTLE_MAX = 2.0       # сколько секунд максимум ждём, пока анимация уляжется
SETTLE_EPS = 0.004     # покадровое шевеление, ниже которого считаем, что улеглось
SETTLE_QUIET = 2       # столько тихих опросов подряд; один — это может быть пауза
                       # внутри длинной надписи, и кадр снимается полудописанным

FRAME_FMT = "t{:08.1f}.jpg"   # t000887.2.jpg — сортируется лексикографически


def require_cv2():
    try:
        import cv2
    except ImportError:
        sys.exit(
            "нужен OpenCV. Поставь в base conda:\n"
            "    /home/user/conda/bin/python3 -m pip install opencv-python-headless"
        )
    return cv2


def resolve_input(arg: str) -> Path:
    """Аргумент — либо путь к mp4, либо youtube_id из data/videos/."""
    p = Path(arg)
    if p.is_file():
        return p
    cand = VIDEOS_DIR / arg / f"{arg}.mp4"
    if cand.is_file():
        return cand
    sys.exit(f"не нашёл видео: ни файла {arg}, ни {cand}")


def block_diff(a, b, grid) -> "object":
    """Поблочная средняя абсолютная разница двух уменьшенных кадров, 0..1."""
    import numpy as np
    gy, gx = grid
    h, w = a.shape[:2]
    bh, bw = h // gy, w // gx
    m = np.abs(a - b).mean(axis=2)[: bh * gy, : bw * gx]
    return m.reshape(gy, bh, gx, bw).mean(axis=(1, 3)) / 255.0


def aggregate(cleaned, power: float) -> float:
    """Свёртка поблочного дрейфа в один скор.

    При power=1 это доля изменившейся площади кадра — и тогда одна дописанная
    строка формулы в пустом углу тонет: она занимает один блок из 108. Степенное
    среднее с power>1 смещает вес в сторону немногих сильно изменившихся блоков,
    так что «новая строка» и «переехала вся картинка» попадают в один порог.
    """
    import numpy as np
    if power == 1.0:
        return float(cleaned.mean())
    return float((cleaned.astype(np.float64) ** power).mean() ** (1.0 / power))


def detect(
    mp4: Path,
    probe_fps: float = PROBE_FPS,
    threshold: float = THRESHOLD,
    min_gap: float = MIN_GAP,
    max_gap: float = MAX_GAP,
    grid=GRID,
    small_size=SMALL,
    noise_window: float = NOISE_WINDOW,
    noise_k: float = NOISE_K,
    agg_power: float = AGG_POWER,
    settle_max: float = SETTLE_MAX,
    settle_eps: float = SETTLE_EPS,
    settle_quiet: int = SETTLE_QUIET,
    every: float = 0.0,
    start: float = 0.0,
    end: float = 0.0,
    out_dir: Path | None = None,
    signal_path: Path | None = None,
) -> list[dict]:
    """Возвращает список {t, score, reason}; при out_dir ещё и пишет кадры."""
    cv2 = require_cv2()
    import numpy as np

    cap = cv2.VideoCapture(str(mp4))
    if not cap.isOpened():
        sys.exit(f"OpenCV не открыл {mp4}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / src_fps if total else 0.0
    if end <= 0:
        end = duration or float("inf")

    if out_dir is not None:
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

    noise_len = max(2, int(round(noise_window * probe_fps)))
    noise_hist: deque = deque(maxlen=noise_len)

    cuts: list[dict] = []
    signal: list[dict] = []
    prev_small = None          # предыдущий опрошенный кадр (для шумового пола)
    prev_full = None           # он же в полном размере: нужен, чтобы дописать
                               # незакрытый pending, если ролик кончился
    ref_small = None           # последний СНЯТЫЙ кадр — опора для дрейфа
    pending = None             # ждём, пока уляжется: {"t0": ..., "score": ...}

    def take(t: float, small, full, reason: str, score: float) -> None:
        nonlocal ref_small
        ref_small = small
        # время округляем ДО записи: имя файла и поле `t` обязаны совпадать,
        # иначе потребитель, читающий время из имени, получит другую секунду
        t = round(float(t), 1)
        if cuts and abs(cuts[-1]["t"] - t) < 0.05:
            # два опроса округлились в одну десятую: имя файла совпадёт,
            # запись перетрёт кадр и потребитель недосчитается времени
            return
        rec = {"t": t, "score": round(float(score), 5), "reason": reason}
        if out_dir is not None:
            name = FRAME_FMT.format(t)
            cv2.imwrite(str(out_dir / name), full, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            dst = out_dir / name
            # путь в bundle.json — относительный от корня репозитория, если он там
            rec["path"] = str(dst.relative_to(ROOT)) if dst.is_relative_to(ROOT) else str(dst)
        cuts.append(rec)

    # режим постоянной частоты: слот фиксированной длины, внутри слота берём
    # САМЫЙ СПОКОЙНЫЙ опрошенный кадр. Нужен там, где нельзя иметь дыр
    # (плотное описание видеоряда), но полукадры так же вредны, как и в режиме
    # порога: сетка ffmpeg сюда не годится ровно поэтому.
    if every > 0:
        probe_fps = max(probe_fps, 4.0 / every)
    best = None

    next_probe = start
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = idx / src_fps
        idx += 1
        if t < start:
            continue
        if t > end:
            break
        if t + 1e-9 < next_probe:
            continue
        next_probe = t + 1.0 / probe_fps

        ok, full = cap.retrieve()
        if not ok:
            break
        prev_full = full
        small = cv2.resize(full, small_size, interpolation=cv2.INTER_AREA).astype(np.float32)

        if ref_small is None:                      # первый кадр считаем снятым
            if every <= 0:
                take(t, small, full, "first", 0.0)
            else:
                # в режиме слотов он не снимается сразу, но обязан участвовать
                # в конкурсе своего слота: иначе слот 0 остаётся без кандидата,
                # если опрос в нём был всего один
                ref_small = small
                best = {"slot": int((t - start) // every), "t": t, "small": small,
                        "full": full, "score": float("inf"), "central": False}
            prev_small = small
            continue

        step = block_diff(small, prev_small, grid)  # шевеление за один опрос
        prev_small = small
        floor = (
            np.median(np.stack(noise_hist), axis=0) if noise_hist
            else np.zeros_like(step)
        )
        noise_hist.append(step)

        drift = block_diff(small, ref_small, grid)
        score = aggregate(np.maximum(drift - noise_k * floor, 0.0), agg_power)
        step_score = aggregate(np.maximum(step - noise_k * floor, 0.0), agg_power)
        if signal_path is not None:
            signal.append({"t": round(t, 2), "score": round(score, 5),
                           "step": round(step_score, 5)})

        if every > 0:
            slot = int((t - start) // every)
            offset = (t - start) - slot * every
            # кандидат из середины слота предпочтительнее самого спокойного:
            # на краях соседние слоты выбирают кадры в 0.1 с друг от друга,
            # и это два почти одинаковых изображения по полной цене prefill
            central = 0.2 * every - 1e-9 <= offset <= 0.8 * every + 1e-9
            cand = {"slot": slot, "t": t, "small": small, "full": full,
                    "score": step_score, "central": central}
            if best is None or slot != best["slot"]:
                if best is not None:
                    take(best["t"], best["small"], best["full"], "slot", best["score"])
                best = cand
            elif (cand["central"], -cand["score"]) > (best["central"], -best["score"]):
                best = cand
            continue

        gap = t - cuts[-1]["t"]

        if pending is not None:
            # Ждём, пока анимация уляжется, но не дольше settle_max. Одного тихого
            # опроса мало: manim пишет формулу несколько секунд, и в середине письма
            # бывает пауза, на которой кадр снимался полудописанным.
            pending["quiet"] = pending["quiet"] + 1 if step_score < settle_eps else 0
            if pending["quiet"] >= settle_quiet or t - pending["t0"] >= settle_max:
                take(t, small, full, pending["reason"], max(pending["score"], score))
                pending = None
            continue

        if gap < min_gap:
            continue
        if score >= threshold:
            pending = {"t0": t, "score": score, "reason": "scene", "quiet": 0}
        elif max_gap > 0 and gap >= max_gap:
            take(t, small, full, "max-gap", score)

    if pending is not None and prev_small is not None:
        # смена сцены за settle_max до конца ролика: ждать больше нечего,
        # снимаем последним, что видели, иначе она пропадает молча
        # ВАЖНО: картинка тут позже записанной секунды (до settle_max),
        # потому и причина отдельная — потребитель должен видеть разницу
        take(pending["t0"], prev_small, prev_full, "scene-eof", pending["score"])
    if best is not None:
        # обрезанный по --end слот успевает набрать один кандидат у самой
        # границы, и он оказывается вплотную к кадру предыдущего слота
        near = cuts and best["t"] - cuts[-1]["t"] < 0.3 * every
        if not near:
            take(best["t"], best["small"], best["full"], "slot", best["score"])
    cap.release()
    if signal_path is not None:
        signal_path.write_text(json.dumps(signal), encoding="utf-8")
    return cuts


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Детекция сцен по накопленному дрейфу от последнего снятого кадра"
    )
    ap.add_argument("video", help="путь к mp4 или youtube_id из data/videos/")
    ap.add_argument("--probe-fps", type=float, default=PROBE_FPS,
                    help=f"опросов видео в секунду (по умолчанию {PROBE_FPS})")
    ap.add_argument("--threshold", type=float, default=THRESHOLD,
                    help=f"порог накопленного дрейфа (по умолчанию {THRESHOLD})")
    ap.add_argument("--min-gap", type=float, default=MIN_GAP,
                    help=f"минимум секунд между кадрами (по умолчанию {MIN_GAP})")
    ap.add_argument("--max-gap", type=float, default=MAX_GAP,
                    help=f"кадр силой, если ничего не менялось столько секунд "
                         f"(по умолчанию {MAX_GAP}, 0 — выключить)")
    ap.add_argument("--noise-k", type=float, default=NOISE_K,
                    help=f"во сколько раз дрейф блока должен перекрыть его шум "
                         f"(по умолчанию {NOISE_K}, 0 — не вычитать шум)")
    ap.add_argument("--agg-power", type=float, default=AGG_POWER,
                    help=f"степень усреднения по блокам (по умолчанию {AGG_POWER}; "
                         f"1 — просто доля изменившейся площади)")
    ap.add_argument("--noise-window", type=float, default=NOISE_WINDOW,
                    help=f"окно оценки шума, секунд (по умолчанию {NOISE_WINDOW})")
    ap.add_argument("--settle-max", type=float, default=SETTLE_MAX,
                    help=f"максимум ожидания, пока анимация уляжется "
                         f"(по умолчанию {SETTLE_MAX}, 0 — снимать сразу)")
    ap.add_argument("--every", type=float, default=0.0,
                    help="режим постоянной частоты: слот такой длины (секунд), "
                         "внутри слота берётся самый спокойный кадр; порог "
                         "и min-gap при этом не действуют")
    ap.add_argument("--settle-quiet", type=int, default=SETTLE_QUIET,
                    help=f"столько тихих опросов подряд считаем концом анимации "
                         f"(по умолчанию {SETTLE_QUIET})")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0, help="0 — до конца")
    ap.add_argument("--write-frames", action="store_true", help="сохранять сами кадры")
    ap.add_argument("--out-dir", help="куда кадры (по умолчанию data/bundles/<id>/frames)")
    ap.add_argument("--clean", action="store_true", help="очистить каталог кадров перед записью")
    ap.add_argument("--json", help="куда записать список времён")
    ap.add_argument("--dump-signal", help="куда записать сырой сигнал (для подбора порога)")
    ap.add_argument("--quiet", action="store_true", help="не печатать список времён")
    args = ap.parse_args()

    mp4 = resolve_input(args.video)
    cv2 = require_cv2()
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    duration = total / fps if fps else 0.0

    out_dir = None
    if args.write_frames:
        out_dir = Path(args.out_dir) if args.out_dir else (
            ROOT / "data" / "bundles" / mp4.stem / "frames"
        )
        if args.clean and out_dir.exists():
            shutil.rmtree(out_dir)

    cuts = detect(
        mp4,
        probe_fps=args.probe_fps,
        threshold=args.threshold,
        min_gap=args.min_gap,
        max_gap=args.max_gap,
        noise_window=args.noise_window,
        noise_k=args.noise_k,
        agg_power=args.agg_power,
        settle_max=args.settle_max,
        settle_quiet=args.settle_quiet,
        every=args.every,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
        signal_path=Path(args.dump_signal) if args.dump_signal else None,
    )

    if args.json:
        Path(args.json).write_text(
            json.dumps(cuts, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    if not args.quiet:
        for c in cuts:
            print(f"{c['t']:9.2f}  {c['score']:.4f}  {c['reason']}")

    # знаменатель — разобранный участок, а не промежуток между первым и
    # последним кадром: иначе оборванный прогон завышает частоту
    span = (min(args.end, duration) if args.end else duration) - args.start
    if span <= 0:
        span = (cuts[-1]["t"] - cuts[0]["t"]) if len(cuts) > 1 else 0.0
    forced = sum(1 for c in cuts if c["reason"] == "max-gap")
    print(f"{mp4.name}: кадров {len(cuts)}"
          + (f", {len(cuts) / span * 60:.1f} на минуту" if span else "")
          + f", из них по max-gap {forced}"
          + (f", кадры → {out_dir}" if out_dir else ""))


if __name__ == "__main__":
    main()

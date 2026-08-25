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


def load_description(vid: str) -> list[dict] | None:
    """Описание видеоряда, если оно построено (tools/describe_video.py).

    Первая строка файла — метаданные прогона, дальше по строке на чанк.
    Отсутствие файла не ошибка: бандл без описания остаётся рабочим.
    """
    path = ROOT / "data" / "bundles" / vid / "description.jsonl"
    if not path.exists():
        return None
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if "chunk_index" in r]


def write_screen(desc: list[dict], out: Path, t0: float, t1: float) -> tuple[int, int]:
    """Текстовый индекс видеоряда: чем искать, а не чем доказывать.

    Кладём два файла разного назначения:

    * `screen.jsonl` — чанки целиком (описание начала и конца, посекундные события,
      распознанный экранный текст). Он большой и читать его целиком не надо —
      он для `grep`;
    * `screen_text.md` — таймлайн распознанного текста, дедуплицированный: строка
      попадает в него один раз, в момент первого появления. Это и есть индекс:
      «где на экране 1.75» становится одним `grep` вместо часа просмотра кадров.

    Режется по тем же границам, что транскрипт, и по той же причине: чанк,
    пересекающий `t1`, выбрасывается целиком. Иначе полу-слепой получил бы
    описание будущего — то есть ровно то, слепоту к чему проверяет его работа.

    **Это описание сделано моделью, а не человеком.** Оно годится, чтобы найти
    момент, и не годится, чтобы что-то утверждать: прежде чем поставить таймкод
    в ревью, момент надо увидеть на настоящем кадре. Об этом сказано и в шапке
    каждого файла — читающий их субагент шапку увидит, а этот докстринг нет.
    """
    chunks = [c for c in desc if c["t_start"] >= t0 and c["t_end"] <= t1]

    # Не глобальный ключ: строка, которая пропала и вернулась через минуту, —
    # обычно и есть интересное появление, а с глобальным ключом она молча
    # схлопывалась в самое первое. Гасим только то, что висит на экране подряд.
    REAPPEAR_GAP = 10.0

    head = (f"# Экранный текст {out.name}: {t0:.0f}-{t1:.0f} с\n"
            f"# Распознан МОДЕЛЬЮ по кадрам, не человеком: годится, чтобы НАЙТИ момент,\n"
            f"# не годится, чтобы его УТВЕРЖДАТЬ. Нашли строку — посмотрите кадр.\n"
            f"# Строка попадает сюда при появлении; если она пропала больше чем\n"
            f"# на {REAPPEAR_GAP:.0f} с и вернулась — это отдельная строка ленты.\n"
            f"# Ищите grep-ом, а не чтением целиком.\n\n")
    last_at: dict[tuple[str, str], float] = {}
    rows: list[tuple[float, str, str]] = []
    for c in chunks:
        # Ключи screen_text и events[].t — АБСОЛЮТНЫЕ секунды ролика, а не смещения
        # внутри чанка и не индексы кадров. Проверяется тем, что максимальный ключ
        # по файлу (1935) совпадает с длительностью ролика, а у чанка [6.8, 11.2]
        # ключи идут 6..11.
        # ключ "?" ставится, когда модель приписала элементу секунду за
        # пределами своего фрагмента: времени у него нет, в ленту по времени
        # он не встаёт
        keys = [k for k in (c.get("screen_text") or {}) if str(k).isdigit()]
        for k in sorted(keys, key=int):
            t = float(int(k))
            for item in (c["screen_text"][k] or []):
                txt = (item.get("text") or "").strip()
                if not txt:
                    continue
                key = (txt, item.get("location") or "")
                prev = last_at.get(key)
                last_at[key] = t
                if prev is not None and t - prev <= REAPPEAR_GAP:
                    continue
                rows.append((t, item.get("location") or "-", txt))
    rows.sort()
    (out / "screen_text.md").write_text(
        head + "\n".join(f"{t:8.1f}  {loc:8} {txt}" for t, loc, txt in rows) + "\n",
        encoding="utf-8")

    with (out / "screen.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps({"_note": "описание видеоряда, сделанное моделью; "
                                     "для поиска момента, не для доказательства. "
                                     "Читать grep-ом, а не целиком.",
                            "from": t0, "until": t1, "chunks": len(chunks)},
                           ensure_ascii=False) + "\n")
        for c in chunks:
            slim = {k: v for k, v in c.items()
                    if k not in ("frames", "frame_times", "latency_s")}
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")
    return len(chunks), len(rows)


def write_frame_index(bundle: dict, out: Path, t0: float, t1: float) -> int:
    """Манифест кадров вместо копий: список таймкодов и путь, где их смотреть.

    Копирование существует ровно ради одного — не дать слепому увидеть будущее.
    Там, где слепоты не требуется (`full_sample`, `full_window` — они и так знают
    эталон), копия бессмысленна: она стоит диска и времени, а бюджет всё равно
    считается по числу открытых кадров, а не по числу лежащих в папке.
    """
    picked = [fr for fr in bundle["frames"] if t0 <= fr["t"] < t1]
    src_dir = (ROOT / "data" / "bundles" / bundle["video_id"] / "frames").resolve()
    lines = [f"# Кадры {bundle['video_id']}: {t0:.0f}-{t1:.0f} с — ИНДЕКС, не копии",
             f"# Смотреть прямо здесь: {src_dir}/<имя>",
             f"# Нарезка по сменам сцен; между соседними строками экран не менялся",
             f"# скачком. Нужно плотнее — tools/prepare_review_workspace.py --dense.",
             ""]
    lines += [f"{fr['t']:8.1f}  {Path(fr['path']).name}" for fr in picked]
    (out / "frames.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(picked)


def copy_sparse(bundle: dict, out: Path, t0: float, t1: float, cap: int) -> int:
    dst = out / "frames"
    dst.mkdir(exist_ok=True)
    picked = [fr for fr in bundle["frames"] if t0 <= fr["t"] < t1]
    # нарезка бандла — детекция сцен, около 13 кадров на минуту: на получасовом
    # участке это несколько сотен файлов, и «дешёвая» обзорная операция съела бы
    # весь бюджет просмотра. Прореживаем равномерно по списку, то есть теряем
    # часть сцен — ревьюер добирает нужное точечно через --dense
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
    if was in ("frames", "both", "both-index"):
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
                    help="потолок обзорных кадров при --until; нарезка бандла "
                         "плотнее, лишнее прореживается равномерно")
    ap.add_argument("--frame", type=float, metavar="T",
                    help="папка ровно из одного кадра (зонд frozen-frame)")
    ap.add_argument("--only", choices=("both", "transcript", "frames"), default="both",
                    help="что класть в папку при --until: обе модальности "
                         "(по умолчанию), только транскрипт (зонд text) или "
                         "только кадры (зонд vision)")
    ap.add_argument("--screen", action="store_true",
                    help="положить текстовый индекс видеоряда (screen_text.md "
                         "и screen.jsonl) из description.jsonl. Только для ревьюеров: "
                         "зондам он ломает замер модальности")
    ap.add_argument("--index-only", action="store_true", dest="index_only",
                    help="не копировать кадры, а положить манифест frames.md "
                         "с таймкодами и путём. ТОЛЬКО для full_sample и "
                         "full_window: манифест называет каталог бандла и границу "
                         "папки не удерживает, поэтому полу-слепому и зондам "
                         "кадры кладутся копиями")
    args = ap.parse_args()

    modes = [args.until is not None, args.dense is not None, args.frame is not None]
    if sum(modes) != 1:
        sys.exit("укажите ровно одно из --until, --dense или --frame")
    if args.only != "both" and args.until is None:
        sys.exit("--only имеет смысл только вместе с --until")
    # Экранный индекс построен ТОЛЬКО по кадрам (в meta прогона описания стоит
    # with_transcript: false), то есть он — функция визуального канала и ничего
    # больше. Отсюда граница проходит не «ревьюеры против зондов», а по тому,
    # какой канал зонду положен:
    #
    #   text  — запрещён: индекс дал бы ему визуальный канал словами, и
    #           textonly_solved перестал бы что-либо мерить;
    #   frame — запрещён: индекс это таймлайн, а frozen-frame обязан видеть один
    #           кадр и ничего вокруг, в том числе никакой истории;
    #   vision, full, ревьюеры — разрешён.
    #
    # Для vision он не просто безвреден, а лечит известный перекос: при одной
    # редкой сетке зонд получает сорок кадров на полчаса, и visiononly_solved
    # систематически уезжает в false, а метка audio_dependency — в required.
    # Индекс построен по 0.5-секундной сетке, то есть плотнее любого бюджета,
    # который зонду можно выдать кадрами.
    if args.screen and (args.only == "transcript" or args.frame is not None):
        who = "text" if args.only == "transcript" else "frozen-frame"
        why = ("индекс дал бы ему визуальный канал словами, и textonly_solved "
               "перестал бы что-либо мерить"
               if args.only == "transcript" else
               "индекс — это таймлайн, а зонд обязан видеть один кадр и ничего "
               "вокруг, в том числе никакой истории")
        sys.exit(f"--screen несовместим с папкой зонда {who}: {why}")
    # Манифест не удерживает границу: в нём написан путь к бандлу, где лежит
    # весь ролик. Роли, которым слепота обязательна, обязаны получать копии.
    if args.index_only and (args.only != "both" or args.frame is not None):
        sys.exit("--index-only несовместим с папкой зонда: манифест называет каталог "
                 "бандла, где лежит весь ролик, и границу папки не удерживает. "
                 "Зондам и полу-слепому кадры кладутся копиями")
    if args.step < 1.0:
        sys.exit(f"--step {args.step}: имена кадров округляются до целой секунды, "
                 f"поэтому сетка мельче секунды молча склеится и вернёт вдвое меньше "
                 f"кадров, чем покажет счётчик")

    out = Path(args.out)
    # Папка с манифестом и папка с копиями — разные режимы, а не вариант одной.
    # Иначе повторный вызов без --index-only оставил бы рядом манифест на весь
    # бандл и «изолированные» копии, и граница держалась бы только на честности.
    mode = "frame" if args.frame is not None else (args.only if args.until is not None else None)
    if mode == "both" and args.index_only:
        mode = "both-index"
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
        for name in ("screen_text.md", "screen.jsonl", "frames.md"):
            (out / name).unlink(missing_ok=True)
        cues = frames = 0
        actual = args.until
        if args.only in ("both", "transcript"):
            cues, actual = write_transcript(bundle, out, args.t_from, args.until)
        if args.only in ("both", "frames"):
            if args.index_only:
                frames = write_frame_index(bundle, out, args.t_from, args.until)
            else:
                frames = copy_sparse(bundle, out, args.t_from, args.until, args.max_sparse)
        screen = None
        if args.screen:
            desc = load_description(args.video_id)
            if desc is None:
                sys.exit(f"нет data/bundles/{args.video_id}/description.jsonl; "
                         f"сначала tools/describe_video.py {args.video_id}")
            screen = write_screen(desc, out, args.t_from, args.until)
        print(f"рабочая папка : {out}  (--only {args.only})")
        if args.only in ("both", "transcript"):
            print(f"  транскрипт  : {cues} реплик, {args.t_from:.0f}–{actual:.0f} с "
                  f"(запрошено до {args.until:.0f})")
        else:
            print("  транскрипт  : не кладётся намеренно")
        if args.only in ("both", "frames"):
            how = "манифест frames.md, копий нет" if args.index_only else "копии, редкая сетка из бандла"
            print(f"  кадры       : {frames} шт. ({how})")
        else:
            print("  кадры       : не кладутся намеренно")
        if screen is not None:
            print(f"  экран       : {screen[0]} чанков, {screen[1]} строк текста "
                  f"(индекс для поиска, не доказательство)")
        print("  разметки в папке нет и быть не должно")
    else:
        check_dense_allowed(out, args.force)
        a, b = clamp_to_workspace(out, *args.dense)
        n = extract_dense(args.video_id, out, a, b, args.step, args.max_frames)
        print(f"добавлено кадров: {n} ({a:.0f}–{b:.0f} с, шаг {args.step} с) -> {out}/frames")


if __name__ == "__main__":
    main()

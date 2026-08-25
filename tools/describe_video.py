#!/usr/bin/env python3
"""Плотное описание видеоряда, выравненное по времени.

Задача: дать разметчику и ревьюеру документ вроде субтитров, но вместо реплик —
подробное описание происходящего на экране. Тогда на большинстве шагов разметки
можно читать текст вместо просмотра десятков кадров.

Как устроено
------------
Ролик режется на окна по `--window` секунд со сдвигом `--stride`, то есть
с перекрытием: крайние секунды описывают оба соседних фрагмента. Кадры окна
уходят одним запросом в VLM (OpenAI-совместимый сервер, например vLLM),
запросы идут параллельно.

Ответ — строгий JSON по схеме, которую держит сам сервер (guided decoding):
`begin` (состояние экрана в начале), `events` (по записи на каждую секунду),
`screen_text` (`{t, text, location}` — дословный текст с экрана и его место
в кадре), `end`. Разбирать свободный текст регулярками не приходится.

Источник кадров подменяем: `--settled` (детекция сцен в режиме постоянной
частоты — рекомендуемый), равномерная нарезка своим ffmpeg (`--interval`),
готовый каталог (`--frames-dir`) или список времён (`--times`). Скрипт ничего
не знает про то, как выбраны времена, — только про то, что у каждого кадра есть
момент в секундах.

Транскрипт в промпт по умолчанию НЕ подаётся. Описание должно быть чистым
видеоканалом: в ProLecture метка `audio_dependency` выводится замером зондами
модальностей, и если бы визуальное описание было заражено содержанием звука,
зонд vision-only перестал бы быть vision-only. Флаг `--with-transcript` есть,
но включать его для материалов бенчмарка не следует.

Примеры (клиент — base conda, ему нужны только openai и Pillow)
-------
    PY=/home/user/conda/bin/python3

    # весь ролик: два спокойных кадра в секунду, окна 5 с со сдвигом 3
    $PY tools/describe_video.py l6DKRf-fAAM --settled 0.5 --workers 16

    # проба на куске перед долгим прогоном
    $PY tools/describe_video.py l6DKRf-fAAM --settled 0.5 --range 900-960 --out-prefix _probe

    # перезапросить только испорченные фрагменты готового прогона
    $PY tools/describe_video.py l6DKRf-fAAM --settled 0.5 --redo-bad

Как поднять сервер и что делать, когда он падает — docs/video_description.md.

Выход: data/bundles/<id>/description.jsonl (машинный, основной) и
       data/bundles/<id>/description.md (для чтения человеком/агентом).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "data" / "videos"
BUNDLES_DIR = ROOT / "data" / "bundles"

# два кадра в секунду: одна секунда описания опирается на два состояния экрана,
# и этого хватает, чтобы поймать момент дорисовки формулы
DEFAULT_SETTLED = 0.5

def rel_path(path: Path) -> str:
    """Путь для записи в jsonl: относительный от корня репозитория, если кадр
    внутри него, иначе абсолютный — каталог кадров разрешено держать снаружи."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


# t00120.jpg -> 120.0, t000907.50.jpg -> 907.5
FRAME_TIME_RE = re.compile(r"t(\d+(?:\.\d+)?)")


# ------------------------------------------------------------------- промпт

SYSTEM_PROMPT = """\
Ты — ассистент, который ведёт покадровую стенограмму видеоряда математической \
лекции (анимация в стиле 3Blue1Brown: чёрный фон, формулы, графики, схемы).

Твоя единственная задача — записать то, что ВИДНО на кадрах. Это не пересказ \
темы и не объяснение математики. Пиши по-русски; формулы, подписи и любой текст \
с экрана — в оригинале (LaTeX-подобной записью, например `p_i`, `-\\log_2 p_i`, \
`\\sum_i`).

Железные правила:
1. Никогда не додумывай. Если символ, индекс или число не читается — пиши \
«неразборчиво» и опиши, что видно (сколько символов, где расположено, какого цвета). \
Особенно это касается мелких подписей: делений на оси, надписей внутри сегментов, \
текста во врезках. Не подставляй «правдоподобную» шкалу вроде `0.0, 0.1, ..., 1.0` \
и не достраивай алфавит по паре различимых букв — либо перепиши то, что реально \
прочитал, либо напиши «подписи слишком мелкие, не читаются».
2. Не переноси в описание знания о предмете. Если на экране `H(p)`, не пиши \
«энтропия», пиши `H(p)`. Ты не знаешь, о чём говорит диктор.
3. Не пиши мета-комментариев («на этих кадрах показано…», «продолжается объяснение»).
4. Числа, подписи осей, деления шкалы, легенды, значения в таблицах и столбиках \
переписывай дословно, вместе с привязкой «что → какое значение».
5. Число называй, только если оно НАПИСАНО на экране. Высоту столбика, длину \
отрезка, значение точки на графике не переводи в число «на глаз»: пиши «выше \
соседнего», «примерно до третьей линии сетки», «самый высокий из всех». \
Выдуманное число хуже пропуска: по нему молча сломается разметка.
6. Между соседними кадрами отмечай именно ИЗМЕНЕНИЯ: что появилось, что исчезло, \
что подсветилось/сменило цвет, что переместилось.
7. Если однотипных элементов много (буквы, столбики, кружки), не перечисляй все: \
назови их число, первый и последний, и что между ними. В одном перечислении не \
больше 12 элементов, и ни один элемент не повторяется дважды.
8. Непрерывно меняющийся фон дословно НЕ переписывай. Ленты случайных бит, \
бегущие строки-примеры, мелькающие наборы символов — это шум: их содержимое \
меняется само по себе и ничего не значит. В `screen_text` их не выноси вовсе, \
в `begin`/`end` упомяни одной фразой («вверху лента случайных бит, меняется \
каждый кадр»), а в `events` про них пиши, только если ничего другого за секунду \
не произошло, и тогда — «лента битов сменилась», без самих цифр. Событие \
«появилась формула» всегда важнее события «сменились случайные биты»: если за \
секунду случилось и то и другое, пиши про формулу.
"""

USER_PROMPT = """\
Фрагмент {chunk_index} видео. Ниже {n_frames} кадров, перед каждым указан его \
момент в секундах; они покрывают интервал {shown_start}–{shown_end} с. Крайние \
секунды интервала описаны и в соседних фрагментах — это сделано нарочно, \
описывай их наравне с остальными.{transcript_block}

Ответ — JSON по заданной схеме, четыре поля:

`begin` — что находится на экране на первом кадре фрагмента. Полная опись: все \
формулы дословно, все подписи, оси и их метки, числа, объекты и их взаимное \
расположение. Если экран пуст — так и напиши.

`events` — ровно по одной записи на каждую секунду из списка: {second_list}. \
Именно эти целые числа, по возрастанию, без пропусков; не бери секунду из подписи \
кадра — кадров на секунду обычно два, и они описываются одной записью. \
В `text` — что изменилось за эту секунду: появилось, исчезло, подсветилось, \
переместилось, дописалось к формуле. Одно предложение, коротко — не пересказывай \
заново то, что уже описано в `begin`. Секунда без изменений: «без изменений».

`screen_text` — по записи на каждый текстовый элемент: формула, подпись, число, \
метка оси. `t` — секунда, где элемент впервые виден в этом фрагменте (висит весь \
фрагмент — хватит первой). `text` — дословно, нечитаемое пиши как «неразборчиво». \
`location` — где на экране. Если текста на экране нет, оставь список пустым.

`end` — одно-два предложения: что остаётся на экране на последнем кадре и чем это \
отличается от `begin`. Не переписывай `begin` целиком.
"""


# Схему держит сам сервер (vLLM, guided decoding): модель физически не может
# выдать невалидный JSON, поставить дробную секунду или выдумать позицию вне
# перечисления. Раньше эти четыре поля вытаскивались регулярками из свободного
# текста, и одна латинская «K» в заголовке уводила целый блок не в то поле.
LOCATIONS = ["up-left", "up", "up-right", "left", "center", "right",
             "down-left", "down", "down-right"]

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["begin", "events", "screen_text", "end"],
    "properties": {
        "begin": {"type": "string"},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["t", "text"],
                "properties": {
                    "t": {"type": "integer", "minimum": 0},
                    "text": {"type": "string"},
                },
            },
        },
        "screen_text": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["t", "text", "location"],
                "properties": {
                    "t": {"type": "integer", "minimum": 0},
                    "text": {"type": "string"},
                    "location": {"enum": LOCATIONS},
                },
            },
        },
        "end": {"type": "string"},
    },
}

# Отдельного «кадра-контекста» больше нет: окна и так перекрываются, и соседние
# фрагменты видят общие секунды целиком. Раньше поле `context` заводилось, но
# всегда оставалось None — промпт про контекст не уходил ни разу, а флаг
# `--no-context-frame` ничего не выключал.


# --------------------------------------------------------------- утилиты

def fmt_t(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.1f}"


def hhmmss(value: float) -> str:
    total = int(value)
    return f"{total // 60:02d}:{total % 60:02d}" if total < 3600 else \
        f"{total // 3600:d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def encode_image(path: Path, upscale: int = 1) -> str:
    """base64 data URL. upscale>1 растягивает кадр — у 360p роликов это заметно
    помогает VLM разбирать мелкие индексы, потому что ViT нарезает больше патчей."""
    raw = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    if upscale > 1:
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img = img.resize((img.width * upscale, img.height * upscale),
                             Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            raw, mime = buf.getvalue(), "image/jpeg"
        except Exception as exc:  # PIL нет или картинка битая — шлём как есть
            print(f"[warn] не удалось увеличить {path.name}: {exc}", file=sys.stderr)
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


# --------------------------------------------------------- источники кадров

def frames_from_dir(directory: Path) -> list[tuple[float, Path]]:
    out: list[tuple[float, Path]] = []
    for p in sorted(directory.iterdir()):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png") or not p.is_file():
            continue
        m = FRAME_TIME_RE.match(p.stem)
        if not m:
            print(f"[warn] пропускаю {p.name}: имя не вида tSSSSS[.ss]", file=sys.stderr)
            continue
        out.append((float(m.group(1)), p))
    return sorted(out)


def times_from_file(path: Path) -> list[float]:
    """Терпимый разбор списка времён: чужой детектор сцен может отдать что угодно."""
    text = path.read_text(encoding="utf-8").strip()
    times: list[float] = []
    if text.startswith(("{", "[")):
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("times", "frames", "scenes", "cuts", "keyframes", "boundaries"):
                if key in data:
                    data = data[key]
                    break
            else:
                raise SystemExit(f"{path}: в объекте нет ключа times/frames/scenes/cuts")
        for item in data:
            if isinstance(item, (int, float)):
                times.append(float(item))
            elif isinstance(item, dict):
                for key in ("t", "time", "start", "start_time", "sec", "timestamp"):
                    if key in item:
                        times.append(float(item[key]))
                        break
    else:
        for line in text.splitlines():
            line = line.strip().rstrip("s")
            if line and not line.startswith("#"):
                times.append(float(line))
    if not times:
        raise SystemExit(f"{path}: не удалось вынуть ни одного времени")
    return sorted(set(times))


def cut_uniform(mp4: Path, out_dir: Path, interval: float, duration: float,
                force: bool = False) -> list[tuple[float, Path]]:
    """Равномерная нарезка одним проходом ffmpeg — на порядок быстрее, чем seek на кадр."""
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = frames_from_dir(out_dir)
    expected = int(duration / interval) + 1
    # мало сверить количество: в каталоге может лежать нарезка с другим шагом
    # (или по списку времён от детектора сцен), и тогда «переиспользование»
    # молча подменяет источник кадров
    step_ok = False
    if len(existing) > 2:
        steps = sorted(b - a for (a, _), (b, _) in zip(existing, existing[1:]))
        step_ok = abs(steps[len(steps) // 2] - interval) < 0.05
    if existing and step_ok and not force and len(existing) >= expected - 2:
        print(f"[кадры] беру готовые {len(existing)} шт. из {out_dir} (--force-frames чтобы перерезать)")
        return existing
    for p in out_dir.glob("*.jpg"):
        p.unlink()
    print(f"[кадры] режу {mp4.name} каждые {interval} с -> {out_dir}")
    # showinfo даёт настоящий pts каждого выданного кадра: имя файла тогда не
    # предположение «i * interval», а измеренное время. Для роликов, у которых
    # поток начинается не с нуля, это единственный честный способ.
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(mp4),
         "-vf", f"fps=1/{interval},showinfo", "-q:v", "3",
         str(out_dir / "seq%06d.jpg"), "-y"],
        check=True, capture_output=True, text=True,
    )
    pts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]
    frames = []
    for i, src in enumerate(sorted(out_dir.glob("seq*.jpg"))):
        t = pts[i] if i < len(pts) else i * interval
        dst = out_dir / f"t{t:09.2f}.jpg"
        src.rename(dst)
        frames.append((t, dst))
    if len(pts) != len(frames):
        print(f"[warn] showinfo дал {len(pts)} меток на {len(frames)} кадров; "
              f"для лишних время посчитано как i*{interval}", file=sys.stderr)
    return frames


def cut_at_times(mp4: Path, out_dir: Path, times: list[float], workers: int = 8,
                 force: bool = False) -> list[tuple[float, Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    # каталог не должен быть смесью двух нарезок: лишние кадры никто не увидит
    # в индексе, но именно их потом находит глазами тот, кто открыл каталог
    wanted = {f"t{t:09.2f}.jpg" for t in times}
    stale = [f for f in out_dir.glob("t*.jpg") if f.name not in wanted]
    if stale:
        print(f"[кадры] в {out_dir} {len(stale)} кадров прошлой нарезки — удаляю")
        for f in stale:
            f.unlink()

    def one(t: float) -> tuple[float, Path] | None:
        dst = out_dir / f"t{t:09.2f}.jpg"
        if not dst.exists() or force:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4),
                 "-frames:v", "1", "-q:v", "3", str(dst), "-y"],
                check=False,
            )
        return (t, dst) if dst.exists() else None

    print(f"[кадры] вырезаю {len(times)} кадров по списку времён -> {out_dir}")
    out: list[tuple[float, Path]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(one, times):
            if res:
                out.append(res)
    lost = len(times) - len(out)
    if lost:
        # молчаливый пропуск выглядит потом как «модель ничего не заметила»
        print(f"[warn] ffmpeg не отдал {lost} кадров из {len(times)} — "
              f"в описании на этих секундах будет дыра", file=sys.stderr)
    return sorted(out)


# ------------------------------------------------------------------ чанки

def build_chunks(frames: list[tuple[float, Path]], window: float,
                 stride: float) -> list[dict]:
    """Окна фиксированной длины со сдвигом `stride` — то есть с перекрытием.

    Перекрытие не роскошь: без него каждое окно кончается на кадре, за которым
    модель не видит ничего, и граница окна систематически ловит недорисованную
    анимацию. Секунды перекрытия описывают ОБА соседних фрагмента, и это нарочно:
    за крайние кадры тогда отвечает не «никто по половинке», а два описания сразу,
    и их можно сверить.

    Границы полуоткрыты: окно `window=5` со сдвигом `stride=4` покрывает секунды
    N…N+4, из них N общая с левым соседом, N+4 — с правым, а N+1…N+3 свои. Пока
    правая граница была включающей, окно захватывало шесть секунд и при сдвиге 3
    своих секунд не оставалось вовсе: каждая секунда описывалась дважды, и на
    prefill уходило втрое больше, чем заказано.
    """
    chunks: list[dict] = []
    if not frames:
        return chunks
    first_t, last_t = frames[0][0], frames[-1][0]
    start = first_t
    while start < last_t + 1e-6:
        end = start + window
        group = [(t, p) for t, p in frames if start - 1e-6 <= t < end - 1e-6]
        # окно, все кадры которого уже показаны предыдущему фрагменту, описывать
        # нечего. Проверяем именно вложение, а не число кадров: одиночный кадр
        # в разреженном месте — это тоже кадр, и молча терять его нельзя
        if group and chunks and group[-1][0] <= chunks[-1]["t_end"] + 1e-6:
            group = []
        if group:
            chunks.append({
                "chunk_index": len(chunks),
                "t_start": round(group[0][0], 2),
                "t_end": round(group[-1][0], 2),
                "frame_times": [round(t, 2) for t, _ in group],
                "paths": [p for _, p in group],
            })
        start += stride
    return chunks


def transcript_slice(cues: list[dict], t0: float, t1: float) -> str:
    picked = [c for c in cues if c["end"] > t0 and c["start"] < t1]
    if not picked:
        return ""
    body = " ".join(c["text"] for c in picked)
    return ("\n\nРечь диктора на этом интервале (ТОЛЬКО фон, описывать её нельзя, "
            f"на экране её может не быть): «{body}»")


# ------------------------------------------------------------------ разбор

# Лента случайных бит поверх сцены — единственный «текст», который модель
# переписывает дословно вопреки правилу 8: он крупный и контрастный. Проверить
# его разметчик всё равно не может, а место в индексе он занимает.
#
# Порог 20, а не 12: ролик — про кодирование, и шестнадцать нулей в записи
# `0000000000000000 -> m_0` (142 таких элемента в пилоте) содержательны.
# Плюс структурные прогоны (одни нули, короткий период) не режем вовсе:
# лента случайна, а осмысленные строки почти всегда регулярны.
BITS_RE = re.compile(r"[01]{20,}")


def _structured(bits: str) -> bool:
    """Двоичный прогон, который похож на данные, а не на шум ленты."""
    for period in range(1, 5):
        if len(bits) >= 2 * period and all(
                c == bits[i % period] for i, c in enumerate(bits)):
            return True
    return False


def strip_bits(text: str) -> str:
    """Вырезает ленту случайных бит, оставляя осмысленные двоичные записи.

    Применяется НЕ при записи, а при показе: `.jsonl` хранит то, что модель
    сказала, дословно. Иначе настоящее двоичное кодовое слово — а ролик именно
    про кодирование — пропадало бы навсегда, и вернуть его стоило бы двадцати
    минут на двух A100.

    Читатели, которым лента мешает (markdown этого же прогона, индекс
    экранного текста в рабочей папке ревьюера), зовут её сами.
    """
    out = BITS_RE.sub(lambda m: m.group(0) if _structured(m.group(0)) else "…", text)
    return re.sub(r"\s{2,}", " ", out).strip()


def repair_json(text: str):
    """Достаёт данные из оборванного по лимиту токенов ответа.

    Строгая схема — палка о двух концах: свободный текст при обрыве терял хвост,
    а JSON перестаёт разбираться целиком, и фрагмент пропадает весь. Здесь ответ
    обрезается по последнему закрытому элементу и дозакрывается скобками; из
    двадцати секунд описания теряются последние одна-две вместо всех.
    """
    for cut in range(len(text) - 1, 0, -1):
        if text[cut] != "}":
            continue
        prefix = text[:cut + 1]
        stack, in_str, esc = [], False, False
        for ch in prefix:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "[{":
                stack.append(ch)
            elif ch in "]}" and stack:
                stack.pop()
        if in_str:
            continue
        closed = prefix + "".join("]" if b == "[" else "}" for b in reversed(stack))
        try:
            return json.loads(closed)
        except json.JSONDecodeError:
            continue
    return None


def normalize(payload: dict, span: tuple[float, float]) -> dict:
    """Приводит ответ модели к записи фрагмента.

    Схему проверил сервер, поэтому здесь не разбор, а раскладка: события
    сортируются по секунде, текст с экрана группируется по секундам. Всё, что
    вылезло за границы своего фрагмента, уезжает в ключ `"?"` — модель иногда
    приписывает элементу секунду соседнего окна, и такой ключ лучше молчаливого
    сдвига в индексе.
    """
    # верхняя граница ровно та, о которой спрашивали в промпте
    # (`range(int(t_start), int(t_end) + 1)`): секунда за ней — уже соседнее
    # окно, и полуслепой ревьюер не должен увидеть её через границу нарезки
    lo, hi = int(span[0]), int(span[1])

    events = []
    for ev in payload.get("events", []):
        t = int(ev.get("t", -1))
        text = str(ev.get("text", "")).strip()
        if not text:
            continue
        events.append({"t": t if lo <= t <= hi else None, "text": text})
    events.sort(key=lambda e: (e["t"] is None, e["t"] or 0))

    screen: dict[str, list[dict]] = {}
    for item in payload.get("screen_text", []):
        text = str(item.get("text", "")).strip().strip("`").strip()
        if not text or text.lower() in ("нет", "-", "—"):
            continue
        t = int(item.get("t", -1))
        key = str(t) if lo <= t <= hi else "?"
        screen.setdefault(key, []).append(
            {"text": text, "location": item.get("location")})

    return {
        "begin": str(payload.get("begin", "")).strip(),
        "end": str(payload.get("end", "")).strip(),
        "events": events,
        "screen_text": screen,
    }


SPLIT_ITEM_RE = re.compile(r"[,;]\s*")


def line_is_runaway(line: str) -> bool:
    """Строка, в которой модель ушла в петлю.

    Диагноз ставим по повторам, а не по длине: длинная строка с честным перечнем
    разных формул — нормальна, а вот `*`, `(`, `)`, `+`, `*`, `(`, `)`, `+`, ... —
    это петля декодера. На таких кадрах у 360p ролика подписи физически не читаются,
    и модель заполняет пустоту правдоподобным мусором.
    """
    if len(line) < 200:
        return False
    # петля без разделителей: «→←↓↑↑→←↓↑↑→←↓↑↑…». Ловим по доле уникальных 4-грамм
    grams = [line[i:i + 4] for i in range(len(line) - 3)]
    if grams and len(set(grams)) / len(grams) < 0.15:
        return True
    if len(line) < 300:
        return False
    items = [i.strip(" `") for i in SPLIT_ITEM_RE.split(line) if i.strip(" `")]
    if len(items) < 20:
        return False
    return len(set(items)) / len(items) < 0.6


def payload_text(payload: dict) -> str:
    """Только то, что написала модель, без каркаса JSON.

    Считать вырождение по сериализованному ответу нельзя: там на каждый элемент
    приходится `"location": "left"}`, и на богатом фрагменте доля повторов сама
    собой уезжает ниже порога. На пилоте так пометились «вырожденными» ровно
    самые содержательные фрагменты — вдвое больше текста с экрана, чем у чистых.
    """
    parts = [str(payload.get("begin", "")), str(payload.get("end", ""))]
    parts += [str(e.get("text", "")) for e in payload.get("events", [])]
    parts += [str(i.get("text", "")) for i in payload.get("screen_text", [])]
    return "\n".join(p for p in parts if p)


def looks_degenerate(text: str) -> bool:
    if any(line_is_runaway(line) for line in text.splitlines()):
        return True
    # петля бывает и многострочной: три десятка одинаковых коротких строк,
    # каждая по отдельности невинна
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15]
    if len(lines) >= 10 and len(set(lines)) / len(lines) < 0.5:
        return True
    return False


def describe_chunk(client, model: str, chunk: dict, cues: list[dict],
                   max_tokens: int, temperature: float, upscale: int,
                   retries: int = 3) -> dict:
    frames = list(zip(chunk["frame_times"], chunk["paths"]))

    content: list[dict] = [{
        "type": "text",
        "text": USER_PROMPT.format(
            chunk_index=chunk["chunk_index"],
            n_frames=len(frames),
            shown_start=fmt_t(chunk["t_start"]),
            shown_end=fmt_t(chunk["t_end"]),
            second_list=", ".join(
                str(x) for x in range(int(chunk["t_start"]),
                                      int(chunk["t_end"]) + 1)),

            transcript_block=transcript_slice(cues, chunk["t_start"], chunk["t_end"]) if cues else "",
        ),
    }]
    for t, path in frames:
        content.append({"type": "text", "text": f"[{fmt_t(t)} с]"})
        content.append({"type": "image_url", "image_url": {"url": encode_image(path, upscale)}})

    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content}]

    base = {
        "chunk_index": chunk["chunk_index"],
        "t_start": chunk["t_start"],
        "t_end": chunk["t_end"],
        "frame_times": chunk["frame_times"],
        "frames": [rel_path(p) for p in chunk["paths"]],
    }

    last: Exception | None = None
    text = ""
    degenerate = False
    truncated = False
    for attempt in range(1, retries + 1):
        # на второй попытке ужесточаем штраф и прямо запрещаем перечисления:
        # именно они запускают петлю
        penalty = 1.05 if attempt == 1 else 1.2
        # повтор с тем же max_tokens упрётся в ту же стену; на обрыве по длине
        # бюджет надо поднимать, на петле — нет, там помогает штраф
        # бюджет растёт с каждой попыткой: повтор с тем же лимитом упирался
        # в ту же стену, и третья попытка была копией второй
        budget = int(max_tokens * (1.8 ** (attempt - 1))) if truncated else max_tokens
        msgs = messages
        if attempt > 1 and degenerate:
            msgs = messages + [
                {"role": "assistant", "content": text[:400]},
                {"role": "user", "content":
                    "Ты ушёл в бесконечный повтор. Перепиши ответ заново по той же "
                    "структуре, но не перечисляй мелкие подписи вообще: там, где они "
                    "не читаются, пиши одной фразой «мелкие подписи не читаются». "
                    "Ни один список не длиннее 12 пунктов."},
            ]
        try:
            started = time.time()
            resp = client.chat.completions.create(
                model=model, messages=msgs,
                max_tokens=budget, temperature=temperature, top_p=0.9,
                # схему держит сервер: грамматика не даст выдать ни сломанный
                # JSON, ни дробную секунду, ни позицию вне перечисления
                response_format={"type": "json_schema", "json_schema": {
                    "name": "fragment", "schema": RESPONSE_SCHEMA, "strict": True}},
                # без штрафа модель на однотипных сценах уходит в петлю и
                # печатает один элемент сотни раз, съедая весь бюджет токенов
                extra_body={"repetition_penalty": penalty},
                presence_penalty=0.2,
            )
            text = (resp.choices[0].message.content or "").strip()
            latency = round(time.time() - started, 2)
            truncated = bool(resp.choices) and resp.choices[0].finish_reason == "length"
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                # при обрыве по длине JSON остаётся недописанным — это не
                # «модель ответила плохо», а «бюджет кончился»
                if attempt < retries:
                    print(f"[warn] чанк {chunk['chunk_index']}: ответ оборван, "
                          f"переспрашиваю ({attempt}/{retries})", file=sys.stderr)
                    continue
                payload = repair_json(text)
                if payload is None:
                    return dict(base, latency_s=latency, error="оборванный JSON",
                                raw=text[:2000], begin="", end="", events=[], screen_text={})
                record = dict(base, latency_s=latency, truncated=True)
                record.update(normalize(payload, (chunk["t_start"], chunk["t_end"])))
                return record
            # это два разных брака: петля лечится штрафом, обрыв — бюджетом.
            # Слитая метка и врала в отчёте, и подсовывала модели упрёк
            # «ты ушёл в повтор» тому, кто просто не уложился в max_tokens
            degenerate = looks_degenerate(payload_text(payload))
            if (degenerate or truncated) and attempt < retries:
                why = "вырождение ответа" if degenerate else "ответ оборван по лимиту"
                print(f"[warn] чанк {chunk['chunk_index']}: {why}, "
                      f"переспрашиваю ({attempt}/{retries})", file=sys.stderr)
                continue
            record = dict(base, latency_s=latency)
            if truncated:
                record["truncated"] = True
            record.update(normalize(payload, (chunk["t_start"], chunk["t_end"])))
            if degenerate:
                # ответ всё равно кривой — пусть это видно и человеку, и коду
                record["degenerate"] = True
            return record
        except Exception as exc:
            last = exc
            print(f"[warn] чанк {chunk['chunk_index']}: попытка {attempt}/{retries}: {exc}",
                  file=sys.stderr)
            if attempt < retries:
                time.sleep(2.0 * attempt)
    return dict(base, error=str(last), begin="", end="",
                events=[], screen_text={})


# -------------------------------------------------------------------- вывод

def write_markdown(path: Path, meta: dict, records: list[dict]) -> None:
    chapters = meta.get("chapters") or []

    def chapter_of(t: float) -> str:
        for c in chapters:
            if c["start"] <= t < c["end"]:
                return c["title"]
        return ""

    lines = [
        f"# Описание видеоряда — {meta.get('title', meta['video_id'])}",
        "",
        f"Видео `{meta['video_id']}`, длительность {meta['duration']:.0f} с. "
        f"Фрагментов {len(records)}, кадров {meta.get('n_frames', '?')} "
        f"(отправок на сервер {sum(len(r.get('frame_times', [])) for r in records)}).",
        "",
        f"Модель `{meta['model']}`, окно {meta.get('window')} с со сдвигом "
        f"{meta.get('stride')} с (перекрытие {meta.get('overlap')} с), "
        f"шаг кадров {meta.get('frame_step', '?')} с, транскрипт в промпте: "
        f"{'да' if meta.get('with_transcript') else 'нет'}.",
        "",
        "Описание порождено моделью и содержит её ошибки. Дословный текст с экрана "
        "перепроверяй по кадру, если сэмпл на нём строится.",
        "",
    ]
    prev_chapter = None
    for rec in records:
        ch = chapter_of(rec["t_start"])
        if ch != prev_chapter:
            lines += ["", f"## [{fmt_t(rec['t_start'])}s] {ch or '—'}", ""]
            prev_chapter = ch
        lines.append(
            f"### [{fmt_t(rec['t_start'])}–{fmt_t(rec['t_end'])} с]  "
            f"({hhmmss(rec['t_start'])}–{hhmmss(rec['t_end'])})"
        )
        lines.append("")
        if rec.get("error"):
            lines += [f"*(ошибка запроса: {rec['error']})*", ""]
            continue
        if rec.get("degenerate"):
            lines += ["> Модель ушла в повтор даже после переспроса — фрагменту "
                      "не верить, смотреть кадры.", ""]
        if rec.get("begin"):
            lines += ["**Начало.** " + strip_bits(rec["begin"].replace("\n", " ")), ""]
        if rec.get("events"):
            lines.append("**События.**")
            lines.append("")
            for ev in rec["events"]:
                mark = f"`{fmt_t(ev['t'])}s`" if ev["t"] is not None else "`?`"
                lines.append(f"- {mark} {strip_bits(ev['text'])}")
            lines.append("")
        if rec.get("screen_text"):
            lines.append("**Текст на экране.**")
            lines.append("")
            for sec in sorted(rec["screen_text"], key=lambda k: (k == "?", k.isdigit() and int(k))):
                for item in rec["screen_text"][sec]:
                    where = f" — {item['location']}" if item.get("location") else ""
                    mark = f"`{sec}s`" if sec != "?" else "`?`"
                    shown = strip_bits(item["text"])
                    if not shown or shown.strip("… ") == "":
                        continue
                    lines.append(f"- {mark} `{shown}`{where}")
            lines.append("")
        if rec.get("end"):
            lines += ["**Конец.** " + strip_bits(rec["end"].replace("\n", " ")), ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- main

def parse_ranges(values: list[str]) -> list[tuple[float, float]]:
    out = []
    for v in values or []:
        m = re.match(r"^(\d+(?:\.\d+)?)\s*[-–:]\s*(\d+(?:\.\d+)?)$", v.strip())
        if not m:
            raise SystemExit(f"--range {v!r}: ожидается вид 120-360")
        out.append((float(m.group(1)), float(m.group(2))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_id", help="youtube-id; ищется data/videos/<id>/<id>.mp4")
    ap.add_argument("--mp4", help="путь к mp4, если он лежит не по конвейеру")

    src = ap.add_mutually_exclusive_group()
    src.add_argument("--interval", type=float, default=None,
                     help="равномерная нарезка, шаг в секундах. Осознанный откат: "
                          "сетка одновременно дублирует статику и теряет сцены, "
                          "по умолчанию кадры берёт детектор")
    src.add_argument("--frames-dir", help="готовый каталог кадров с именами tSSSSS[.ss].jpg")
    src.add_argument("--times", help="файл со списком времён (json/txt), напр. выход detect_scenes.py")
    src.add_argument("--settled", type=float, metavar="СЕК",
                     help="кадры выбирает detect_scenes в режиме постоянной частоты: "
                          "слот такой длины, внутри слота берётся самый спокойный кадр "
                          "(0.5 = два кадра в секунду). Дыр не оставляет, но и полукадров тоже")

    ap.add_argument("--force-frames", action="store_true", help="перерезать кадры, даже если есть")
    ap.add_argument("--range", action="append", dest="ranges",
                    help="ограничить участком, напр. 0-300; можно повторять")
    ap.add_argument("--window", type=float, default=5.0,
                    help="длина окна одного запроса, секунд")
    ap.add_argument("--stride", type=float, default=4.0,
                    help="сдвиг окна, секунд; окно 5 со сдвигом 4 даёт секунду "
                         "перекрытия с левым соседом и секунду с правым, "
                         "три секунды свои")
    ap.add_argument("--workers", type=int, default=12, help="параллельных запросов")
    # значения по умолчанию совпадают с тем сервером, который описан
    # в docs/video_description.md и на котором собран description.jsonl
    ap.add_argument("--model", default=os.environ.get("DESCRIBE_MODEL", "qwen36"))
    ap.add_argument("--api-base", default=os.environ.get("DESCRIBE_API_BASE",
                                                         "http://localhost:8078/v1"))
    ap.add_argument("--max-tokens", type=int, default=2600,
                    help="бюджет ответа; при обрыве повтор идёт с ×1.8")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--upscale", type=int, default=2,
                    help="во сколько раз растянуть кадр перед отправкой (360p -> 720p)")
    ap.add_argument("--with-transcript", action="store_true",
                    help="подать речь диктора как фон (по умолчанию нет: см. докстринг)")
    ap.add_argument("--out-prefix", default="description")
    ap.add_argument("--limit-chunks", type=int, default=0, help="отладка: только первые N чанков")
    ap.add_argument("--redo-bad", action="store_true",
                    help="перезапросить только фрагменты с ошибкой, обрывом или "
                         "вырождением из уже готового файла, остальные взять как есть")
    args = ap.parse_args()

    # без явного источника кадры берёт детектор в режиме слотов: равномерная
    # сетка по умолчанию — ровно то, от чего уходили в make_bundle.py
    if args.interval is None and not (args.frames_dir or args.times or args.settled):
        args.settled = DEFAULT_SETTLED

    vid = args.video_id
    mp4 = Path(args.mp4) if args.mp4 else VIDEOS_DIR / vid / f"{vid}.mp4"
    bdir = BUNDLES_DIR / vid
    bdir.mkdir(parents=True, exist_ok=True)

    bundle = {}
    bundle_path = bdir / "bundle.json"
    if bundle_path.exists():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    duration = float(bundle.get("duration") or 0)
    if not duration:
        if not mp4.exists():
            raise SystemExit(f"нет ни {bundle_path}, ни {mp4}: неоткуда взять длительность")
        duration = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(mp4)],
            capture_output=True, text=True, check=True).stdout.strip())

    ranges = parse_ranges(args.ranges)
    if args.settled is not None and args.settled <= 0:
        raise SystemExit("--settled должен быть больше нуля")
    if args.interval is not None and args.interval <= 0:
        raise SystemExit("--interval должен быть больше нуля")
    for a, b in ranges:
        if b <= a:
            raise SystemExit(f"--range {a:g}-{b:g}: конец не позже начала")

    # у каждого выходного файла свой каталог кадров. Иначе проба на минуте
    # материала сносит нарезку полного прогона прямо у него из-под ног —
    # ровно так упал прогон, шедший параллельно пробе
    safe_prefix = re.sub(r"[^A-Za-z0-9_.-]", "_", args.out_prefix)
    frames_dir_name = ("frames_desc" if args.out_prefix == "description"
                       else f"frames_desc_{safe_prefix}")

    # шаг нарезки известен до резки, и проверка совместимости --redo-bad
    # обязана отработать раньше, чем каталог кадров будет тронут: иначе она
    # сносит 3878 кадров и только потом сообщает, что чинить нечего
    if args.frames_dir or args.times:
        frame_step = None
    elif args.settled:
        frame_step = args.settled
    else:
        frame_step = args.interval

    meta_probe = {"window": args.window, "stride": args.stride,
                  "frame_step": frame_step, "ranges": [list(r) for r in ranges]}
    prev_records: list[dict] | None = None
    if args.redo_bad:
        prev_path = bdir / f"{args.out_prefix}.jsonl"
        if not prev_path.exists():
            raise SystemExit(f"--redo-bad: нет {prev_path}, нечего чинить")
        prev_records = [json.loads(l)
                        for l in prev_path.read_text(encoding="utf-8").splitlines()]
        prev_meta = next((r["meta"] for r in prev_records if "meta" in r), {})
        for key in ("window", "stride", "frame_step", "ranges"):
            if prev_meta.get(key) != meta_probe.get(key):
                raise SystemExit(
                    f"--redo-bad: прошлый прогон делался с {key}={prev_meta.get(key)}, "
                    f"сейчас {meta_probe.get(key)} — нарезка другая, чинить нечего")

    def in_ranges(t: float) -> bool:
        return not ranges or any(a <= t < b for a, b in ranges)

    # --- кадры
    if args.frames_dir:
        frames = frames_from_dir(Path(args.frames_dir).resolve())
        frame_step = None
        if not frames:
            raise SystemExit(f"{args.frames_dir}: кадров не нашлось")
    elif args.settled or args.times:
        if not mp4.exists():
            raise SystemExit(f"нет {mp4}, а кадры надо резать")
        if args.settled:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import detect_scenes
            print(f"[кадры] выбираю самый спокойный кадр в каждом слоте {args.settled} с")
            lo = min((a for a, _ in ranges), default=0.0)
            hi = max((b for _, b in ranges), default=0.0)
            times = [c["t"] for c in detect_scenes.detect(
                mp4, every=args.settled, start=lo, end=hi)]
        else:
            times = times_from_file(Path(args.times))
        times = [t for t in times if in_ranges(t)]
        frames = cut_at_times(mp4, bdir / frames_dir_name, times,
                              workers=args.workers, force=args.force_frames)
    else:
        if not mp4.exists():
            raise SystemExit(f"нет {mp4}")
        frames = cut_uniform(mp4, bdir / frames_dir_name, args.interval, duration,
                             force=args.force_frames)

    if ranges:
        frames = [(t, p) for t, p in frames if in_ranges(t)]
        if not frames:
            raise SystemExit("после --range не осталось ни одного кадра")

    if args.stride <= 0:
        raise SystemExit("--stride должен быть больше нуля, иначе окна не двигаются")
    if args.stride > args.window:
        print(f"[warn] --stride {args.stride} больше --window {args.window}: между "
              f"фрагментами останутся неописанные дыры", file=sys.stderr)
    chunks = build_chunks(frames, args.window, args.stride)
    if args.limit_chunks:
        chunks = chunks[:args.limit_chunks]

    print(f"[план] кадров {len(frames)}, фрагментов {len(chunks)}, окно {args.window} с "
          f"со сдвигом {args.stride} с, потоков {args.workers}, модель {args.model}")

    # В окружении прописан HTTP_PROXY, и без этого запрос к своему же серверу
    # уходит наружу и возвращается 502 Bad Gateway. Симптом выглядит как «сервер
    # не поднялся», хотя он поднялся.
    host = re.sub(r"^https?://", "", args.api_base).split(":")[0].split("/")[0]
    current = os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "")
    parts = [p for p in current.split(",") if p]
    for extra in ("localhost", "127.0.0.1", host):
        if extra and extra not in parts:
            parts.append(extra)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = ",".join(parts)
    if host not in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        # сервер на соседней машине — тот же 502, только чинить его руками
        # было бы некому: имя хоста прокси не знает
        print(f"[сеть] {host} добавлен в NO_PROXY. Если до сервера надо идти "
              f"именно через прокси, задай NO_PROXY сам", file=sys.stderr)

    from openai import OpenAI

    client = OpenAI(api_key="EMPTY", base_url=args.api_base, timeout=1800, max_retries=0)
    cues = bundle.get("transcript", []) if args.with_transcript else []

    started = time.time()
    records: list[dict] = []
    done = 0

    kept: dict[int, dict] = {}
    if prev_records is not None:
        for rec in prev_records:
            if "chunk_index" not in rec:
                continue
            bad = rec.get("error") or rec.get("degenerate") or rec.get("truncated")
            if not bad:
                kept[rec["chunk_index"]] = rec
        by_index = {ch["chunk_index"]: ch for ch in chunks}
        for i, rec in kept.items():
            ch = by_index.get(i)
            # chunk_index — просто порядковый номер, он совпадёт и у чужой
            # нарезки; отличить её можно только по границам окна
            if ch is None:
                raise SystemExit(
                    f"--redo-bad: фрагмента {i} в новой нарезке нет — "
                    f"кадры изменились, чинить нечего")
            if (abs(ch["t_start"] - rec["t_start"]) > 1e-6
                    or abs(ch["t_end"] - rec["t_end"]) > 1e-6):
                raise SystemExit(
                    f"--redo-bad: фрагмент {i} в файле — "
                    f"[{rec['t_start']}, {rec['t_end']}], в новой нарезке — "
                    f"[{ch['t_start']}, {ch['t_end']}]: чинить нечего")
        chunks = [ch for ch in chunks if ch["chunk_index"] not in kept]
        records.extend(kept.values())
        print(f"[redo] беру готовыми {len(kept)} фрагментов, перезапрашиваю {len(chunks)}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(describe_chunk, client, args.model, ch, cues,
                        args.max_tokens, args.temperature, args.upscale): ch
            for ch in chunks
        }
        for fut in as_completed(futures):
            records.append(fut.result())
            done += 1
            if done % 5 == 0 or done == len(chunks):
                elapsed = time.time() - started
                print(f"  {done}/{len(chunks)} чанков, {elapsed:.0f} с, "
                      f"осталось ~{elapsed / done * (len(chunks) - done):.0f} с", flush=True)
    records.sort(key=lambda r: r["chunk_index"])
    elapsed = time.time() - started

    # Знаменатель — ЗАПРОШЕННЫЙ участок, а не собранные окна. Если считать
    # по окнам, то потерянные кадры выпадают вместе со своими секундами
    # из обеих частей дроби, и проверка радостно рапортует «дыр нет».
    covered = {e["t"] for r in records for e in r.get("events", []) if e.get("t") is not None}
    want_seconds: set[int] = set()
    for a, b in (ranges or [(0.0, duration)]):
        want_seconds.update(range(int(a), int(min(b, duration))))
    missing = sorted(want_seconds - covered)
    if missing:
        print(f"[warn] без событий осталось {len(missing)} секунд из "
              f"{len(want_seconds)}, первые: {missing[:10]}", file=sys.stderr)

    meta = {
        "video_id": vid,
        "title": bundle.get("title", vid),
        "duration": duration,
        "chapters": bundle.get("chapters", []),
        "model": args.model,
        "api_base": args.api_base,
        "window": args.window,
        "stride": args.stride,
        # перекрытие с каждым соседом, а не суммарное: границы полуоткрыты
        "overlap": round(max(0.0, args.window - args.stride), 2),
        "frame_step": frame_step,
        "upscale": args.upscale,
        "with_transcript": args.with_transcript,
        "temperature": args.temperature,
        "ranges": [list(r) for r in ranges],
        "n_chunks": len(records),
        "n_frames": len(frames),
        "n_errors": sum(1 for r in records if r.get("error")),
        "n_degenerate": sum(1 for r in records if r.get("degenerate")),
        "n_truncated": sum(1 for r in records if r.get("truncated")),
        # контракт «описание посекундное» до сих пор проверялся только руками:
        # фрагмент с ошибкой отдаёт events=[], и его секунды исчезали молча
        "seconds_expected": len(want_seconds),
        "seconds_covered": len(covered),
        "elapsed_s": round(elapsed, 1),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    jsonl = bdir / f"{args.out_prefix}.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    md = bdir / f"{args.out_prefix}.md"
    write_markdown(md, meta, records)

    print(f"\nготово за {elapsed:.0f} с ({elapsed / 60:.1f} мин), ошибок {meta['n_errors']}, "
          f"вырожденных ответов {meta['n_degenerate']}")
    print(f"  {jsonl}")
    print(f"  {md}")


if __name__ == "__main__":
    main()

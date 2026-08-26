#!/usr/bin/env python3
"""Валидирует файлы разметки: JSON Schema + семантические проверки.

    python tools/validate_samples.py data/annotations/*.jsonl

Код возврата 1 при любой ошибке; при нуле ошибок печатает разбивку покрытия.

Как читать этот файл
--------------------
Тестового фреймворка в проекте нет, и роль тестов играет сам валидатор. Чтобы
это не превращалось в «правило есть, но давно ничего не проверяет», каждое
семантическое правило снабжено паспортом из трёх строк:

    # S-NN · чеклист X.Y — что проверяется.
    #   Ломается: что проходит незамеченным, если правило убрать.
    #   Проверить: <мутация корректного сэмпла> -> <ожидаемая подстрока>.

`S-NN` — устойчивый идентификатор правила, на него можно ссылаться в ревью
и коммитах. `чеклист X.Y` — пункт docs/annotation_checklist.md, который это
правило закрывает; там же написано, почему пункт вообще существует.

Строка «Проверить» задаёт воспроизводимый негативный тест: взять корректный
файл разметки, применить описанную мутацию, прогнать валидатор, убедиться,
что в выводе есть ожидаемая подстрока. Шаблон:

    import json
    S = [json.loads(l) for l in open("data/annotations/<id>.jsonl")]
    S[0]["triggers"][0]["t_ideal"] = S[0]["triggers"][0]["t_end"]   # мутация
    open("/tmp/neg.jsonl", "w").write("\n".join(json.dumps(x, ensure_ascii=False) for x in S))
    # python tools/validate_samples.py /tmp/neg.jsonl  ->  "t_ideal вне окна"

Проверки формы (обязательность полей, типы, enum, additionalProperties) сюда
не входят: их делает JSON-схема, и отдельного паспорта они не имеют.
"""

import argparse
import functools
import json
import re
import sys
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "sample.schema.json").read_text(encoding="utf-8"))


def evidence_span(t: dict) -> tuple[float, float]:
    # где в видео лежит ПОСЛЕДНЕЕ доказательство, нужное для ответа.
    # Поле обязательно: подставлять вместо него окно ответа нельзя — тогда
    # ось temporal_rel выводилась бы из окна, то есть из того, из чего её
    # выводить и запрещено, и post-вопрос стал бы неотличим от at.
    span = t["evidence_span"]
    return (span[0], span[1])


def derive_temporal_rel(s: dict) -> str:
    # ось B определяется положением question_time относительно ДОКАЗАТЕЛЬСТВА,
    # а не относительно окна ответа: у post-вопроса окно ответа тоже начинается
    # в момент выдачи вопроса, и по окну его не отличить от at.
    qt = s["question_time"]
    req = [t for t in s["triggers"] if t["required"]]
    spans = [evidence_span(t) for t in req]
    # По краям берём минимум и максимум, а не req[0] и req[-1]: триггеры
    # упорядочены по t_start (S-09), а доказательства по нему не обязаны идти
    # монотонно — визуальное доказательство второго триггера может появиться
    # раньше речевого доказательства первого. На позиционных краях сэмпл
    # с question_time между ними получал «pre» вместо «at».
    first_a = min(a for a, _ in spans)
    last_b = max(b for _, b in spans)
    if qt < first_a:
        return "pre"
    if qt >= last_b:
        return "post"
    return "at"


# Пол ширины окна ответа. Пять секунд — не измеренная величина, а первое
# осознанное ограничение: точное значение выведем из замера сквозной задержки
# одной модели, пока же граница нужна, чтобы узкие окна не появлялись молча.
MIN_WINDOW = 5.0

BUNDLES = ROOT / "data" / "bundles"


# Видео, для которых бандла на диске нет. Без бандла молча вырождаются в no-op
# сразу три правила — S-01 (сверка длительности), S-21 и S-33 (обе смотрят
# в транскрипт), — и опечатка в youtube_id отключает как раз ту проверку, которая
# поймала бы неверный duration, а duration — граница для всех правил «за пределами
# видео». Собираем такие id и говорим о них вслух в конце прогона.
NO_BUNDLE: set[str] = set()

BUNDLE_DEPENDENT = "S-01, S-21, S-33"


@functools.lru_cache(maxsize=None)
def bundle(video_id: str) -> dict | None:
    f = BUNDLES / video_id / "bundle.json"
    if not f.exists():
        NO_BUNDLE.add(video_id)
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def bundle_duration(video_id: str) -> float | None:
    b = bundle(video_id)
    return float(b["duration"]) if b else None


def check_evidence(s: dict, dur: float) -> list[str]:
    """Ссылки на источник ground truth: указывают ли они на существующие моменты.

    Проверка стала возможной после перехода provenance.evidence на структурный
    формат: по свободной прозе регулярное выражение видело только записи вида
    «кадр t=<число>».
    """
    errs = []
    b = bundle(s["video"]["youtube_id"])
    cues = b["transcript"] if b else []
    starts = [c["start"] for c in cues]
    ends = [c["end"] for c in cues]

    for i, e in enumerate(s["provenance"]["evidence"]):
        tag = f"provenance.evidence[{i}]"
        if e["type"] == "frame":
            # S-19 · чеклист 8.1 — кадр существует.
            #   Ломается: ссылка на несуществующий момент выглядит как проверяемая,
            #   но перепроверить по ней ничего нельзя.
            #   Проверить: evidence[0]["t"] := 99999 -> "за пределами видео".
            if e["t"] > dur:
                errs.append(f"{tag}: кадр t={e['t']} за пределами видео")
        elif e["type"] == "speech":
            # S-20 · чеклист 8.1 — речевой интервал осмыслен и лежит внутри ролика.
            #   Проверить: t_end := t_start -> "пуст или вывернут";
            #   t_end := duration + 10 -> "выходит за длительность".
            if not (e["t_start"] < e["t_end"]):
                errs.append(f"{tag}: речевой интервал пуст или вывернут")
                continue
            if e["t_end"] > dur:
                errs.append(f"{tag}: речевой интервал выходит за длительность")
            if not cues:
                continue
            # S-21 · чеклист 8.1 — интервал совпадает с границами реплик.
            #   Обе границы обязаны в точности лежать на границах субтитров:
            #   начало — на начале какой-то реплики, конец — на конце какой-то.
            #   Ломается: ссылка, обрывающаяся посреди фразы, не проверяется глазами —
            #   открыв транскрипт на этом месте, читатель видит обрывок, а не то,
            #   на что ссылались.
            #   Правило намеренно асимметрично по цене ошибки: захватить лишнюю
            #   соседнюю фразу не страшно (ссылка остаётся читаемой и проверяемой),
            #   а обрезать нужную — страшно. Поэтому выравнивать интервал следует
            #   наружу, к концу последней задетой реплики.
            #   Допуск ±0.5 с — на округление таймкодов при записи, не на смысл.
            #   Проверить: t_start := середина реплики -> "не совпадает с началом
            #   ни одной реплики"; t_end := середина реплики -> "не совпадает
            #   с концом ни одной реплики".
            if not any(abs(e["t_start"] - x) <= 0.5 for x in starts):
                errs.append(f"{tag}: начало {e['t_start']} не совпадает с началом "
                            f"ни одной реплики транскрипта")
            if not any(abs(e["t_end"] - x) <= 0.5 for x in ends):
                errs.append(f"{tag}: конец {e['t_end']} не совпадает с концом "
                            f"ни одной реплики транскрипта")
    return errs


# Предупреждения — не ошибки: они не роняют прогон и не мешают продвинуть сэмпл
# в validated. Нужны там, где нарушение правдоподобно, но законные исключения
# существуют, и превращать его в блокировку значило бы заставить разметчика
# подгонять числа под правило.
WARNINGS: list[tuple[str, str]] = []


def warn(sid: str, msg: str) -> None:
    WARNINGS.append((sid, msg))


def semantic_checks(s: dict) -> list[str]:
    """Правила, которых не выразить схемой: они связывают поля друг с другом,
    с длительностью видео и с транскриптом. Паспорт каждого правила — см. модульный
    docstring."""
    errs = []
    dur = s["video"]["duration"]

    # S-01 · чеклист 1.6 — длительность в сэмпле совпадает с фактической.
    #   Ломается: скопированный сэмпл с чужой длительностью делает бессмысленными
    #   все проверки «за пределами видео» — они сравнивают с неверной границей.
    #   Проверить: video.duration := 100.0 -> "расходится с bundle.json".
    bd = bundle_duration(s["video"]["youtube_id"])
    if bd is not None and abs(bd - dur) > 1.0:
        errs.append(f"video.duration={dur} расходится с bundle.json ({bd}) более чем на секунду")
    if bd is None and s["validation"]["status"] == "validated":
        errs.append(f"нет data/bundles/{s['video']['youtube_id']}/bundle.json, поэтому правила "
                    f"{BUNDLE_DEPENDENT} на этом сэмпле не выполнялись — "
                    f"статус validated при непроверенных правилах не ставится")
    trigs = s["triggers"]

    # S-02 · чеклист 1.3 — есть хотя бы один обязательный триггер.
    #   Ломается: сэмпл, на который нельзя ответить верно ни в один момент;
    #   вдобавок derive_temporal_rel падает на пустом списке.
    #   Проверить: у всех триггеров required := false -> "нет ни одного обязательного".
    if not any(x["required"] for x in trigs):
        errs.append("нет ни одного обязательного триггера")
        return errs

    # S-03 · чеклист 1.3 — вопрос выдан внутри ролика.
    #   Ломается: сэмпл, который в стриминге не будет задан никогда.
    #   Проверить: question_time := duration + 10 -> "больше длительности видео".
    if s["question_time"] > dur:
        errs.append(f"question_time={s['question_time']} больше длительности видео {dur}")

    # S-04 · чеклист 1.5 — у многотриггерного сэмпла есть чем наказать спам.
    #   Ломается: стратегия «говорить постоянно» набирает полный балл, потому что
    #   ложным срабатыванием оказаться негде.
    #   Проверить: удалить distractor_windows у сэмпла с >1 триггером
    #   -> "многотриггерный сэмпл без distractor_windows".
    if len(trigs) > 1 and not s.get("distractor_windows"):
        errs.append("многотриггерный сэмпл без distractor_windows: спам-стратегия ничем не наказана "
                    "(план §3.1 п.3)")

    # S-05 · чеклист 7.1 — ось pre/at/post выводится, а не проставляется рукой.
    #   Ломается: метка перестаёт отражать положение question_time относительно
    #   доказательства; чаще всего post-сэмпл живёт с меткой at и наоборот.
    #   Проверить: у post-сэмпла evidence_span := [t_start, t_end]
    #   -> "должно быть at".
    want = derive_temporal_rel(s)
    if s["temporal_rel"] != want:
        errs.append(f"temporal_rel={s['temporal_rel']}, но по question_time="
                    f"{s['question_time']} и evidence_span должно быть {want}")

    for t in trigs:
        a, b = evidence_span(t)
        # S-06 · чеклист 1.9 — evidence_span непуст и лежит внутри ролика.
        #   Ломается: ось выводится из бессмысленного интервала, причём молча.
        #   Проверить: evidence_span := [500, 100] -> "пустой или вывернут";
        #   evidence_span := [0, duration + 10] -> "выходит за длительность".
        if not (a < b):
            errs.append(f"trigger[{t['idx']}]: evidence_span пустой или вывернут")
        if b > dur:
            errs.append(f"trigger[{t['idx']}]: evidence_span выходит за длительность")
        # S-07 · чеклист 1.1 — доказательство появляется до закрытия окна ответа.
        #   Ломается: GT недостижим — модель обязана ответить раньше, чем в ролике
        #   появится то, из чего ответ следует.
        #   Проверить: evidence_span := [t_end + 1, t_end + 5] -> "GT недостижим".
        if a >= t["t_end"]:
            errs.append(f"trigger[{t['idx']}]: доказательство появляется после закрытия окна "
                        f"ответа — GT недостижим")
        # S-35 · чеклист 1.1 — последнее доказательство появляется до закрытия окна.
        #   S-07 сторожил только левый край, правый не сторожил никто: сэмпл
        #   с evidence_span [314, 1500] при окне [315, 382] проходил молча.
        #   Ломается: по определению поля (1.9) там лежит ПОСЛЕДНЕЕ доказательство,
        #   нужное для ответа; если оно появляется после t_end, эталон внутри окна
        #   недостижим — правильно рассуждающая модель наказана по построению.
        #   Вдобавок derive_temporal_rel читает именно правый край, так что ось
        #   выводится из момента, до которого отвечать уже поздно.
        #   Проверить: evidence_span := [t_start, t_end + 100] -> "последнее
        #   доказательство появляется после закрытия окна".
        if b > t["t_end"]:
            errs.append(f"trigger[{t['idx']}]: последнее доказательство появляется в {b}, "
                        f"а окно закрывается в {t['t_end']} — эталон внутри окна недостижим")

        # S-29 · чеклист 1.1 — окно не открывается раньше доказательства.
        #   Ломается: между t_start и появлением доказательства лежит зона, где
        #   ответ засчитывается, а отвечать ещё не из чего, — то есть засчитывается
        #   угадывание. Задержка модели меряется от t_start, поэтому левая граница
        #   и есть точка отсчёта: она обязана совпадать с моментом, когда мгновенно
        #   рассуждающая модель уже могла бы ответить.
        #   Раньше сравнивали с t_ideal, но t_ideal теперь выставляется механически
        #   (t_start + 1) и ничего не проверяет.
        #   Проверить: evidence_span := [t_start + 5, t_end - 1]
        #   -> "окно открывается раньше доказательства".
        if t["t_start"] < a:
            errs.append(f"trigger[{t['idx']}]: окно открывается в {t['t_start']}, "
                        f"а доказательство появляется в {a} — в зазоре засчитывается "
                        f"угадывание")

    # S-36 · чеклист 1.11 — окно не короче пяти секунд.
    #   Ломается: модель в стриминге тратит на ответ секунды, и на слишком узком
    #   окне PAUC меряет скорость генерации, а не понимание. Ширину окна задаёт
    #   содержание, но у содержания нет причин совпадать с временем ответа —
    #   поэтому нужен пол, ниже которого сэмпл не берётся.
    #   Проверить: t_end := t_start + 3 -> "окно шириной 3.0 с".
    for t in trigs:
        width = t["t_end"] - t["t_start"]
        if width < MIN_WINDOW:
            errs.append(f"trigger[{t['idx']}]: окно шириной {width:.1f} с при минимуме "
                        f"{MIN_WINDOW:.0f} с — на таком окне метрика меряет скорость "
                        f"генерации, а не понимание")

    # S-08 · чеклист 1.3 — idx идут подряд с нуля.
    #   Ломается: depends_on ссылается не на тот триггер, на который выглядит.
    #   Проверить: idx второго триггера := 5 -> "должны идти подряд с 0".
    if [t["idx"] for t in trigs] != list(range(len(trigs))):
        errs.append("idx триггеров должны идти подряд с 0")

    # S-09 · чеклист 1.3 — порядок idx совпадает с хронологическим.
    #   Ломается: derive_temporal_rel берёт доказательства первого и последнего
    #   обязательных триггеров по месту в списке, и при перестановке ось выводится
    #   не из тех окон. Раньше нарушение всплывало под чужим именем — как
    #   «окно пересекается с предыдущим».
    #   Проверить: поменять местами содержимое триггеров 1 и 2 (не трогая idx)
    #   -> "идут не по возрастанию t_start".
    starts = [t["t_start"] for t in trigs]
    if starts != sorted(starts):
        errs.append(f"триггеры идут не по возрастанию t_start: {starts}")

    prev_end = -1.0
    for t in trigs:
        tag = f"trigger[{t['idx']}]"
        # S-10 · чеклист 1.1 — геометрия окна ответа.
        #   Ломается: окно нулевой длины или вывернутое; t_ideal вне окна делает
        #   недостижимой вершину метрики; окно за длительностью недостижимо вовсе.
        #   Проверить: t_end := t_start -> "t_start >= t_end";
        #   t_ideal := t_end -> "t_ideal вне окна";
        #   t_end := duration + 10 -> "окно выходит за длительность видео".
        if not (t["t_start"] < t["t_end"]):
            errs.append(f"{tag}: t_start >= t_end")
        if not (t["t_start"] <= t["t_ideal"] < t["t_end"]):
            errs.append(f"{tag}: t_ideal вне окна")
        if t["t_end"] > dur:
            errs.append(f"{tag}: окно выходит за длительность видео")
        # S-11 · чеклист 1.1 — окна одного сэмпла не пересекаются.
        #   Ломается: один ответ попадает сразу в два окна и судится по двум разным
        #   рубрикам; метрика перестаёт быть определённой.
        #   Проверить: t_start второго триггера := t_start первого
        #   -> "окно пересекается с предыдущим".
        if t["t_start"] < prev_end:
            errs.append(f"{tag}: окно пересекается с предыдущим")
        # S-12 · чеклист 1.1 — окно не начинается раньше выдачи вопроса.
        #   Ломается: начало окна недостижимо — модель ещё не знает, что спросили,
        #   а по метрике уже обязана отвечать.
        #   Проверить: question_time := t_start + 5 -> "начинается до выдачи вопроса".
        if t["t_start"] < s["question_time"]:
            errs.append(f"{tag}: окно ответа начинается до выдачи вопроса — его начало недостижимо")
        prev_end = t["t_end"]
        # S-13 · чеклист 1.4 — depends_on указывает строго назад.
        #   Ломается: цепочка зависимостей с циклом или ссылкой вперёд, по которой
        #   нельзя посчитать долю верно выстроенных цепочек.
        #   Проверить: depends_on := [idx] у любого триггера -> "не раньше самого триггера".
        for dep in t.get("depends_on", []):
            if dep >= t["idx"]:
                errs.append(f"{tag}: depends_on={dep} не раньше самого триггера")

    for i, d in enumerate(s.get("distractor_windows", [])):
        # S-14 · чеклист 1.2 — геометрия окна-приманки.
        #   Ломается: приманка нулевой длины или за пределами ролика ничего не ловит,
        #   но выглядит в разметке как защита от спама.
        #   Проверить: t_end := t_start -> "t_start >= t_end";
        #   t_end := duration + 10 -> "окно выходит за длительность видео".
        if not (d["t_start"] < d["t_end"]):
            errs.append(f"distractor[{i}]: t_start >= t_end")
        if d["t_end"] > dur:
            errs.append(f"distractor[{i}]: окно выходит за длительность видео")
        # S-15 · чеклист 1.2 — приманка не лежит целиком до выдачи вопроса.
        #   Ломается: ловить нечего — модель ещё не знает вопроса и молчит по любой
        #   стратегии, а разметка засчитывает это как защиту от спама.
        #   Проверить: question_time := t_end приманки + 1 -> "целиком до выдачи вопроса".
        if d["t_end"] <= s["question_time"]:
            errs.append(f"distractor[{i}] целиком до выдачи вопроса — ложным срабатыванием "
                        f"там быть нечему")
        # S-16 · чеклист 1.2 — приманка не пересекается с триггером.
        #   Ломается: один и тот же ответ одновременно верный и ложный.
        #   Проверить: t_start приманки := t_start первого триггера
        #   -> "пересекается с trigger".
        for t in trigs:
            if d["t_start"] < t["t_end"] and t["t_start"] < d["t_end"]:
                errs.append(f"distractor[{i}] пересекается с trigger[{t['idx']}]")

    st = s["validation"]["status"]
    vis = s["validation"].get("visiononly_solved")
    solv = s["validation"].get("solvable")

    # S-17 · чеклист 7.2 — audio_dependency пуст, пока замер не завершён.
    #   Ломается: метка, влияющая на выводы о модальностях, ставится мнением
    #   разметчика вместо замера — ровно та ошибка, за которую мы критикуем чужие
    #   работы. Мнение живёт отдельно, в audio_dependency_claim.
    #
    #   «Замер завершён» — это наличие ОБОИХ флагов, из которых метка выводится
    #   по 4.5, а не статус сэмпла. Прежняя редакция требовала status=validated
    #   и тем запрещала метку у rejected навсегда: сэмпл, решённый вслепую,
    #   в validated не пройдёт по S-18 никогда, значит и замерить у него
    #   зависимость от звука было нельзя. А замерять надо: отклонённые сэмплы —
    #   материал для бейзлайнов-пустышек и для счёта контаминации, они уходят
    #   из набора заданий, но не из измерений.
    #   Проверить: audio_dependency := "required" при пустых зондах
    #   -> "зонды ещё не отвечены".
    if s["audio_dependency"] is not None and (vis is None or solv is None):
        errs.append(f"audio_dependency заполнен, а зонды, из которых он выводится, "
                    f"не отвечены (visiononly_solved={vis}, solvable={solv}): "
                    f"метка ставится только замером")

    # S-18 · чеклист 7.2 — условия продвижения в validated.
    #   Ломается: сэмпл объявляется проверенным без ответов зондов, на которых
    #   держится вся его ценность; сэмпл, решаемый без видео, попадает в набор
    #   и меряет знание предмета вместо стриминга; сэмпл, не решаемый вовсе,
    #   наказывает любую модель одинаково.
    #   Проверить: status := "validated" при draft-полях -> "не отвечены зонды"
    #   и "при незамеренном audio_dependency"; затем blind_solved := true
    #   -> "несовместим с validated"; solvable := false -> "вопрос не решается".
    if st == "validated":
        if s["audio_dependency"] is None:
            errs.append("status=validated при незамеренном audio_dependency")
        missing = [k for k in ("solvable", "blind_solved", "textonly_solved",
                               "visiononly_solved", "frozenframe_solved")
                   if s["validation"].get(k) is None]
        if missing:
            errs.append(f"status=validated, но не отвечены зонды: {', '.join(missing)}")
        if s["validation"].get("blind_solved"):
            errs.append("blind_solved=true несовместим с validated: сэмпл решается без видео "
                        "-> status должен быть rejected")
        if s["validation"].get("solvable") is False:
            errs.append("solvable=false несовместим с validated: вопрос не решается "
                        "и по полному материалу -> status должен быть rejected")

    # S-25 · чеклист 7.6 — audio_dependency совпадает с выводимым из зондов.
    #   Метка не ставится мнением: она вычисляется из ответа vision-зонда.
    #   Решился по одним кадрам -> звук не нужен; не решился, но вопрос решаем
    #   по совокупности -> звук обязателен. Во всех прочих сочетаниях (зонды ещё
    #   не отвечены) метка обязана быть null, и это ловит S-17 вместе с 7.2.
    #   Ломается: расхождение метки с флагами, из которых она выведена, — то есть
    #   ровно та подмена замера мнением, ради запрета которой поле и разделено
    #   на audio_dependency и audio_dependency_claim.
    #   Проверить: visiononly_solved := true, audio_dependency := "required"
    #   -> "выводится unnecessary".
    if vis is True:
        derived = "unnecessary"
    elif vis is False and solv is True:
        derived = "required"
    else:
        derived = None
    # Совпадения требуем в двух случаях: метка уже записана (тогда она обязана
    # совпадать с выводимой при любом статусе — иначе rejected становится лазейкой
    # для метки, поставленной мнением) и статус validated (там метка обязана быть).
    # Промежуточное состояние «оба флага записаны, метка ещё не выведена» остаётся
    # законным у draft и rejected — иначе сэмпл заклинивало бы между S-17 и S-25.
    label = s["audio_dependency"]
    if (label is not None or st == "validated") and label != derived:
        errs.append(f"audio_dependency={label!r}, но по зондам "
                    f"(visiononly_solved={vis}, solvable={solv}) выводится {derived!r}")

    # S-27 · чеклист 7.7 — solvable согласован с одномодальными зондами.
    #   Флаг ставит координатор: успех любого одномодального зонда уже доказывает
    #   решаемость, и зонд 4.7 тогда не запускается вовсе. Без этого правила
    #   solvable оставался пустым в самом частом случае, а S-18 не пускал сэмпл
    #   в validated — то есть проверка блокировала сама себя.
    #   Ломается: сэмпл, решённый текстовым зондом, объявляется нерешаемым и уходит
    #   в CRITICAL_FAIL; либо наоборот, solvable=true появляется там, где ни один
    #   зонд не ответил.
    #   Проверить: textonly_solved := true, solvable := false
    #   -> "solvable=false, но зонд";
    #   frozenframe_solved := true, visiononly_solved := false
    #   -> "решился по одному кадру".
    v = s["validation"]
    solved_by = [k for k in ("blind_solved", "textonly_solved", "visiononly_solved",
                             "frozenframe_solved") if v.get(k) is True]
    if solved_by and v.get("solvable") is False:
        errs.append(f"solvable=false, но зонд {solved_by[0]} ответил: успех любого зонда "
                    f"уже доказывает решаемость")
    # Один кадр — подмножество кадров, поэтому frozen-frame сильнее vision.
    if v.get("frozenframe_solved") is True and v.get("visiononly_solved") is False:
        errs.append("frozenframe_solved=true при visiononly_solved=false: решился "
                    "по одному кадру, но не по всем кадрам — зонды противоречат друг другу")

    # S-28 · чеклист 1.10 — триггер не держится на одном sound.
    #   Ломается: единственная модальность триггера — звук, а звукового зонда нет:
    #   probe_text читает текст речи, probe_vision смотрит кадры. Флаг
    #   visiononly_solved у такого триггера ничего не измеряет, а из него выводится
    #   audio_dependency — то есть метка получается из несостоявшегося замера.
    #   Проверить: trigger_modality := ["sound"] -> "нет зонда, который это проверит".
    for t in trigs:
        if t["trigger_modality"] == ["sound"]:
            errs.append(f"trigger[{t['idx']}]: единственная модальность sound — "
                        f"нет зонда, который это проверит; добавьте speech или visual")

    # S-30 · чеклист 7.4 — обязательный триггер не зависит от опционального.
    #   Ломается: модель, законно промолчавшая в опциональном окне (рубрика там
    #   прямо разрешает молчание), автоматически рвёт цепочку в знаменателе
    #   цепочечной метрики — то есть наказывается за поведение, которое разметка
    #   объявила правильным.
    #   Проверить: у обязательного триггера depends_on на required: false
    #   -> "зависит от опционального".
    opt = {t["idx"] for t in trigs if not t["required"]}
    for t in trigs:
        if not t["required"]:
            continue
        bad = sorted(opt & set(t.get("depends_on") or []))
        if bad:
            errs.append(f"trigger[{t['idx']}]: обязательный триггер зависит от "
                        f"опционального {bad} — молчание там законно, а цепочка рвётся")

    # S-31 · чеклист 1.2 — приманки не пересекаются между собой.
    #   Ломается: один преждевременный ответ засчитывается как два ложных
    #   срабатывания — наказание непропорционально поступку.
    #   Проверить: добавить приманку, накрывающую две соседние
    #   -> "приманки пересекаются".
    ds = sorted(s.get("distractor_windows", []), key=lambda d: d["t_start"])
    for i in range(1, len(ds)):
        if ds[i]["t_start"] < ds[i - 1]["t_end"]:
            errs.append(f"приманки пересекаются: [{ds[i-1]['t_start']}, {ds[i-1]['t_end']}] "
                        f"и [{ds[i]['t_start']}, {ds[i]['t_end']}]")

    # S-32 · чеклист 8.1 — среди ссылок есть хотя бы одна с таймкодом.
    #   Ломается: provenance объявлен защитой от выдуманного эталона, но запись
    #   типа other ничем не проверяется — заменив ею все ссылки, можно записать
    #   «я так решил» и пройти валидацию.
    #   Проверить: evidence := [{"type": "other", "explanation": "я так решил"}]
    #   -> "ни одной ссылки с таймкодом".
    ev = s["provenance"]["evidence"]
    if not any(e["type"] in ("frame", "speech") for e in ev):
        errs.append("ни одной ссылки с таймкодом: provenance из одних other "
                    "не даёт перепроверить эталон")

    # S-37 · чеклист 2.5 — приманка не начинается ровно на границе окна.
    #   Ломается: ответ, верный по существу, но выданный на секунду позже
    #   закрытия окна, попадает в приманку и штрафуется дважды — как пропуск
    #   и как ложное срабатывание. Разница между «вовремя» и «ловушка»
    #   становится разницей в скорости генерации.
    #   Нулевой зазор — ошибка, ненулевой, но короткий — предупреждение:
    #   бывает, что приманка и должна начинаться близко, и тогда решает ревьюер.
    #   Проверить: приманка с t_start := t_end триггера -> "начинается ровно
    #   на границе окна".
    for i, d in enumerate(s.get("distractor_windows", [])):
        for tr in trigs:
            if d["t_start"] == tr["t_end"]:
                errs.append(f"приманка[{i}] начинается ровно на границе окна "
                            f"trigger[{tr['idx']}] ({tr['t_end']}): верный, но поздний "
                            f"на долю секунды ответ попадёт в неё и будет наказан дважды")

    for i, d in enumerate(s.get("distractor_windows", [])):
        for tr in trigs:
            gap = d["t_start"] - tr["t_end"]
            if 0 < gap < 10:
                warn(s["id"], f"приманка[{i}] начинается через {gap:.1f} с после окна "
                              f"trigger[{tr['idx']}]: правильный, но поздний ответ попадёт "
                              f"в неё — это гонка на скорость генерации (чеклист 2.5)")

    # S-33 · чеклист 2.1 — общая граница двух окон не режет реплику пополам.
    #   Ломается: ответ, начатый на этой фразе, попадает в чужое окно и судится
    #   по чужой рубрике — модель наказывается за то, что заговорила там, где
    #   разметка сама провела границу посреди мысли.
    #   Проверить: сдвинуть общую границу двух соседних окон внутрь реплики
    #   -> "общая граница ... режет реплику".
    b = bundle(s["video"]["youtube_id"])
    if b:
        ends = {tr["t_end"] for tr in trigs}
        for tr in trigs:
            if tr["t_start"] not in ends:
                continue
            for c in b["transcript"]:
                if c["start"] < tr["t_start"] < c["end"]:
                    errs.append(f"общая граница окон {tr['t_start']} режет реплику "
                                f"[{c['start']:.1f}, {c['end']:.1f}]: ответ на этой фразе "
                                f"попадёт в чужое окно и в чужую рубрику")
                    break

    errs += check_evidence(s, dur)

    # Только обязательные: один опциональный визуальный триггер добавлял "visual"
    # в общее множество и молча снимал претензию с целиком речевого сэмпла.
    req_trigs = [t for t in trigs if t["required"]] or trigs
    mods = {m for t in req_trigs for m in t["trigger_modality"]}
    claim = s.get("audio_dependency_claim")
    # S-22 · чеклист 1.7 — заявленная зависимость от звука не противоречит модальностям.
    #   Ломается: сэмпл заявляет «звук не нужен», хотя все его триггеры детектируются
    #   только по речи, — и наоборот. Это не замер, а проверка внутренней связности.
    #   Проверить: audio_dependency_claim := "unnecessary" у сэмпла, где все
    #   trigger_modality == ["speech"] -> "все триггеры только речевые";
    #   claim := "required" у чисто визуального -> "нет speech/sound".
    if claim == "unnecessary" and mods == {"speech"}:
        errs.append("claim=unnecessary, но все триггеры только речевые")
    if claim == "required" and "speech" not in mods and "sound" not in mods:
        errs.append("claim=required, но среди модальностей нет speech/sound")
    if claim == "helpful" and "speech" not in mods and "sound" not in mods:
        errs.append("claim=helpful, но среди обязательных модальностей нет speech/sound: "
                    "чем именно звук помогает, из разметки не следует")

    return errs


def twin_groups(samples: dict[str, dict]) -> list[list[str]]:
    """Разбивает сэмплы на группы близнецов по неориентированным ссылкам twin_of.

    Ссылка не обязана быть взаимной: достаточно, чтобы её проставил один
    из пары. Группа может быть и больше двух — один и тот же вопрос,
    выданный в трёх разных точках, это законная тройня.
    """
    parent = {sid: sid for sid in samples}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for sid, s in samples.items():
        other = s.get("twin_of")
        if other in parent:
            parent[find(sid)] = find(other)

    groups: dict[str, list[str]] = {}
    for sid in samples:
        groups.setdefault(find(sid), []).append(sid)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def cross_sample_checks(samples: dict[str, dict]) -> dict[str, list[str]]:
    """Проверки, которым одного сэмпла мало: связь контрольных близнецов.

    Возвращает отображение «id сэмпла -> список претензий». Претензия
    приписывается тому сэмплу, в котором её можно исправить: битая ссылка —
    источнику ссылки, расхождение внутри группы — каждому её участнику,
    кроме первого по `id` (он считается опорным).
    """
    errs: dict[str, list[str]] = {}

    def add(sid: str, msg: str) -> None:
        errs.setdefault(sid, []).append(msg)

    # S-23 · чеклист 5.1 — ссылка twin_of ведёт на существующий сэмпл.
    #   Ломается: близнец потерян из-за опечатки в id, группа распадается,
    #   и сравнение рубрик (S-24) молча не выполняется ни для кого.
    #   Проверить: twin_of := "нет-такого-id" -> "twin_of ссылается на неизвестный id".
    for sid, s in samples.items():
        other = s.get("twin_of")
        if other is None:
            continue
        if other == sid:
            add(sid, "twin_of ссылается на сам сэмпл")
        elif other not in samples:
            add(sid, f"twin_of ссылается на неизвестный id {other!r} "
                     f"(близнецы должны проверяться одним прогоном)")
        elif samples[other].get("twin_of") not in (None, sid):
            add(sid, f"twin_of={other!r}, но тот указывает на "
                     f"{samples[other]['twin_of']!r}: ссылки не согласованы")

    # S-24 · чеклист 5.1 — у близнецов совпадает всё, кроме момента выдачи вопроса.
    #   Ломается: разность метрик пары задумана как цена одного лишь тайминга.
    #   Если у близнецов разошлись рубрики, act или уровень рассуждения, та же
    #   разность меряет ещё и смену требований к ответу — и результат
    #   не интерпретируется.
    #   Сравниваются рубрики ТОЛЬКО обязательных триггеров: опциональное окно
    #   у одного из близнецов (например, до появления объекта на экране)
    #   законно отсутствует у другого.
    #   Проверить: у одного из пары дописать пункт в rubric обязательного триггера
    #     -> "рубрика обязательных триггеров расходится с близнецом";
    #   поменять reasoning_level одному из пары -> "reasoning_level расходится";
    #   убрать "visual" из trigger_modality одного из пары
    #     -> "trigger_modality обязательных триггеров расходится".
    for group in twin_groups(samples):
        base = group[0]

        def key(sid: str) -> list[str]:
            return [r.strip()
                    for t in samples[sid]["triggers"] if t.get("required")
                    for r in t["rubric"]]

        for sid in group[1:]:
            if key(sid) != key(base):
                add(sid, f"рубрика обязательных триггеров расходится с близнецом {base}")
            mods = lambda x: [tr["trigger_modality"]
                              for tr in samples[x]["triggers"] if tr.get("required")]
            if mods(sid) != mods(base):
                add(sid, f"trigger_modality обязательных триггеров расходится с близнецом "
                         f"{base}: {mods(sid)} против {mods(base)}. Доказательство у пары "
                         f"одно и то же — оно не может быть визуальным у одного и нет "
                         f"у другого")
            for field in ("act", "reasoning_level"):
                if samples[sid].get(field) != samples[base].get(field):
                    add(sid, f"{field} расходится с близнецом {base}: "
                             f"{samples[sid].get(field)!r} против {samples[base].get(field)!r}")
            if samples[sid]["video"]["youtube_id"] != samples[base]["video"]["youtube_id"]:
                add(sid, f"близнец {base} размечен по другому видео")
            if samples[sid]["question_time"] == samples[base]["question_time"]:
                add(sid, f"question_time совпадает с близнецом {base}: "
                         f"пара не меряет цену тайминга")

    # S-26 · чеклист 6.3 — у близнецов не пропала приманка, которая могла у них быть.
    #   Пара близнецов существует ради сравнения метрик, в том числе доли попаданий
    #   в ловушку. Если приманка есть у одного и отсутствует у другого без причины,
    #   эта доля несравнима.
    #   Отсутствие законно ровно в одном случае: приманка целиком раньше
    #   question_time второго близнеца, и там её запрещает S-15 (чеклист 1.2).
    #   Именно так выглядят обе пары пилота, поэтому правило сформулировано как
    #   «законная у обоих обязана быть у обоих», а не «наборы совпадают».
    #   Ломается: приманку удалили или добавили только одному из пары, и колонка
    #   ложных срабатываний по паре молча теряет смысл.
    #   Проверить: у q07 (question_time=930) добавить приманку [1000, 1010]
    #   -> "приманка ... есть у ..., но не у близнеца".
    for group in twin_groups(samples):
        for sid in group:
            mine = samples[sid].get("distractor_windows", [])
            for other in group:
                if other == sid:
                    continue
                qt = samples[other]["question_time"]
                theirs = samples[other].get("distractor_windows", [])
                for d in mine:
                    if d["t_end"] <= qt:
                        continue          # у близнеца она запрещена по 1.2 — законно
                    if not any(abs(x["t_start"] - d["t_start"]) <= 1.0
                               and abs(x["t_end"] - d["t_end"]) <= 1.0 for x in theirs):
                        add(sid, f"приманка [{d['t_start']}, {d['t_end']}] есть у {sid}, "
                                 f"но не у близнеца {other}, хотя там она законна")

    return errs


def rules_table() -> str:
    """Оглавление правил: S-NN, пункт чеклиста, что ломается без него.

    Паспорта живут в комментариях рядом с самими правилами — так они не расходятся
    с кодом. Но искать их там глазами невозможно, а в разговоре про разметку
    номер `S-25` всплывает раньше, чем кто-либо вспомнит, что он проверяет.
    Поэтому оглавление собирается из тех же комментариев, а не пишется отдельно:
    отдельное разошлось бы с кодом на первой же правке.
    """
    src = Path(__file__).read_text(encoding="utf-8").splitlines()
    head = re.compile(r"^\s*# (S-\d+) · чеклист ([\d.]+) — (.+)$")
    rows, cur = [], None
    for line in src:
        m = head.match(line)
        if m:
            cur = {"id": m.group(1), "item": m.group(2), "what": m.group(3).rstrip(".")}
            rows.append(cur)
        elif cur is not None:
            b = re.match(r"^\s*#\s+Ломается: (.+)$", line)
            if b:
                cur["breaks"] = b.group(1)
            elif not re.match(r"^\s*#", line):
                cur = None
    out = [f"{len(rows)} правил валидатора\n"]
    for r in sorted(rows, key=lambda r: int(r["id"].split("-")[1])):
        out.append(f"{r['id']:6s} чеклист {r['item']:5s} {r['what']}")
        if r.get("breaks"):
            out.append(f"{'':6s} ломается: {r['breaks']}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*",
                    help="файлы разметки; не нужны при --rules")
    ap.add_argument("--rules", action="store_true",
                    help="напечатать оглавление правил: S-NN, пункт чеклиста, что ломается")
    args = ap.parse_args()

    total = 0
    bad_ids: set[str] = set()
    samples: dict[str, dict] = {}
    seen_ids: dict[str, str] = {}
    stats = {k: Counter() for k in ("act", "temporal_rel", "reasoning_level",
                                    "template", "audio_dependency_claim")}
    ntrig = Counter()

    if args.rules:
        print(rules_table())
        return

    for fp in args.files:
        if not Path(fp).exists():
            sys.exit(f"нет файла {fp}")
        for lineno, line in enumerate(Path(fp).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            try:
                s = json.loads(line)
            except json.JSONDecodeError as e:
                bad_ids.add(f"{fp}:{lineno}")
                print(f"\n!! {fp}:{lineno}  строка не разбирается как JSON: {e}")
                continue
            errs = []
            sid = s.get("id")
            if sid in seen_ids:
                errs.append(f"id уже встречался в {seen_ids[sid]}")
            elif sid:
                seen_ids[sid] = f"{fp}:{lineno}"
                samples[sid] = s
            # S-34 · чеклист 1.8 — файл соответствует JSON-схеме.
            #   Ломается: всё остальное. Схема с additionalProperties: false на всех
            #   уровнях ловит опечатку в имени поля, которая иначе прошла бы молча
            #   и оставила поле незаполненным.
            #   Проверить: дописать сэмплу поле "note": "x" -> "schema:".
            try:
                jsonschema.validate(s, SCHEMA)
            except jsonschema.ValidationError as e:
                errs.append(f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}")
            try:
                errs += semantic_checks(s)
            except (KeyError, IndexError, TypeError) as e:
                errs.append(f"semantic: не удалось проверить ({type(e).__name__}: {e})")
            if errs:
                bad_ids.add(sid or f"{fp}:{lineno}")
                print(f"\n!! {fp}:{lineno}  {s.get('id')}")
                for e in errs:
                    print(f"   - {e}")
            for k, c in stats.items():
                c[s.get(k)] += 1
            ntrig[len(s.get("triggers", []))] += 1

    try:
        cross = cross_sample_checks(samples)
    except (KeyError, IndexError, TypeError) as e:
        # Сэмпл, не прошедший схему, до сюда доезжает как есть: раньше падение
        # внутри межсэмпловых проверок уносило весь отчёт вместе с итогом.
        cross = {}
        bad_ids.add("cross-sample")
        print(f"\n!! межсэмпловые проверки не выполнены ({type(e).__name__}: {e}) — "
              f"почините ошибки выше и запустите снова")
    for sid, errs in sorted(cross.items()):
        bad_ids.add(sid)
        print(f"\n!! {seen_ids[sid]}  {sid}")
        for e in errs:
            print(f"   - {e}")

    for sid, msg in WARNINGS:
        print(f"\n?? {sid}\n   - {msg}")

    if NO_BUNDLE:
        print(f"\n?? правила {BUNDLE_DEPENDENT} пропущены: нет бандла у "
              f"{', '.join(sorted(NO_BUNDLE))}")

    bad = len(bad_ids)
    if not total:
        sys.exit("не передано ни одного сэмпла: пустой прогон — не зелёный прогон")
    print(f"\nпроверено {total}, с ошибками {bad}, предупреждений {len(WARNINGS)}")
    if not bad:
        print("\nпокрытие:")
        for k, c in stats.items():
            print(f"  {k:24} {dict(c)}")
        print(f"  {'триггеров на сэмпл':24} {dict(sorted(ntrig.items()))}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

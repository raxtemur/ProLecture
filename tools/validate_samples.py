#!/usr/bin/env python3
"""Валидирует файлы разметки: JSON Schema + семантические проверки.

    python tools/validate_samples.py data/annotations/*.jsonl
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "sample.schema.json").read_text(encoding="utf-8"))


def evidence_span(t: dict) -> tuple[float, float]:
    # где в видео лежит информация для ответа; по умолчанию — само окно ответа
    span = t.get("evidence_span")
    return (span[0], span[1]) if span else (t["t_start"], t["t_end"])


def derive_temporal_rel(s: dict) -> str:
    # ось B определяется положением question_time относительно ДОКАЗАТЕЛЬСТВА,
    # а не относительно окна ответа: у post-вопроса окно ответа тоже начинается
    # в момент выдачи вопроса, и по окну его не отличить от at.
    qt = s["question_time"]
    req = [t for t in s["triggers"] if t["required"]]
    first, last = evidence_span(req[0]), evidence_span(req[-1])
    if qt < first[0]:
        return "pre"
    if qt >= last[1]:
        return "post"
    return "at"


def semantic_checks(s: dict) -> list[str]:
    errs = []
    dur = s["video"]["duration"]
    trigs = s["triggers"]

    if s["question_time"] > dur:
        errs.append(f"question_time={s['question_time']} больше длительности видео {dur}")
    if len(trigs) > 1 and not s.get("distractor_windows"):
        errs.append("многотриггерный сэмпл без distractor_windows: спам-стратегия ничем не наказана "
                    "(план §3.1 п.3)")

    want = derive_temporal_rel(s)
    if s["temporal_rel"] != want:
        errs.append(f"temporal_rel={s['temporal_rel']}, но по question_time="
                    f"{s['question_time']} и evidence_span должно быть {want}")

    for t in trigs:
        a, b = evidence_span(t)
        if not (a < b):
            errs.append(f"trigger[{t['idx']}]: evidence_span пустой или вывернут")
        if b > dur:
            errs.append(f"trigger[{t['idx']}]: evidence_span выходит за длительность")

    if [t["idx"] for t in trigs] != list(range(len(trigs))):
        errs.append("idx триггеров должны идти подряд с 0")
    if not any(t["required"] for t in trigs):
        errs.append("нет ни одного обязательного триггера")

    prev_end = -1.0
    for t in trigs:
        tag = f"trigger[{t['idx']}]"
        if not (t["t_start"] < t["t_end"]):
            errs.append(f"{tag}: t_start >= t_end")
        if not (t["t_start"] <= t["t_ideal"] < t["t_end"]):
            errs.append(f"{tag}: t_ideal вне окна")
        if t["t_end"] > dur:
            errs.append(f"{tag}: окно выходит за длительность видео")
        if t["t_start"] < prev_end:
            errs.append(f"{tag}: окно пересекается с предыдущим")
        if t["t_end"] <= s["question_time"]:
            errs.append(f"{tag}: окно ответа целиком до выдачи вопроса — отвечать в нём невозможно")
        prev_end = t["t_end"]
        for dep in t.get("depends_on", []):
            if dep >= t["idx"]:
                errs.append(f"{tag}: depends_on={dep} не раньше самого триггера")

    for i, d in enumerate(s.get("distractor_windows", [])):
        if not (d["t_start"] < d["t_end"]):
            errs.append(f"distractor[{i}]: t_start >= t_end")
        if d["t_end"] <= s["question_time"]:
            errs.append(f"distractor[{i}] целиком до выдачи вопроса — ложным срабатыванием "
                        f"там быть нечему")
        for t in trigs:
            if d["t_start"] < t["t_end"] and t["t_start"] < d["t_end"]:
                errs.append(f"distractor[{i}] пересекается с trigger[{t['idx']}]")

    if s["audio_dependency"] is not None and s["validation"]["status"] == "draft":
        errs.append("audio_dependency заполнен, но статус draft: метка ставится только замером")

    mods = {m for t in trigs for m in t["trigger_modality"]}
    claim = s.get("audio_dependency_claim")
    if claim == "unnecessary" and mods == {"speech"}:
        errs.append("claim=unnecessary, но все триггеры только речевые")
    if claim == "required" and "speech" not in mods and "sound" not in mods:
        errs.append("claim=required, но среди модальностей нет speech/sound")

    return errs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    total, bad = 0, 0
    seen_ids: dict[str, str] = {}
    stats = {k: Counter() for k in ("act", "temporal_rel", "reasoning_level",
                                    "template", "audio_dependency_claim")}
    ntrig = Counter()

    for fp in args.files:
        for lineno, line in enumerate(Path(fp).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            s = json.loads(line)
            errs = []
            sid = s.get("id")
            if sid in seen_ids:
                errs.append(f"id уже встречался в {seen_ids[sid]}")
            elif sid:
                seen_ids[sid] = f"{fp}:{lineno}"
            try:
                jsonschema.validate(s, SCHEMA)
            except jsonschema.ValidationError as e:
                errs.append(f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}")
            try:
                errs += semantic_checks(s)
            except (KeyError, IndexError, TypeError) as e:
                errs.append(f"semantic: не удалось проверить ({type(e).__name__}: {e})")
            if errs:
                bad += 1
                print(f"\n!! {fp}:{lineno}  {s.get('id')}")
                for e in errs:
                    print(f"   - {e}")
            for k, c in stats.items():
                c[s.get(k)] += 1
            ntrig[len(s["triggers"])] += 1

    print(f"\nпроверено {total}, с ошибками {bad}")
    if not bad:
        print("\nпокрытие:")
        for k, c in stats.items():
            print(f"  {k:24} {dict(c)}")
        print(f"  {'триггеров на сэмпл':24} {dict(sorted(ntrig.items()))}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

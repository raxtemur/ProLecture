#!/usr/bin/env python3
"""Score a judged run by docs/plans/general.md, §4.

Reads `<out>/judged/<task>.json` (eval_judge.py) and the samples, and computes per task, then
per sample (the mean over its runs), then over samples:

- PAUC at ω = 0 and ω = 0.5: the main number over the required windows, the second with the
  optional ones as well. On a window the points are the utterances that start inside it
  (inclusive bounds), each timed by its first chunk and taken whole, as SPECTRA and
  ProactiveVideoQA do: a window is often shorter than the answer it asks for, and an answer
  begun in it would otherwise never be complete there. The quality at a point is 2 when every
  item of the window is credited over the lines of those utterances so far, 1 when some are,
  0 when none; the curve starts at 0.5, the maximum is 2, so a silent window scores 0.25 — the
  floor of the scale, not a result. The same curve over single chunks instead of utterances is
  kept as a diagnostic (`pauc_chunk_*`, in the JSON only);
- an item is credited over a set of lines when one of them states it correctly and none states
  it wrongly or offers an alternative for it (the judge's two lists);
- False-Alarm Rate: utterances (joined chunks, timed by the first) starting outside every
  window, required or optional. One utterance may run for minutes, so the same share over
  chunks (about seconds of speech) is kept beside it, and so is the speech before the question
  is asked: the stream starts at 0 s, and a model that narrates the lecture unasked shows here; latency of the first utterance starting inside a required
  window, from its `t_start`; silence rate (required windows where no utterance starts);
  Trigger Recall (required windows whose quality reached 1); utterances per sample next to the
  number of windows;
- rubric accuracy over the required windows' items in three readings, with text attributed to
  the second of its chunk (general.md): (1) credited over the lines inside any window, (2) over
  all lines, (3) as (2), but on `predict` only over lines up to the item's window `t_end`.

The simplest score, `acc`, comes first in the tables: the share of the required windows' rubric
items the model said inside any window of the sample, required or optional. Inside a window means
a chunk timed within it (so a phrase begun before the window counts from the window's start) or
any part of a phrase begun within it (so an answer may run past a short window).

Chain accuracy is not computed: it needs a rubric item of its own that the samples do not have.

An offline run (eval_run_offline.py, `"mode": "offline"` in its config) answers once, after the
last window, so it has no timing to score: its `acc` is the share of the required windows' items
credited over the whole answer, and its tables show that alone.

    $BASE tools/eval_score.py --out data/eval/minicpmo45/<date>

Writes `<out>/scores/tasks.jsonl`, `<out>/scores/summary.json` and `<out>/scores/summary.md`.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_common as ec  # noqa: E402

OMEGAS = (0.0, 0.5)
BOOTSTRAP = 4000
JUDGE_MAX = 2
START = 0.5


def pauc(times: list[float], scores: list[int], t_start: float, t_end: float, omega: float) -> float | None:
    """SPECTRA's step PAUC (spectra/metrics/pauc.py), restated to keep base conda standalone."""
    max_area = (t_end - t_start) * JUDGE_MAX
    if max_area <= 0:
        return None
    if not times:
        return START / JUDGE_MAX
    taus = [t_start + (1 - omega) * (t - t_start) for t in times]
    area = (taus[0] - t_start) * START
    for p in range(len(taus) - 1):
        area += (taus[p + 1] - taus[p]) * scores[p]
    area += (t_end - taus[-1]) * scores[-1]
    return area / max_area


def credited(item: dict, allowed: set[int]) -> bool:
    return bool(allowed & set(item["correct"])) and not (allowed & set(item["wrong"]))


def inside(t: float, trigger: dict) -> bool:
    return float(trigger["t_start"]) <= t <= float(trigger["t_end"])


def one_per_second(curve: list[tuple[float, int]]) -> tuple[list[float], list[int]]:
    """Points of one second merge into one, holding the quality reached last."""
    times: list[float] = []
    scores: list[int] = []
    for t, quality in curve:
        if times and t == times[-1]:
            scores[-1] = quality
        else:
            times.append(t)
            scores.append(quality)
    return times, scores


def window_quality(items: list[dict], allowed: set[int]) -> int:
    hits = sum(credited(item, allowed) for item in items)
    return 2 if hits == len(items) else 1 if hits else 0


def score_task(sample: dict, judged: dict) -> dict:
    lines = judged["lines"]
    items = judged["items"]
    by_window = defaultdict(list)
    for item in items:
        by_window[item["window"]].append(item)
    triggers = sample["triggers"]

    utterances = ec.utterances(lines)
    windows = []
    said_in_windows: set[int] = set()
    for trigger in triggers:
        w_items = by_window[trigger["idx"]]
        t0, t1 = float(trigger["t_start"]), float(trigger["t_end"])
        starting = [u for u in utterances if inside(u["t"], trigger)]
        curve = []
        seen: set[int] = set()
        for utterance in starting:
            seen |= set(utterance["lines"])
            curve.append((utterance["t"], window_quality(w_items, seen)))
        chunk_curve = []
        seen = set()
        for line in lines:
            if inside(line["t"], trigger):
                seen.add(line["n"])
                chunk_curve.append((line["t"], window_quality(w_items, seen)))
        scores = [q for _, q in curve]
        # what was said in this window: its chunks (the in-window part of a phrase begun earlier)
        # and the whole of every phrase begun in it (an answer may run past a short window)
        said_here = {line["n"] for line in lines if inside(line["t"], trigger)}
        for utterance in starting:
            said_here |= set(utterance["lines"])
        said_in_windows |= said_here
        windows.append({
            "idx": trigger["idx"], "required": bool(trigger.get("required", True)),
            "t_start": t0, "t_end": t1, "n_utterances": len(starting),
            "latency": (starting[0]["t"] - t0) if starting else None,
            "quality": scores, "best": max(scores) if scores else None,
            **{f"pauc_{omega}": pauc(*one_per_second(curve), t0, t1, omega) for omega in OMEGAS},
            **{f"pauc_chunk_{omega}": pauc(*one_per_second(chunk_curve), t0, t1, omega)
               for omega in OMEGAS},
        })

    outside = [u for u in utterances if not any(inside(u["t"], trigger) for trigger in triggers)]
    required = [w for w in windows if w["required"]]
    every_line = {line["n"] for line in lines}
    in_any = {line["n"] for line in lines if any(inside(line["t"], trigger) for trigger in triggers)}
    end_of = {trigger["idx"]: float(trigger["t_end"]) for trigger in triggers}
    required_items = [item for item in items if item["required"]]

    def accuracy(allowed_of) -> float | None:
        if not required_items:
            return None
        return sum(credited(item, allowed_of(item)) for item in required_items) / len(required_items)

    def before_end(item: dict) -> set[int]:
        if sample["act"] != "predict":
            return every_line
        return {line["n"] for line in lines if line["t"] <= end_of[item["window"]]}

    def mean(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None

    result = {
        "task": judged["task"], "sample_id": sample["id"], "run": judged["run"],
        "windows": windows,
        "n_utterances": len(utterances), "n_lines": len(lines),
        "n_required": len(required), "n_windows": len(windows),
        "far": (len(outside) / len(utterances)) if utterances else None,
        "far_chunks": (sum(not any(inside(line["t"], trigger) for trigger in triggers)
                           for line in lines) / len(lines)) if lines else None,
        "chunks_before_question": sum(line["t"] < float(sample["question_time"]) for line in lines),
        "spoke_before_question": float(any(line["t"] < float(sample["question_time"]) for line in lines)),
        "chunks_after_question": sum(line["t"] >= float(sample["question_time"]) for line in lines),
        "silence": sum(w["n_utterances"] == 0 for w in required) / len(required),
        "recall": sum((w["best"] or 0) >= 1 for w in required) / len(required),
        "latencies": [w["latency"] for w in required if w["latency"] is not None],
        # the simple score: the share of the required windows' items said inside any window of
        # the sample, required or optional
        "acc": accuracy(lambda item: said_in_windows),
        "acc_in_window": accuracy(lambda item: in_any),
        "acc_anywhere": accuracy(lambda item: every_line),
        "acc_before_end": accuracy(before_end),
    }
    for omega in OMEGAS:
        result[f"pauc_{omega}"] = mean(w[f"pauc_{omega}"] for w in required)
        result[f"pauc_all_{omega}"] = mean(w[f"pauc_{omega}"] for w in windows)
        result[f"pauc_chunk_{omega}"] = mean(w[f"pauc_chunk_{omega}"] for w in required)
    return result


METRICS = [
    ("acc", "acc: items done in their window"),
    ("pauc_0.0", "PAUC ω=0 (required)"),
    ("pauc_0.5", "PAUC ω=0.5 (required)"),
    ("pauc_all_0.0", "PAUC ω=0 (+optional)"),
    ("pauc_all_0.5", "PAUC ω=0.5 (+optional)"),
    ("pauc_chunk_0.0", "PAUC ω=0 by chunks (diagnostic)"),
    ("pauc_chunk_0.5", "PAUC ω=0.5 by chunks (diagnostic)"),
    ("recall", "Trigger Recall"),
    ("silence", "Silence rate"),
    ("far", "FAR"),
    ("far_chunks", "FAR by chunks"),
    ("n_utterances", "Utterances / sample"),
    ("spoke_before_question", "Sessions speaking before the question"),
    ("chunks_before_question", "Chunks before the question"),
    ("chunks_after_question", "Chunks after the question"),
    ("acc_in_window", "Rubric acc. (1) in window"),
    ("acc_anywhere", "Rubric acc. (2) anywhere"),
    ("acc_before_end", "Rubric acc. (3) before t_end on predict"),
]


def mean_or_none(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def bootstrap_ci(values: list[float], resamples: int = BOOTSTRAP, level: float = 0.95):
    """Percentile interval of the mean over samples, the samples drawn with replacement: the
    spread between samples, which dominates the spread between runs of one sample."""
    if len(values) < 2:
        return None
    rng = random.Random(0)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(resamples))
    tail = (1 - level) / 2
    return [means[int(tail * resamples)], means[int((1 - tail) * resamples) - 1]]


def aggregate(samples: list[dict], per_sample: dict[str, list[dict]]) -> dict:
    """Mean over samples of the mean over runs; the spread is across the runs' set means, the
    interval is a bootstrap over samples."""
    present = [s for s in samples if per_sample.get(s["id"])]
    out: dict = {"n_samples": len(present), "n_tasks": sum(len(per_sample[s["id"]]) for s in present)}
    runs = sorted({task["run"] for s in present for task in per_sample[s["id"]]})
    for key, _ in METRICS:
        sample_means = [mean_or_none(task[key] for task in per_sample[s["id"]]) for s in present]
        run_means = [mean_or_none(task[key] for s in present for task in per_sample[s["id"]]
                                  if task["run"] == run) for run in runs]
        run_means = [v for v in run_means if v is not None]
        out[key] = mean_or_none(sample_means)
        out[key + "_sd_runs"] = statistics.stdev(run_means) if len(run_means) > 1 else None
        out[key + "_ci"] = bootstrap_ci([v for v in sample_means if v is not None])
    latencies = sorted(l for s in present for task in per_sample[s["id"]] for l in task["latencies"])
    if latencies:
        out["latency"] = {"n": len(latencies), "min": latencies[0], "median": statistics.median(latencies),
                          "p75": latencies[int(0.75 * (len(latencies) - 1))], "max": latencies[-1]}
    out["n_windows_required"] = mean_or_none(len([t for t in s["triggers"] if t.get("required", True)])
                                             for s in present)
    return out


def fmt(value, digits=3):
    return "—" if value is None else f"{value:.{digits}f}"


def table(title: str, groups: dict[str, dict], offline: bool = False) -> list[str]:
    keys = ["acc"] if offline else [
        "acc", "pauc_0.0", "pauc_0.5", "pauc_all_0.5", "recall", "silence", "far", "far_chunks",
        "n_utterances", "spoke_before_question", "chunks_before_question",
        "chunks_after_question", "acc_in_window", "acc_anywhere", "acc_before_end"]
    names = dict(METRICS)
    lines = [f"### {title}", "", "| group | n | " + " | ".join(names[k] for k in keys) + " |",
             "|---|---|" + "---|" * len(keys)]
    for name, agg in groups.items():
        cells = []
        for key in keys:
            value, sd = agg.get(key), agg.get(key + "_sd_runs")
            digits = 1 if key in ("n_utterances", "chunks_before_question", "chunks_after_question") else 3
            cells.append(fmt(value, digits) + ("" if sd is None else f" ±{sd:.{digits}f}"))
        lines.append(f"| {name} | {agg['n_samples']} | " + " | ".join(cells) + " |")
    return lines + [""]


def ci_table(title: str, groups: dict[str, dict], offline: bool = False) -> list[str]:
    keys = ["acc"] if offline else [
        "acc", "pauc_0.0", "pauc_0.5", "pauc_all_0.5", "pauc_chunk_0.0", "recall", "silence",
        "acc_in_window", "acc_anywhere", "acc_before_end"]
    names = dict(METRICS)
    lines = [f"### {title}", "", "| group | n | " + " | ".join(names[k] for k in keys) + " |",
             "|---|---|" + "---|" * len(keys)]
    for name, agg in groups.items():
        cells = []
        for key in keys:
            ci = agg.get(key + "_ci")
            cells.append(fmt(agg.get(key)) + ("" if not ci else f" [{ci[0]:.3f}, {ci[1]:.3f}]"))
        lines.append(f"| {name} | {agg['n_samples']} | " + " | ".join(cells) + " |")
    return lines + [""]


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else ec.ROOT / args.out

    config = json.loads((out / "config.json").read_text(encoding="utf-8"))
    offline = config.get("mode") == "offline"
    wanted = set(config["samples"])
    samples = [s for video in ec.annotation_videos() for s in ec.read_records(video) if s["id"] in wanted]
    by_id = {s["id"]: s for s in samples}

    per_sample: dict[str, list[dict]] = defaultdict(list)
    tasks = []
    for path in sorted((out / "judged").glob("*.json")):
        judged = json.loads(path.read_text(encoding="utf-8"))
        sample = by_id.get(judged["sample_id"])
        if sample is None:
            continue
        task = score_task(sample, judged)
        if offline:
            task["acc"] = task["acc_anywhere"]
        saved = out / "responses" / f"{judged['task']}.json"
        if saved.exists():
            task["seconds"] = json.loads(saved.read_text(encoding="utf-8")).get("seconds")
        tasks.append(task)
        per_sample[sample["id"]].append(task)

    expected = len(wanted) * int(config["runs"])
    missing = expected - len(tasks)
    scores_dir = out / "scores"
    scores_dir.mkdir(exist_ok=True)
    with (scores_dir / "tasks.jsonl").open("w", encoding="utf-8") as fh:
        for task in tasks:
            fh.write(json.dumps(task, ensure_ascii=False) + "\n")

    def blind(sample):
        return bool((sample.get("validation") or {}).get("blind_solved"))

    primary = [s for s in samples if not blind(s)]
    sets = {"primary (not blind_solved)": primary,
            "blind_solved": [s for s in samples if blind(s)],
            "all": samples}
    summary = {"tasks_scored": len(tasks), "tasks_expected": expected,
               "sets": {name: aggregate(group, per_sample) for name, group in sets.items()},
               "breakdowns": {}}
    for axis in ("act", "reasoning_level", "temporal_rel", "audio_dependency", "video"):
        groups = defaultdict(list)
        for sample in primary:
            key = sample["video"]["youtube_id"] if axis == "video" else str(sample.get(axis))
            groups[key].append(sample)
        summary["breakdowns"][axis] = {key: aggregate(group, per_sample)
                                       for key, group in sorted(groups.items())}
    seconds = [t["seconds"] for t in tasks if t.get("seconds")]
    summary["model_hours"] = sum(seconds) / 3600 if seconds else None
    (scores_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                             encoding="utf-8")

    md = [f"# Scores: {out.name}", "",
          f"Tasks scored: {len(tasks)} of {expected}" + (f" ({missing} missing)" if missing else ""),
          ("Offline run: one answer after the last window, acc over the whole answer. "
           if offline else "PAUC floor (silence) is 0.25; ")
          + "± is the standard deviation across the runs' set means; "
          "[a, b] is a 95% bootstrap interval over samples.", ""]
    md += table("Sets", summary["sets"], offline)
    for axis, groups in summary["breakdowns"].items():
        md += table(f"Primary set by {axis}", groups, offline)
    md += ci_table("Primary set by reasoning_level, mean and 95% bootstrap interval over samples",
                   {"all primary": summary["sets"]["primary (not blind_solved)"],
                    **summary["breakdowns"]["reasoning_level"]}, offline)
    latency = summary["sets"]["primary (not blind_solved)"].get("latency")
    if latency and not offline:
        md += ["Latency of the first utterance inside a required window, from t_start (primary set): "
               + ", ".join(f"{k} {fmt(v, 1) if k != 'n' else v}" for k, v in latency.items()), ""]
    (scores_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""What the three evaluation scripts share: which samples are measured, what the model is
shown, how the rubric splits into items and how emitted chunks join into answers.

Standard library only: eval_run_minicpm.py runs in the model's environment, eval_judge.py and
eval_score.py in the base one.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = ROOT / "data" / "annotations"
VIDEOS = ROOT / "data" / "videos"
EVAL = ROOT / "data" / "eval"

# The pilot's records are archived and not measured: their videos are annotated anew.
ARCHIVED = ("l6DKRf-fAAM", "GlYgs6v2YfU", "3d6DsjIBzJ4")

# The stream runs on past the last window, so that a late answer is seen as late rather than
# cut off (the notebook's POST_PAD_SECONDS).
POST_PAD_SECONDS = 20.0

NEGATIVE_PREFIX = "do not count"


def annotation_videos() -> list[str]:
    return sorted(p.stem for p in ANNOTATIONS.glob("*.jsonl") if p.stem not in ARCHIVED)


def read_records(video_id: str) -> list[dict]:
    path = ANNOTATIONS / f"{video_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select_samples(videos: list[str] | None = None, statuses: tuple[str, ...] = ("validated",),
                   sample_ids: list[str] | None = None) -> list[dict]:
    """The measured samples: blind baselines (blind_solved) included, they are told apart in
    the scores, not here."""
    chosen = []
    for video_id in videos or annotation_videos():
        for record in read_records(video_id):
            if (record.get("validation") or {}).get("status") not in statuses:
                continue
            if sample_ids and record["id"] not in sample_ids:
                continue
            chosen.append(record)
    return chosen


def stream_bounds(sample: dict) -> tuple[float, float]:
    """The participant watches the lecture from its start (docs/plans/general.md, §4): a clip
    around the question would hide what an L2 question links to and, on a `post` sample, every
    fact before the last one (docs/reports/2026-09-29-eval-notebook-fixes.md, item 5)."""
    end = max(float(t["t_end"]) for t in sample["triggers"]) + POST_PAD_SECONDS
    duration = float((sample.get("video") or {}).get("duration") or end)
    return 0.0, min(duration, end)


def video_path(sample: dict) -> Path:
    video_id = sample["video"]["youtube_id"]
    return VIDEOS / video_id / f"{video_id}.mp4"


def task_name(sample_id: str, run: int) -> str:
    return f"{sample_id}.r{run}"


def rubric_items(trigger: dict) -> tuple[list[str], list[str]]:
    """The items an answer must state, and the "do NOT count" lines that only restrict them."""
    items, restrictions = [], []
    for line in trigger.get("rubric") or []:
        (restrictions if line.strip().lower().startswith(NEGATIVE_PREFIX) else items).append(line)
    return items, restrictions


def item_id(window: int, k: int) -> str:
    return f"w{window}.{k + 1}"


def output_lines(responses: list[dict]) -> list[dict]:
    """One line per emitted chunk, numbered from 1: text is attributed to the second it was
    emitted in, not to the start of its utterance (general.md, §4, rubric accuracy)."""
    lines = []
    for response in sorted(responses, key=lambda r: float(r["t"])):
        text = (response.get("content") or "").strip()
        if text:
            lines.append({"n": len(lines) + 1, "t": float(response["t"]), "text": text,
                          "utterance": response.get("utterance_id")})
    return lines


def utterances(lines: list[dict]) -> list[dict]:
    """Answers as a listener hears them: consecutive chunks of one utterance joined, timed by
    their first chunk, with the numbers of the lines they are made of."""
    joined: list[dict] = []
    for line in lines:
        last = joined[-1] if joined else None
        if last and line["utterance"] is not None and line["utterance"] == last["utterance"]:
            last["text"] += " " + line["text"]
            last["t_last"] = line["t"]
            last["lines"].append(line["n"])
        else:
            joined.append({"t": line["t"], "t_last": line["t"], "text": line["text"],
                           "utterance": line["utterance"], "lines": [line["n"]]})
    return joined

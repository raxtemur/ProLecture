#!/usr/bin/env python3
"""Judge a model's saved output against the rubric with an LLM (Qwen3.8-27B on vLLM).

One call per task (`<sample_id>.r<run>`, a file in `<out>/responses/`). The judge sees the
question, every window's reference answer and rubric items, and the model's output as numbered
lines, one per emitted chunk with its second. For every item it returns the lines that state it
correctly and the lines that state it wrongly or offer an alternative for it. It does not
score time: when an item was stated, and whether that counts, is eval_score.py's business, so
one judgement serves PAUC, Trigger Recall and the three readings of rubric accuracy.

    $BASE tools/eval_judge.py --out data/eval/minicpmo45/<date> \
        --base-url http://127.0.0.1:8000/v1 --api-key dummy --model local

Writes `<out>/judged/<task>.json`; a task already judged is skipped unless --force. A task
with no output needs no call: every item is unstated.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_common as ec  # noqa: E402

PROMPT_VERSION = "2026-10-14b"

INSTRUCTIONS = """You grade the answer of a model that watched a lecture video as a stream and
answered a question while watching. You get the question, the reference answer and the rubric
of every answer window, and the model's output as numbered lines: each line is what it said in
one second of the stream, so a sentence may run over several lines.

For every rubric item, list:
- "correct": the lines where the model's output states the item correctly. A paraphrase counts;
  a number counts within the tolerance the item gives. Every part the item names must be there:
  an item that asks why or how something holds is not stated by its result alone. If the
  statement runs over several lines, give the line where it is complete. An item is about
  content only: when it was said does not matter here.
- "wrong": the lines where the output states something for the same item that contradicts it,
  or offers alternatives for it ("X or Y", "either ... or ...", two different values), whether
  or not one of them is right. A line that says nothing about the item is in neither list.

The "Not credited" notes of a window restrict its items: a statement they exclude is not
correct for any item, and if it contradicts an item it is wrong for that item. The reference
answer shows what the items mean; an item may be stated without repeating the reference.
Each item is about the subject of its own window (the example, the object, the case its
reference answer is about): a statement about the subject of another window states neither
that window's items nor this one's unless it is about both.

Judge only what the output says, never what the model could have meant. Return JSON only:
{"items": [{"id": "<item id>", "correct": [<line numbers>], "wrong": [<line numbers>]}, ...]}
with one entry for every item id below, in the same order."""


def judged_items(sample: dict) -> tuple[str, list[dict], list[dict]]:
    """The prompt's rubric part, the unique items the judge answers for, and every window's
    items. A window that repeats an earlier one's rubric (the same answer anchored at another
    moment) shares its items: the judge rules on a statement once, and the windows differ only
    in which lines fall inside them, which eval_score.py decides."""
    parts, unique, per_window = [], {}, []
    shown = {}
    for trigger in sample["triggers"]:
        window = trigger["idx"]
        required = bool(trigger.get("required", True))
        positive, restrictions = ec.rubric_items(trigger)
        ids = []
        for k, text in enumerate(positive):
            key = (text, tuple(restrictions))
            if key not in unique:
                unique[key] = {"id": f"i{len(unique) + 1}", "text": text}
            ids.append(unique[key]["id"])
            per_window.append({"id": ec.item_id(window, k), "window": window, "required": required,
                               "judged_as": unique[key]["id"], "text": text})
        signature = (trigger.get("response") or "", tuple(ids), tuple(restrictions))
        kind = "required" if required else "optional"
        if signature in shown:
            parts.append(f"Window {window} ({kind}): the same reference and items as window "
                         f"{shown[signature]}.")
            continue
        shown[signature] = window
        parts.append(f"Window {window} ({kind})\nReference answer: {signature[0]}")
        for iid in ids:
            text = next(u["text"] for u in unique.values() if u["id"] == iid)
            parts.append(f"  item {iid}: {text}")
        for text in restrictions:
            parts.append(f"  Not credited: {text}")
    return "\n".join(parts), list(unique.values()), per_window


def prompt(sample: dict, lines: list[dict]) -> tuple[str, list[dict], list[dict]]:
    block, items, per_window = judged_items(sample)
    output = "\n".join(f"{line['n']}. [{line['t']:.0f} s] {line['text']}" for line in lines)
    text = (f"Question: {sample['question']}\n\n{block}\n\nThe model's output:\n{output}\n\n"
            f"Item ids: {', '.join(item['id'] for item in items)}")
    return text, items, per_window


def parse(text: str, items: list[dict], n_lines: int) -> dict[str, dict]:
    """The judge's JSON, checked: every item present, line numbers in range."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the answer")
    data = json.loads(text[start:end + 1])
    by_id = {entry.get("id"): entry for entry in data.get("items", []) if isinstance(entry, dict)}
    missing = [item["id"] for item in items if item["id"] not in by_id]
    if missing:
        raise ValueError(f"items missing from the answer: {missing}")
    result = {}
    for item in items:
        entry = by_id[item["id"]]
        lists = {}
        for key in ("correct", "wrong"):
            values = entry.get(key) or []
            if not isinstance(values, list) or not all(isinstance(v, int) for v in values):
                raise ValueError(f"{item['id']}.{key} is not a list of line numbers")
            lists[key] = sorted({v for v in values if 1 <= v <= n_lines})
        result[item["id"]] = lists
    return result


def judge_task(client, model: str, sample: dict, saved: dict, retries: int = 3) -> dict:
    lines = ec.output_lines(saved.get("responses") or [])
    text, items, per_window = prompt(sample, lines)
    record = {"task": saved["task"], "sample_id": sample["id"], "run": saved["run"],
              "prompt_version": PROMPT_VERSION, "judge_model": model, "lines": lines}
    if not lines:
        for item in per_window:
            item.update(correct=[], wrong=[])
        return {**record, "items": per_window, "raw": None}
    error = None
    thinking = True
    for attempt in range(retries):
        answer = client.chat.completions.create(
            model=model, temperature=0.0, max_tokens=32000,
            messages=[{"role": "system", "content": INSTRUCTIONS},
                      {"role": "user", "content": text}],
            extra_body=None if thinking else {"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = answer.choices[0].message.content or ""
        if answer.choices[0].finish_reason == "length" and not raw.strip():
            # the reasoning ran out of tokens; the last try answers without it
            thinking = attempt + 2 < retries
        try:
            verdicts = parse(raw, items, len(lines))
        except (ValueError, json.JSONDecodeError) as exc:
            error = f"attempt {attempt + 1}: {exc}"
            continue
        for item in per_window:
            item.update(verdicts[item["judged_as"]])
        return {**record, "items": per_window, "raw": raw, "attempts": attempt + 1,
                "thinking": thinking}
    raise RuntimeError(f"{saved['task']}: the judge's answer could not be read ({error})")


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="dummy")
    parser.add_argument("--model", default="local", help="the served model name")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--tasks", nargs="*", help="only these tasks")
    args = parser.parse_args()

    import httpx
    from openai import OpenAI

    out = args.out if args.out.is_absolute() else ec.ROOT / args.out
    judged_dir = out / "judged"
    judged_dir.mkdir(parents=True, exist_ok=True)
    samples = {}
    for path in sorted((out / "responses").glob("*.r[0-9]*.json")):
        if path.name.endswith(".error.json"):
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))
        if args.tasks and saved["task"] not in args.tasks:
            continue
        if (judged_dir / f"{saved['task']}.json").exists() and not args.force:
            continue
        samples.setdefault(saved["video"], {})
        samples[saved["video"]].setdefault("todo", []).append(saved)
    todo = []
    for video_id, entry in samples.items():
        records = {r["id"]: r for r in ec.read_records(video_id)}
        todo += [(records[saved["sample_id"]], saved) for saved in entry["todo"]]
    print(f"{len(todo)} tasks to judge", flush=True)

    # HTTP(S)_PROXY in this environment would route even 127.0.0.1 through the proxy
    local = urlparse(args.base_url).hostname in ("127.0.0.1", "localhost", "::1")
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=900,
                    http_client=httpx.Client(trust_env=not local, timeout=900))
    failed = 0
    started = time.time()
    with futures.ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(judge_task, client, args.model, sample, saved): saved["task"]
                for sample, saved in todo}
        for i, job in enumerate(futures.as_completed(jobs), 1):
            task = jobs[job]
            try:
                result = job.result()
            except Exception as exc:  # one bad answer must not stop the others
                failed += 1
                print(f"[{task}] failed: {exc}", flush=True)
                continue
            (judged_dir / f"{task}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            if i % 10 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)} judged, {time.time() - started:.0f} s", flush=True)
    print(f"judge done: {len(todo) - failed} judged, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

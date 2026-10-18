#!/usr/bin/env python3
"""Run a video model served by vLLM on the measured samples offline: one answer per sample and
run, given after the material, not a stream. The answers are saved untouched; the judge and the
metrics are eval_judge.py and eval_score.py, as for the streaming runs.

The model gets the lecture from 0 s to one second past the end of the sample's last window, as
one-minute segments at 1 fps, each followed by the narration spoken in it (the subtitles: the
served model takes no audio), and then the question with the moment it was asked. Every window
closes before the author gives the answer it asks for (on L2, L3 and `predict` at least 10 s
before), so the cut shows no reveal. What this measures is what the model answers with all the
material its windows allow, not when it would speak: there is no timing to score.

The video goes in as one-minute items because the server caps the embedding of one video item
(16384 tokens); one minute at 640x360 is about 6.8k. The segments start at whole minutes, so all
the samples of a video share the prompt up to their last whole minute, and the prefix cache
serves the runs of one sample and the samples of one video.

    $BASE tools/eval_run_offline.py --out data/eval/qwen38_offline/2026-10-14 --runs 3 --workers 2

Every task is `<sample_id>.r<run>` and lands in `<out>/responses/<task>.json` in the format of
eval_run_minicpm.py: the answer split into sentences, every line timed at the cut. A task whose
file exists is skipped; a failed one leaves `<task>.error.json` and is retried by the next start.

The server shares its queue with other clients, and some of these requests never get scheduled
(vLLM 0.27.1, the served model a hybrid with its prefix cache in the experimental Mamba "align"
mode). A waiting request that cannot be scheduled blocks every request queued behind it
(2026-10-14: an hour of the proposers' requests). Both times it was two runs of one prompt sent
together; the same prompt alone went through, and a cache salt did not help, so the prefix
cache is not the cause (two video requests contending for the encoder cache is a guess, not
traced). So the answers are streamed, and a guard watches the server: when requests wait and no
prefill moves for STALL_SECONDS, the requests of this run that have not started answering are
cancelled and sent once more with a cache salt; one that has not started answering after
FIRST_TOKEN_SECONDS is given up and left for the next start, best made with --workers 1.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_common as ec  # noqa: E402

SEGMENT_SECONDS = 60
CUT_PAD_SECONDS = 1.0

SYSTEM_PROMPT = (
    "You are watching a lecture video. It is given as one-minute segments at one frame per "
    "second, each followed by the narration spoken during it. A viewer asked a question at a "
    "moment of the lecture. Answer it from what the lecture has shown and said up to the end "
    "of the material given. Answer briefly and concretely, in English: give the answer itself, "
    "without restating the question."
)

SAMPLING = {"temperature": 0.6, "top_p": 0.95, "top_k": 20}  # Qwen's settings for thinking
MAX_TOKENS = 16384
STALL_SECONDS = 90           # requests wait and no prefill moves: the queue is blocked
FIRST_TOKEN_SECONDS = 1200   # a request that has not started answering by then is stuck


def mmss(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def cut_of(sample: dict) -> float:
    end = max(float(t["t_end"]) for t in sample["triggers"]) + CUT_PAD_SECONDS
    duration = float((sample.get("video") or {}).get("duration") or end)
    return min(end, duration)


def segment(video: Path, start: float, end: float, cache: Path) -> Path:
    """The stretch [start, end) at 1 fps, 640x360, without sound; made once and kept."""
    path = cache / f"{start:07.1f}-{end:07.1f}.mp4"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        # two workers may cut the same segment at once: each writes its own file
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
                        "-i", str(video), "-an", "-r", "1", "-vf", "scale=640:360",
                        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast", str(tmp)], check=True)
        tmp.replace(path)
    return path


def narration(cues: list[dict], start: float, end: float) -> str:
    return " ".join(c["text"].strip() for c in cues if start <= float(c["start"]) < end).strip()


def build_messages(sample: dict, cut: float, cache: Path, with_narration: bool) -> list[dict]:
    video_id = sample["video"]["youtube_id"]
    cues = json.loads((ec.ROOT / "data" / "bundles" / video_id / "bundle.json").read_text(
        encoding="utf-8"))["transcript"]
    content: list[dict] = []
    start = 0.0
    while start < cut:
        end = min(start + SEGMENT_SECONDS, cut)
        path = segment(ec.video_path(sample), start, end, cache / video_id)
        content.append({"type": "text", "text": f"Video {mmss(start)}-{mmss(end)}:"})
        content.append({"type": "video_url", "video_url": {
            "url": "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode()}})
        if with_narration:
            said = narration(cues, start, end)
            content.append({"type": "text", "text": f"Narration {mmss(start)}-{mmss(end)}: "
                                                    + (said or "(silence)")})
        start = end
    content.append({"type": "text", "text": (
        f"The material above runs from 0:00 to {mmss(cut)}. At {mmss(float(sample['question_time']))} "
        f"the viewer asked:\n{sample['question']}")})
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]


def split_lines(answer: str) -> list[str]:
    """Sentences, so that the judge can point at the one that states an item."""
    lines = []
    for paragraph in answer.splitlines():
        lines += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", paragraph) if s.strip()]
    return lines


class Stall(Exception):
    """The request was cancelled by the guard: the server did not schedule it."""


class Guard:
    """Cancels this run's requests that have not started answering while the server's queue is
    blocked (see the module docstring)."""

    def __init__(self, base_url: str):
        self.metrics_url = base_url.rsplit("/v1", 1)[0] + "/metrics"
        self.unstarted: dict[str, tuple[asyncio.Task, float]] = {}
        self.stalled: set[str] = set()

    @staticmethod
    def metric(text: str, name: str) -> float:
        return sum(float(line.rsplit(" ", 1)[1]) for line in text.splitlines()
                   if line.startswith(name + "{"))

    def cancel(self, why: str) -> None:
        for name, (request, _) in list(self.unstarted.items()):
            if why == "blocked" or time.time() - self.unstarted[name][1] > FIRST_TOKEN_SECONDS:
                print(f"[{name}] cancelled: {why}", flush=True)
                self.stalled.add(name)
                self.unstarted.pop(name, None)
                request.cancel()

    async def watch(self, client) -> None:
        last, since = None, None
        while True:
            await asyncio.sleep(10)
            try:
                text = (await client.get(self.metrics_url, timeout=10)).text
            except Exception:  # noqa: BLE001 - a missed poll is not a stall
                continue
            waiting = self.metric(text, "vllm:num_requests_waiting")
            # the tokens scheduled minus the tokens generated: the prefill done since the last poll
            prefill = (self.metric(text, "vllm:iteration_tokens_total_sum")
                       - self.metric(text, "vllm:generation_tokens_total"))
            moving = last is None or prefill - last > 0
            last = prefill
            since = (since or time.time()) if waiting > 0 and not moving else None
            if since and time.time() - since >= STALL_SECONDS and self.unstarted:
                self.cancel("blocked")
                since = None
            self.cancel("no answer after %d s" % FIRST_TOKEN_SECONDS)


async def stream(client, args, guard: Guard, task: str, body: dict) -> dict:
    """One streamed request; the reply put together as a non-streamed one would be."""
    content, reasoning, finish, usage = [], [], None, None
    async with client.stream("POST", f"{args.base_url}/chat/completions", json=body,
                             headers={"Authorization": f"Bearer {args.api_key}"}) as response:
        if response.status_code != 200:
            await response.aread()
            response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data:") or line.strip() == "data: [DONE]":
                continue
            guard.unstarted.pop(task, None)
            chunk = json.loads(line[5:])
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                content.append(delta.get("content") or "")
                reasoning.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
                finish = choice.get("finish_reason") or finish
    return {"content": "".join(content), "reasoning": "".join(reasoning), "finish_reason": finish,
            "usage": usage}


async def run_task(client, args, guard: Guard, sample: dict, run: int, cache: Path) -> dict:
    task = ec.task_name(sample["id"], run)
    seed = int(hashlib.sha256(task.encode()).hexdigest()[:8], 16)
    cut = cut_of(sample)
    messages = await asyncio.to_thread(build_messages, sample, cut, cache, not args.no_narration)
    body = {"model": args.model, "messages": messages, "max_tokens": MAX_TOKENS, "seed": seed,
            "stream": True, "stream_options": {"include_usage": True}, **SAMPLING}
    started = time.time()
    salted = False
    for attempt in range(2):
        if attempt:  # the retry of a stalled request: no prefix cache, prefill from the start
            body["cache_salt"] = uuid.uuid4().hex
            salted = True
        request = asyncio.create_task(stream(client, args, guard, task, body))
        guard.unstarted[task] = (request, time.time())
        try:
            reply = await request
            break
        except asyncio.CancelledError:
            if task not in guard.stalled:
                raise
            guard.stalled.discard(task)
        finally:
            guard.unstarted.pop(task, None)
    else:
        raise Stall("not scheduled by the server, also with a cache salt")
    answer = reply["content"].strip()
    responses = [{"t": cut, "content": line, "utterance_id": 0, "is_utterance_complete": True}
                 for line in split_lines(answer)]
    return {
        "task": task, "sample_id": sample["id"], "video": sample["video"]["youtube_id"], "run": run,
        "seed": seed, "question_time": sample["question_time"], "stream": [0.0, cut],
        "audio": False, "narration": not args.no_narration, "fps": 1.0,
        "seconds": round(time.time() - started, 1), "cache_salt": salted,
        "finished": datetime.now(timezone.utc).isoformat(), "host": socket.gethostname(),
        "finish_reason": reply["finish_reason"], "usage": reply["usage"],
        "answer": answer, "reasoning_chars": len(reply["reasoning"]), "responses": responses,
    }


async def run_all(args, todo: list, responses_dir: Path, cache: Path) -> int:
    import httpx

    guard = Guard(args.base_url)
    gate = asyncio.Semaphore(args.workers)
    # HTTP(S)_PROXY in this environment would route even 127.0.0.1 through the proxy
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(None, connect=30)) as client:
        watcher = asyncio.create_task(guard.watch(client))

        async def one(sample, run):
            async with gate:
                try:
                    return ec.task_name(sample["id"], run), await run_task(
                        client, args, guard, sample, run, cache), None
                except Exception as exc:  # noqa: BLE001 - one failure must not stop the others
                    return ec.task_name(sample["id"], run), None, (exc, traceback.format_exc())

        failed = 0
        jobs = [asyncio.create_task(one(s, k)) for s, k in todo]
        for i, job in enumerate(asyncio.as_completed(jobs), 1):
            task, result, error = await job
            if error:
                failed += 1
                (responses_dir / f"{task}.error.json").write_text(json.dumps(
                    {"task": task, "error": repr(error[0]), "traceback": error[1]},
                    indent=1), encoding="utf-8")
                print(f"[{task}] failed: {error[0]!r}", flush=True)
                continue
            (responses_dir / f"{task}.error.json").unlink(missing_ok=True)
            (responses_dir / f"{task}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            usage = result.get("usage") or {}
            print(f"[{i}/{len(jobs)}] {task}: {result['seconds']:.0f} s, prompt "
                  f"{usage.get('prompt_tokens')}, completion {usage.get('completion_tokens')}, "
                  f"{result['finish_reason']}, {len(result['responses'])} lines"
                  + (", cache salt" if result["cache_salt"] else ""), flush=True)
        watcher.cancel()
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--videos", nargs="*")
    parser.add_argument("--samples", nargs="*")
    parser.add_argument("--status", nargs="*", default=["validated"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="dummy")
    parser.add_argument("--model", default="local", help="the served model name")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--no-narration", action="store_true", help="video only")
    args = parser.parse_args()

    out = args.out if args.out.is_absolute() else ec.ROOT / args.out
    responses_dir = out / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    cache = out / "segments"
    samples = ec.select_samples(args.videos, tuple(args.status), args.samples)
    config = {"mode": "offline", "model": args.model, "base_url": args.base_url, "runs": args.runs,
              "status": args.status, "samples": [s["id"] for s in samples],
              "material": f"0 s to the last window's t_end + {CUT_PAD_SECONDS:g} s, "
                          f"{SEGMENT_SECONDS}-s video segments at 1 fps, 640x360",
              "narration": not args.no_narration, "system_prompt": SYSTEM_PROMPT,
              "sampling": SAMPLING, "max_tokens": MAX_TOKENS}
    (out / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")

    # the runs of one sample and the samples of one video next to each other: the prefix cache
    todo = [(s, k) for s in sorted(samples, key=lambda s: (s["video"]["youtube_id"], cut_of(s)))
            for k in range(args.runs)
            if not (responses_dir / f"{ec.task_name(s['id'], k)}.json").exists()]
    print(f"{len(samples)} samples, {len(todo)} tasks to run", flush=True)
    failed = asyncio.run(run_all(args, todo, responses_dir, cache))
    print(f"done: {len(todo) - failed} answered, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

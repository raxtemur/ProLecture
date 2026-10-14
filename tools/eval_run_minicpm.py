#!/usr/bin/env python3
"""Run MiniCPM-o 4.5 (duplex, through the SPECTRA adapter) on the measured samples and save
what it said, untouched: the judge and the metrics are separate steps (eval_judge.py,
eval_score.py).

One duplex session per sample and run. The stream starts at 0 s (eval_common.stream_bounds),
the question is injected at `question_time`, frames come at 1 fps with the lecture's audio, and
the model decides itself when to speak. It samples (temperature 0.7, top-p 0.8), so the runs of
one sample differ; each run's seed follows from its name, so a rerun of one task repeats it.

    $ENV_PY tools/eval_run_minicpm.py --out data/eval/minicpmo45/2026-10-14 --runs 3

Every task is `<sample_id>.r<run>` and lands in `<out>/responses/<task>.json`; a task whose
file exists is skipped, so a restarted job goes on where it stopped. Workers sharing `--out` —
on one GPU, on several, or in several jobs at once — take tasks through `<task>.claim` files.
A worker touches its claim every minute; a claim untouched for STALE_CLAIM_SECONDS was left by
a worker that died or was preempted, and the next worker takes the task over. A failed task
leaves `<task>.error.json` and is retried by the next start.

The interpreter is the model's environment (torch, transformers, decord, librosa), not base
conda: /workspace-SR004.nfs2/abdullaeva/envs/abdullaeva_video_env/bin/python.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_common as ec  # noqa: E402

SPECTRA_ROOT = Path(os.environ.get("SPECTRA_ROOT", "/workspace-SR004.nfs2/abdullaeva/video-llm/Streaming/SPECTRA"))
CHECKPOINT = Path(os.environ.get("MINICPM_CHECKPOINT",
                                 "/workspace-SR004.nfs2/abdullaeva/video-llm/Streaming/MiniCPM-o-4_5"))

# The notebook's prompt, unchanged: the participant is told only to answer once it can.
SYSTEM_PROMPT = (
    "You are an AI assistant for real-time video stream question answering. "
    "Answer each question as soon as the video and audio observed so far "
    "contain enough information to support an answer. "
    "If a question cannot yet be answered, or no question is "
    "currently active keep silent."
)


def model_config(audio: bool, fps: float) -> dict:
    return {
        "model_name": "minicpmo45-duplex",
        "model_type": "minicpmo45_duplex",
        "checkpoint_path": str(CHECKPOINT),
        "device": "cuda",
        "session_mode": "per_question",
        # the Omni chunk stream injects the question as OmniChunk.question_text
        "modality": "video_audio",
        "default_system_prompt": SYSTEM_PROMPT,
        "inference": {
            "fps": fps,
            "load_audio": audio,
            "max_new_speak_tokens": 256,
            "basic_window_high_tokens": 8_000,
            "basic_window_low_tokens": 6_000,
        },
    }


def seed_of(task: str) -> int:
    return int(hashlib.sha256(task.encode()).hexdigest()[:8], 16)


STALE_CLAIM_SECONDS = 600
HEARTBEAT_SECONDS = 60
MAX_IDLE_SECONDS = 2400  # longer than the longest task: a waiting worker outlasts a live one


def claim(path: Path) -> bool:
    try:
        if time.time() - path.stat().st_mtime > STALE_CLAIM_SECONDS:
            # its worker is gone; two workers taking it over at once may both run it, which
            # costs time only: the answer file is written atomically
            path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.write(fd, f"{socket.gethostname()} pid {os.getpid()} {datetime.now(timezone.utc).isoformat()}\n".encode())
    os.close(fd)
    return True


class Heartbeat:
    """Touches a claim while its task runs, so that other workers see it is alive."""

    def __init__(self, path: Path):
        self.path, self.stop = path, threading.Event()
        self.thread = threading.Thread(target=self.beat, daemon=True)

    def beat(self):
        while not self.stop.wait(HEARTBEAT_SECONDS):
            try:
                os.utime(self.path)
            except FileNotFoundError:
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")  # two writers never share it
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


class Runner:
    """The model, loaded once per worker on the first task that needs it."""

    def __init__(self, config: dict):
        for path in (SPECTRA_ROOT / "src", SPECTRA_ROOT / "scripts"):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        import numpy as np
        import torch
        from _eval_common import make_chunk_stream
        from spectra.models.minicpmo45_duplex import MiniCPMO45DuplexModel
        from spectra.runtime.loop import run_record
        from spectra.schema import BenchmarkRecord, response_to_dict

        self.np, self.torch = np, torch
        self.make_chunk_stream, self.run_record = make_chunk_stream, run_record
        self.BenchmarkRecord, self.response_to_dict = BenchmarkRecord, response_to_dict
        self.config = config
        self.model = MiniCPMO45DuplexModel.from_config(config)

    def run(self, sample: dict, seed: int) -> list[dict]:
        random.seed(seed)
        self.np.random.seed(seed)
        self.torch.manual_seed(seed)
        self.torch.cuda.manual_seed_all(seed)
        start, end = ec.stream_bounds(sample)
        record = self.BenchmarkRecord(
            record_id=sample["id"],
            video_path=str(ec.video_path(sample)),
            instruction=sample["question"],
            triggers=[],  # duplex decides itself when to speak
            source_benchmark="manim_play",
            task_name=sample["act"],
            question_inject_t=float(sample["question_time"]),
            stream_start_t=start,
            stream_end_t=end,
            inference_strategy="per_question",
            stop_on_first_response=False,
        )
        responses = self.run_record(record, self.model, self.make_chunk_stream(record, self.config))
        return [self.response_to_dict(r) for r in responses if (r.content or "").strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--out", required=True, type=Path,
                        help="the run's folder, e.g. data/eval/minicpmo45/<date>")
    parser.add_argument("--runs", type=int, default=3, help="sessions per sample")
    parser.add_argument("--videos", nargs="*", help="default: every annotated video but the archived pilot")
    parser.add_argument("--samples", nargs="*", help="only these sample ids")
    parser.add_argument("--status", nargs="*", default=["validated"])
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--no-audio", action="store_true", help="frames only, as the notebook ran")
    parser.add_argument("--list", action="store_true", help="print the tasks and their state, run nothing")
    args = parser.parse_args()

    samples = ec.select_samples(args.videos, tuple(args.status), args.samples)
    config = model_config(audio=not args.no_audio, fps=args.fps)
    out = args.out if args.out.is_absolute() else ec.ROOT / args.out
    responses_dir = out / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    meta = out / "config.json"
    if not meta.exists():
        write_json(meta, {"model": config, "runs": args.runs, "status": args.status,
                          "stream": "from 0 s to the last t_end + %.0f s" % ec.POST_PAD_SECONDS,
                          "samples": [s["id"] for s in samples]})

    # longest streams first, so that the workers finish together
    tasks = sorted(((s, k) for s in samples for k in range(args.runs)),
                   key=lambda task: -ec.stream_bounds(task[0])[1])
    if args.list:
        for sample, k in tasks:
            name = ec.task_name(sample["id"], k)
            state = ("done" if (responses_dir / f"{name}.json").exists() else
                     "claimed" if (responses_dir / f"{name}.claim").exists() else
                     "failed" if (responses_dir / f"{name}.error.json").exists() else "todo")
            print(f"{name}\t{ec.stream_bounds(sample)[1]:.0f} s\t{state}")
        return 0

    runner = None
    done = failed = 0
    failed_here: set[str] = set()  # retried by the next start, not by this worker
    idle_since = None
    while True:
        took = waiting = False
        for sample, k in tasks:
            name = ec.task_name(sample["id"], k)
            target = responses_dir / f"{name}.json"
            claim_file = responses_dir / f"{name}.claim"
            if name in failed_here or target.exists():
                continue
            if not claim(claim_file):
                waiting = True  # another worker has it; it may still go stale
                continue
            if target.exists():  # finished by another worker between the check and the claim
                claim_file.unlink(missing_ok=True)
                continue
            if runner is None:
                try:
                    runner = Runner(config)
                except Exception:
                    # a worker that cannot load the model would otherwise fail every task it claims
                    claim_file.unlink(missing_ok=True)
                    print(f"the model did not load:\n{traceback.format_exc()}", flush=True)
                    return 2
            took = True
            seed = seed_of(name)
            started = time.time()
            try:
                with Heartbeat(claim_file):
                    responses = runner.run(sample, seed)
            except Exception:
                write_json(responses_dir / f"{name}.error.json",
                           {"task": name, "error": traceback.format_exc()})
                claim_file.unlink(missing_ok=True)
                failed += 1
                failed_here.add(name)
                print(f"[{name}] failed:\n{traceback.format_exc()}", flush=True)
                continue
            start, end = ec.stream_bounds(sample)
            write_json(target, {
                "task": name, "sample_id": sample["id"], "video": sample["video"]["youtube_id"],
                "run": k, "seed": seed, "question_time": sample["question_time"],
                "stream": [start, end], "audio": not args.no_audio, "fps": args.fps,
                "seconds": round(time.time() - started, 1),
                "finished": datetime.now(timezone.utc).isoformat(), "host": socket.gethostname(),
                "gpu": runner.torch.cuda.get_device_name(), "torch": runner.torch.__version__,
                "responses": responses,
            })
            (responses_dir / f"{name}.error.json").unlink(missing_ok=True)
            claim_file.unlink(missing_ok=True)
            done += 1
            print(f"[{name}] {len(responses)} chunks in {time.time() - started:.0f} s "
                  f"(stream {end - start:.0f} s)", flush=True)
        # The list is scanned again: a task claimed by a worker that was preempted since this
        # one passed it goes stale and is taken over. With nothing to take, the worker waits
        # while others still hold tasks, but not forever: a hung worker keeps its claim alive.
        if took:
            idle_since = None
            continue
        if not waiting:
            break
        idle_since = idle_since or time.time()
        if time.time() - idle_since > MAX_IDLE_SECONDS:
            print("leaving the tasks still claimed to their workers", flush=True)
            break
        time.sleep(HEARTBEAT_SECONDS)
    print(f"worker done: {done} tasks run, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

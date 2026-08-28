#!/usr/bin/env python3
"""Append and validate the coordinator's per-video operational log.

Each line of ``data/reviews/<VIDEO_ID>/coordinator.log`` is one JSON event. The
coordinator is the sole writer; reviewer subagents never touch this file.

Examples::

    python3 tools/coordinator_log.py VIDEO spawn \
        --agent /root/q05_semiblind_r4 --sample-id sample-q05 \
        --role semiblind --iteration 4 --model gpt-5.6-sol \
        --reasoning-effort medium
    python3 tools/coordinator_log.py VIDEO finish \
        --agent /root/q05_semiblind_r4 --status completed \
        --artifact data/reviews/VIDEO/sample-q05/semiblind.4.json \
        --summary "Prior could not answer; t_val=951.0."
    python3 tools/coordinator_log.py VIDEO sample-edit \
        --sample-id sample-q05 --changes "Added one distractor window." \
        --source full_sample.4.json
    python3 tools/coordinator_log.py VIDEO check
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(
    os.environ.get("COORDINATOR_LOG_ROOT", Path(__file__).resolve().parent.parent)
).resolve()
VIDEO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def log_path(video_id: str) -> Path:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("video id must contain only letters, digits, dot, underscore or hyphen")
    return ROOT / "data" / "reviews" / video_id / "coordinator.log"


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def validate_log(path: Path) -> int:
    if not path.exists():
        print(f"log does not exist: {path}", file=sys.stderr)
        return 1

    active: set[str] = set()
    errors: list[str] = []
    launches = finishes = edits = 0

    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue

        event_type = event.get("event")
        agent = event.get("agent")
        if event_type == "spawn":
            launches += 1
            if not agent:
                errors.append(f"line {line_number}: spawn has no agent")
            elif agent in active:
                errors.append(f"line {line_number}: duplicate active launch: {agent}")
            else:
                active.add(agent)
        elif event_type == "finish":
            finishes += 1
            if not agent:
                errors.append(f"line {line_number}: finish has no agent")
            elif agent not in active:
                errors.append(f"line {line_number}: finish without launch: {agent}")
            else:
                active.remove(agent)
        elif event_type == "sample_edit":
            edits += 1
        else:
            errors.append(f"line {line_number}: unknown event: {event_type!r}")

    for agent in sorted(active):
        errors.append(f"launch without finish: {agent}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"log valid: {launches} launches, {finishes} finishes, {edits} sample edits")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("video_id")
    commands = result.add_subparsers(dest="command", required=True)

    spawn = commands.add_parser("spawn", help="record a successful subagent launch")
    spawn.add_argument("--agent", required=True)
    spawn.add_argument("--sample-id", required=True)
    spawn.add_argument("--role", required=True)
    spawn.add_argument("--iteration", required=True, type=int)
    spawn.add_argument("--model", required=True)
    spawn.add_argument("--reasoning-effort", required=True)

    finish = commands.add_parser("finish", help="record a terminal subagent result")
    finish.add_argument("--agent", required=True)
    finish.add_argument("--status", required=True,
                        choices=("completed", "failed", "interrupted"))
    finish.add_argument("--artifact")
    finish.add_argument("--summary", required=True)

    edit = commands.add_parser("sample-edit", help="record an applied sample change")
    edit.add_argument("--sample-id", required=True)
    edit.add_argument("--changes", required=True)
    edit.add_argument("--source", required=True)

    commands.add_parser("check", help="validate JSON and balance launches with finishes")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        path = log_path(args.video_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "check":
        return validate_log(path)

    if args.command == "spawn":
        event = {
            "ts": timestamp(),
            "event": "spawn",
            "agent": args.agent,
            "sample_id": args.sample_id,
            "role": args.role,
            "iteration": args.iteration,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
        }
    elif args.command == "finish":
        event = {
            "ts": timestamp(),
            "event": "finish",
            "agent": args.agent,
            "status": args.status,
            "summary": args.summary,
        }
        if args.artifact:
            event["artifact"] = args.artifact
    else:
        event = {
            "ts": timestamp(),
            "event": "sample_edit",
            "sample_id": args.sample_id,
            "changes": args.changes,
            "source": args.source,
        }

    append_event(path, event)
    print(f"logged {event['event']}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

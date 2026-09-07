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
        --sample-id sample-q05 --changes "Moved t_start of trigger 0 to 704.0." \
        --source full_sample.4.json
    python3 tools/coordinator_log.py VIDEO adjudicate \
        --sample-id sample-q10 --iteration 3 --t-val-a 704.0 --t-s 690.0 \
        --verified no --t-val 704.0 --source semiblind.3.json
    python3 tools/coordinator_log.py VIDEO check

The ``adjudicate`` event records the outcome of the left-boundary check (checklist 2.2,
stages A–C): ``t_val_a`` is the first answer of the semi-blind trajectory that met the
rubric, ``t_s`` the sighted proposal if any, ``verified`` whether the verification probe
met the rubric at ``t_s`` (``yes``/``no``/``na`` when no probe was needed), ``t_val`` the
resulting boundary compared against ``t_start``. The table itself lives in
``coordinator.<ROUND>.md``; the event is the machine-readable summary of it.
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
    launches = finishes = edits = adjudications = 0

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
        elif event_type == "adjudicate":
            adjudications += 1
            errors += [f"line {line_number}: {e}" for e in check_adjudication(event)]
        else:
            errors.append(f"line {line_number}: unknown event: {event_type!r}")

    for agent in sorted(active):
        errors.append(f"launch without finish: {agent}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"log valid: {launches} launches, {finishes} finishes, {edits} sample edits, "
          f"{adjudications} adjudications")
    return 0


def check_adjudication(event: dict) -> list[str]:
    """The arithmetic of stages A-C, so that the log cannot record an unverified boundary move.

    t_val_a is the first answer of the semi-blind trajectory that met the rubric (None if
    none did); t_s the sighted proposal (None if none); verified says whether the
    verification probe met the rubric at t_s. The rules:

    * a sighted proposal earlier than t_val_a — or any proposal when t_val_a is None,
      which is exactly where a proposal is most likely and least checked — must be
      verified: verified is yes or no, never na;
    * verified=yes needs a t_s, and t_val is t_s;
    * verified=no and verified=na leave t_val at t_val_a, None included.
    """
    t_val_a, t_s, t_val = event.get("t_val_a"), event.get("t_s"), event.get("t_val")
    verified = event.get("verified")
    problems = []
    if verified not in ("yes", "no", "na"):
        return [f"verified must be yes, no or na, not {verified!r}"]
    needs_probe = t_s is not None and (t_val_a is None or t_s < t_val_a)
    if needs_probe and verified == "na":
        problems.append("t_s lies before t_val_a (or t_val_a is null) but no verification was run")
    if verified == "yes":
        if t_s is None:
            problems.append("verified=yes without a t_s: nothing was there to verify")
        elif t_val != t_s:
            problems.append("verified=yes but t_val != t_s")
    if verified in ("no", "na") and t_val != t_val_a:
        problems.append(f"verified={verified} but t_val != t_val_a")
    return problems


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

    adj = commands.add_parser("adjudicate",
                              help="record the outcome of the left-boundary check (2.2, stages A-C)")
    adj.add_argument("--sample-id", required=True)
    adj.add_argument("--iteration", required=True, type=int)
    adj.add_argument("--t-val-a", type=float, default=None,
                     help="the first answer of the semi-blind trajectory that met the rubric; omit if none")
    adj.add_argument("--t-s", type=float, default=None, help="the sighted proposal, if any")
    adj.add_argument("--verified", required=True, choices=("yes", "no", "na"),
                     help="did the verification probe meet the rubric at t_s; na when no probe was needed")
    adj.add_argument("--t-val", type=float, default=None,
                     help="the resulting boundary compared against t_start; omit if none")
    adj.add_argument("--source", required=True,
                     help="the semi-blind review the trajectory came from")

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
    elif args.command == "sample-edit":
        event = {
            "ts": timestamp(),
            "event": "sample_edit",
            "sample_id": args.sample_id,
            "changes": args.changes,
            "source": args.source,
        }
    else:
        event = {
            "ts": timestamp(),
            "event": "adjudicate",
            "sample_id": args.sample_id,
            "iteration": args.iteration,
            "t_val_a": args.t_val_a,
            "t_s": args.t_s,
            "verified": args.verified,
            "t_val": args.t_val,
            "source": args.source,
        }

    append_event(path, event)
    print(f"logged {event['event']}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

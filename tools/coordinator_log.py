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
        --sample-id sample-q05 --kind boundary --window 0 \
        --changes "Moved t_start of trigger 0 to 704.0." --source full_sample.4.json
    python3 tools/coordinator_log.py VIDEO note --agent /root/q05_semiblind_r4 \
        --text "Relaunched after HTTP 429 under the same name; the first run left no artifact."
    python3 tools/coordinator_log.py VIDEO adjudicate \
        --sample-id sample-q10 --iteration 3 --t-val-a 704.0 --t-s 690.0 \
        --verified no --t-val 704.0 --source semiblind.3.json
    python3 tools/coordinator_log.py VIDEO check
    python3 tools/coordinator_log.py VIDEO check --final

The log is append-only: a line is never edited or deleted. A wrong or missing record is
repaired by appending a ``note`` that names the agent; ``check`` then tolerates the
unmatched ``spawn`` or ``finish`` of that agent instead of rejecting the log.

``sample-edit`` carries a ``kind`` naming what changed while the participant-visible
question stayed the same (``boundary``, ``rubric``, ``level``, ``timing``, ``metadata``) or
``wording`` when it did not. Each kind names the roles that must be rerun afterwards
(``RERUN_AFTER``, the table in ``docs/prompts/coordinator.md`` §3). A ``boundary`` edit
must name the window it touched with ``--window N``, and a ``rubric`` edit may (one event
per touched window; omit it when every window's rubric changed); the debt is then
``full_windowN`` exactly, so that a review of another window of the same sample cannot
settle it. Without ``--window`` any window review counts (``full_window0`` as
``full_window``), which is right for a wording change — every window runs again anyway —
so ``--window`` is refused for the kinds that do not touch one window. ``check`` lists a missing
rerun as pending and passes; ``check --final`` fails on it. Edits without a kind — the lines
written before the field existed — are not checked.

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


EDIT_KINDS = ("boundary", "rubric", "level", "timing", "metadata", "wording")

# Which roles a sample edit of each kind must be followed by (the table in
# docs/prompts/coordinator.md, section 3). The probes are listed once for "wording": a
# changed question is a new review version and every role runs again.
RERUN_AFTER: dict[str, frozenset[str]] = {
    "boundary": frozenset({"full_window"}),
    "rubric": frozenset({"full_sample", "full_window"}),
    "level": frozenset(),
    "timing": frozenset({"full_sample"}),
    "metadata": frozenset(),
    "wording": frozenset({"semiblind", "probe_text", "probe_vision", "probe_frame",
                          "full_sample", "full_window"}),
}


def base_role(role: str | None) -> str:
    """The role a spawn counts as for the rerun table.

    Window reviews are logged per window (``full_window0``, ``full_window3``); a
    trailing index is dropped so that any of them satisfies a ``full_window`` requirement.
    """
    return re.sub(r"\d+$", "", role or "")


def validate_log(path: Path, final: bool = False) -> int:
    if not path.exists():
        print(f"log does not exist: {path}", file=sys.stderr)
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[tuple[int, dict]] = []
    errors: list[str] = []
    for line_number, raw in enumerate(lines, 1):
        try:
            events.append((line_number, json.loads(raw)))
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")

    # A note that names an agent documents a hole in that agent's spawn/finish pair,
    # wherever in the log the note stands: the repair is appended after the fact.
    noted: set[str] = {e.get("agent") for _, e in events
                       if e.get("event") == "note" and e.get("agent")}

    active: set[str] = set()
    launches = finishes = edits = adjudications = notes = 0
    # kind-tagged edits waiting for their reruns: (line, sample_id, roles still missing)
    pending: list[tuple[int, str, set[str]]] = []

    for line_number, event in events:
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
            role, sample_id = event.get("role") or "", event.get("sample_id")
            for _, edited, missing in pending:
                if edited == sample_id:
                    missing.discard(role)             # full_window3 settles full_window3
                    missing.discard(base_role(role))  # full_window3 settles full_window
        elif event_type == "finish":
            finishes += 1
            if not agent:
                errors.append(f"line {line_number}: finish has no agent")
            elif agent in active:
                active.remove(agent)
            elif agent not in noted:
                errors.append(f"line {line_number}: finish without launch: {agent}")
        elif event_type == "sample_edit":
            edits += 1
            kind = event.get("kind")
            if kind is not None:
                if kind not in RERUN_AFTER:
                    errors.append(f"line {line_number}: unknown edit kind: {kind!r}")
                elif RERUN_AFTER[kind]:
                    required = set(RERUN_AFTER[kind])
                    window = event.get("window")
                    if window is not None and "full_window" in required:
                        required.remove("full_window")
                        required.add(f"full_window{window}")
                    pending.append((line_number, event.get("sample_id", ""), required))
        elif event_type == "adjudicate":
            adjudications += 1
            errors += [f"line {line_number}: {e}" for e in check_adjudication(event)]
        elif event_type == "note":
            notes += 1
            if not event.get("text"):
                errors.append(f"line {line_number}: note has no text")
        else:
            errors.append(f"line {line_number}: unknown event: {event_type!r}")

    for agent in sorted(active - noted):
        errors.append(f"launch without finish: {agent}")

    stale = [f"line {line}: edit of {sample_id} not followed by {', '.join(sorted(missing))}"
             for line, sample_id, missing in pending if missing]
    if final:
        errors += stale
    else:
        for message in stale:
            print(f"pending rerun: {message}", file=sys.stderr)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"log valid: {launches} launches, {finishes} finishes, {edits} sample edits, "
          f"{adjudications} adjudications, {notes} notes"
          + (f", {len(stale)} pending reruns" if stale else ""))
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
    edit.add_argument("--kind", choices=EDIT_KINDS, default=None,
                      help="what changed: boundary, rubric, level, timing, metadata with the "
                           "question text untouched, or wording; decides which roles must rerun")
    edit.add_argument("--window", type=int, default=None,
                      help="index of the trigger a boundary or rubric edit touched; the rerun "
                           "debt is then that window's review, not any window's")
    edit.add_argument("--changes", required=True)
    edit.add_argument("--source", required=True)

    note = commands.add_parser("note", help="append a remark: a reconstruction, an unknown "
                                            "fate, anything the other events cannot say")
    note.add_argument("--text", required=True)
    note.add_argument("--agent", default=None,
                      help="the agent whose spawn/finish pair the note documents; check then "
                           "tolerates that agent's unmatched event")
    note.add_argument("--refers-to", default=None,
                      help="a line number or artifact the note is about")

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

    check = commands.add_parser("check", help="validate JSON and balance launches with finishes")
    check.add_argument("--final", action="store_true",
                       help="also fail on kind-tagged edits whose reruns have not happened")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        path = log_path(args.video_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "check":
        return validate_log(path, final=args.final)

    if args.command == "sample-edit":
        if args.kind == "boundary" and args.window is None:
            print("--kind boundary needs --window: the rerun debt is that window's review, "
                  "not any window's", file=sys.stderr)
            return 2
        if args.window is not None and args.kind not in ("boundary", "rubric"):
            print(f"--window applies to --kind boundary or rubric, not {args.kind!r}",
                  file=sys.stderr)
            return 2

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
        if args.kind:
            event["kind"] = args.kind
        if args.window is not None:
            event["window"] = args.window
    elif args.command == "note":
        event = {"ts": timestamp(), "event": "note", "text": args.text}
        if args.agent:
            event["agent"] = args.agent
        if args.refers_to:
            event["refers_to"] = args.refers_to
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

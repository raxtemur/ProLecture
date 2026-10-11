#!/usr/bin/env python3
"""Append and validate the coordinator's per-video operational log.

Each line of ``data/reviews/<VIDEO_ID>/coordinator.log`` is one JSON event. The
coordinator is the sole writer; reviewer subagents never touch this file.

Examples::

    python3 tools/coordinator_log.py VIDEO spawn \
        --agent q05_semiblind_r4 --sample-id sample-q05 \
        --role semiblind --iteration 4 --model local \
        --reasoning-effort default --workspace .review_ws/VIDEO/q05/semiblind_r4
    python3 tools/coordinator_log.py VIDEO finish \
        --agent q05_semiblind_r4 --status completed \
        --artifact data/reviews/VIDEO/sample-q05/semiblind.4.json \
        --summary "Prior could not answer; t_val=951.0."
    python3 tools/coordinator_log.py VIDEO sample-edit \
        --sample-id sample-q05 --kind boundary --window 0 \
        --changes "Moved t_start of trigger 0 to 212.0." --source full_sample.4.json
    python3 tools/coordinator_log.py VIDEO note --agent q05_semiblind_r4 \
        --text "Relaunched after HTTP 429 under the same name; the first run left no artifact."
    python3 tools/coordinator_log.py VIDEO adjudicate \
        --sample-id sample-q10 --iteration 3 --window 0 --t-val-a 212.0 \
        --t-s 198.0 --t-s-source full_sample --verified no --t-val 212.0 \
        --source semiblind.3.json
    python3 tools/coordinator_log.py VIDEO check
    python3 tools/coordinator_log.py VIDEO check --final

The log is append-only: a line is never edited or deleted. A wrong or missing record is
repaired by appending a ``note`` that names the agent; ``check`` then tolerates the
unmatched ``spawn`` or ``finish`` of that agent instead of rejecting the log, and a relaunch
under the same name (fix list 5, 5.1). ``finish`` refuses an agent that has no open launch
and no such note: a finish written under another name (a thread id) would leave the real
launch open and the log unbalanced.

``sample-edit`` carries a ``kind`` naming what changed while the participant-visible
question stayed the same (``boundary``, ``nudge``, ``rubric``, ``level``, ``timing``,
``metadata``) or ``wording`` when it did not. ``nudge`` is a ``t_start`` or ``t_end``
moved by at most two seconds to a reviewer's own frame measurement; it names its window
like ``boundary`` but owes no rerun. ``evidence_span`` edits are never nudges. Each kind names the roles that must be rerun afterwards
(``RERUN_AFTER``, the table in ``docs/prompts/coordinator.md`` §3). A ``boundary`` edit
must name the window it touched with ``--window N``, and a ``rubric`` edit may (one event
per touched window; omit it when every window's rubric changed); the debt is then
``full_windowN`` exactly, so that a review of another window of the same sample cannot
settle it. Without ``--window`` any window review counts (``full_window0`` as
``full_window``), which is right for a wording change — every window runs again anyway —
so ``--window`` is refused for the kinds that do not touch one window. ``check`` lists a missing
rerun as pending and passes; ``check --final`` fails on it. Edits without a kind — the lines
written before the field existed — are not checked.

``spawn`` accepts only the roles that have a prompt (``ROLE_PROMPTS``), a window review
and a frame probe with the window's index (``full_window0``, ``probe_frame1``). It records
which text the subagent was given: the sha256 of the role's prompt and of
``docs/annotation_checklist.md``, ``git rev-parse HEAD``, and whether either file differs
from that commit. It also records which material: ``--workspace`` names a folder prepared
with ``prepare_review_workspace.py --sample-id``, whose note (``<workspace>.inputs.json``)
says from which version of the record the folder was cut; a launch on a folder whose record
has changed since is refused. The coordinator types none of it.

``finish`` reads the artifact, when one is given: its ``role``, ``sample_id`` and verdict go
into the event next to the summary, which is free text and has drifted from the file (5.3).
For a modality probe it also compares the material the probe was given with what the current
record gives: a probe cut at a window that has moved since measured nothing about the
current windows (5.10). ``check --final`` fails on such a probe until it has been run again.

The ``adjudicate`` event records the outcome of the left-boundary check (checklist 2.2,
stages A–C) for the stretch of one required window (``--window``): ``t_val_a`` is the first
answer of the semi-blind trajectory that met the rubric by the route of the level or a
cheaper one, ``t_s`` a sighted proposal if any and ``t_s_source`` where it came from
(``full_sample``, ``full_windowN``, ``annotation`` for an annotated ``evidence_span`` that
ends early, ``provenance`` for a reference that places the evidence before the window,
``model`` for an evaluated model's early answer), ``verified`` what the
verification probe did at ``t_s`` (``yes`` — met the rubric by the route of the level or a
cheaper one; ``harder`` — only by a harder route; ``no``; ``na`` when no probe was needed),
``t_val`` the resulting boundary. A stretch with several ``t_s`` gets one event per ``t_s``,
and ``t_val`` is the earliest of ``t_val_a`` and the ``t_s`` verified ``yes``. The table
itself lives in ``coordinator.<ROUND>.md``; the event is the machine-readable summary of it.

``sample-edit --span`` marks an edit of a window's ``evidence_span``. It is refused until
that window's stretch has been adjudicated: a span is applied only after it has been checked
against ``t_val`` (checklist 7.5).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_inputs  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("COORDINATOR_LOG_ROOT", REPO)).resolve()
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


EDIT_KINDS = ("boundary", "nudge", "rubric", "level", "timing", "metadata", "wording")

# Which roles a sample edit of each kind must be followed by (the table in
# docs/prompts/coordinator.md, section 3). The probes are listed once for "wording": a
# changed question is a new review version and every role runs again.
RERUN_AFTER: dict[str, frozenset[str]] = {
    "boundary": frozenset({"full_window"}),
    # t_start or t_end moved by two seconds or less to a reviewer's own frame measurement:
    # the reviewer's frames are the verification, no second review is owed (checklist, group 2)
    "nudge": frozenset(),
    "rubric": frozenset({"full_sample", "full_window"}),
    "level": frozenset(),
    # question_time moved by two seconds or less: no second review (definitions.md, "Boundary
    # tolerance"); a larger move is a new version of the question and is logged as "wording"
    "timing": frozenset(),
    "metadata": frozenset(),
    "wording": frozenset({"semiblind", "probe_text", "probe_vision", "probe_frame",
                          "full_sample", "full_window"}),
}


# The prompt each role is launched with. A review can be traced to its text only if the
# launch records it: the runs of 2026-09-21 went on uncommitted prompts, and which version
# a given review saw could no longer be told (fix list 5, item 5.4).
ROLE_PROMPTS: dict[str, str] = {
    "semiblind": "reviewer_semiblind.md",
    "full_sample": "reviewer_full_sample.md",
    "full_window": "reviewer_full_window.md",
    "probe_text": "probe_text.md",
    "probe_vision": "probe_vision.md",
    "probe_frame": "probe_frame.md",
    "probe_full": "probe_full.md",
    "probe_verify": "probe_verify.md",
}
CHECKLIST = "docs/annotation_checklist.md"


# Roles launched once per window: the role carries the window's index.
WINDOW_INDEXED = ("full_window", "probe_frame")


def role_error(role: str) -> str | None:
    """Why a spawn role is refused, or None.

    A bare ``full_window`` used to be accepted, and it settles only a debt on "any window":
    a boundary edit of window 0 then stayed pending although its review existed (5.2). The
    frame probe runs once per required window, on that window's middle, and is named alike.
    """
    if role in WINDOW_INDEXED:
        return f"--role {role} needs the window index: {role}0, {role}1, ..."
    if base_role(role) not in ROLE_PROMPTS or (role != base_role(role)
                                               and base_role(role) not in WINDOW_INDEXED):
        plain = ", ".join(r for r in ROLE_PROMPTS if r not in WINDOW_INDEXED)
        return f"unknown --role {role!r}: use one of {plain}, full_window<N> or probe_frame<N>"
    return None


def role_window(role: str) -> int | None:
    match = re.search(r"(\d+)$", role or "")
    return int(match.group(1)) if match else None


def file_sha(relative: str) -> str:
    return hashlib.sha256((REPO / relative).read_bytes()).hexdigest()


def prompt_version(role: str) -> dict:
    """The fields that tie a launch to the text its subagent read."""
    prompt = f"docs/prompts/{ROLE_PROMPTS[base_role(role)]}"
    version = {"prompt": prompt, "prompt_sha": file_sha(prompt),
               "checklist_sha": file_sha(CHECKLIST), "git_head": None, "prompts_dirty": None}

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True, check=False)

    head = git("rev-parse", "HEAD")
    if head.returncode == 0:
        version["git_head"] = head.stdout.strip()
        # Only these two files: an unrelated edit elsewhere in the tree would mark every
        # launch dirty, and the flag would stop saying anything about the prompt.
        version["prompts_dirty"] = git("diff", "--quiet", "HEAD", "--",
                                       prompt, CHECKLIST).returncode != 0
    return version


def base_role(role: str | None) -> str:
    """The role a spawn counts as for the rerun table.

    Window reviews are logged per window (``full_window0``, ``full_window3``); a
    trailing index is dropped so that any of them satisfies a ``full_window`` requirement.
    """
    return re.sub(r"\d+$", "", role or "")




def read_log(path: Path) -> tuple[list[tuple[int, dict]], list[str]]:
    events: list[tuple[int, dict]] = []
    errors: list[str] = []
    if not path.exists():
        return events, errors
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            events.append((line_number, json.loads(raw)))
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
    return events, errors


def noted_agents(events: list[tuple[int, dict]]) -> set[str]:
    """A note that names an agent documents a hole in that agent's spawn/finish pair,
    wherever in the log the note stands: the repair is appended after the fact."""
    return {e.get("agent") for _, e in events if e.get("event") == "note" and e.get("agent")}


def open_launches(events: list[tuple[int, dict]]) -> dict[str, tuple[int, dict]]:
    """The launches with no finish yet, by agent: the spawn line and event."""
    active: dict[str, tuple[int, dict]] = {}
    for line_number, event in events:
        agent = event.get("agent")
        if event.get("event") == "spawn" and agent:
            active[agent] = (line_number, event)
        elif event.get("event") == "finish" and agent:
            active.pop(agent, None)
    return active


def last_spawn(events: list[tuple[int, dict]], agent: str) -> dict | None:
    found = None
    for _, event in events:
        if event.get("event") == "spawn" and event.get("agent") == agent:
            found = event
    return found


def describe(inputs: dict) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(inputs.items()))


def stale_inputs(spawn: dict) -> str | None:
    """Why a modality probe's material no longer matches the current record, or None.

    Only a launch that recorded its inputs can be checked; the logs written before
    ``--workspace`` existed are not.
    """
    inputs, role = spawn.get("inputs"), base_role(spawn.get("role"))
    if not inputs or role not in review_inputs.STALE_ROLES or not spawn.get("annotations"):
        return None
    try:
        _, record = review_inputs.find_record(REPO, spawn["sample_id"], Path(spawn["annotations"]))
        current = review_inputs.derive_inputs(role, record, spawn.get("window"))
    except (OSError, review_inputs.InputsError) as exc:
        return f"its material cannot be derived from the record any more: {exc}"
    if current != inputs:
        return f"it ran on {describe(inputs)}, the record now gives {describe(current)}"
    return None


def record_statuses(path: Path, events: list[tuple[int, dict]]) -> dict[str, str]:
    """validation.status of every sample the log names, read from the annotation files its
    launches were prepared from, or from data/annotations/<VIDEO_ID>.jsonl."""
    files = {Path(e["annotations"]) for _, e in events if e.get("annotations")}
    files.add(ROOT / "data" / "annotations" / f"{path.parent.name}.jsonl")
    statuses: dict[str, str] = {}
    for file in files:
        try:
            records = review_inputs.read_records(file)
        except (OSError, json.JSONDecodeError):
            continue
        for sample_id, record in records.items():
            status = (record.get("validation") or {}).get("status")
            if status:
                statuses[sample_id] = status
    return statuses


def validate_log(path: Path, final: bool = False) -> int:
    if not path.exists():
        print(f"log does not exist: {path}", file=sys.stderr)
        return 1

    events, errors = read_log(path)
    noted = noted_agents(events)

    active: set[str] = set()
    launches = finishes = edits = adjudications = notes = 0
    # kind-tagged edits waiting for their reruns: (line, sample_id, roles still missing)
    pending: list[tuple[int, str, set[str]]] = []
    # adjudicated stretches: (sample_id, window) -> lines; windowed events by (sample, round, window)
    adjudicated: set[tuple[str, int]] = set()
    stretches: dict[tuple[str, int, int], list[tuple[int, dict]]] = {}
    # the last launch of each probe, by (sample_id, role with its index)
    last_probe: dict[tuple[str, str], tuple[int, dict]] = {}

    for line_number, event in events:
        event_type = event.get("event")
        agent = event.get("agent")
        if event_type == "spawn":
            launches += 1
            if not agent:
                errors.append(f"line {line_number}: spawn has no agent")
            elif agent in active and agent not in noted:
                errors.append(f"line {line_number}: duplicate active launch: {agent}")
            else:
                active.add(agent)
            role, sample_id = event.get("role") or "", event.get("sample_id")
            for _, edited, missing in pending:
                if edited == sample_id:
                    missing.discard(role)             # full_window3 settles full_window3
                    missing.discard(base_role(role))  # full_window3 settles full_window
            if base_role(role) in review_inputs.STALE_ROLES:
                last_probe[(sample_id, role)] = (line_number, event)
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
            if event.get("span") and (event.get("sample_id"), event.get("window")) not in adjudicated:
                errors.append(f"line {line_number}: evidence_span of window {event.get('window')} "
                              f"of {event.get('sample_id')} edited before its stretch was "
                              f"adjudicated: check the span against t_val first "
                              f"(coordinator.md, §6, \"Check every span against t_val\")")
        elif event_type == "adjudicate":
            adjudications += 1
            errors += [f"line {line_number}: {e}" for e in check_adjudication(event)]
            window = event.get("window")
            if window is not None:
                adjudicated.add((event.get("sample_id"), window))
                key = (event.get("sample_id"), event.get("iteration"), window)
                stretches.setdefault(key, []).append((line_number, event))
        elif event_type == "note":
            notes += 1
            if not event.get("text"):
                errors.append(f"line {line_number}: note has no text")
        else:
            errors.append(f"line {line_number}: unknown event: {event_type!r}")

    for (sample_id, iteration, window), rows in stretches.items():
        errors += [f"line {rows[-1][0]}: {sample_id}, round {iteration}, window {window}: {e}"
                   for e in check_stretch([event for _, event in rows])]

    for agent in sorted(active - noted):
        errors.append(f"launch without finish: {agent}")

    statuses = record_statuses(path, events) if final else {}
    rejected = {sample_id for sample_id, status in statuses.items() if status == "rejected"}
    stale = [f"line {line}: edit of {sample_id} not followed by {', '.join(sorted(missing))}"
             for line, sample_id, missing in pending if missing and sample_id not in rejected]
    if final:
        errors += stale
        for (sample_id, role), (line, spawn) in sorted(last_probe.items()):
            if sample_id in rejected:
                continue
            why = stale_inputs(spawn)
            if why:
                errors.append(f"line {line}: {role} of {sample_id} ({spawn.get('agent')}) is "
                              f"stale: {why}. Prepare its workspace again with --sample-id and "
                              f"run {role} anew; its old outcome does not set a flag")
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


VERIFIED = ("yes", "harder", "no", "na")
T_S_SOURCE = re.compile(r"^(full_sample|full_window\d+|annotation|provenance|model)$")


def check_adjudication(event: dict) -> list[str]:
    """The arithmetic of stages A-C for one t_s, so that the log cannot record an unverified
    boundary move.

    t_val_a is the first answer of the semi-blind trajectory that met the rubric by the route
    of the level or a cheaper one (None if none did); t_s a sighted proposal (None if none);
    verified says what the verification probe did at t_s. The rules:

    * a sighted proposal earlier than t_val_a — or any proposal when t_val_a is None,
      which is exactly where a proposal is most likely and least checked — must be
      verified: verified is yes, harder or no, never na;
    * yes and harder need a t_s;
    * an event without a window (the logs before --window) is a whole stretch: yes sets
      t_val to t_s, the rest leave it at t_val_a. A windowed event is one row of its
      stretch, and check_stretch weighs the rows together.
    """
    t_val_a, t_s, t_val = event.get("t_val_a"), event.get("t_s"), event.get("t_val")
    verified = event.get("verified")
    if verified not in VERIFIED:
        return [f"verified must be one of {', '.join(VERIFIED)}, not {verified!r}"]
    problems = []
    needs_probe = t_s is not None and (t_val_a is None or t_s < t_val_a)
    if needs_probe and verified == "na":
        problems.append("t_s lies before t_val_a (or t_val_a is null) but no verification was run")
    if verified in ("yes", "harder") and t_s is None:
        problems.append(f"verified={verified} without a t_s: nothing was there to verify")
    if event.get("window") is None:
        if verified == "yes" and t_s is not None and t_val != t_s:
            problems.append("verified=yes but t_val != t_s")
        if verified in ("no", "na", "harder") and t_val != t_val_a:
            problems.append(f"verified={verified} but t_val != t_val_a")
    elif t_s is not None and not T_S_SOURCE.match(str(event.get("t_s_source") or "")):
        problems.append("a t_s needs its source: full_sample, full_window<N>, annotation, "
                        "provenance or model")
    return problems


def check_stretch(rows: list[dict]) -> list[str]:
    """All rows of one stretch agree: one t_val_a, and t_val the earliest of t_val_a and the
    t_s that the verification probe passed by the route of the level or a cheaper one."""
    t_val_as = {row.get("t_val_a") for row in rows}
    if len(t_val_as) > 1:
        return [f"rows disagree on t_val_a: {sorted(t_val_as, key=str)}"]
    candidates = [t for t in [rows[0].get("t_val_a")] if t is not None]
    candidates += [row["t_s"] for row in rows if row.get("verified") == "yes" and row.get("t_s") is not None]
    expected = min(candidates) if candidates else None
    wrong = sorted({row.get("t_val") for row in rows if row.get("t_val") != expected}, key=str)
    if wrong:
        return [f"t_val {wrong} but the earliest of t_val_a and the t_s verified yes is {expected}"]
    return []


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("video_id")
    commands = result.add_subparsers(dest="command", required=True)

    spawn = commands.add_parser("spawn", help="record a successful subagent launch")
    spawn.add_argument("--agent", required=True)
    spawn.add_argument("--sample-id", required=True)
    spawn.add_argument("--role", required=True)
    spawn.add_argument("--iteration", required=True, type=int)
    spawn.add_argument("--model", required=True)
    spawn.add_argument("--reasoning-effort", required=True)
    spawn.add_argument("--workspace", required=True, type=Path,
                       help="the folder the subagent works in, prepared with "
                            "prepare_review_workspace.py --sample-id; its inputs note is checked "
                            "against the current record")

    finish = commands.add_parser("finish", help="record a terminal subagent result")
    finish.add_argument("--agent", required=True,
                        help="the name the launch was logged with, not a thread id")
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
                      help="index of the trigger the edit touched; for boundary and rubric the "
                           "rerun debt is then that window's review, not any window's")
    edit.add_argument("--span", action="store_true",
                      help="the edit changes the window's evidence_span; refused until that "
                           "window's stretch has been adjudicated")
    edit.add_argument("--changes", required=True)
    edit.add_argument("--source", required=True)

    note = commands.add_parser("note", help="append a remark: a reconstruction, an unknown "
                                            "fate, anything the other events cannot say")
    note.add_argument("--text", required=True)
    note.add_argument("--agent", default=None,
                      help="the agent whose spawn/finish pair the note documents; check then "
                           "tolerates that agent's unmatched event or a relaunch under its name")
    note.add_argument("--refers-to", default=None,
                      help="a line number or artifact the note is about")

    adj = commands.add_parser("adjudicate",
                              help="record the outcome of the left-boundary check (2.2, stages "
                                   "A-C) for one window's stretch, one event per t_s")
    adj.add_argument("--sample-id", required=True)
    adj.add_argument("--iteration", required=True, type=int)
    adj.add_argument("--window", required=True, type=int,
                     help="the required window whose stretch this is")
    adj.add_argument("--t-val-a", type=float, default=None,
                     help="the first answer of the semi-blind trajectory that met the rubric by "
                          "the route of the level or a cheaper one; omit if none")
    adj.add_argument("--t-s", type=float, default=None, help="a sighted proposal, if any")
    adj.add_argument("--t-s-source", default=None,
                     help="where the t_s came from: full_sample, full_window<N>, annotation "
                          "(an annotated evidence_span ending early), provenance (a reference "
                          "placing the evidence before the window) or model")
    adj.add_argument("--verified", required=True, choices=VERIFIED,
                     help="what the verification probe did at t_s: yes (met the rubric by the "
                          "route of the level or a cheaper one), harder (only by a harder "
                          "route), no; na when no probe was needed")
    adj.add_argument("--t-val", type=float, default=None,
                     help="the resulting boundary of the stretch; omit if none")
    adj.add_argument("--source", required=True,
                     help="the semi-blind review the trajectory came from")

    check = commands.add_parser("check", help="validate JSON and balance launches with finishes")
    check.add_argument("--final", action="store_true",
                       help="also fail on kind-tagged edits whose reruns have not happened and "
                            "on probes whose material the record no longer gives")
    return result


def spawn_event(args: argparse.Namespace, events: list[tuple[int, dict]]) -> dict | str:
    """The spawn event, or why the launch is refused."""
    error = role_error(args.role)
    if error:
        return error
    active = open_launches(events)
    if args.agent in active and args.agent not in noted_agents(events):
        return (f"{args.agent} is still open (line {active[args.agent][0]}). Log its finish "
                f"first; to relaunch under the same name after a failed start, first add "
                f"`note --agent {args.agent} --text \"<why>\"`")
    try:
        note = review_inputs.read_sidecar(args.workspace)
        if note.get("sample_id") != args.sample_id:
            raise review_inputs.InputsError(
                f"{args.workspace} was prepared for {note.get('sample_id')}, not {args.sample_id}")
        if note.get("role") != base_role(args.role):
            raise review_inputs.InputsError(
                f"{args.workspace} was prepared for --role {note.get('role')}, not {args.role}")
        window = role_window(args.role) if base_role(args.role) in WINDOW_INDEXED else None
        if window is not None and note.get("window") not in (None, window):
            raise review_inputs.InputsError(
                f"{args.workspace} was cut at window {note.get('window')}, not {window}")
        _, record = review_inputs.find_record(REPO, args.sample_id, Path(note["annotations"]))
        if review_inputs.record_sha(record) != note.get("record_sha"):
            raise review_inputs.InputsError(
                f"{args.sample_id} has changed since {args.workspace} was prepared: prepare it "
                f"again with the same prepare_review_workspace.py command, then launch")
    except (OSError, KeyError, json.JSONDecodeError, review_inputs.InputsError) as exc:
        return str(exc)
    return {
        "ts": timestamp(),
        "event": "spawn",
        "agent": args.agent,
        "sample_id": args.sample_id,
        "role": args.role,
        "iteration": args.iteration,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        **prompt_version(args.role),
        "workspace": str(args.workspace),
        "annotations": note["annotations"],
        "record_sha": note["record_sha"],
        "window": note.get("window"),
        "inputs": note.get("inputs"),
    }


def read_artifact(path: str) -> dict | None:
    for candidate in (Path(path), REPO / path):
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


def finish_event(args: argparse.Namespace, events: list[tuple[int, dict]]) -> tuple[dict | str, list[str]]:
    """The finish event and the warnings to print, or why it is refused."""
    active = open_launches(events)
    if args.agent not in active and args.agent not in noted_agents(events):
        names = ", ".join(sorted(active)) or "none"
        return (f"no open launch named {args.agent!r}. A finish goes under the name its spawn "
                f"was logged with, not under a thread id. Open launches: {names}. If the spawn "
                f"was never logged, add `note --agent {args.agent} --text \"<what happened>\"` "
                f"first"), []
    event = {"ts": timestamp(), "event": "finish", "agent": args.agent,
             "status": args.status, "summary": args.summary}
    warnings: list[str] = []
    spawn = last_spawn(events, args.agent)
    if args.artifact:
        event["artifact"] = args.artifact
        artifact = read_artifact(args.artifact)
        if artifact is None:
            if args.status == "completed":
                warnings.append(f"the artifact {args.artifact} cannot be read: a completed review "
                                f"leaves a valid JSON file — check the path")
        else:
            event["artifact_role"] = artifact.get("role")
            if "verdict" in artifact:
                event["artifact_verdict"] = artifact.get("verdict")
            if spawn is not None:
                mismatch = []
                if artifact.get("role") != base_role(spawn.get("role")):
                    mismatch.append(f"role {artifact.get('role')} (launched as {spawn.get('role')})")
                if artifact.get("sample_id") != spawn.get("sample_id"):
                    mismatch.append(f"sample {artifact.get('sample_id')} "
                                    f"(launched for {spawn.get('sample_id')})")
                if mismatch:
                    event["artifact_mismatch"] = "; ".join(mismatch)
                    warnings.append(f"the artifact does not match the launch: {event['artifact_mismatch']}")
    if spawn is not None:
        why = stale_inputs(spawn)
        if why:
            event["stale_inputs"] = why
            warnings.append(f"{spawn.get('role')} of {spawn.get('sample_id')} is stale: {why}. Its "
                            f"outcome sets no flag: prepare the workspace again with --sample-id "
                            f"and run {spawn.get('role')} anew")
    return event, warnings


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        path = log_path(args.video_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "check":
        return validate_log(path, final=args.final)

    events, _ = read_log(path)
    warnings: list[str] = []
    if args.command == "spawn":
        event = spawn_event(args, events)
    elif args.command == "finish":
        event, warnings = finish_event(args, events)
    elif args.command == "sample-edit":
        if args.kind in ("boundary", "nudge") and args.window is None:
            event = f"--kind {args.kind} needs --window: the edit is to one window's boundary"
        elif args.window is not None and args.kind not in ("boundary", "nudge", "rubric", "metadata"):
            event = f"--window applies to --kind boundary, nudge, rubric or metadata, not {args.kind!r}"
        elif args.span and (args.window is None or args.kind not in ("boundary", "metadata")):
            event = ("--span needs --window and --kind boundary (the derived temporal_rel changes) "
                     "or metadata (it does not); a span edit is never a nudge")
        elif args.span and not any(e.get("event") == "adjudicate" and e.get("sample_id") == args.sample_id
                                   and e.get("window") == args.window for _, e in events):
            event = (f"window {args.window} of {args.sample_id} has no adjudicate event yet: a span "
                     f"is applied only after it has been checked against t_val of its stretch "
                     f"(coordinator.md, §6, \"Check every span against t_val\"). Adjudicate the "
                     f"stretch with --window {args.window}, then apply the span if it agrees")
        else:
            event = {"ts": timestamp(), "event": "sample_edit", "sample_id": args.sample_id,
                     "changes": args.changes, "source": args.source}
            if args.kind:
                event["kind"] = args.kind
            if args.window is not None:
                event["window"] = args.window
            if args.span:
                event["span"] = True
    elif args.command == "note":
        event = {"ts": timestamp(), "event": "note", "text": args.text}
        if args.agent:
            event["agent"] = args.agent
        if args.refers_to:
            event["refers_to"] = args.refers_to
    else:
        if (args.t_s is None) != (args.t_s_source is None):
            event = "--t-s and --t-s-source go together: a sighted proposal names where it came from"
        elif args.t_s_source is not None and not T_S_SOURCE.match(args.t_s_source):
            event = (f"--t-s-source {args.t_s_source!r}: one of full_sample, full_window<N>, "
                     f"annotation, provenance, model")
        else:
            event = {"ts": timestamp(), "event": "adjudicate", "sample_id": args.sample_id,
                     "iteration": args.iteration, "window": args.window,
                     "t_val_a": args.t_val_a, "t_s": args.t_s, "t_s_source": args.t_s_source,
                     "verified": args.verified, "t_val": args.t_val, "source": args.source}
            problems = check_adjudication(event)
            if problems:
                event = "; ".join(problems)

    if isinstance(event, str):
        print(event, file=sys.stderr)
        return 2
    append_event(path, event)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"logged {event['event']}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

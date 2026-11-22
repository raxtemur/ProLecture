#!/usr/bin/env python3
"""Append and validate the coordinator's per-video operational log, and change its records.

Each line of ``data/reviews/<VIDEO_ID>/coordinator.log`` is one JSON event. The
coordinator is the sole writer; reviewer subagents never touch this file.

Examples::

    python3 tools/coordinator_log.py VIDEO spawn \
        --agent 019a2f7c-51d0-7e52-b3a4-0c6f1d2e9a10 --iteration 4 --model local \
        --workspace .review_ws/VIDEO/q05/semiblind_r4
    python3 tools/coordinator_log.py VIDEO finish \
        --agent 019a2f7c-51d0-7e52-b3a4-0c6f1d2e9a10 --status completed \
        --summary "Prior could not answer; t_val=951.0."
    python3 tools/coordinator_log.py VIDEO sample-edit \
        --sample-id sample-q05 --set 'triggers[0].t_start=212.0' --source full_window0.4.json
    python3 tools/coordinator_log.py VIDEO sample-get --sample-id sample-q05
    python3 tools/coordinator_log.py VIDEO sample-edit \
        --sample-id sample-q05 --source full_sample.4.json
    python3 tools/coordinator_log.py VIDEO note --text "The agent service was down for an hour."
    python3 tools/coordinator_log.py VIDEO adjudicate \
        --sample-id sample-q10 --iteration 3 --window 0 --t-val-a 212.0 \
        --t-s 198.0 --t-s-source full_sample --verified no --source semiblind.3.json
    python3 tools/coordinator_log.py VIDEO check
    python3 tools/coordinator_log.py VIDEO check --final
    python3 tools/coordinator_log.py VIDEO open --wait 50

The coordinator learns no flag in advance. What a command can read off the log and the files
it reads itself; a wrong call is refused before anything is written, and the refusal says what
to do, naming a flag only where one is needed.

The log is append-only: a line is never edited or deleted, and every row carries the format it
was written in (``v``; ``data/reviews/README.md``, "Formats of a row"). The rules that changed
how a log reads apply by the row, so a log written before them checks as it did.

``spawn`` is logged under the ``agent_id`` that ``spawn_agent`` returned and takes the folder
the subagent works in (``--workspace``), prepared with ``prepare_review_workspace.py
--sample-id``. The note next to the folder (``<workspace>.inputs.json``) says which sample, role
and window it was cut for and from which version of the record; ``spawn`` takes them from
there, with the window's index in the role (``full_window2``, ``probe_frame1``), and refuses a
folder whose record has changed since. It records which text the subagent was given: the
sha256 of the role's prompt and of ``docs/annotation_checklist.md``, ``git rev-parse HEAD``,
and whether either file differs from that commit. ``--reasoning-effort`` is what the launch
ran with, ``default`` when none was passed. A name is launched again only after an
``interrupted`` or ``failed`` finish, or for the next stretch of the same semi-blind reviewer;
any other new launch has a new name.

A probe measured again is a **repeat**: the same probe of the same sample on the same material
as its last completed launch, with no edit in between after which the probe is owed anyway.
A negative outcome is measured again at most once, and only with a named defect of the
attempt (``coordinator.md`` §3): ``spawn`` refuses a repeat without ``--reason``, refuses a
second one, and refuses a launch while the earlier one on the same material is open. An
interrupted or failed attempt measured nothing and does not count.

``finish`` goes under the name of its ``spawn`` and reads the review file: its ``role``,
``sample_id`` and verdict go into the event next to the summary, which is free text and has
drifted from the file (5.3). ``--artifact`` may be omitted when the launch saved exactly one
file that passes ``schema/review.py --check``; a completed probe must have one. A completed
finish keeps a copy of the review file as it stands (``<sample>/.finished/``, named by its
hash): a repeat writes the same file name, and the first attempt is what the decision to
measure again rests on. For a modality probe ``finish`` also compares the material the probe was given
with what the current record gives: a probe cut at a window that has moved since measured
nothing about the current windows (5.10). ``check --final`` fails on such a probe until it has
been run again. A frame probe cut at a window that is no longer required — the window turned
optional, or the windows were renumbered when an optional one was put before it — is
superseded rather than stale: it cannot be run there again, and it sets no flag. ``check
--final`` then asks only that every required window of the record has a frame probe of its own.

A ``finish`` whose ``spawn`` was never logged restores the launch: from the review file it
takes the role and the sample, finds the prepared folder of that role, sample and window that
no logged launch used and that was cut before the review was saved, and writes the ``spawn``
row (``recovered``) from the folder's note, then the ``finish``. Such a launch settles the
rerun an edit owes only if it ran on the record as that edit left it. With several such
folders the refusal asks for ``--workspace``; with none, the finish is logged with ``material:
"not found"`` — its outcome sets no flag and settles no rerun, and the role is launched again.
A ``note`` repairs nothing: in a log of format 1 a note naming an agent excused that agent's
unmatched ``spawn`` or ``finish``, and it still does there, for rows of format 1 only.

A record is changed only through the tool. ``sample-edit --set <field>=<value>`` changes a
field in place; for a larger edit ``sample-get`` writes the record to a file, the coordinator
edits the file, and ``sample-edit`` applies it. The tool refuses a file taken before another
edit was applied, an edit that adds a validator error, and a change of ``id`` or ``video``; it
reads the kind of each change off the record (``tools/sample_edit.py``: ``boundary``,
``nudge``, ``rubric``, ``level``, ``timing``, ``metadata``, ``wording``), logs one event per
kind and window with the values before and after and the hashes of the record, and only then
writes the record — to a file next to it that replaces the old one in one step, the other
records untouched. Each kind names the roles that must be rerun afterwards (``RERUN_AFTER``,
the table in ``docs/prompts/coordinator.md`` §3); a ``boundary`` or ``rubric`` edit of one
window owes that window's review exactly (``full_window2``). ``check`` lists a missing rerun
as pending and passes; ``check --final`` fails on it. An ``evidence_span`` is applied only
after the stretch of its window has been adjudicated (checklist 7.5). While the video is open
(its records are in ``data/annotations/partial/``), ``check`` compares every record with the
version the log last knew and names one that was changed without the tool (``sample-edit
--adopt`` logs the difference) or left unwritten by an edit that was cut off: the next
``sample-get`` or ``sample-edit`` of that sample writes it first, from the copy of the new
version the tool keeps, so that no row stays in the log for a version that never existed. ``spawn`` and ``sample-edit`` refuse to go on a record that is
not the version the log knows: logged, it would become that version, and the change made
without the tool, with the reviews it owes, would never be recorded.
Edits of format 1 without a kind are not checked.

A row names a window by the number it had when the row was written. An edit that puts a
window before others or removes one logs how the numbers moved (``renumbered``, ``removed``),
and the rows before it are read through that map: the ``adjudicate`` rows of a stretch follow
their window, the rows of a removed window drop out of the check, the window reviews that
earlier edits still owe follow their windows, and a stretch of a semi-blind review is read
under the number its window had at the launch that walked it.

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
and ``t_val`` is the earliest of ``t_val_a`` and the ``t_s`` verified ``yes``. An event may be
logged as soon as its stage is done: its ``t_val`` is then the boundary as it stands after it,
and the stretch's last event holds the final one. The tool derives ``t_val`` itself, a later
row of a stretch without ``--t-val-a`` takes the stretch's, and a row that would not pass the
check of its stretch is refused before it is written, with what to do instead: an append-only
log cannot take a written row back. The table
itself lives in ``coordinator.<ROUND>.md``; the event is the machine-readable summary of it.

The first row of a stretch is stage A, and it is held to the trajectory: it cites the
semi-blind review (``--source semiblind.<ROUND>.json``), its ``t_val_a`` is the moment of an
answer of its window's own stretch there (null only where that stretch was walked), and it is
logged under the round of that review or a round that has a launch. After an edit of format 2
that changes a boundary or the rubric of the window, or the level, stage A is read again: the
next row of the stretch opens a new part of it, weighed by itself, and may move the boundary
either way; ``check`` names every such re-adjudication.

The log is never edited, so a wrong ``adjudicate`` row is corrected by a row logged with
``--correction "<what the earlier rows got wrong>"``: it opens its stretch anew, the earlier rows
stay in the log as history and drop out of the check, and the rows from the correction on are
checked as one stretch. A correction re-reads stage A; it cannot hide what the check is there
for. Its ``t_val_a`` is the moment of an answer of its window's own stretch in the semi-blind
review it cites: a moment that no answer of the stretch has is a ``t_s``, and only stage C
makes a ``t_s`` the boundary. It makes the boundary stricter, never looser: no later than the
earliest answer of the stretch an earlier row logged (for a value logged that is no answer, the
first answer after it), and null only when no such answer exists — an answer wrongly taken as
passing is settled by the next round of review. Every ``t_s`` of the earlier rows is logged
again in the corrected stretch with its source, and until it is, ``check`` lists it as a
pending correction and ``check --final`` fails. One whose probe has run keeps the outcome the
probe gave; one logged unverified gets an outcome only from a ``probe_verify`` of the round
launched at that moment.

``open`` lists the launches that have no finish yet and, for each, whether its subagent has
already saved a review file that passes ``schema/review.py --check``. A completion notice
reaches the coordinator only while its turn lasts and only while the agent tools work; the
file on disk does not depend on either. ``--wait N`` polls for up to N seconds and returns as
soon as one more launch has a valid file. It writes nothing to the log.

``blind-judge`` scores the semi-blind reviewer's answer before viewing (``prior_answer``)
with the evaluation judge, ``tools/eval_judge.py``, against the rubric the record has now, and
logs the verdict with a hash of the required windows' rubric. The judge runs ``JUDGE_RUNS``
times, and an item is met when most runs credit it. The coordinator used to score it
by eye and kept in the primary set answers that met every item
(docs/reports/2026-10-18-objections-audit.md). ``blind-ruling`` records a departure
from the judge with its grounds: ``screen-guess`` or ``video-content`` for an answer the judge
credited, ``repaired`` for an earlier round's answer that took from the old wording what the
new one withholds, ``look-only`` for one whose uncredited items are about the look of the
screen. ``--review`` names the judged round a ruling is about; the last one by default.
``check --final`` fails on a validated sample whose ``blind_solved`` disagrees with the judged
answers of its current rubric and no ruling explains it; one judged answer that met that
rubric and has no ruling against it keeps the flag true whatever a later run answers. A sample
whose last semi-blind launch is from ``BLIND_JUDGE_SINCE`` on must have its latest round
judged, and every answer judged once must be judged again after the rubric changes. A verdict
counts only with ``JUDGE_RUNS`` runs, and an answer is not judged twice by one judge on one
rubric: the verdict cannot be redrawn until it flips.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_inputs  # noqa: E402
import sample_edit  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("COORDINATOR_LOG_ROOT", REPO)).resolve()
VIDEO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def log_path(video_id: str) -> Path:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("video id must contain only letters, digits, dot, underscore or hyphen")
    return ROOT / "data" / "reviews" / video_id / "coordinator.log"


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# The format of a row. A row without "v" is format 1: every row written before 2026-11-22.
# The rules that changed how a log READS apply by the row, never by the date, so that a log
# written before them checks as it did (data/reviews/README.md, "Formats of a row"):
#   * a note names an agent: it excuses an unmatched spawn or finish of format 1 only, and
#     only a note of format 1 does;
#   * a sample_edit of format 2 that changes a boundary, a rubric or the level closes the
#     adjudicated stretch of its window (a re-adjudication follows it);
#   * the hash of a record is compared with the one the log knows only from rows of format 2.
FORMAT = 2


def is_new(event: dict) -> bool:
    return isinstance(event.get("v"), int) and event["v"] >= 2


def append_event(path: Path, event: dict | list[dict]) -> None:
    """Append a row, or the rows of one command — an edit of several kinds, a restored spawn
    with its finish — in a single write: a failure half-way must not leave a part of them,
    with the reviews the other rows owe never recorded."""
    rows = event if isinstance(event, list) else [event]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:  # appends go to the end whatever the read position
        size = stream.seek(0, os.SEEK_END)
        cut = False
        if size:
            stream.seek(size - 1)
            cut = stream.read(1) != b"\n"
        # a line cut off by a failed write stays as it is; the new row starts a line of its own
        lines = "".join(json.dumps({**row, "v": FORMAT}, ensure_ascii=False,
                                   separators=(",", ":")) + "\n" for row in rows)
        stream.write((("\n" if cut else "") + lines).encode("utf-8"))


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
# The roles whose outcome sets a flag or verifies a boundary: a negative outcome is measured
# again at most once, and only with a named defect of the attempt (coordinator.md §3).
PROBES = ("probe_text", "probe_vision", "probe_frame", "probe_full", "probe_verify")
# What a launch may have run with; "default" when the launch tool was given no effort.
EFFORTS = ("default", "none", "minimal", "low", "medium", "high", "xhigh")


# A semi-blind launch from this day on owes a judge verdict on its blind answer; the logs
# written before blind-judge existed are checked only where a verdict was logged.
BLIND_JUDGE_SINCE = "2026-10-19"
# What a blind-ruling may say, and the flag it gives (coordinator.md, "Blind solving").
RULING_BASES = {"screen-guess": False, "video-content": False, "repaired": False,
                "look-only": True}
JUDGE_URL = "http://127.0.0.1:8000/v1"
# The judge is not deterministic on a borderline answer even at temperature 0 (batched vLLM):
# one answer of 2026-10-19 was credited in three runs of four. An item is met when most runs
# credit it.
JUDGE_RUNS = 3


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
    """In a log of format 1, a note that names an agent documents a hole in that agent's
    spawn/finish pair, wherever the note stands. A note of format 2 excuses nothing: a missed
    spawn is restored by finish, and a launch that did not start is finished as failed."""
    return {e.get("agent") for _, e in events
            if e.get("event") == "note" and e.get("agent") and not is_new(e)}


def excused(event: dict, noted: set[str]) -> bool:
    """Whether a note covers this unmatched spawn or finish: rows of format 1 only."""
    return not is_new(event) and event.get("agent") in noted


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
        _, record = review_inputs.find_logged_record(ROOT, spawn["sample_id"], spawn["annotations"])
        current = review_inputs.derive_inputs(role, record, spawn.get("window"))
    except (OSError, review_inputs.InputsError) as exc:
        return f"its material cannot be derived from the record any more: {exc}"
    if current != inputs:
        return f"it ran on {describe(inputs)}, the record now gives {describe(current)}"
    return None


def record_windows(spawn: dict) -> tuple[set[int], set[int]] | None:
    """The indices of all windows and of the required ones in the record a launch was
    prepared from, as the record stands now; None when it cannot be read."""
    try:
        _, record = review_inputs.find_logged_record(ROOT, spawn["sample_id"], spawn["annotations"])
    except (OSError, KeyError, review_inputs.InputsError):
        return None
    triggers = record.get("triggers", [])
    return {t.get("idx") for t in triggers}, {t.get("idx") for t in triggers if t.get("required")}


def superseded_frame_probe(spawn: dict, last_probe: dict[tuple[str, str], tuple[int, dict]]
                           ) -> tuple[bool, str | None]:
    """Whether a frame probe was cut at a window that is no longer required, and if so,
    what is still owed: the required windows that have no frame probe of their own.

    The frame probe runs on required windows only (review_inputs.window_trigger), so one cut
    at a window that has since turned optional, or that went away when the windows were
    renumbered, cannot be run there again; the probe of the window that is required now
    replaces it. Asking for a rerun of the old one sent the coordinators of two videos round
    three turns for a launch the tool itself refuses.
    """
    window, role = role_window(spawn.get("role") or ""), base_role(spawn.get("role"))
    if role != "probe_frame" or window is None or not spawn.get("inputs"):
        return False, None
    windows = record_windows(spawn)
    if windows is None or window in windows[1]:
        return False, None
    every, required = windows
    owed = sorted(w for w in required if (spawn["sample_id"], f"probe_frame{w}") not in last_probe)
    if not owed:
        return True, None
    now = "is optional now" if window in every else "the record no longer has"
    names = ", ".join(f"probe_frame{w}" for w in owed)
    return True, (f"it was cut at window {window}, which {now}, so it sets no flag and cannot "
                  f"be run there again; required window(s) {', '.join(map(str, owed))} have no "
                  f"frame probe of their own. Prepare a workspace with --sample-id --role "
                  f"probe_frame --window <idx> and run {names}")


def record_statuses(path: Path, events: list[tuple[int, dict]]) -> dict[str, str]:
    """validation.status of every sample the log names, read from the annotation files its
    launches were prepared from, or from data/annotations/<VIDEO_ID>.jsonl."""
    files = {review_inputs.locate(ROOT, e["annotations"]) for _, e in events if e.get("annotations")}
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


def rubric_sha(record: dict) -> str:
    """What a blind answer has to contain: the rubric of the required windows, in order. A
    rewrite that keeps it asks for the same answer, however the question is worded."""
    rubrics = [t.get("rubric") or [] for t in sorted(record.get("triggers", []),
                                                    key=lambda t: t.get("idx", 0))
               if t.get("required", True)]
    return hashlib.sha256(json.dumps(rubrics, ensure_ascii=False).encode("utf-8")).hexdigest()


def current_record(sample_id: str, events: list[tuple[int, dict]]) -> dict | None:
    """The record as it stands now; None when it cannot be read."""
    found = record_file(sample_id, events)
    return found[1] if found else None


def judge_answer(record: dict, answer: str, base_url: str, model: str) -> dict:
    """The evaluation judge's verdict on one answer, as eval_judge.py gives it for a model's
    output: the answer is one line at question_time."""
    import httpx
    from openai import OpenAI
    import eval_judge

    local = base_url.split("//")[-1].split(":")[0].split("/")[0] in ("127.0.0.1", "localhost")
    client = OpenAI(base_url=base_url, api_key=os.environ.get("VLLM_API_KEY") or "dummy",
                    timeout=900, http_client=httpx.Client(trust_env=not local, timeout=900))
    saved = {"task": f"{record['id']}.blind", "run": 0,
             "responses": [{"t": float(record.get("question_time") or 0.0),
                            "content": answer}]}
    return eval_judge.judge_task(client, model, record, saved)


def review_key(name: str) -> str:
    """A review file as the log names it: relative to the root, whichever way it was given, so
    that one answer is one answer."""
    path = Path(name)
    if not path.is_absolute():
        path = path if path.exists() else ROOT / path
    return portable_path(path.resolve())


def judge_runs(event: dict) -> int:
    """How many runs of the judge a verdict pooled; the first majority verdicts were logged
    without the field, and their votes ("2/3") say it."""
    if isinstance(event.get("runs"), int):
        return event["runs"]
    try:
        return min(int(str(vote).split("/")[1]) for vote in event["votes"].values())
    except (KeyError, AttributeError, IndexError, ValueError):
        return 1


def counts(event: dict) -> bool:
    """A verdict counts when it pooled JUDGE_RUNS runs of the judge. The verdicts of a single
    run, logged before the majority existed, do not: a single run flips on a borderline item."""
    return (event.get("event") == "blind_judge" and isinstance(event.get("met"), bool)
            and judge_runs(event) >= JUDGE_RUNS)


def blind_judge_event(args: argparse.Namespace, events: list[tuple[int, dict]],
                      video_id: str) -> dict | str:
    """The judge's verdict on a saved blind answer, or why it cannot be had."""
    key = review_key(args.review)
    try:
        review = json.loads((ROOT / key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"cannot read the semi-blind review {args.review}: {exc}"
    if review.get("role") != "semiblind" or review.get("sample_id") != args.sample_id:
        return (f"{args.review} is a {review.get('role')} review of {review.get('sample_id')}: "
                f"give the semiblind.<round>.json of {args.sample_id}")
    answer = (review.get("prior_answer") or "").strip()
    if not answer:
        return (f"{args.review} has no prior_answer: send the semi-blind reviewer back for the "
                f"content of its answer (coordinator.md, \"Blind solving\"), then judge it")
    record = current_record(args.sample_id, events)
    if record is None:
        return f"the record {args.sample_id} cannot be read from the annotation files"
    try:
        import httpx  # noqa: F401
        import openai
        import eval_judge
    except ImportError as exc:
        return (f"the judge cannot be loaded ({exc}): run coordinator_log.py with "
                f"/home/user/conda/bin/python3")
    sha = rubric_sha(record)
    for line, event in events:
        if (counts(event) and event.get("sample_id") == args.sample_id
                and review_key(str(event.get("review"))) == key
                and event.get("rubric_sha") == sha
                and event.get("judge_prompt") == eval_judge.PROMPT_VERSION):
            return (f"{key} is judged already on this rubric by this judge (line {line}). A "
                    f"verdict is not drawn again: it is redone only when the rubric or the judge "
                    f"changes. Decide from that verdict")
    runs = []
    for _ in range(JUDGE_RUNS):  # one after another: runs batched together tend to agree
        try:
            runs.append(judge_answer(record, answer, args.base_url, args.model))
        except RuntimeError as exc:
            return f"the judge's answer could not be read ({exc}): run blind-judge again"
        except (openai.OpenAIError, OSError) as exc:
            return (f"the judge at {args.base_url} gave no verdict: {exc}. It is the vLLM server "
                    f"you run on; check that it answers (curl {args.base_url}/models). Do not "
                    f"set blind_solved until the judge has run")
    required = [item["id"] for item in runs[0]["items"] if item["required"]]
    votes = {iid: sum(any(i["id"] == iid and i["correct"] and not i["wrong"] for i in run["items"])
                      for run in runs) for iid in required}
    met = [iid for iid in required if 2 * votes[iid] > JUDGE_RUNS]
    label = re.search(r"semiblind\.(\d+[a-z]?)\.json$", key)
    label = label.group(1) if label else str(review.get("iteration"))
    saved = (ROOT / "data" / "reviews" / video_id / args.sample_id
             / f"blind_judge.{label}.{sha[:8]}.{eval_judge.PROMPT_VERSION}.json")
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"review": key, "answer": answer, "rubric_sha": sha,
                                 "votes": votes, "runs": runs}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return {"ts": timestamp(), "event": "blind_judge", "sample_id": args.sample_id,
            "review": key, "iteration": review.get("iteration"), "rubric_sha": sha,
            "judge_model": args.model, "judge_prompt": eval_judge.PROMPT_VERSION,
            "runs": JUDGE_RUNS, "met": bool(required) and len(met) == len(required),
            "items_met": met, "items_unmet": [i for i in required if i not in met],
            "votes": {iid: f"{n}/{JUDGE_RUNS}" for iid, n in votes.items()},
            "result": portable_path(saved)}


def portable_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def verdicts_on(sample_id: str, events: list[tuple[int, dict]], sha: str
                ) -> list[tuple[int, dict]]:
    """The judge's verdicts on the sample's blind answers against the rubric with this hash,
    in the order of the semi-blind rounds: the last one for each review, since an answer judged
    again (after a fix of the judge or of the rubric) is judged anew. Only the verdicts that
    count (``counts``)."""
    last = {}
    for line_number, event in events:
        if counts(event) and event.get("sample_id") == sample_id and event.get("rubric_sha") == sha:
            last[review_key(str(event.get("review")))] = (line_number, event)

    def round_order(verdict: tuple[int, dict]) -> tuple[int, int]:
        iteration = str(verdict[1].get("iteration"))
        return (int(iteration) if iteration.isdigit() else 0, verdict[0])

    return sorted(last.values(), key=round_order)


def blind_ruling_event(args: argparse.Namespace, events: list[tuple[int, dict]]) -> dict | str:
    """A departure from the judge, checked against its last verdict on the current rubric."""
    record = current_record(args.sample_id, events)
    if record is None:
        return f"the record {args.sample_id} cannot be read from the annotation files"
    verdicts = verdicts_on(args.sample_id, events, rubric_sha(record))
    if not verdicts:
        return (f"{args.sample_id} has no judge verdict on its current rubric: run blind-judge "
                f"first; a ruling departs from a verdict")
    chosen = [v for v in verdicts
              if args.review is None or review_key(str(v[1].get("review"))) == review_key(args.review)]
    if not chosen:
        reviews = ", ".join(sorted({str(e.get("review")) for _, e in verdicts}))
        return (f"no judge verdict on the current rubric for {args.review}; the judged rounds "
                f"are {reviews}")
    line, judged = chosen[-1]
    items = [item.strip() for item in args.items.split(",") if item.strip()]
    solved = RULING_BASES[args.basis]
    if args.basis == "repaired" and chosen[-1] == verdicts[-1]:
        return ("repaired is a ruling on an earlier round's answer, once the new wording has its "
                "own judged round: run blind-judge on the new round's review, then rule on the "
                "old one with --review")
    if not solved and not judged["met"]:
        return (f"the judge did not credit the blind answer (line {line}, unmet: "
                f"{', '.join(judged['items_unmet'])}), so blind_solved is false without a ruling")
    if solved and judged["met"]:
        return f"the judge credited every required item (line {line}): blind_solved is true already"
    pool = judged["items_met"] if not solved else judged["items_unmet"]
    stray = [item for item in items if item not in pool]
    if solved and not stray and set(items) != set(pool):
        return (f"look-only names every item the judge did not credit (line {line}): "
                f"{', '.join(pool)}. If one of them is substantive, the flag stays false and no "
                f"ruling is needed")
    if not items or stray:
        which = "credited" if not solved else "did not credit"
        return (f"--items must name the items the judge {which} (line {line}): "
                f"{', '.join(pool)}; {', '.join(stray) or 'none given'} is not among them")
    if len(args.text.strip()) < 20:
        return ("--text gives the grounds: the alternative screen content and the answer under "
                "it, the content only this video has, what the old wording gave that the new one "
                "withholds, or why the uncredited items are about the look of the screen only")
    return {"ts": timestamp(), "event": "blind_ruling", "sample_id": args.sample_id,
            "judge_line": line, "basis": args.basis, "solved": solved, "items": items,
            "text": args.text.strip()}


def blind_errors(video_id: str, events: list[tuple[int, dict]], statuses: dict[str, str]
                 ) -> list[str]:
    """Where a validated sample's blind_solved disagrees with the judge (coordinator.md,
    "Blind solving")."""
    errors = []
    samples = {e.get("sample_id") for _, e in events
               if e.get("event") == "blind_judge"
               or (e.get("event") == "spawn" and base_role(e.get("role")) == "semiblind")}
    rulings = {e.get("judge_line"): e for _, e in events if e.get("event") == "blind_ruling"}
    for sample_id in sorted(s for s in samples if s and statuses.get(s) == "validated"):
        record = current_record(sample_id, events)
        if record is None:
            continue
        sha = rubric_sha(record)
        judged = verdicts_on(sample_id, events, sha)
        spawns = [e for _, e in events if e.get("event") == "spawn"
                  and e.get("sample_id") == sample_id and base_role(e.get("role")) == "semiblind"]
        last = spawns[-1] if spawns else None
        if (last is not None and str(last.get("ts", ""))[:10] >= BLIND_JUDGE_SINCE
                and not any(e.get("iteration") == last.get("iteration") for _, e in judged)):
            errors.append(f"{sample_id}: the blind answer of semi-blind round "
                          f"{last.get('iteration')} has no judge verdict on the current rubric. "
                          f"Run `coordinator_log.py {video_id} blind-judge --sample-id "
                          f"{sample_id} --review data/reviews/{video_id}/{sample_id}/"
                          f"semiblind.{last.get('iteration')}.json` and set blind_solved from "
                          f"it (coordinator.md, \"Blind solving\")")
            continue
        current = {review_key(str(e.get("review"))) for _, e in judged}
        stale = {}
        for line, e in events:
            if (e.get("event") == "blind_judge" and e.get("sample_id") == sample_id
                    and review_key(str(e.get("review"))) not in current):
                stale[review_key(str(e.get("review")))] = line
        if stale:
            for review, line in sorted(stale.items()):
                errors.append(f"{sample_id}: the blind answer in {review} was judged (line "
                              f"{line}) on another rubric or by a single run of the judge. Judge "
                              f"it again: `coordinator_log.py {video_id} blind-judge --sample-id "
                              f"{sample_id} --review {review}`. Every judged answer counts, not "
                              f"only the latest round's (coordinator.md, \"A rewrite that keeps "
                              f"the rubric keeps the flag\")")
            continue
        if not judged:
            continue
        verdicts = [(line, e, rulings.get(line)) for line, e in judged]
        solved = [(line, e, r) for line, e, r in verdicts if (r.get("solved") if r else e["met"])]
        flag = bool((record.get("validation") or {}).get("blind_solved"))
        latest_line, latest, _ = verdicts[-1]
        if solved and not flag:
            line, e, _ = solved[-1]
            if line == latest_line:
                errors.append(
                    f"{sample_id}: the judge credited every required item of the blind answer "
                    f"in {e.get('review')} (line {line}), but blind_solved is false and no "
                    f"blind-ruling explains it. Set blind_solved to true and keep the sample as "
                    f"a blind baseline, or, if a credited item rests on a guess, log "
                    f"`blind-ruling --sample-id {sample_id} --basis screen-guess|video-content "
                    f"--items <ids> --text \"<grounds>\"` naming the alternative screen content "
                    f"or the content only this video has (coordinator.md, \"Departing from the "
                    f"judge\")")
            else:
                errors.append(
                    f"{sample_id}: the blind answer in {e.get('review')} (line {line}) met the "
                    f"rubric the record has now, and no ruling departs from that verdict; the "
                    f"verdict on {latest.get('review')} (line {latest_line}) does not clear the "
                    f"flag. Set blind_solved to true, or rule on that answer: `blind-ruling "
                    f"--sample-id {sample_id} --review {e.get('review')} --basis "
                    f"repaired|screen-guess|video-content --items <ids> --text \"<grounds>\"` — "
                    f"repaired when it took from the old wording what the new one withholds "
                    f"(coordinator.md, \"A rewrite that keeps the rubric keeps the flag\")")
        elif flag and not solved:
            errors.append(
                f"{sample_id}: blind_solved is true, but the judge did not credit the blind "
                f"answer in {latest.get('review')} (line {latest_line}, unmet: "
                f"{', '.join(latest.get('items_unmet') or [])}) and no ruling says those items "
                f"are about the look of the screen only. Set blind_solved to false, or log "
                f"`blind-ruling --sample-id {sample_id} --basis look-only --items <ids> --text "
                f"\"<grounds>\"` (coordinator.md, \"Departing from the judge\")")
    return errors


def validate_log(path: Path, final: bool = False) -> int:
    if not path.exists():
        print(f"log does not exist: {path}", file=sys.stderr)
        return 1

    events, errors = read_log(path)
    noted = noted_agents(events)

    active: dict[str, dict] = {}
    launches = finishes = edits = adjudications = notes = blind = 0
    # kind-tagged edits waiting for their reruns: (line, sample_id, roles still missing)
    pending: list[tuple[int, str, set[str]]] = []
    # the versions each sample went through, by the edits that say them: (line, hash after)
    versions: dict[str, list[tuple[int, str]]] = {}
    # adjudicated stretches: (sample_id, window) -> lines; windowed events by (sample, round, window)
    adjudicated: set[tuple[str, int]] = set()
    stretches: dict[tuple[str, int, int], list[tuple[int, dict]]] = {}
    # the last launch of each probe, by (sample_id, role with its index)
    last_probe: dict[tuple[str, str], tuple[int, dict]] = {}
    # the edits made to a record without the tool and logged after the fact
    adopted: list[str] = []
    # the edits that renumbered the windows of each sample
    renumbered: dict[str, list] = {}

    for line_number, event in events:
        event_type = event.get("event")
        agent = event.get("agent")
        if event_type == "spawn":
            launches += 1
            if not agent:
                errors.append(f"line {line_number}: spawn has no agent")
            elif agent in active and not excused(event, noted):
                errors.append(f"line {line_number}: duplicate active launch: {agent}")
            else:
                active[agent] = event
            role, sample_id = event.get("role") or "", event.get("sample_id")
            for edit_line, edited, missing in pending:
                if edited != sample_id:
                    continue
                # A launch restored by finish was not checked against the record when it
                # started: it settles an edit only if it ran on the record as that edit, or a
                # later one, left it.
                if event.get("recovered") and event.get("record_sha") not in {
                        sha for at, sha in versions.get(sample_id, []) if at >= edit_line}:
                    continue
                missing.discard(role)             # full_window3 settles full_window3
                missing.discard(base_role(role))  # full_window3 settles full_window
            if base_role(role) in review_inputs.STALE_ROLES:
                last_probe[(sample_id, role)] = (line_number, event)
        elif event_type == "finish":
            finishes += 1
            if not agent:
                errors.append(f"line {line_number}: finish has no agent")
            elif agent in active:
                del active[agent]
            elif not excused(event, noted) and event.get("material") != "not found":
                errors.append(f"line {line_number}: finish without launch: {agent}")
        elif event_type == "sample_edit":
            edits += 1
            if event.get("sha_after"):
                versions.setdefault(event.get("sample_id", ""), []).append(
                    (line_number, event["sha_after"]))
            kind = event.get("kind")
            if event.get("renumbered") or event.get("removed"):
                # the window reviews that earlier edits still owe follow their windows to the
                # new numbers; the review of a window that is gone is owed no more
                moved_to = {int(old): int(new) for old, new in (event.get("renumbered") or {}).items()}
                gone = set(event.get("removed") or [])
                for _, edited, missing in pending:
                    if edited != event.get("sample_id"):
                        continue
                    owed_windows = {role: role_window(role) for role in missing
                                    if base_role(role) == "full_window" and role != "full_window"}
                    missing -= set(owed_windows)
                    missing |= {f"full_window{moved_to.get(window, window)}"
                                for window in owed_windows.values() if window not in gone}
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
            remap_windows(adjudicated, event)  # the windows keep their marks under new numbers
            if event.get("adopted"):
                adopted.append(f"line {line_number}: {event.get('sample_id')} was changed without "
                               f"sample-edit ({kind}"
                               + (f", window {event['window']}" if event.get("window") is not None
                                  else "") + f"): {event.get('changes')}")
            elif event.get("span") and (event.get("sample_id"), event.get("window")) not in adjudicated:
                errors.append(f"line {line_number}: evidence_span of window {event.get('window')} "
                              f"of {event.get('sample_id')} edited before its stretch was "
                              f"adjudicated: check the span against t_val first "
                              f"(coordinator.md, §6, \"Check every span against t_val\")")
        elif event_type == "adjudicate":
            adjudications += 1
            window = event.get("window")
            if window is None:
                errors += [f"line {line_number}: {e}" for e in check_adjudication(event)]
            else:
                # a windowed row is weighed with its stretch, which a correction may supersede;
                # the stretch is named by the number its window has now, and the rows of a
                # window that was removed since are history
                adjudicated.add((event.get("sample_id"), window))
                sample_id = event.get("sample_id")
                if sample_id not in renumbered:
                    renumbered[sample_id] = renumberings(events, sample_id)
                now = window_now(renumbered[sample_id], window, line_number)
                if now is not None:
                    key = (event.get("sample_id"), event.get("iteration"), now)
                    stretches.setdefault(key, []).append((line_number, event))
        elif event_type == "note":
            notes += 1
            if not event.get("text"):
                errors.append(f"line {line_number}: note has no text")
        elif event_type == "blind_judge":
            blind += 1
            if not (event.get("sample_id") and event.get("review") and event.get("rubric_sha")
                    and isinstance(event.get("met"), bool)):
                errors.append(f"line {line_number}: blind_judge needs sample_id, review, "
                              f"rubric_sha and met: log verdicts with blind-judge only")
        elif event_type == "blind_ruling":
            blind += 1
            if not (isinstance(event.get("judge_line"), int) and isinstance(event.get("solved"), bool)
                    and event.get("basis") in RULING_BASES):
                errors.append(f"line {line_number}: blind_ruling needs judge_line, solved and a "
                              f"basis: log rulings with blind-ruling only")
        else:
            errors.append(f"line {line_number}: unknown event: {event_type!r}")

    corrections, owed, reread = [], [], []
    for sample_id, iteration, window in stretches:
        parts, _ = stretch_segments(events, sample_id, iteration, window)
        for index, part in enumerate(parts):
            rows = part["rows"]
            problems, debts = weigh_stretch(path, (sample_id, iteration, window), rows, events)
            errors += problems
            owed += debts
            current = current_rows(rows)
            superseded = rows[:len(rows) - len(current)]
            if superseded:
                line, correction = current[0]
                corrections.append(f"line {line}: {sample_id}, round {iteration}, window {window} "
                                   f"corrected, lines {', '.join(str(old) for old, _ in superseded)} "
                                   f"superseded: {correction.get('correction')}")
            if part["edit"] is not None:
                before = parts[index - 1]["rows"][-1][1]
                reread.append(f"line {rows[0][0]}: {sample_id}, round {iteration}, window {window} "
                              f"re-adjudicated after the edit of line {part['edit']}: t_val_a "
                              f"{before.get('t_val_a')} -> {rows[0][1].get('t_val_a')}, t_val "
                              f"{before.get('t_val')} -> {rows[-1][1].get('t_val')}")

    for agent in sorted(agent for agent, spawn in active.items() if not excused(spawn, noted)):
        errors.append(f"launch without finish: {agent}")
    errors += record_drift(events)

    statuses = record_statuses(path, events) if final else {}
    rejected = {sample_id for sample_id, status in statuses.items() if status == "rejected"}
    stale = [f"line {line}: edit of {sample_id} not followed by {', '.join(sorted(missing))}"
             for line, sample_id, missing in pending if missing and sample_id not in rejected]
    if final:
        errors += stale
        errors += owed
        errors += blind_errors(path.parent.name, events, statuses)
        for (sample_id, role), (line, spawn) in sorted(last_probe.items()):
            if sample_id in rejected:
                continue
            superseded, owed = superseded_frame_probe(spawn, last_probe)
            if superseded:
                if owed:
                    errors.append(f"line {line}: {role} of {sample_id} ({spawn.get('agent')}): "
                                  f"{owed}")
                continue
            why = stale_inputs(spawn)
            if why:
                errors.append(f"line {line}: {role} of {sample_id} ({spawn.get('agent')}) is "
                              f"stale: {why}. Prepare its workspace again with --sample-id and "
                              f"run {role} anew; its old outcome does not set a flag")
    else:
        for message in stale:
            print(f"pending rerun: {message}", file=sys.stderr)
        for message in owed:
            print(f"pending correction: {message}", file=sys.stderr)

    for message in corrections:
        print(f"correction: {message}")
    for message in reread:
        print(f"re-adjudication: {message}")
    for message in adopted:
        print(f"adopted: {message}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"log valid: {launches} launches, {finishes} finishes, {edits} sample edits, "
          f"{adjudications} adjudications, {notes} notes, {blind} blind verdicts and rulings"
          + (f", {len(corrections)} corrected stretches" if corrections else "")
          + (f", {len(stale)} pending reruns" if stale else "")
          + (f", {len(owed)} rows owed by corrections" if owed else ""))
    return 0


VERIFIED = ("yes", "harder", "no", "na")
T_S_SOURCE = re.compile(r"^(full_sample|full_window\d+|annotation|provenance|model)$")
SEMIBLIND_REVIEW = re.compile(r"^(semiblind\.[0-9A-Za-z]+\.json)\b")
SEMIBLIND_CITED = re.compile(r"(?:^|[/\s(])(semiblind\.[0-9A-Za-z]+\.json)\b")
MOMENT_TOLERANCE = 0.05  # seconds: a logged moment and the answer's t are the same number
CORRECTION_HINT = ("If an earlier row of this stretch is wrong, log the stretch anew with "
                   "adjudicate ... --correction \"<what the earlier rows got wrong>\" "
                   "(coordinator.md §6, \"Correcting a stretch\")")

def renumberings(events: list[tuple[int, dict]], sample_id: str
                 ) -> list[tuple[int, dict[int, int], set[int]]]:
    """The edits that renumbered or removed windows of a sample: (line, {old: new}, removed).
    Only sample-edit of format 2 writes them, so a log from before reads as it did."""
    found = []
    for line, event in events:
        if event.get("event") == "sample_edit" and event.get("sample_id") == sample_id \
                and (event.get("renumbered") or event.get("removed")):
            moved = {int(old): int(new) for old, new in (event.get("renumbered") or {}).items()}
            found.append((line, moved, set(event.get("removed") or [])))
    return found


def window_now(changes: list[tuple[int, dict[int, int], set[int]]], window, line: int):
    """The number that the window called `window` at `line` of the log has at its end, or None
    if the window was removed since. The log names a window by the number it had when the row
    was written; an optional window put before it shifts that number."""
    for at, moved, removed in changes:
        if at <= line or window is None:
            continue
        if window in removed:
            return None
        window = moved.get(window, window)
    return window


def only_structure(event: dict) -> bool:
    """An edit row that changes the content of no window: one renumbered, or one removed."""
    fields = event.get("fields") or {}
    return bool(fields) and all(name.endswith((".idx", " (removed)")) for name in fields)


def scan_windows(events: list[tuple[int, dict]], sample_id: str, name: str, scans: list) -> list:
    """For each stretch of a semi-blind review, the number its window has now.

    A stretch carries the number its window had when the reviewer walked it. After an edit
    that renumbered the windows, the same file may hold stretches under the old numbers and
    under the new: each is told by the launch that walked it — the semi-blind launch of that
    round cut at that window, up to that stretch's end — and carried over the edits logged
    after that launch."""
    numbers = [scan.get("idx") if isinstance(scan, dict) else None for scan in scans]
    changes = renumberings(events, sample_id)
    if not changes:
        return numbers
    round_ = review_round(name)
    launches = [(line, e) for line, e in events
                if e.get("event") == "spawn" and e.get("sample_id") == sample_id
                and base_role(e.get("role")) == "semiblind"
                and (round_ is None or e.get("iteration") == round_)]
    for index, scan in enumerate(scans):
        idx, t_to = numbers[index], scan.get("t_to") if isinstance(scan, dict) else None
        if not isinstance(idx, int) or not isinstance(t_to, (int, float)):
            continue
        walked = [line for line, e in launches
                  if e.get("window") in (None, idx)
                  and isinstance((e.get("inputs") or {}).get("until"), (int, float))
                  and abs(e["inputs"]["until"] - t_to) <= MOMENT_TOLERANCE]
        if walked:
            numbers[index] = window_now(changes, idx, walked[-1])
    return numbers


def read_stretch(sample_dir: Path, window: int, name: str, events: list[tuple[int, dict]] = ()
                 ) -> tuple[list[float], bool, str | None]:
    """The stretch of `window` in a semi-blind review: the moments of its answers, whether the
    review has that stretch at all, and what is missing when the moments cannot be read from
    it. `window` is the window's number now; the stretch is found under the number it was
    walked with (scan_windows)."""
    review = sample_dir / name
    try:
        scans = json.loads(review.read_text(encoding="utf-8")).get("scans") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return [], False, "cannot be read"
    numbers = scan_windows(list(events), sample_dir.name, name, scans)
    own = [scan for scan, number in zip(scans, numbers)
           if isinstance(scan, dict) and number == window]
    moments = [t for scan in own for candidate in scan.get("candidates") or []
               if isinstance(candidate, dict)
               for t in [candidate.get("t")] if isinstance(t, (int, float))]
    if moments:
        return moments, True, None
    found = sorted(str(number) for scan, number in zip(scans, numbers)
                   if isinstance(scan, dict) and number is not None)
    return [], bool(own), (
        f"has no timed answers in its stretch of window {window}" if own else
        f"has no stretch of window {window} (its stretches: {', '.join(found) or 'none'})")


def stretch_answers(sample_dir: Path, window: int, source, events: list[tuple[int, dict]] = ()
                    ) -> tuple[list[float], str | None]:
    """The moments of the answers in the stretch of `window` of the semi-blind review `source`
    names, or why a correction cannot be weighed against it."""
    match = SEMIBLIND_REVIEW.match(str(source or ""))
    if not match:
        return [], (f"a correction cites the semi-blind review its t_val_a comes from: --source "
                    f"semiblind.<ROUND>.json, not {source!r}")
    review = sample_dir / match.group(1)
    moments, _, what = read_stretch(sample_dir, window, match.group(1), events)
    if what == "cannot be read":
        return [], f"the semi-blind review {portable_path(review)} cannot be read"
    if not moments:
        # no stretch of its own (one scan over several windows) or no timed answers (the legacy
        # shape): "no answer" cannot be told from "not read", so nothing is weighed there
        return [], (f"the semi-blind review {portable_path(review)} {what}, so the tool cannot "
                    f"weigh a correction of this window against it. Leave the stretch as it is "
                    f"and settle it in the next round of review, or record the case with "
                    f"`note --text \"tool problem: ...\"`")
    return moments, None


def review_round(name: str) -> int | None:
    """The round of a semi-blind review file (semiblind.2.json, semiblind.2b.json), if any."""
    match = re.match(r"^semiblind\.(\d+)[a-z]?\.json$", name)
    return int(match.group(1)) if match else None


def correction_trajectory(sample_dir: Path, window: int, superseded: list[tuple[int, dict]],
                          correction: dict, events: list[tuple[int, dict]] = ()
                          ) -> tuple[list[float], str | None]:
    """The answers in the stretch of `window` of the semi-blind review a correction re-reads, or
    why it cannot re-read it there. It is the trajectory the earlier rows cite, or, when none
    cites one, a semi-blind review of the stretch's round or an earlier one."""
    cited = sorted({match.group(1) for _, row in superseded
                    for match in [SEMIBLIND_CITED.search(str(row.get("source") or ""))] if match})
    named = SEMIBLIND_REVIEW.match(str(correction.get("source") or ""))
    if named and cited and named.group(1) not in cited:
        return [], (f"--source {named.group(1)}, but the earlier rows of this stretch cite "
                    f"{' or '.join(cited)}: a correction re-reads the trajectory they were read "
                    f"from")
    if named and not cited:
        round_ = review_round(named.group(1))
        if round_ is None or not isinstance(correction.get("iteration"), int) \
                or round_ > correction["iteration"]:
            return [], (f"--source {named.group(1)}: a correction of a round "
                        f"{correction.get('iteration')} stretch re-reads a semi-blind review of "
                        f"that round or an earlier one")
    return stretch_answers(sample_dir, window, correction.get("source"), events)


def is_answer(moments: list[float], t) -> bool:
    return isinstance(t, (int, float)) and any(abs(moment - t) <= MOMENT_TOLERANCE
                                               for moment in moments)


def correction_refusal(sample_dir: Path, window: int, superseded: list[tuple[int, dict]],
                       correction: dict, events: list[tuple[int, dict]] = ()) -> list[str]:
    """Why a correction cannot be logged: it names nothing it corrects, its stretch has no
    earlier row, it does not re-read the trajectory of the earlier rows, its t_val_a is no
    answer of its window's stretch there, or it makes the boundary looser.

    An earlier t_val_a that is an answer bounds the correction by itself. One that is no answer
    was never stage A (a sighted placement, or another stretch's value copied in): it bounds the
    correction by the first answer at or after it, where stage A reading the same trajectory
    would have put the boundary. A sighted placement moves the boundary earlier only as a t_s
    that stage C verifies, and whether stage C was owed on it is decided by the sighted
    reviewers' proposals as in coordinator.md §6, the same as for a stretch logged right the
    first time; the t_s of the superseded rows are logged again (correction_problems)."""
    problems = []
    if not str(correction.get("correction") or "").strip():
        problems.append("a correction says what the earlier rows got wrong")
    if not superseded:
        return problems + ["a correction with no earlier row in its stretch has nothing to "
                           "correct: log the row without --correction"]
    t_val_a = correction.get("t_val_a")
    if t_val_a is None and all(row.get("t_val_a") is None for _, row in superseded):
        return problems  # none for none: nothing on the trajectory to weigh
    moments, unreadable = correction_trajectory(sample_dir, window, superseded, correction,
                                                events)
    if unreadable:
        return problems + [unreadable]
    if t_val_a is not None and not is_answer(moments, t_val_a):
        problems.append(f"t_val_a {t_val_a} is the moment of no answer in the stretch of window "
                        f"{window} of {correction.get('source')}: stage A takes t_val_a from the "
                        f"answers of the window's own stretch. A moment the sighted reviewers "
                        f"place earlier is a t_s (--t-s, --t-s-source), and only stage C makes it "
                        f"the boundary")
    limits = []
    for line, row in superseded:
        value = row.get("t_val_a")
        if value is None:
            continue
        if is_answer(moments, value):
            limits.append((value, f"{value}, the answer that line {line} logged"))
            continue
        later = [moment for moment in moments if moment >= value - MOMENT_TOLERANCE]
        if later:
            limits.append((min(later), f"{min(later)}, the first answer at or after the {value} "
                                       f"that line {line} logged (no answer of the trajectory)"))
    if limits:
        limit, what = min(limits)
        looser = ("A correction makes a boundary stricter, never looser: an answer wrongly taken "
                  "as passing is settled by the next round of review, not by a correction")
        if t_val_a is None:
            problems.append(f"t_val_a null drops {what}. {looser}")
        elif t_val_a > limit + MOMENT_TOLERANCE:
            problems.append(f"t_val_a {t_val_a} is later than {what}. {looser}")
    return problems


def passed_placements(sample_dir: Path, window: int, superseded: list[tuple[int, dict]],
                      correction: dict, events: list[tuple[int, dict]] = ()
                      ) -> list[tuple[int, float]]:
    """The earlier t_val_a that are no answer of the trajectory and that a correction moves
    past: sighted placements, on which stage C may have been owed."""
    moments, unreadable = correction_trajectory(sample_dir, window, superseded, correction,
                                                events)
    if unreadable:
        return []
    t_val_a = correction.get("t_val_a")
    passed = {}
    for line, row in superseded:
        value = row.get("t_val_a")
        if value is not None and not is_answer(moments, value) \
                and (t_val_a is None or t_val_a > value + MOMENT_TOLERANCE):
            passed.setdefault(value, line)
    return [(line, value) for value, line in passed.items()]


def stretch_segments(events: list[tuple[int, dict]], sample_id: str, iteration: int,
                     window: int) -> tuple[list[dict], int | None]:
    """The adjudicate rows of one stretch, split where an edit closed it, and the line of the
    edit after which the next row will open a new part (None when the stretch is open).

    An edit of format 2 that changes a boundary or the rubric of the window, or the level of
    the sample, asks for stage A to be read again (coordinator.md §3, the last column of the
    table). The rows logged after it are that re-adjudication: a part of their own, weighed
    by themselves, with the earlier rows left as history. It may move the boundary either
    way, which a correction may not: what the answers are scored against has changed. A
    record that is back at the version the rows were read on (the level lowered and raised
    again) opens nothing. Edits of format 1 close nothing: the logs written before the rule
    read as they did. Each part is {"rows": [(line, event)], "edit": the line of the edit that
    opened it, or None}.

    `window` is the window's number now. A row logged before an edit that renumbered the
    windows names the window by its number then, and is read under the number the window has
    now (window_now): the stretch follows its window. A row that only renumbers a window, or
    removes another, changes nothing its answers are scored against and closes nothing."""
    changes = renumberings(events, sample_id)
    parts: list[dict] = [{"rows": [], "edit": None}]
    closed: tuple[int, str | None] | None = None   # the closing edit and the version before it
    for line, event in events:
        kind = event.get("event")
        if event.get("sample_id") != sample_id:
            continue
        if kind == "sample_edit" and is_new(event):
            mine = event.get("window") is None \
                or window_now(changes, event["window"], line) == window
            if closed is not None and event.get("sha_after") == closed[1]:
                closed = None
            elif (closed is None and parts[-1]["rows"] and event.get("kind") in CLOSING_KINDS
                  and mine and not only_structure(event)):
                closed = (line, event.get("sha_before"))
        elif kind == "adjudicate" and event.get("iteration") == iteration \
                and event.get("window") is not None \
                and window_now(changes, event["window"], line) == window:
            if closed is not None:
                parts.append({"rows": [], "edit": closed[0]})
                closed = None
            parts[-1]["rows"].append((line, event))
    return parts, (closed[0] if closed else None)


def stage_a_refusal(path: Path, events: list[tuple[int, dict]], args: argparse.Namespace,
                    opens_stretch: bool) -> str | None:
    """Why the row that sets a stretch's t_val_a is not logged, or None.

    The first row of a stretch is stage A: its t_val_a is the first answer of the semi-blind
    trajectory that met the rubric. Nothing used to hold it to the trajectory: a value the
    sighted reviewers had placed, or one probed in stage C, went in as stage A under a round
    that had no review at all. The rows after it, one per t_s, cite what they like."""
    cited = SEMIBLIND_CITED.search(str(args.source or ""))
    if not cited:
        return (f"the first row of a stretch sets stage A's t_val_a, and it cites the semi-blind "
                f"review whose trajectory it was read from: --source semiblind.<ROUND>.json, not "
                f"{args.source!r}. A moment that a sighted reviewer, the annotation or a probe "
                f"gives is a t_s of a later row (--t-s, --t-s-source), not stage A")
    name, window = cited.group(1), args.window
    moments, walked, missing = read_stretch(path.parent / args.sample_id, window, name, events)
    if not walked:
        return (f"{name} {missing}: stage A of window {window} is read from the semi-blind "
                f"reviewer's stretch of that window. Cite the review that walked it; if none "
                f"did, run the semi-blind reviewer over that stretch first (coordinator.md §6, "
                f"stage A)")
    if args.t_val_a is not None and not is_answer(moments, args.t_val_a):
        return (f"t_val_a {args.t_val_a} is the moment of no answer in the stretch of window "
                f"{window} of {name} (its answers: {', '.join(map(str, moments)) or 'none'}). "
                f"Stage A takes t_val_a from the answers of the window's own stretch: copy the "
                f"moment from the file, or omit --t-val-a if no answer met the rubric. A moment "
                f"that a sighted reviewer or the annotation places earlier is a t_s: log it with "
                f"--t-s {args.t_val_a} --t-s-source <full_sample | full_window<N> | annotation | "
                f"provenance | model>, and only stage C makes it the boundary (coordinator.md §6)")
    if opens_stretch and review_round(name) != args.iteration and not any(
            e.get("event") == "spawn" and e.get("sample_id") == args.sample_id
            and e.get("iteration") == args.iteration for _, e in events):
        return (f"round {args.iteration} of {args.sample_id} has no launch yet, and {name} is not "
                f"its trajectory: a stage A row is logged under the round whose review it reads. "
                f"Log it with --iteration {review_round(name)}. A re-adjudication after an edit "
                f"of a boundary, the rubric or the level needs no new round: logged under the "
                f"round of the stretch, it opens a new part of it by itself (coordinator.md §6)")
    return None


def current_rows(rows: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    """The rows of a stretch from its last correction on: the ones the check weighs."""
    marks = [index for index, (_, event) in enumerate(rows) if "correction" in event]
    return rows[marks[-1]:] if marks else rows


def boundary_after(rows: list[dict]) -> float | None:
    """t_val after the last of these rows of one stretch: the earliest of their t_val_a and the
    t_s verified yes among them."""
    candidates = [rows[-1]["t_val_a"]] if rows[-1].get("t_val_a") is not None else []
    candidates += [row["t_s"] for row in rows
                   if row.get("verified") == "yes" and row.get("t_s") is not None]
    return min(candidates) if candidates else None


def weigh_stretch(path: Path, key: tuple[str, int, int], rows: list[tuple[int, dict]],
                  events: list[tuple[int, dict]]) -> tuple[list[str], list[str]]:
    """What check says of one stretch: its errors, and the rows a correction of it still owes.
    adjudicate weighs a row with its stretch the same way before writing it, so that the
    append-only log never takes a row that check would reject."""
    sample_id, iteration, window = key
    where = f"{sample_id}, round {iteration}, window {window}"
    current = current_rows(rows)
    errors, owed = [], []
    for line, event in current:
        errors += [f"line {line}: {e}" for e in check_adjudication(event)]
    for index, problem in check_stretch([event for _, event in current]):
        line, event = current[index]
        errors.append(f"line {line}: {where}: {problem}. {CORRECTION_HINT}")
    if "correction" in current[0][1]:
        superseded = rows[:len(rows) - len(current)]
        problems, debts = correction_problems(path.parent / sample_id, window, superseded,
                                              current, events)
        errors += [f"line {line}: {where}: {problem}" for line, problem in problems]
        owed += [f"line {current[0][0]}: {where}: {debt}" for debt in debts]
    return errors, owed


def adjudicate_event(args: argparse.Namespace, events: list[tuple[int, dict]],
                     path: Path) -> tuple[dict | str, list[str]]:
    """The adjudicate event and the hints to print, or why nothing is logged.

    A row is weighed with its stretch before it is written, by the weigh_stretch that check
    runs, so that the log never takes a row that check would reject later: an append-only log
    cannot take it back. The tool derives t_val itself, and a row without --t-val-a takes the
    t_val_a of its stretch."""
    hints: list[str] = []
    if (args.t_s is None) != (args.t_s_source is None):
        return "--t-s and --t-s-source go together: a sighted proposal names where it came from", hints
    if args.t_s_source is not None and not T_S_SOURCE.match(args.t_s_source):
        return (f"--t-s-source {args.t_s_source!r}: one of full_sample, full_window<N>, "
                f"annotation, provenance, model"), hints
    key = (args.sample_id, args.iteration, args.window)
    where = f"{args.sample_id}, round {args.iteration}, window {args.window}"
    parts, reopened = stretch_segments(events, *key)
    logged_before = any(part["rows"] for part in parts)
    # the rows this one is weighed with: the open part of the stretch, or none when an edit
    # has closed it and this row re-adjudicates
    rows = [] if reopened is not None else parts[-1]["rows"]
    if reopened is not None and args.correction is not None:
        return (f"the stretch {where} was closed by the edit of line {reopened}: this row "
                f"re-adjudicates stage A after it and may move the boundary either way. Log it "
                f"without --correction"), hints
    if args.correction is None and not rows:
        refusal = stage_a_refusal(path, events, args, opens_stretch=not logged_before)
        if refusal:
            return refusal, hints
    if reopened is not None:
        before = parts[-1]["rows"][-1][1]
        hints.append(f"this row re-adjudicates stage A after the edit of line {reopened}: "
                     f"t_val_a {before.get('t_val_a')} -> {args.t_val_a}; the earlier rows of "
                     f"the stretch stay in the log as history. Write it into the table of "
                     f"coordinator.<ROUND>.md")
    if args.correction is None and rows:
        broken, _ = weigh_stretch(path, key, rows, events)
        if broken:
            found = "; ".join(problem.replace(f". {CORRECTION_HINT}", "") for problem in broken)
            return (f"the stretch {where} already fails check, and a further row cannot repair "
                    f"it ({found}). Log the stretch anew with adjudicate ... "
                    f"--correction \"<what the earlier rows got wrong>\" (coordinator.md §6, "
                    f"\"Correcting a stretch\"); the correction may carry this row's t_s"), hints
    current = [] if args.correction is not None else current_rows(rows)
    t_val_a = args.t_val_a
    if current:
        stretch_line, stretch_t_val_a = current[-1][0], current[-1][1].get("t_val_a")
        if t_val_a is None and stretch_t_val_a is not None:
            t_val_a = stretch_t_val_a
            hints.append(f"t_val_a {t_val_a} is the stretch's (line {stretch_line})")
        elif t_val_a != stretch_t_val_a:
            return (f"t_val_a {t_val_a} disagrees with {stretch_t_val_a}, the t_val_a of {where} "
                    f"(line {stretch_line}): the rows of a stretch share stage A's t_val_a. Omit "
                    f"--t-val-a to take the stretch's; if stage A was read wrongly, log the "
                    f"stretch anew with --correction (coordinator.md §6, \"Correcting a "
                    f"stretch\")"), hints
    event = {"ts": timestamp(), "event": "adjudicate", "sample_id": args.sample_id,
             "iteration": args.iteration, "window": args.window,
             "t_val_a": t_val_a, "t_s": args.t_s, "t_s_source": args.t_s_source,
             "verified": args.verified, "t_val": None, "source": args.source}
    if args.correction is not None:
        event["correction"] = args.correction
    derived = boundary_after([e for _, e in current] + [event])
    event["t_val"] = derived
    problems = []
    if args.t_val is not None and (derived is None or abs(args.t_val - derived) > MOMENT_TOLERANCE):
        passed = [f"{e['t_s']} (line {line})" for line, e in current
                  if e.get("verified") == "yes" and e.get("t_s") is not None]
        if args.verified == "yes" and args.t_s is not None:
            passed.append(f"{args.t_s} (this row)")
        problems.append(f"--t-val {args.t_val}, but the boundary after this row is {derived}: the "
                        f"earliest of t_val_a {t_val_a} and the t_s verified yes "
                        f"({', '.join(passed) or 'none'}). A harder route or a failed probe "
                        f"leaves t_val at t_val_a. Omit --t-val: the tool sets it")
    line = (len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0) + 1
    after, owed = weigh_stretch(path, key, rows + [(line, event)], events)
    this = f"line {line}: "
    problems += ["this row: " + p[len(this):] if p.startswith(this) else p for p in after]
    if problems:
        return "; ".join(problems), hints
    hints.insert(0, f"t_val after this row: {derived}")
    if args.correction is not None:
        for placed_line, value in passed_placements(path.parent / args.sample_id, args.window,
                                                    rows, event, events):
            hints.append(f"line {placed_line} logged t_val_a {value}, which is no answer of the "
                         f"trajectory, and the correction moves past it. If a sighted reviewer "
                         f"proposed it (a t_s of full_sample, or a span ending more than 2 s "
                         f"before t_val_A), stage C is owed on it as in coordinator.md §6: log "
                         f"it with --t-s {value} --t-s-source <that reviewer> and the probe's "
                         f"outcome")
        hints.append("re-check what was decided on the old t_val: 2.2 and 2.3 (the ladder "
                     "of coordinator.md §6) and the spans checked against it (7.5)")
        hints.append("write the correction and why into the table of "
                     "coordinator.<ROUND>.md")
    if owed:
        hints.append("the corrected stretch stands once these rows follow it, and check --final "
                     "fails until then: " + "; ".join(owed))
    return event, hints


def probe_ran(events: list[tuple[int, dict]], sample_id: str | None, iteration: int | None,
              t_s: float) -> bool:
    """Whether a probe_verify of the sample, launched in this round at t_s (its --until), has
    finished: the measurement an outcome of t_s stands on."""
    agents = set()
    for _, event in events:
        inputs = event.get("inputs") if event.get("event") == "spawn" else None
        until = inputs.get("until") if isinstance(inputs, dict) else None
        if (isinstance(until, (int, float)) and abs(until - t_s) <= MOMENT_TOLERANCE
                and event.get("sample_id") == sample_id and event.get("iteration") == iteration
                and base_role(event.get("role")) == "probe_verify"):
            agents.add(event.get("agent"))
    return any(event.get("event") == "finish" and event.get("agent") in agents
               and event.get("status") == "completed" for _, event in events)


def correction_problems(sample_dir: Path, window: int, superseded: list[tuple[int, dict]],
                        current: list[tuple[int, dict]], events: list[tuple[int, dict]]
                        ) -> tuple[list[tuple[int, str]], list[str]]:
    """What keeps a corrected stretch from standing, by row, and what it still owes.

    Problems: the refusals of correction_refusal (on the correction's row); a row that changes
    the outcome a probe measured for a t_s of the superseded rows; a row that gives an outcome
    to a t_s that no probe_verify of this round ran at, unless a superseded row carries that
    same outcome. Owed: a t_s of the superseded rows that the corrected stretch has not logged
    again."""
    line, correction = current[0]
    problems = [(line, problem)
                for problem in correction_refusal(sample_dir, window, superseded, correction,
                                                  events)]
    sample_id, iteration = correction.get("sample_id"), correction.get("iteration")
    t_val_a = correction.get("t_val_a")

    def same(row: dict, other: dict) -> bool:
        return (row.get("t_s") is not None and other.get("t_s") is not None
                and abs(row["t_s"] - other["t_s"]) <= MOMENT_TOLERANCE
                and row.get("t_s_source") == other.get("t_s_source"))

    owed, seen = [], []
    for old_line, old in superseded:
        if old.get("t_s") is None or any(same(old, row) for _, row in current) \
                or any(same(old, row) for row in seen):
            continue
        seen.append(old)
        logged = f"--t-s {old['t_s']} --t-s-source {old.get('t_s_source')}"
        if old.get("verified") != "na":
            how = f"{logged} --verified {old.get('verified')}, the outcome its probe gave"
        elif t_val_a is None or old["t_s"] < t_val_a:
            how = (f"{logged}: it lies before the corrected t_val_a, so run stage C at it first "
                   f"and log the outcome with --verified")
        else:
            how = f"{logged} --verified na"
        owed.append(f"log again the t_s {old['t_s']} ({old.get('t_s_source')}) of line {old_line} "
                    f"with the corrected t_val_a: {how}")
    for row_line, row in current:
        outcome = row.get("verified")
        if row.get("t_s") is None:
            continue
        measured = {old.get("verified"): old_line for old_line, old in superseded
                    if same(old, row) and old.get("verified") != "na"}
        if measured and outcome not in measured:
            what = ", ".join(f"{was} (line {at})" for was, at in measured.items())
            problems.append((row_line, f"the t_s {row['t_s']} ({row.get('t_s_source')}) was "
                                       f"verified {what}, and this row says {outcome}: a "
                                       f"correction does not change what a probe measured"))
        elif not measured and outcome in ("yes", "harder", "no") \
                and not probe_ran(events, sample_id, iteration, row["t_s"]):
            problems.append((row_line, f"the t_s {row['t_s']} gets the outcome {outcome}, but no "
                                       f"probe_verify of {sample_id} launched in round "
                                       f"{iteration} at it (--until {row['t_s']}) has finished: "
                                       f"run stage C at that moment before logging what it "
                                       f"measured"))
    return problems, owed


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
        problems.append("t_s lies before t_val_a (or t_val_a is null) but no verification was "
                        "run: run stage C, probe_verify at t_s (coordinator.md §6), and log its "
                        "outcome as --verified yes, harder or no")
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


def check_stretch(rows: list[dict]) -> list[tuple[int, str]]:
    """All rows of one stretch agree on t_val_a, and the stretch ends on t_val the earliest of
    t_val_a and the t_s that the verification probe passed by the route of the level or a
    cheaper one. A row logged as soon as its stage is done holds the boundary as it stood then
    (stage A before stage C has run); a row logged after the stretch holds the final one. Either
    is right for a row before the last; the last one holds the final boundary. Returns the
    index of each wrong row with its problem."""
    t_val_as = {row.get("t_val_a") for row in rows}
    if len(t_val_as) > 1:
        return [(len(rows) - 1, f"rows disagree on t_val_a: {sorted(t_val_as, key=str)}")]
    candidates = [t for t in [rows[0].get("t_val_a")] if t is not None]
    so_far = []
    for row in rows:
        if row.get("verified") == "yes" and row.get("t_s") is not None:
            candidates.append(row["t_s"])
        so_far.append(min(candidates) if candidates else None)
    final = so_far[-1]
    problems = []
    for index, (row, then) in enumerate(zip(rows, so_far)):
        if row.get("t_val") in (then, final):
            continue
        expected = f"{final}" if then == final else f"{then} after this row and {final} at the end"
        problems.append((index, f"t_val {row.get('t_val')} but the earliest of t_val_a and the "
                                f"t_s verified yes is {expected}"))
    return problems


def saved_reviews(path: Path, spawn: dict) -> list[Path]:
    """The review files the launch has saved since it started: ``<role>.<iteration>`` with the
    role as logged (``full_window0``), a number after ``probe_verify`` and a letter after the
    round (a repeat, ``probe_frame0.1b``)."""
    role, iteration = spawn.get("role") or "", spawn.get("iteration")
    pattern = re.compile(rf"{re.escape(role)}\d*\.{iteration}[a-z]?\.json")
    try:
        started = datetime.fromisoformat(spawn["ts"]).timestamp()
    except (KeyError, ValueError):
        started = 0.0
    folder = path.parent / (spawn.get("sample_id") or "")
    return [f for f in folder.glob(f"{role}*.json")
            if pattern.fullmatch(f.name) and f.stat().st_mtime >= started]


def saved_review(path: Path, spawn: dict) -> Path | None:
    """The latest of them, if any."""
    found = saved_reviews(path, spawn)
    return max(found, key=lambda f: f.stat().st_mtime) if found else None


def passes_check(review: Path) -> bool:
    result = subprocess.run([sys.executable, str(REPO / "schema" / "review.py"), "--check",
                             str(review)], capture_output=True, text=True, check=False)
    return result.returncode == 0


def ready_launches(path: Path) -> tuple[dict[str, dict], dict[str, tuple[Path | None, bool]]]:
    events, _ = read_log(path)
    launches = {agent: spawn for agent, (_, spawn) in open_launches(events).items()}
    status = {}
    for agent, spawn in launches.items():
        review = saved_review(path, spawn)
        status[agent] = (review, review is not None and passes_check(review))
    return launches, status


def show_open(path: Path, wait: float) -> int:
    launches, status = ready_launches(path)
    deadline = time.monotonic() + wait
    ready = sum(ok for _, ok in status.values())
    while wait and time.monotonic() < deadline and launches:
        time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
        launches, status = ready_launches(path)
        if sum(ok for _, ok in status.values()) > ready:
            break
    now = datetime.now().astimezone()
    print(f"open launches: {len(launches)}")
    for agent, spawn in launches.items():
        review, ok = status[agent]
        try:
            age = f"{(now - datetime.fromisoformat(spawn['ts'])).total_seconds() / 60:.0f} min"
        except (KeyError, ValueError):
            age = "age unknown"
        where = (f"saved and passes --check: {review.relative_to(ROOT)}" if ok else
                 f"saved, does not pass --check yet: {review.relative_to(ROOT)}" if review else
                 "no review file yet")
        print(f"  {agent} ({spawn.get('role')}, {spawn.get('sample_id')}, round "
              f"{spawn.get('iteration')}), {age}: {where}")
    if any(ok for _, ok in status.values()):
        print("A file that passes --check is the subagent's result even if its completion notice "
              "has not reached you: record the finish with --artifact <that file> and go on.")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("video_id")
    commands = result.add_subparsers(dest="command", required=True)

    spawn = commands.add_parser("spawn", help="record a successful subagent launch")
    spawn.add_argument("--agent", required=True,
                       help="the agent_id that spawn_agent returned (not the nickname)")
    spawn.add_argument("--sample-id", default=None,
                       help="read from the workspace note; when given, checked against it")
    spawn.add_argument("--role", default=None,
                       help="read from the workspace note, with the window's index; when "
                            "given, checked against it")
    spawn.add_argument("--iteration", required=True, type=int)
    spawn.add_argument("--model", required=True)
    spawn.add_argument("--reasoning-effort", default="default",
                       help=f"what the launch ran with: {', '.join(EFFORTS)}; default when "
                            f"spawn_agent was given none")
    spawn.add_argument("--reason", default=None,
                       help="for a repeat of a probe only, when the tool asks for it: the "
                            "defect of the earlier attempt, with the evidence")
    spawn.add_argument("--workspace", required=True, type=Path,
                       help="the folder the subagent works in, prepared with "
                            "prepare_review_workspace.py --sample-id; its inputs note is checked "
                            "against the current record")

    finish = commands.add_parser("finish", help="record a terminal subagent result")
    finish.add_argument("--agent", required=True,
                        help="the name its spawn was logged with: the agent_id that "
                             "spawn_agent returned")
    finish.add_argument("--status", required=True,
                        choices=("completed", "failed", "interrupted"))
    finish.add_argument("--artifact",
                        help="the review file the subagent saved; may be omitted when the "
                             "launch saved exactly one file that passes --check")
    finish.add_argument("--summary", required=True)
    finish.add_argument("--workspace", type=Path, default=None,
                        help="only when the tool asks for it: the workspace of a launch whose "
                             "spawn was never logged")
    finish.add_argument("--reason", default=None,
                        help="only when the tool asks for it: the defect of the earlier "
                             "attempt, for a restored launch that repeats a probe")

    get = commands.add_parser("sample-get", help="write a record to a file to be edited")
    get.add_argument("--sample-id", required=True)
    get.add_argument("--out", type=Path, default=None,
                     help="where to write it; data/reviews/<VIDEO_ID>/<SAMPLE_ID>/.edit/record.json "
                          "by default")
    get.add_argument("--annotations", type=Path, default=None,
                     help="only when the tool asks for it: the file the record is in")

    edit = commands.add_parser("sample-edit",
                               help="change a record: the tool reads what changed, checks the "
                                    "record, logs the edit and writes the file")
    edit.add_argument("--sample-id", required=True)
    edit.add_argument("--source", required=True,
                      help="the review or decision the edit comes from (full_window0.2.json, "
                           "coordinator.2.md)")
    edit.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                      help="change one field in place, as often as needed: "
                           "validation.blind_solved=false, 'triggers[1].t_start=212.0'")
    edit.add_argument("--from", dest="source_file", type=Path, default=None,
                      help="the edited file sample-get wrote, when it is not the default one")
    edit.add_argument("--adopt", action="store_true",
                      help="only when check asks for it: log a change that was made to the "
                           "record without the tool")
    edit.add_argument("--annotations", type=Path, default=None,
                      help="only when the tool asks for it: the file the record is in, or the "
                           "file of data/annotations/partial/ a new sample goes to")
    for flag, extra in (("--kind", {}), ("--changes", {}), ("--window", {}),
                        ("--span", {"action": "store_true"})):  # refused with what to do instead
        edit.add_argument(flag, default=None, help=argparse.SUPPRESS, **extra)

    note = commands.add_parser("note", help="append a remark: a reconstruction, an unknown "
                                            "fate, anything the other events cannot say")
    note.add_argument("--text", required=True)
    note.add_argument("--agent", default=None,
                      help="the agent the note is about. A note repairs nothing: a launch that "
                           "did not start is finished with --status failed, and a spawn that "
                           "was never logged is restored by finish")
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
                          "the route of the level or a cheaper one; omit if none. A later row of "
                          "the stretch may omit it and takes the stretch's")
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
                     help="the boundary as it stands after this event: the earliest of t_val_a "
                          "and the t_s verified yes so far. The tool derives it, so it may be "
                          "omitted; one that is given and differs is refused")
    adj.add_argument("--source", required=True,
                     help="the semi-blind review the trajectory came from")
    adj.add_argument("--correction", default=None,
                     help="what the earlier rows of this stretch got wrong: this row opens the "
                          "stretch anew and they drop out of the check. Its t_val_a is the moment "
                          "of an answer of the window's own stretch in the semi-blind review "
                          "--source names, no later than the earliest answer they logged (null "
                          "only if there is none); every t_s of the earlier rows is logged again, "
                          "keeping its probe outcome")

    judge = commands.add_parser("blind-judge",
                                help="score the semi-blind reviewer's blind answer with the "
                                     "evaluation judge against the current rubric")
    judge.add_argument("--sample-id", required=True)
    judge.add_argument("--review", required=True, help="the saved semiblind.<round>.json")
    judge.add_argument("--base-url", default=JUDGE_URL,
                       help="the vLLM server you run on; the key is $VLLM_API_KEY, or dummy")
    judge.add_argument("--model", default="local", help="the served model name")

    ruling = commands.add_parser("blind-ruling",
                                 help="depart from the judge's verdict on the blind answer, "
                                      "with the grounds")
    ruling.add_argument("--sample-id", required=True)
    ruling.add_argument("--basis", required=True, choices=tuple(RULING_BASES),
                        help="screen-guess or video-content: a credited item rests on a guess or "
                             "on what only this video has; repaired: an earlier round's answer "
                             "took from the old wording what the new one withholds (all three "
                             "blind_solved false); look-only: the uncredited items are about the "
                             "look of the screen (true)")
    ruling.add_argument("--review", default=None,
                        help="the judged semi-blind review the ruling is about, as blind-judge "
                             "logged it; the last judged round by default")
    ruling.add_argument("--items", required=True,
                        help="comma-separated item ids of the judge's verdict, w<window>.<k>")
    ruling.add_argument("--text", required=True,
                        help="the grounds: the alternative screen content and the answer under "
                             "it, the content only this video has, or why the items are about "
                             "the look only")

    check = commands.add_parser("check", help="validate JSON and balance launches with finishes")
    check.add_argument("--final", action="store_true",
                       help="also fail on kind-tagged edits whose reruns have not happened, on "
                            "probes whose material the record no longer gives, and on validated "
                            "samples whose blind_solved disagrees with the judge's verdicts "
                            "without a ruling")

    shown = commands.add_parser("open", help="list the launches with no finish and the review "
                                             "files their subagents have already saved")
    shown.add_argument("--wait", type=float, default=0.0, metavar="SECONDS",
                       help="poll up to this long; return as soon as one more launch has a "
                            "file that passes --check")
    return result


# ---- the records: get, edit, adopt ---------------------------------------------------------

# The review files a nudge may rest on: a boundary is nudged to a full_window or semi-blind
# review's own frame measurement (coordinator.md §3).
REVIEW_NAMED = re.compile(r"\b((?:full_window\d+|semiblind)\.\d+[a-z]?\.json)\b")
# The kinds of edit after which stage A of the window is read again (the last column of the
# table in coordinator.md §3): such an edit of format 2 closes the adjudicated stretch.
CLOSING_KINDS = ("boundary", "rubric", "level")
# What each kind of edit owes, said when the edit is logged.
AFTER_EDIT = {
    "wording": "a new version of the question: every role runs again on new workspaces — the "
               "semi-blind reviewer, the probes, full_sample and every full_window — and "
               "blind-judge scores the new semi-blind review. Set validation.status to draft "
               "if it is not",
    "boundary": "run {window_review} again, and every probe whose material moved (check --final "
                "names them); re-adjudicate stage A of the window against the new boundary",
    "nudge": "no rerun is owed: the reviewer's frames are the verification",
    "rubric": "run full_sample and {window_review} again; run blind-judge again on the saved "
              "blind answer; re-score the saved probe answers against the new rubric; "
              "re-adjudicate stage A",
    "level": "no rerun is owed; re-read every 2.5 split against the new level and re-adjudicate "
             "stage A by the route of the new level",
    "timing": "no rerun is owed",
    "metadata": "no rerun is owed",
}
# A boundary row that changes the content of no window (only_structure).
AFTER_RENUMBERING = ("run {window_review} again: reviews and probes are named by the new "
                     "number. Nothing is re-adjudicated: the tool reads the window's earlier "
                     "adjudicate rows under its new number")
AFTER_REMOVAL = ("run a full_window of a window that remains (a launch owed for another row of "
                 "this edit settles it). Nothing is re-adjudicated")


def edit_file(path: Path, sample_id: str) -> Path:
    """Where sample-get puts a record to be edited, unless --out names another file."""
    return path.parent / sample_id / ".edit" / "record.json"


def base_note(file: Path) -> Path:
    """The note next to a file sample-get wrote: which version of the record it holds."""
    return file.with_name(file.name + ".base.json")


def keep_version(path: Path, record: dict) -> None:
    """A copy of a version of a record the tool has seen, next to the sample's reviews."""
    sha = review_inputs.record_sha(record)
    copy = path.parent / str(record.get("id")) / ".versions" / f"{sha[:12]}.json"
    if kept_version(path, str(record.get("id")), sha) is not None:
        return
    # written next to it and moved into place: a write cut off half-way leaves no copy rather
    # than a broken one, and a copy that does not read back as this version is written again
    copy.parent.mkdir(parents=True, exist_ok=True)
    temporary = copy.with_name(f".{copy.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(temporary, copy)


def kept_version(path: Path, sample_id: str, sha: str | None) -> dict | None:
    if not sha:
        return None
    try:
        record = json.loads((path.parent / sample_id / ".versions" / f"{sha[:12]}.json")
                            .read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if review_inputs.record_sha(record) == sha else None


def locate_record(sample_id: str, events: list[tuple[int, dict]], annotations=None
                  ) -> tuple[Path, dict]:
    """The record as it stands now and the file it is in: the file --annotations names, else
    the one the sample's last launch or edit names, else wherever the id is found."""
    if annotations is not None:
        return review_inputs.find_record(ROOT, sample_id,
                                         review_inputs.locate(ROOT, str(annotations)))
    names = [e["annotations"] for _, e in events
             if e.get("sample_id") == sample_id and e.get("annotations")]
    if names:
        return review_inputs.find_logged_record(ROOT, sample_id, names[-1])
    return review_inputs.find_record(ROOT, sample_id)


def record_file(sample_id: str, events: list[tuple[int, dict]]) -> tuple[Path, dict] | None:
    """locate_record, or None when the record cannot be read."""
    try:
        return locate_record(sample_id, events)
    except (OSError, KeyError, json.JSONDecodeError, review_inputs.InputsError):
        return None


def known_versions(events: list[tuple[int, dict]]) -> dict[str, tuple[int, dict]]:
    """For each sample, the last row of format 2 that says which version of its record the log
    knows: an edit (the hash after it) or a launch (the hash it ran on; not a launch restored
    by finish, which ran on an earlier version)."""
    known: dict[str, tuple[int, dict]] = {}
    for line, event in events:
        if not is_new(event) or not event.get("sample_id"):
            continue
        if event.get("event") == "sample_edit" and event.get("sha_after"):
            known[event["sample_id"]] = (line, event)
        elif event.get("event") == "spawn" and event.get("record_sha") and not event.get("recovered"):
            known[event["sample_id"]] = (line, event)
    return known


def record_drift(events: list[tuple[int, dict]]) -> list[str]:
    """The records of an open video that are not the version the log last knew: changed
    without sample-edit, or left unwritten by a sample-edit that was cut off.

    Only while the record is in data/annotations/partial/: a merged file is closed, and a
    later migration of the schema changes every hash in it."""
    problems = []
    for sample_id, (line, event) in sorted(known_versions(events).items()):
        found = record_file(sample_id, events)
        cut_off = (f"the tool was cut off between the two. Run `sample-get --sample-id "
                   f"{sample_id}` (or the same sample-edit command again): the tool writes the "
                   f"record from the copy it kept and logs nothing new")
        if found is None:
            if event.get("added"):
                problems.append(f"{sample_id}: the new sample of line {line} is in the log, but "
                                f"not in {event.get('annotations')}: {cut_off}")
            continue
        if found[0].parent.name != "partial":
            continue
        now = review_inputs.record_sha(found[1])
        if now == (event.get("sha_after") or event.get("record_sha")):
            continue
        if event.get("event") == "sample_edit" and not event.get("adopted") \
                and now == event.get("sha_before"):
            problems.append(f"{sample_id}: the edit of line {line} is in the log, but the record "
                            f"does not hold it: {cut_off}")
        else:
            problems.append(
                f"{sample_id}: the record is not the version the log last knew (line {line}): it "
                f"was changed without sample-edit. A record is changed only through the tool "
                f"(coordinator.md §3). Log what was changed: `sample-edit --sample-id "
                f"{sample_id} --adopt --source \"<what was changed and why>\"`")
    return problems


def measured_in(path: Path, events: list[tuple[int, dict]], sample_id: str, source: str
                ) -> "callable":
    """Whether a moment is a reviewer's own measurement: a number of a full_window or
    semi-blind review the edit names as its source, or a t_s verified yes."""
    values: list[float] = []
    for name in REVIEW_NAMED.findall(source or ""):
        try:
            review = json.loads((path.parent / sample_id / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        values += sample_edit.numbers_in(review)
    values += [e["t_s"] for _, e in events
               if e.get("event") == "adjudicate" and e.get("sample_id") == sample_id
               and e.get("verified") == "yes" and isinstance(e.get("t_s"), (int, float))]
    return lambda t: any(abs(value - t) <= MOMENT_TOLERANCE for value in values)


def remap_windows(marks: set[tuple[str, int]], event: dict) -> None:
    """Carry the marks of a sample's windows over an edit that renumbered them."""
    moved, gone = event.get("renumbered") or {}, set(event.get("removed") or [])
    if not moved and not gone:
        return
    sample_id = event.get("sample_id")
    mine = {window for sample, window in marks if sample == sample_id}
    marks -= {(sample_id, window) for window in mine}
    marks |= {(sample_id, int(moved.get(str(window), moved.get(window, window))))
              for window in mine if window not in gone}


def adjudicated_windows(events: list[tuple[int, dict]]) -> set[tuple[str, int]]:
    """The windows whose stretch has an adjudicate row, under the numbers they have now."""
    marks: set[tuple[str, int]] = set()
    for _, event in events:
        if event.get("event") == "adjudicate" and event.get("window") is not None:
            marks.add((event.get("sample_id"), event["window"]))
        elif event.get("event") == "sample_edit":
            remap_windows(marks, event)
    return marks


FIELD_PATH = re.compile(r"^([A-Za-z_]+)((?:\[\d+\])*)$")


def set_field(record: dict, assignment: str) -> None:
    """Apply one --set <path>=<value>: validation.blind_solved=false, triggers[1].t_start=212.0.
    The value is read as JSON, and as plain text when it is not JSON."""
    path, equals, raw = assignment.partition("=")
    if not equals or not path.strip():
        raise sample_edit.EditError(f"--set {assignment!r}: write <field>=<value>, for example "
                                    f"validation.blind_solved=false or triggers[1].t_start=212.0")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    steps: list = []
    for part in path.strip().split("."):
        match = FIELD_PATH.match(part)
        if not match:
            raise sample_edit.EditError(f"--set {assignment!r}: {part!r} is not a field name")
        steps.append(match.group(1))
        steps += [int(index) for index in re.findall(r"\[(\d+)\]", match.group(2))]
    target = record
    for step in steps[:-1]:
        try:
            target = target[step]
        except (KeyError, IndexError, TypeError):
            raise sample_edit.EditError(f"--set {assignment!r}: the record has no {step!r} on "
                                        f"the way to that field") from None
    last = steps[-1]
    if isinstance(last, int):
        if not isinstance(target, list) or last >= len(target):
            raise sample_edit.EditError(f"--set {assignment!r}: no element {last} there; to "
                                        f"add or remove one, use sample-get and edit the file")
        target[last] = value
    elif isinstance(target, dict):
        target[last] = value
    else:
        raise sample_edit.EditError(f"--set {assignment!r}: {last!r} is not a field there")


def sample_get(args: argparse.Namespace, events: list[tuple[int, dict]], path: Path) -> int:
    """Write a record to a file to be edited, with a note of the version it is."""
    done, waiting = finish_cut_off(path, events, args.sample_id)
    if waiting:
        print(f"nothing was written. {waiting}", file=sys.stderr)
        return 2
    if done:
        print(done)
    try:
        file, record = locate_record(args.sample_id, events, args.annotations)
    except (OSError, json.JSONDecodeError, review_inputs.InputsError) as exc:
        print(f"nothing was written. {exc}", file=sys.stderr)
        return 2
    out = args.out or edit_file(path, args.sample_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    base_note(out).write_text(json.dumps({
        "sample_id": args.sample_id, "annotations": portable_path(file),
        "sha": review_inputs.record_sha(record), "got_at": timestamp()}) + "\n", encoding="utf-8")
    keep_version(path, record)
    named = "" if args.out is None else f" --from {out}"
    print(f"{args.sample_id} (from {portable_path(file)}) is in {portable_path(out)}\n"
          f"next: edit that file — any field but id and video — and run `coordinator_log.py "
          f"{args.video_id} sample-edit --sample-id {args.sample_id}{named} --source \"<the "
          f"review or decision the edit comes from>\"`. The tool reads what changed off the "
          f"file, checks the record, logs the edit, writes the record and says which reviews "
          f"the edit owes. Nothing is logged for sample-get")
    return 0


def put_record(file: Path, sample_id: str, expected_sha: str | None, record: dict) -> str | None:
    """sample_edit.write_record; a failure of the disk is a reason like any other."""
    try:
        return sample_edit.write_record(file, sample_id, expected_sha, record)
    except (OSError, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"


def finish_cut_off(path: Path, events: list[tuple[int, dict]], sample_id: str
                   ) -> tuple[str | None, str | None]:
    """Write the record of an edit that was logged and then cut off before the record was
    written: (what was written, why the record still does not hold the edit); both None when
    no edit is waiting.

    The log is the account of what the record holds, and the reviews an edit owes are counted
    from its rows. So a logged edit is finished before anything else is done to the record: a
    different edit applied instead would leave a row in the log for a version that never
    existed. The tool keeps a copy of the new version before it logs the edit (keep_version),
    and writes the record from it."""
    known = known_versions(events).get(sample_id)
    if known is None or known[1].get("event") != "sample_edit" or known[1].get("adopted"):
        return None, None
    line, edit = known
    try:
        file, current = review_inputs.find_logged_record(ROOT, sample_id, edit["annotations"])
        was = review_inputs.record_sha(current)
    except review_inputs.InputsError:
        if not edit.get("added"):
            return None, None
        file, was = review_inputs.locate(ROOT, edit["annotations"]), None
    except (OSError, KeyError, json.JSONDecodeError):
        return None, None
    if was == edit["sha_after"] or (was is not None and was != edit.get("sha_before")):
        return None, None  # written, or changed without the tool: check names the second
    kept = kept_version(path, sample_id, edit["sha_after"])
    waiting = f"the edit of line {line} is in the log and not in the record"
    if kept is None:
        return None, (f"{waiting}, and the copy the tool kept of the new version is gone. Run "
                      f"the sample-edit command of that edit again, with the same values "
                      f"({edit.get('changes')}); it writes the record and logs nothing new")
    why = put_record(file, sample_id, was, kept)
    if why:
        return None, f"{waiting}, and it cannot be written now: {why}"
    return (f"the edit of line {line} was in the log and not in the record: the record is "
            f"written now ({portable_path(file)}) from the copy the tool kept; nothing new was "
            f"logged"), None


def edit_events(args: argparse.Namespace, rows: list[dict], moved: dict, file: Path,
                before: str | None, after: str, **marks) -> list[dict]:
    """The rows of one edit: one per kind and window, all with the hashes of the record before
    and after it. How the windows were renumbered goes on the first."""
    stamp = timestamp()
    events = []
    for row in rows:
        event = {"ts": stamp, "event": "sample_edit", "sample_id": args.sample_id,
                 "kind": row["kind"], "changes": row.get("changes") or sample_edit.describe(row["fields"]),
                 "source": args.source, "fields": row["fields"], "sha_before": before,
                 "sha_after": after, "annotations": portable_path(file), **marks}
        if row["window"] is not None:
            event["window"] = row["window"]
        if row["span"]:
            event["span"] = True
        events.append(event)
    if moved.get("renumbered"):
        events[0]["renumbered"] = {str(was): now for was, now in moved["renumbered"].items()}
    if moved.get("removed"):
        events[0]["removed"] = moved["removed"]
    return events


def owed_after(event: dict) -> str:
    window = event.get("window")
    review = f"full_window{window}" if window is not None else "a full_window"
    what = f"{event['kind']}" + (f", window {window}" if window is not None else "") \
        + (", evidence_span" if event.get("span") else "")
    owed = AFTER_EDIT[event["kind"]]
    if event["kind"] == "boundary" and only_structure(event):
        owed = AFTER_REMOVAL if window is None else AFTER_RENUMBERING
    return f"{what} ({event['changes']}): {owed.format(window_review=review)}"


def old_edit_flags(args: argparse.Namespace) -> str | None:
    given = [flag for flag, value in (("--kind", args.kind), ("--changes", args.changes),
                                      ("--window", args.window), ("--span", args.span))
             if value not in (None, False)]
    if not given:
        return None
    return (f"sample-edit no longer takes {', '.join(given)}: the tool reads what changed off the "
            f"record itself and logs the kind, the window and the values. Change a field or two "
            f"with `sample-edit --sample-id {args.sample_id} --set <field>=<value> --source "
            f"\"<the review or decision the edit comes from>\"`; for a larger edit, `sample-get "
            f"--sample-id {args.sample_id}`, edit the file it names, then `sample-edit --sample-id "
            f"{args.sample_id} --source \"...\"` (coordinator.md §3)")


def sample_edit_command(args: argparse.Namespace, events: list[tuple[int, dict]], path: Path) -> int:
    """Apply an edit of one record: log it, then write the record.

    The rows go to the log first and the record second: a failure between the two leaves a
    record that check names, and the same command run again finishes the edit. The other way
    round, a record would change with nothing in the log to say so."""
    sample_id = args.sample_id

    def refuse(message: str) -> int:
        print(f"not logged: nothing was written to {portable_path(path)} or to the record. "
              f"{message}", file=sys.stderr)
        return 2

    flags = old_edit_flags(args)
    if flags:
        return refuse(flags)
    if sum([args.adopt, bool(args.set), args.source_file is not None]) > 1:
        return refuse("--set, --from and --adopt are three ways to say what changed: use one")
    last = [(line, e) for line, e in events if e.get("event") == "sample_edit" and is_new(e)
            and e.get("sample_id") == sample_id and e.get("sha_after")]
    done, waiting = finish_cut_off(path, events, sample_id)
    if done:
        print(done)
    try:
        if args.adopt:
            return refuse(waiting) if waiting else adopt_edit(args, events, path, refuse)
        source = args.source_file or edit_file(path, sample_id)
        base = None
        if args.set:
            file, current = locate_record(sample_id, events, args.annotations)
            new = json.loads(json.dumps(current))
            for assignment in args.set:
                set_field(new, assignment)
        else:
            try:
                new = json.loads(source.read_text(encoding="utf-8"))
            except OSError:
                return refuse(f"there is no {source}. Change a field with --set <field>=<value>, "
                              f"or get the record with `coordinator_log.py {args.video_id} "
                              f"sample-get --sample-id {sample_id}`, edit the file it names and "
                              f"run this command again")
            except json.JSONDecodeError as exc:
                return refuse(f"{source} is not valid JSON ({exc.msg}, line {exc.lineno}): fix "
                              f"the file and run this command again")
            if not isinstance(new, dict) or new.get("id") != sample_id:
                found = new.get("id") if isinstance(new, dict) else type(new).__name__
                return refuse(f"{source} holds {found!r}, not the record {sample_id}: id is not "
                              f"edited, and --sample-id names the record the file was taken from")
            try:
                base = json.loads(base_note(source).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                base = None
            if base is None and args.annotations is not None:
                return add_record(args, events, path, new, refuse)
            file, current = locate_record(sample_id, events,
                                          args.annotations or (base or {}).get("annotations"))
    except sample_edit.EditError as exc:
        return refuse(str(exc))
    except (json.JSONDecodeError, AttributeError) as exc:
        return refuse(f"a file of data/annotations/ has a line that is not a record ({exc}). "
                      f"`tools/validate_samples.py data/annotations/partial/{args.video_id}."
                      f"*.jsonl` names the file and the line; the tool does not write a file "
                      f"it cannot read whole")
    except (OSError, review_inputs.InputsError) as exc:
        missing = str(exc).startswith("no record")
        return refuse(str(exc) + (
            f". To add a new sample, write its record to a file and name the file of "
            f"data/annotations/partial/ it goes to: sample-edit --sample-id {sample_id} --from "
            f"<file> --annotations <partial file> --source \"...\"" if missing else ""))
    was, now = review_inputs.record_sha(current), review_inputs.record_sha(new)
    if last and last[-1][1]["sha_after"] == now:
        line = last[-1][0]
        if was == now:
            if not args.set and base is not None:
                base_note(source).write_text(json.dumps({**base, "sha": now}) + "\n",
                                             encoding="utf-8")
            print(f"the record already holds this edit (line {line}): nothing was written")
            return 0
        if was == last[-1][1].get("sha_before"):
            # logged, then cut off before the record was written: finish it
            why = put_record(file, sample_id, was, new)
            if why:
                return refuse(f"the record still does not hold the edit of line {line}: {why}")
            keep_version(path, new)
            if not args.set:
                base_note(source).write_text(json.dumps({
                    **(base or {}), "sample_id": sample_id, "annotations": portable_path(file),
                    "sha": now}) + "\n", encoding="utf-8")
            print(f"the edit of line {line} was in the log and not in the record: the record is "
                  f"written now ({portable_path(file)}); nothing new was logged")
            return 0
    if waiting:
        return refuse(waiting)
    # A record changed without the tool is logged first (--adopt): an edit applied on top of
    # it would make the changed record the version the log knows, with the change, and the
    # reviews it owes, never recorded.
    drift = [problem for problem in record_drift(events) if problem.startswith(f"{sample_id}: ")]
    if drift:
        return refuse(f"{drift[0]}. Then run this command again")
    if not args.set:
        if base is None:
            return refuse(f"{base_note(source).name} is missing, so the tool cannot tell which "
                          f"version of the record {source} was taken from. Get the record with "
                          f"sample-get and make the edit in the file it writes")
        if base.get("sha") != was:
            return refuse(f"{sample_id} has changed since {source} was taken from it: another "
                          f"edit was applied in between, and this file would write the earlier "
                          f"version back over it. Run sample-get again and make this edit in the "
                          f"fresh file")
    if was == now:
        return refuse("the record already has these values: nothing changed")
    try:
        rows, moved, remarks = sample_edit.diff_record(
            current, new, measured_in(path, events, sample_id, args.source))
    except sample_edit.EditError as exc:
        return refuse(str(exc))
    if not rows:
        return refuse("the values are the ones the record has, written differently (212 and "
                      "212.0, for example): nothing changed that a review reads, so there is "
                      "nothing to log or write. Write a value as the record has it")
    fresh = sample_edit.new_errors(current, new)
    if fresh:
        return refuse(f"the edit breaks the record ({'; '.join(fresh)}). Fix "
                      f"{'the values' if args.set else source} and run the command again; "
                      f"`tools/validate_samples.py --rules` lists the rules")
    adjudicated = adjudicated_windows(events)
    remap_windows(adjudicated, {"sample_id": sample_id, **moved})
    for row in rows:
        if row["span"] and (sample_id, row["window"]) not in adjudicated:
            return refuse(f"window {row['window']} of {sample_id} has no adjudicate event yet: a "
                          f"span is applied only after it has been checked against t_val of its "
                          f"stretch (coordinator.md, §6, \"Check every span against t_val\"). "
                          f"Adjudicate the stretch with --window {row['window']}, then apply the "
                          f"span if it agrees" + ("; the other changes of this edit can be "
                                                  "applied now without it" if len(rows) > 1 else ""))
    logged = edit_events(args, rows, moved, file, was, now)
    keep_version(path, current)
    keep_version(path, new)
    append_event(path, logged)
    why = put_record(file, sample_id, was, new)
    if why:
        print(f"the edit is logged ({len(logged)} rows), but the record was not written: {why}. "
              f"Do not write the record yourself. Run `coordinator_log.py {args.video_id} check`: "
              f"it says how to bring the log and the record together", file=sys.stderr)
        return 2
    if not args.set:
        base_note(source).write_text(json.dumps({**base, "sha": now}) + "\n", encoding="utf-8")
    return report_edit(logged, remarks, file, path)


def report_edit(logged: list[dict], remarks: list[str], file: Path, path: Path) -> int:
    print(f"logged {len(logged)} sample_edit row{'s' if len(logged) > 1 else ''} ({path}) and "
          f"wrote the record ({portable_path(file)})")
    for event in logged:
        print(f"next: {owed_after(event)}")
    for remark in remarks:
        print(f"note: {remark}")
    if any(event["kind"] in ("wording", "boundary", "nudge", "timing") for event in logged):
        print("next: re-read validation.notes, question_time_note and provenance for sentences "
              "that state the old value (coordinator.md §3)")
    return 0


def add_record(args: argparse.Namespace, events: list[tuple[int, dict]], path: Path,
               new: dict, refuse) -> int:
    """A new sample: its record goes to the end of the file --annotations names."""
    file = review_inputs.locate(ROOT, str(args.annotations))
    if file.parent.name != "partial":
        return refuse(f"a new sample goes to a file of data/annotations/partial/, not "
                      f"{portable_path(file)}")
    now = review_inputs.record_sha(new)
    logged_before = any(e.get("event") == "sample_edit" and e.get("added")
                        and e.get("sha_after") == now and e.get("sample_id") == args.sample_id
                        for _, e in events)
    try:
        elsewhere, existing = review_inputs.find_record(ROOT, args.sample_id)
        if logged_before and review_inputs.record_sha(existing) == now:
            print(f"{args.sample_id} is in {portable_path(elsewhere)} and in the log already: "
                  f"nothing was written")
            return 0
        return refuse(f"{args.sample_id} is already in {portable_path(elsewhere)}: to change it, "
                      f"use sample-get; a new sample takes a new id")
    except review_inputs.InputsError as exc:
        if "several files" in str(exc):
            return refuse(str(exc))
    errors = sample_edit.record_errors(new)
    if errors:
        return refuse(f"the new record does not pass the validator ({'; '.join(errors)}). Fix "
                      f"the file and run the command again")
    if logged_before:
        why = put_record(file, args.sample_id, None, new)  # logged before, cut off: finish it
        if why:
            return refuse(why)
        print(f"{args.sample_id} was in the log and not in {portable_path(file)}: the record is "
              f"written now; nothing new was logged")
        return 0
    row = {"kind": "wording", "window": None, "span": False, "fields": {},
           "changes": "a new sample: every role runs on it from the start"}
    logged = edit_events(args, [row], {}, file, None, now, added=True)
    keep_version(path, new)
    append_event(path, logged[0])
    why = put_record(file, args.sample_id, None, new)
    if why:
        print(f"the new sample is logged, but its record was not written: {why}. Run the same "
              f"command again", file=sys.stderr)
        return 2
    print(f"logged sample_edit ({path}) and added {args.sample_id} to {portable_path(file)}\n"
          f"next: the sample goes through the full cycle from the start (coordinator.md §3)")
    return 0


def adopt_edit(args: argparse.Namespace, events: list[tuple[int, dict]], path: Path, refuse) -> int:
    """Log a change that was made to a record without the tool: the difference between the
    last version the log knows and the record as it is."""
    sample_id = args.sample_id
    file, current = locate_record(sample_id, events, args.annotations)
    now = review_inputs.record_sha(current)
    known = known_versions(events).get(sample_id)
    if known is None:
        # nothing to compare the record with, so nothing can be said to have changed: an
        # adopt row here would owe every review of a record that may never have been touched
        return refuse(f"the log holds no version of {sample_id} to compare the record with (no "
                      f"launch or edit of it logged by this version of the tool), so there is "
                      f"nothing to adopt and nothing is owed. `check` names a record that was "
                      f"changed without sample-edit, and only such a record is adopted")
    was = known[1].get("sha_after") or known[1].get("record_sha")
    if was == now:
        return refuse(f"the record is the version the log knows (line {known[0]}): there is "
                      f"nothing to adopt")
    old = kept_version(path, sample_id, was)
    remarks = []
    rows, moved = None, {}
    if old is not None:
        try:
            rows, moved, remarks = sample_edit.diff_record(
                old, current, measured_in(path, events, sample_id, args.source))
        except sample_edit.EditError as exc:
            remarks.append(f"the change cannot be read field by field ({exc})")
        if rows == []:
            # the same values written differently (212 and 212.0): no review reads that
            rows = [{"kind": "metadata", "window": None, "span": False, "fields": {},
                     "changes": "the same values written differently; nothing a review reads "
                                "changed"}]
    if not rows:
        rows, moved = [{"kind": "wording", "window": None, "span": False, "fields": {},
                        "changes": "changed without the tool, and the version before is not "
                                   "kept: logged as a new version of the question"}], {}
        remarks.append("the version of the record before the change is not kept, so the tool "
                       "cannot tell what changed: every role runs again")
    logged = edit_events(args, rows, moved, file, was, now, adopted=True)
    keep_version(path, current)
    append_event(path, logged)
    errors = sample_edit.record_errors(current)
    if errors:
        remarks.append(f"the record does not pass the validator: {'; '.join(errors)}")
    print(f"logged {len(logged)} sample_edit row{'s' if len(logged) > 1 else ''} ({path}) for a "
          f"change made without the tool; the record ({portable_path(file)}) is left as it is")
    for event in logged:
        print(f"next: {owed_after(event)}")
    for remark in remarks:
        print(f"note: {remark}")
    print("next: change records only through sample-edit (--set, or sample-get and the file): "
          "the tool checks the record, keeps every version and never leaves the file half-written")
    return 0


def launch_pairs(events: list[tuple[int, dict]]) -> list[dict]:
    """Every logged launch with its finish, in log order."""
    pairs: list[dict] = []
    running: dict[str, dict] = {}
    for line, event in events:
        agent = event.get("agent")
        if event.get("event") == "spawn" and agent:
            pair = {"line": line, "spawn": event, "finish": None, "finish_line": None}
            pairs.append(pair)
            running[agent] = pair
        elif event.get("event") == "finish" and agent in running:
            pair = running.pop(agent)
            pair["finish"], pair["finish_line"] = event, line
    return pairs


def measured_before(events: list[tuple[int, dict]], sample_id: str, role: str,
                    inputs: dict | None) -> tuple[str, dict | None]:
    """What a launch of a probe is, next to the launches the log holds: "open" with the
    launch of the same probe on the same material that has no finish yet; "repeat" with the
    completed launch it measures again; "second" when that one was a repeat already; "new".

    A repeat is the same probe on the same material as its last completed launch, with no edit
    in between after which the probe is owed anyway: a change of wording, or a kind whose row
    in the table of coordinator.md §3 names the role. Such an edit makes a new measurement.
    An interrupted or failed launch measured nothing and does not count. probe_verify is one
    probe per moment: its launches at other moments are other probes."""
    same = [p for p in launch_pairs(events)
            if p["spawn"].get("sample_id") == sample_id and p["spawn"].get("role") == role]
    if base_role(role) == "probe_verify":
        same = [p for p in same if p["spawn"].get("inputs") == inputs]
    if not inputs:
        return "new", None
    for pair in same:
        if pair["finish"] is None and pair["spawn"].get("inputs") == inputs:
            return "open", pair
    done = [p for p in same if p["finish"] and p["finish"].get("status") == "completed"]
    if not done or done[-1]["spawn"].get("inputs") != inputs:
        return "new", None
    last = done[-1]

    def asked_again(after: int, before: float) -> bool:
        """An edit between two lines after which the probe is measured anew."""
        for line, event in events:
            if after < line < before and event.get("event") == "sample_edit" \
                    and event.get("sample_id") == sample_id:
                kind = event.get("kind")
                if kind is None or kind == "wording" or base_role(role) in RERUN_AFTER.get(kind, ()):
                    return True
        return False

    if asked_again(last["line"], float("inf")):
        return "new", None
    # the last attempt was a repeat itself: its row says so, and a row of format 1, which
    # has no such field, is told by the same rule from the attempt before it
    was_repeat = last["spawn"].get("repeat_of") is not None or (
        len(done) > 1 and done[-2]["spawn"].get("inputs") == inputs
        and not asked_again(done[-2]["line"], last["line"]))
    return ("second" if was_repeat else "repeat"), last


REPEAT_RULE = ("A negative outcome is measured again at most once per probe and version of "
               "the sample, and only when you can name the defect of the attempt with evidence "
               "(coordinator.md §3, \"Flags are set from probe outcomes only\")")


def repeat_refusal(events: list[tuple[int, dict]], sample_id: str, role: str,
                   inputs: dict | None, reason: str | None) -> tuple[str | None, dict]:
    """Why a launch of a probe is refused, or the fields it adds to the spawn row."""
    if base_role(role) not in PROBES:
        return None, {}
    what, pair = measured_before(events, sample_id, role, inputs)
    if what == "new":
        return None, {}
    agent, line = pair["spawn"].get("agent"), pair["line"]
    if what == "open":
        return (f"{role} of {sample_id} on the same material is still open: {agent} (line "
                f"{line}). Log its finish first — completed with its review file, or "
                f"interrupted or failed — and launch again only then"), {}
    if what == "second":
        return (f"{role} of {sample_id} was measured again already: {agent} (line {line}) is "
                f"itself a repeat on the same material. {REPEAT_RULE}. A second repeat sets no "
                f"flag: the outcome of line {pair['finish_line']} is final. If this agent is "
                f"running, close it; nothing is logged for it"), {}
    if not (reason or "").strip():
        return (f"this is a repeat of {agent} (line {line}): the same probe on the same material, "
                f"with no edit of the sample in between that asks for it again. {REPEAT_RULE}. "
                f"If the attempt had such a defect, log this row again with --reason \"<the "
                f"defect, with the evidence>\"; if not, the outcome of line "
                f"{pair['finish_line']} stands and this launch sets no flag"), {}
    return None, {"repeat_of": line, "reason": reason.strip()}


def artifact_file(name: str) -> Path | None:
    for candidate in (Path(name), ROOT / name, REPO / name):
        if candidate.is_file():
            return candidate.resolve()
    return None


def keep_copy(file: Path) -> tuple[str, str]:
    """A copy of a review file as it stands, next to it in .finished/ and named by its hash:
    a later launch of the same role may write the same file name, and the earlier attempt is
    what a decision to measure again stands on."""
    data = file.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    copy = file.parent / ".finished" / f"{file.stem}.{sha[:12]}{file.suffix}"
    if not copy.exists():
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(data)
    return portable_path(copy), sha


def keep_earlier(events: list[tuple[int, dict]], sample_id: str, role: str,
                 current: Path | None = None) -> list[dict]:
    """Copies of the review files of this role's finished launches that have none yet (the
    finishes of format 1), taken before the next launch can write over them."""
    kept, seen = [], set()
    for pair in launch_pairs(events):
        spawn, finish = pair["spawn"], pair["finish"]
        if (spawn.get("sample_id"), spawn.get("role")) != (sample_id, role) or not finish:
            continue
        name = finish.get("artifact")
        if finish.get("status") != "completed" or not name or finish.get("artifact_copy"):
            continue
        file = artifact_file(name)
        if file is None or file == current or file in seen:
            continue
        try:
            finished = datetime.fromisoformat(finish["ts"]).timestamp()
        except (KeyError, ValueError):
            finished = None
        if finished is not None and file.stat().st_mtime > finished + 120:
            continue  # written again since that finish: it is no longer that attempt
        seen.add(file)
        copy, sha = keep_copy(file)
        kept.append({"finish_line": pair["finish_line"], "artifact": name, "copy": copy, "sha": sha})
    return kept


def workspace_key(name) -> str:
    """A workspace as two rows name it alike: the path from .review_ws on, whichever way it
    was typed and wherever the repository is mounted."""
    parts = Path(str(name)).parts
    if ".review_ws" in parts:
        return "/".join(parts[len(parts) - 1 - parts[::-1].index(".review_ws"):])
    path = Path(str(name))
    return portable_path((path if path.is_absolute() else ROOT / path).resolve())


def epoch(stamp) -> float | None:
    try:
        return datetime.fromisoformat(str(stamp)).timestamp()
    except ValueError:
        return None


def used_by_a_launch(workspace: Path, note: dict, prepared: float, slack: float,
                     events: list[tuple[int, dict]]) -> bool:
    """Whether a logged launch ran on this workspace as this note describes it: the same
    folder, version of the record and material, logged after the folder was cut. `slack` is
    how far the two clocks may disagree: a note that says when it was written (prepared_at)
    and the log go by the same clock; an older note is dated by its file, on the file
    server's clock. Too much slack only calls a folder used that was not, and then finish
    restores nothing from it — the safe side."""
    key = workspace_key(workspace)
    for _, event in events:
        if event.get("event") != "spawn" or not event.get("workspace"):
            continue
        if (workspace_key(event["workspace"]) == key
                and event.get("record_sha") == note.get("record_sha")
                and event.get("inputs") == note.get("inputs")):
            logged = epoch(event.get("ts"))
            if logged is None or logged >= prepared - slack:
                return True
    return False


ARTIFACT_NAME = re.compile(r"^([a-z_]+?)(\d*)\.(\d+)[a-z]?\.json$")


def restore_launch(args: argparse.Namespace, events: list[tuple[int, dict]], path: Path,
                   artifact: dict, file: Path) -> tuple[dict | str | None, list[str]]:
    """The spawn row of a launch that was never logged, restored from the workspace note it
    ran on; a refusal; or None when no note can be told to be its material.

    The note is the one of the artifact's role, sample and window that no logged launch used
    and that was cut before the artifact was saved. The row says what the subagent was given
    as the note says it; it is not compared with the record as it is now."""
    role, sample_id = artifact.get("role"), artifact.get("sample_id")
    if role not in ROLE_PROMPTS or not sample_id:
        return (f"{args.artifact} names no role and sample the tool knows (role {role!r}, "
                f"sample {sample_id!r}), so the launch it came from cannot be restored"), []
    name = ARTIFACT_NAME.match(file.name)
    window = None
    if role in WINDOW_INDEXED:
        window = artifact.get("window_idx")
        if window is None and name and name.group(2):
            window = int(name.group(2))
    iteration = artifact.get("iteration")
    if not isinstance(iteration, int) and name:
        iteration = int(name.group(3))
    saved = file.stat().st_mtime
    chosen = workspace_key(args.workspace) if args.workspace else None
    candidates = []
    for sidecar in sorted((ROOT / ".review_ws" / path.parent.name).rglob("*.inputs.json")):
        try:
            note = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        workspace = sidecar.with_name(sidecar.name[:-len(".inputs.json")])
        if chosen is not None and workspace_key(workspace) != chosen:
            continue
        if note.get("role") != role or note.get("sample_id") != sample_id:
            continue
        if window is not None and note.get("window") not in (None, window):
            continue
        cut = sidecar.stat().st_mtime
        if cut > saved + 1:
            continue  # cut after the answer was saved: the subagent did not see it
        prepared = epoch(note.get("prepared_at"))
        slack = 1.0 if prepared is not None else 120.0
        prepared = prepared or cut
        if used_by_a_launch(workspace, note, prepared, slack, events):
            continue
        candidates.append((workspace, note, prepared))
    if len(candidates) > 1:
        names = ", ".join(portable_path(w) for w, _, _ in candidates)
        return (f"the launch of {args.agent} was never logged, and several prepared workspaces "
                f"could be its material: {names}. Name the one it ran on: add --workspace "
                f"<folder> to this finish"), []
    if not candidates:
        return None, []
    workspace, note, prepared = candidates[0]
    if window is None:
        window = note.get("window")
    if role in WINDOW_INDEXED and window is None:
        return None, []
    full_role = f"{role}{window}" if role in WINDOW_INDEXED else role
    refusal, repeat = repeat_refusal(events, sample_id, full_role, note.get("inputs"),
                                     getattr(args, "reason", None))
    if refusal:
        return refusal.replace("log this row again with --reason", "log this finish again with --reason"), []
    spawn = {"ts": timestamp(), "event": "spawn", "agent": args.agent, "sample_id": sample_id,
             "role": full_role, "iteration": iteration, "model": None, "reasoning_effort": None,
             "prompt": f"docs/prompts/{ROLE_PROMPTS[role]}", "prompt_sha": None,
             "checklist_sha": None, "git_head": None, "prompts_dirty": None,
             "workspace": portable_path(workspace), "annotations": note.get("annotations"),
             "record_sha": note.get("record_sha"), "window": note.get("window"),
             "inputs": note.get("inputs"),
             "prepared_at": datetime.fromtimestamp(prepared).astimezone().isoformat(timespec="seconds"),
             "recovered": True, **repeat}
    kept = keep_earlier(events, sample_id, full_role, current=file)
    if kept:
        spawn["kept"] = kept
    return spawn, [f"the spawn of {args.agent} was never logged: it is restored from "
                   f"{portable_path(review_inputs.sidecar_path(workspace))} ({full_role} of "
                   f"{sample_id}, {describe(note.get('inputs') or {})}). Log every spawn as soon "
                   f"as spawn_agent returns the agent id"]


def last_rows(events: list[tuple[int, dict]], agent: str
              ) -> tuple[tuple[int, dict] | None, tuple[int, dict] | None]:
    """The last spawn and the last finish logged under this name, with their lines."""
    spawn = finish = None
    for line, event in events:
        if event.get("agent") != agent:
            continue
        if event.get("event") == "spawn":
            spawn = (line, event)
        elif event.get("event") == "finish":
            finish = (line, event)
    return spawn, finish


def spawn_event(args: argparse.Namespace, events: list[tuple[int, dict]], path: Path
                ) -> dict | str:
    """The spawn event, or why the launch is refused.

    The sample, the role and the window come from the note prepare_review_workspace.py left
    next to the workspace; --sample-id and --role, when given, are checked against it."""
    if args.reasoning_effort not in EFFORTS:
        return (f"--reasoning-effort {args.reasoning_effort!r}: one of {', '.join(EFFORTS)}. "
                f"Log what the launch ran with: the effort spawn_agent accepted, or default "
                f"when none was passed (omit the key)")
    if args.role and args.role not in WINDOW_INDEXED and role_error(args.role):
        return role_error(args.role)
    try:
        note = review_inputs.read_sidecar(args.workspace)
    except (OSError, json.JSONDecodeError, review_inputs.InputsError) as exc:
        return str(exc)
    sample_id = args.sample_id or note.get("sample_id")
    role = args.role or note.get("role") or ""
    if role in WINDOW_INDEXED:
        if note.get("role") == role and note.get("window") is not None:
            role = f"{role}{note['window']}"   # the note names the window; nobody types it
        elif note.get("role") == role:
            return (f"{args.workspace} was prepared for {role} with no window, and {role} is "
                    f"launched and logged per window. Prepare it again: "
                    f"prepare_review_workspace.py <VIDEO_ID> --sample-id {sample_id} --role "
                    f"{role} --window <idx> --out {args.workspace}")
    error = role_error(role)
    if error:
        return error
    active = open_launches(events)
    if args.agent in active:
        return (f"{args.agent} is still open (line {active[args.agent][0]}). Log its finish "
                f"first: completed with its review file, interrupted if it was cut off, failed "
                f"if it never started. A relaunch after an interrupted or failed finish may keep "
                f"the name")
    try:
        if note.get("sample_id") != sample_id:
            raise review_inputs.InputsError(
                f"{args.workspace} was prepared for {note.get('sample_id')}, not {sample_id}")
        if note.get("role") != base_role(role):
            raise review_inputs.InputsError(
                f"{args.workspace} was prepared for --role {note.get('role')}, not {role}")
        window = role_window(role) if base_role(role) in WINDOW_INDEXED else None
        if window is not None and note.get("window") not in (None, window):
            raise review_inputs.InputsError(
                f"{args.workspace} was cut at window {note.get('window')}, not {window}")
        _, record = review_inputs.find_logged_record(ROOT, sample_id, note["annotations"])
        if review_inputs.record_sha(record) != note.get("record_sha"):
            raise review_inputs.InputsError(
                f"{sample_id} has changed since {args.workspace} was prepared: prepare it "
                f"again with the same prepare_review_workspace.py command, then launch")
    except (OSError, KeyError, json.JSONDecodeError, review_inputs.InputsError) as exc:
        return str(exc)
    # A launch on a version of the record the log does not know would become the version it
    # knows: an edit made without the tool, or one logged and never written, would pass unseen.
    drift = [problem for problem in record_drift(events) if problem.startswith(f"{sample_id}: ")]
    if drift:
        return f"{drift[0]}. Then prepare the workspace again and launch"
    earlier, finished = last_rows(events, args.agent)
    if finished is not None and finished[1].get("status") == "completed":
        before = (earlier[1].get("inputs") or {}).get("until") if earlier else None
        after = (note.get("inputs") or {}).get("until")
        next_stretch = (base_role(role) == "semiblind" and earlier is not None
                        and earlier[1].get("sample_id") == sample_id
                        and base_role(earlier[1].get("role")) == "semiblind"
                        and (before is None or (after is not None and after > before)))
        if not next_stretch:
            return (f"{args.agent} has finished (line {finished[0]}, completed): a new launch is "
                    f"logged under a new name — the agent_id that spawn_agent returned for it. "
                    f"Only a relaunch after an interrupted or failed finish, and the next "
                    f"stretch of the same semi-blind reviewer (a workspace cut further), keep "
                    f"the name. A launch that ran and finished earlier is not logged after the "
                    f"fact: finish restores a spawn that was missed, from the workspace it ran on")
    refusal, repeat = repeat_refusal(events, sample_id, role, note.get("inputs"), args.reason)
    if refusal:
        return refusal
    event = {
        "ts": timestamp(),
        "event": "spawn",
        "agent": args.agent,
        "sample_id": sample_id,
        "role": role,
        "iteration": args.iteration,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        **prompt_version(role),
        "workspace": str(args.workspace),
        "annotations": note["annotations"],
        "record_sha": note["record_sha"],
        "window": note.get("window"),
        "inputs": note.get("inputs"),
        **repeat,
    }
    if note.get("prepared_at"):
        event["prepared_at"] = note["prepared_at"]
    kept = keep_earlier(events, sample_id, role)
    if kept:
        event["kept"] = kept
    keep_version(path, record)  # what an edit made without the tool is compared with
    return event


def event_sample(events: list[tuple[int, dict]], agent: str) -> str | None:
    spawn = last_spawn(events, agent)
    return spawn.get("sample_id") if spawn else None


def read_artifact(path: str) -> dict | None:
    file = artifact_file(path)
    if file is None:
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def finish_event(args: argparse.Namespace, events: list[tuple[int, dict]], path: Path
                 ) -> tuple[list[dict] | str, list[str], list[str]]:
    """The rows a finish writes — the finish, preceded by the spawn when it was never logged —
    with the warnings and hints to print; or why nothing is written."""
    active = open_launches(events)
    warnings: list[str] = []
    hints: list[str] = []
    rows: list[dict] = []
    spawn = active[args.agent][1] if args.agent in active else None
    artifact_name = args.artifact
    unlaunched = False
    several = ""
    if spawn is None:
        earlier, finished = last_rows(events, args.agent)
        file = artifact_file(artifact_name) if artifact_name else None
        artifact = read_artifact(artifact_name) if artifact_name else None
        names = ", ".join(sorted(active)) or "none"
        had = (f" {args.agent} already has a finish (line {finished[0]}): one launch has one "
               f"finish." if finished is not None else "")
        if file is None or not isinstance(artifact, dict):
            return (f"no open launch named {args.agent!r}.{had} A finish goes under the name its "
                    f"spawn was logged with: the agent_id that spawn_agent returned. Open "
                    f"launches: {names}. If the spawn of this agent was never logged, give the "
                    f"review file it saved (--artifact <file>): the tool restores the launch "
                    f"from the workspace it ran on"), [], []
        # the same role of the same sample is open under another name: most likely this is its
        # finish, typed under a name the spawn was not logged with
        named = ARTIFACT_NAME.match(file.name)
        window = artifact.get("window_idx")
        if window is None and artifact.get("role") in WINDOW_INDEXED and named and named.group(2):
            window = int(named.group(2))  # probe_frame2.1.json
        twins = [(name, line) for name, (line, row) in sorted(active.items())
                 if row.get("sample_id") == artifact.get("sample_id")
                 and base_role(row.get("role")) == artifact.get("role")
                 and (window is None or role_window(row.get("role") or "") in (None, window))]
        if twins and args.workspace is None:
            listed = ", ".join(f"{name} (line {line})" for name, line in twins)
            return (f"no open launch named {args.agent!r}, and {args.artifact} is a review of "
                    f"{artifact.get('role')} of {artifact.get('sample_id')}, which is open under "
                    f"another name: {listed}. A finish goes under the name its spawn was logged "
                    f"with: log it with --agent <that name>. Only if {args.agent} is a different "
                    f"launch whose spawn was never logged, add --workspace <the folder it ran "
                    f"in> to this finish"), [], []
        restored, notes = restore_launch(args, events, path, artifact, file)
        if isinstance(restored, str):
            return restored, [], []
        if restored is None and finished is not None:
            return (f"{args.agent} already has a finish (line {finished[0]}), and no prepared "
                    f"workspace that a launch has not used matches {artifact_name}. One launch "
                    f"has one finish. Open launches: {names}"), [], []
        if restored is None:
            unlaunched = True
            warnings.append(
                f"the spawn of {args.agent} was never logged, and no workspace note says what it "
                f"was given (none of this role and sample that no launch used and that was cut "
                f"before {artifact_name} was saved). The finish is logged with material \"not "
                f"found\": this outcome sets no flag and settles no rerun. Prepare a workspace "
                f"and launch the role again; that launch is a new measurement, not a repeat")
        else:
            spawn = restored
            rows.append(restored)
            warnings += notes
    elif not artifact_name and args.status == "completed":
        valid = [f for f in saved_reviews(path, spawn) if passes_check(f)]
        if len(valid) == 1:
            artifact_name = portable_path(valid[0])
            hints.append(f"artifact: {artifact_name} (the one review file this launch saved)")
        elif len(valid) > 1:
            several = ", ".join(portable_path(f) for f in valid)
    event = {"ts": timestamp(), "event": "finish", "agent": args.agent,
             "status": args.status, "summary": args.summary}
    if spawn is not None:
        for field in ("sample_id", "role", "iteration"):
            event[field] = spawn.get(field)
    if unlaunched:
        event["material"] = "not found"
        for field in ("sample_id", "role", "iteration"):
            event[field] = artifact.get(field)
    role = base_role(spawn.get("role")) if spawn else None
    artifact = read_artifact(artifact_name) if artifact_name else None
    if args.status == "completed" and role in PROBES and artifact is None:
        found = (f"{artifact_name} cannot be read as one" if artifact_name else
                 f"this launch has saved several that pass --check ({several}): name the one "
                 f"of this launch" if several else
                 "this launch has saved none that passes --check")
        return (f"a completed {spawn.get('role')} leaves its review file, and {found}. Give the "
                f"file with --artifact (`open` lists what each launch has saved); if the probe "
                f"saved none, it did not complete: log --status interrupted or failed and launch "
                f"it again"), [], []
    if artifact_name:
        event["artifact"] = artifact_name
        if artifact is None:
            if args.status == "completed":
                warnings.append(f"the artifact {artifact_name} cannot be read: a completed review "
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
            if args.status == "completed":
                # the attempt as it finished: a later launch may write the same file name
                event["artifact_copy"], event["artifact_sha"] = keep_copy(artifact_file(artifact_name))
    if spawn is not None:
        why = stale_inputs(spawn)
        if why:
            event["stale_inputs"] = why
            warnings.append(f"{spawn.get('role')} of {spawn.get('sample_id')} is stale: {why}. Its "
                            f"outcome sets no flag: prepare the workspace again with --sample-id "
                            f"and run {spawn.get('role')} anew")
    rows.append(event)
    return rows, warnings, hints


def main(argv: list[str] | None = None) -> int:
    """run(), and when the tool itself fails, a message that says so instead of a traceback:
    whether the row was written (the log grew) and what to do."""
    args = parser().parse_args(argv)
    try:
        path = log_path(args.video_id)
        size = path.stat().st_size if path.exists() else 0
    except (ValueError, OSError):
        path, size = None, 0
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 — the message is for an agent, who cannot debug
        error = f"{type(exc).__name__}: {exc}"
        report = (f"If you cannot see a cause in your arguments, record it with "
                  f"`coordinator_log.py {args.video_id} note --text \"tool problem: ...\"` and go "
                  f"on (coordinator.md, \"You change your video's data\")")
        if args.command in ("check", "open", "sample-get"):
            print(f"`{args.command}` stopped on an error of its own ({error}); it writes nothing "
                  f"to the log, so the log is as it was. {report}", file=sys.stderr)
            return 2
        grew = path is not None and path.exists() and path.stat().st_size != size
        last = path.read_text(encoding="utf-8").splitlines()[-1] if grew else ""
        try:
            whole = isinstance(json.loads(last), dict) and last.endswith("}")
        except json.JSONDecodeError:
            whole = False
        if grew and not whole:
            print(f"`{args.command}` failed on an error of its own while it wrote its row to "
                  f"{portable_path(path)} ({error}), and the last line of the log is cut off: "
                  f"check will report it as invalid JSON until the person running the pipeline "
                  f"repairs it. Do not edit the log: log the row again (it starts a line of its "
                  f"own), record `coordinator_log.py {args.video_id} note --text \"tool problem: "
                  f"a cut-off line\"`, and say so in your final message", file=sys.stderr)
        elif grew and args.command == "sample-edit":
            print(f"`sample-edit` failed on an error of its own after it logged the edit to "
                  f"{portable_path(path)} ({error}); the record may not hold it yet. Do not write "
                  f"the record yourself: run `coordinator_log.py {args.video_id} check`, which "
                  f"says whether the log and the record agree and what to do. {report}",
                  file=sys.stderr)
        elif grew:
            print(f"`{args.command}` failed on an error of its own after it wrote its row to "
                  f"{portable_path(path)} ({error}): the row stands, do not log it again. Its "
                  f"hints were not printed: run check to see where the log stands. {report}",
                  file=sys.stderr)
        else:
            saved = (" A blind_judge.*.json result file may have been saved; the verdict counts "
                     "only once it is in the log." if args.command == "blind-judge" else "")
            print(f"not logged: `{args.command}` stopped on an error of its own ({error}). "
                  f"Nothing was written to the log.{saved} {report}", file=sys.stderr)
        return 2


def run(args: argparse.Namespace) -> int:
    try:
        path = log_path(args.video_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "check":
        return validate_log(path, final=args.final)
    if args.command == "open":
        return show_open(path, args.wait)

    events, _ = read_log(path)
    if args.command == "sample-get":
        return sample_get(args, events, path)
    if args.command == "sample-edit":
        return sample_edit_command(args, events, path)
    warnings: list[str] = []
    hints: list[str] = []
    if args.command == "spawn":
        event = spawn_event(args, events, path)
        if isinstance(event, dict) and event.get("kept"):
            hints.append("the review files of the earlier attempts are kept: "
                         + ", ".join(k["copy"] for k in event["kept"]))
    elif args.command == "finish":
        event, warnings, hints = finish_event(args, events, path)
        if isinstance(event, list) and event[-1].get("artifact_role") == "semiblind":
            hints.append(f"score the blind answer: `coordinator_log.py {args.video_id} blind-judge "
                         f"--sample-id {event[-1].get('sample_id')} --review "
                         f"{event[-1].get('artifact')}`; blind_solved is set from its verdict")
    elif args.command == "blind-judge":
        event = blind_judge_event(args, events, args.video_id)
        if isinstance(event, dict):
            verdict = ("credited every required item: blind_solved is true unless a blind-ruling "
                       "names a guess or content only this video has" if event["met"] else
                       f"did not credit {', '.join(event['items_unmet'])}: blind_solved is false "
                       f"unless a blind-ruling says these items are about the look of the screen "
                       f"only")
            hints.append(f"the judge {verdict} (coordinator.md, \"Blind solving\"). Read the "
                         f"review's prior_answer_assumptions too: a credited item that rests on "
                         f"an assumption about the screen listed there is ruled screen-guess. "
                         f"Copy the item-by-item verdict from {event['result']} into "
                         f"coordinator.<ROUND>.md")
    elif args.command == "blind-ruling":
        event = blind_ruling_event(args, events)
    elif args.command == "note":
        event = {"ts": timestamp(), "event": "note", "text": args.text}
        if args.agent:
            event["agent"] = args.agent
        if args.refers_to:
            event["refers_to"] = args.refers_to
    else:
        event, hints = adjudicate_event(args, events, path)

    if isinstance(event, str):
        print(f"not logged: nothing was written to {portable_path(path)}. {event}", file=sys.stderr)
        return 2
    rows = event if isinstance(event, list) else [event]
    append_event(path, rows)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"logged {' and '.join(row['event'] for row in rows)}: {path}")
    for hint in hints:
        print(f"next: {hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

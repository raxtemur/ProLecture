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
    python3 tools/coordinator_log.py VIDEO open --wait 50

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
A frame probe cut at a window that is no longer required — the window turned optional, or
the windows were renumbered when an optional one was put before it — is superseded rather
than stale: it cannot be run there again, and it sets no flag. ``check --final`` then asks
only that every required window of the record has a frame probe of its own.

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

``sample-edit --span`` marks an edit of a window's ``evidence_span``. It is refused until
that window's stretch has been adjudicated: a span is applied only after it has been checked
against ``t_val`` (checklist 7.5).

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
    with path.open("a+b") as stream:  # appends go to the end whatever the read position
        size = stream.seek(0, os.SEEK_END)
        cut = False
        if size:
            stream.seek(size - 1)
            cut = stream.read(1) != b"\n"
        # a line cut off by a failed write stays as it is; the new row starts a line of its own
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        stream.write((("\n" if cut else "") + line).encode("utf-8"))


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
    """The record as it stands now, found through the file the sample's last launch was
    prepared from; None when it cannot be read."""
    names = [e["annotations"] for _, e in events
             if e.get("sample_id") == sample_id and e.get("annotations")]
    try:
        if names:
            return review_inputs.find_logged_record(ROOT, sample_id, names[-1])[1]
        return review_inputs.find_record(ROOT, sample_id)[1]
    except (OSError, KeyError, json.JSONDecodeError, review_inputs.InputsError):
        return None


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

    active: set[str] = set()
    launches = finishes = edits = adjudications = notes = blind = 0
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
            window = event.get("window")
            if window is None:
                errors += [f"line {line_number}: {e}" for e in check_adjudication(event)]
            else:
                # a windowed row is weighed with its stretch, which a correction may supersede
                adjudicated.add((event.get("sample_id"), window))
                key = (event.get("sample_id"), event.get("iteration"), window)
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

    corrections, owed = [], []
    for (sample_id, iteration, window), rows in stretches.items():
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

    for agent in sorted(active - noted):
        errors.append(f"launch without finish: {agent}")

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

# Temporary, 2026-10-21: a caption for the rows whose error check did not report while a
# coordinator's loosening of check_stretch was in tools/ (04:29 until its revert), and for one
# that a note tried to correct, keyed by (video, line, ts). Remove an entry once its log passes
# check --final.
LOOSENED = ("Earlier this row passed check by mistake: on 2026-10-21 from 04:29 until its revert, "
            "tools/coordinator_log.py carried a coordinator's loosening of check_stretch, and the "
            "sample was wrongly taken to pass. Why it is an error: ")
CAPTIONS = {
    ("YtkIWDE36qU", 43, "2026-10-20T14:25:09+03:00"): LOOSENED + (
        "t_val 633.0 is the boundary of window 0's stretch (line 42), not of window 1. Every "
        "window has its own t_val from its own rows (t_val[k] < t_start[k] is 2.2 of window k), "
        "and coordinator.1.md gives window 1's as 672.0, the author's reveal. The 2.3 hit and "
        "the move of question_time rest on window 0 and are not affected: only this row is "
        "wrong."),
    ("851U557j6HE", 153, "2026-10-21T01:50:40+03:00"): LOOSENED + (
        "576.0 is no answer of the semi-blind trajectory: semiblind.1.json has none between "
        "573.2 and 582.9. It is where full_sample and full_window0 place the length, a sighted "
        "placement, and a sighted placement becomes the boundary only as a t_s that stage C "
        "verifies. None was owed here: full_sample returned no t_s, and the span [576.0, 582.9] "
        "does not end more than 2 s before t_val_A. Line 168 (round 2) carries the same 576.0."),
    ("VYQVlVoWoPY", 59, "2026-10-21T00:48:04+03:00"): LOOSENED + (
        "the re-read of stage A in coordinator.1.md (the answers from 135.4 are the route of "
        "the level, not a harder one) changed t_val_a 936.0 -> 135.4, but a second plain row is "
        "a disagreement within the stretch, not a correction of it."),
    ("VYQVlVoWoPY", 18, "2026-10-20T21:47:05+03:00"): (
        "The note at line 19 records the right values (t_val_a and t_val null; 73.0 is q01's), "
        "but check reads the adjudicate rows, not notes."),
}
# Temporary, 2026-10-21: rows check passes although they are wrong, because nothing compares the
# first row of a stretch with the trajectory, keyed as CAPTIONS. Each is an error until its
# stretch is corrected, and a stretch that holds one takes no further row but a correction.
WRONG_ROWS = {
    ("851U557j6HE", 168, "2026-10-21T04:21:21+03:00"): (
        "this row was logged under round 2 to get around check_stretch (the note at line 169), "
        "with no review of round 2 behind it, and carries the 576.0 of line 153, which is no "
        "answer of the semi-blind trajectory (see line 153). It passed check only because "
        "nothing compares the first row of a stretch with the trajectory. Correct this stretch "
        "in round 2 as you correct round 1's, from the same semiblind.1.json, and log nothing "
        "further under round 2 unless a round 2 of review takes place"),
}


def stretch_answers(sample_dir: Path, window: int, source) -> tuple[list[float], str | None]:
    """The moments of the answers in the stretch of `window` of the semi-blind review `source`
    names (its scan with that idx), or why they cannot be read."""
    match = SEMIBLIND_REVIEW.match(str(source or ""))
    if not match:
        return [], (f"a correction cites the semi-blind review its t_val_a comes from: --source "
                    f"semiblind.<ROUND>.json, not {source!r}")
    review = sample_dir / match.group(1)
    try:
        scans = json.loads(review.read_text(encoding="utf-8")).get("scans") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return [], f"the semi-blind review {portable_path(review)} cannot be read"
    own = [scan for scan in scans if isinstance(scan, dict) and scan.get("idx") == window]
    moments = [t for scan in own for candidate in scan.get("candidates") or []
               if isinstance(candidate, dict)
               for t in [candidate.get("t")] if isinstance(t, (int, float))]
    if not moments:
        # no stretch of its own (one scan over several windows) or no timed answers (the legacy
        # shape): "no answer" cannot be told from "not read", so nothing is weighed there
        found = sorted(str(scan.get("idx")) for scan in scans if isinstance(scan, dict))
        what = (f"has no timed answers in its stretch of window {window}" if own else
                f"has no stretch of window {window} (its stretches: {', '.join(found) or 'none'})")
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
                          correction: dict) -> tuple[list[float], str | None]:
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
    return stretch_answers(sample_dir, window, correction.get("source"))


def is_answer(moments: list[float], t) -> bool:
    return isinstance(t, (int, float)) and any(abs(moment - t) <= MOMENT_TOLERANCE
                                               for moment in moments)


def correction_refusal(sample_dir: Path, window: int, superseded: list[tuple[int, dict]],
                       correction: dict) -> list[str]:
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
    moments, unreadable = correction_trajectory(sample_dir, window, superseded, correction)
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
                      correction: dict) -> list[tuple[int, float]]:
    """The earlier t_val_a that are no answer of the trajectory and that a correction moves
    past: sighted placements, on which stage C may have been owed."""
    moments, unreadable = correction_trajectory(sample_dir, window, superseded, correction)
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


def stretch_rows(events: list[tuple[int, dict]], sample_id: str, iteration: int,
                 window: int) -> list[tuple[int, dict]]:
    """The adjudicate rows of one stretch, in log order."""
    key = (sample_id, iteration, window)
    return [(line, e) for line, e in events if e.get("event") == "adjudicate"
            and (e.get("sample_id"), e.get("iteration"), e.get("window")) == key]


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
    video = path.parent.name
    current = current_rows(rows)
    errors, owed = [], []
    for line, event in current:
        errors += [f"line {line}: {e}" for e in check_adjudication(event)]
        wrong = WRONG_ROWS.get((video, line, event.get("ts")))
        if wrong:
            errors.append(f"line {line}: {where}: {wrong}. {CORRECTION_HINT}")
    for index, problem in check_stretch([event for _, event in current]):
        line, event = current[index]
        message = f"line {line}: {where}: {problem}. {CORRECTION_HINT}"
        caption = CAPTIONS.get((video, line, event.get("ts")))
        errors.append(f"{message}\n  {caption}" if caption else message)
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
    rows = stretch_rows(events, *key)
    if args.correction is None and rows:
        broken, _ = weigh_stretch(path, key, rows, events)
        if broken:
            found = "; ".join(problem.replace(f". {CORRECTION_HINT}", "").replace("\n  ", " ")
                              for problem in broken)
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
                                                    rows, event):
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
                for problem in correction_refusal(sample_dir, window, superseded, correction)]
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


def saved_review(path: Path, spawn: dict) -> Path | None:
    """The review file the launch has saved since it started, if any: ``<role>.<iteration>``
    with the role as logged (``full_window0``), a number after ``probe_verify`` and a letter
    after the round (a repeat, ``probe_frame0.1b``)."""
    role, iteration = spawn.get("role") or "", spawn.get("iteration")
    pattern = re.compile(rf"{re.escape(role)}\d*\.{iteration}[a-z]?\.json")
    try:
        started = datetime.fromisoformat(spawn["ts"]).timestamp()
    except (KeyError, ValueError):
        started = 0.0
    folder = path.parent / (spawn.get("sample_id") or "")
    found = [f for f in folder.glob(f"{role}*.json")
             if pattern.fullmatch(f.name) and f.stat().st_mtime >= started]
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
        _, record = review_inputs.find_logged_record(ROOT, args.sample_id, note["annotations"])
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


def event_sample(events: list[tuple[int, dict]], agent: str) -> str | None:
    spawn = last_spawn(events, agent)
    return spawn.get("sample_id") if spawn else None


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
        if args.command in ("check", "open"):
            print(f"`{args.command}` stopped on an error of its own ({error}); it writes nothing, "
                  f"so the log is as it was. {report}", file=sys.stderr)
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
    warnings: list[str] = []
    hints: list[str] = []
    if args.command == "spawn":
        event = spawn_event(args, events)
    elif args.command == "finish":
        event, warnings = finish_event(args, events)
        if isinstance(event, dict) and event.get("artifact_role") == "semiblind":
            hints.append(f"score the blind answer: `coordinator_log.py {args.video_id} blind-judge "
                         f"--sample-id {event_sample(events, args.agent)} --review "
                         f"{args.artifact}`; blind_solved is set from its verdict")
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
            if args.kind in ("rubric", "wording"):
                hints.append("the rubric the blind answer was judged on may have changed: run "
                             "blind-judge again on the semi-blind review the new version has")
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
    append_event(path, event)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"logged {event['event']}: {path}")
    for hint in hints:
        print(f"next: {hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

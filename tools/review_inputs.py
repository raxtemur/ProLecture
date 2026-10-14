"""Which material a review role gets, read off the sample record itself.

The coordinator used to type the boundaries of every workspace by hand — `--until` from one
window, `--frame` from another — and once the material of a whole run slid by one question
(fix list 6, 6.7.4). Here the boundaries come from the record found by its id, and the
workspace keeps a note of which version of the record it was built from:

    <workspace>.inputs.json   next to the workspace, never inside it

`tools/prepare_review_workspace.py --sample-id` writes the note; `tools/coordinator_log.py
spawn --workspace` refuses a launch whose record has changed since, and `finish` and
`check --final` name a probe whose inputs no longer match the current windows (6.7.5).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# What each role is given. `until` from the last required window: the modality probes run
# once per sample and answer to the rubric of every required window.
LAST_WINDOW_ROLES = {"probe_text": "transcript", "probe_vision": "frames", "probe_full": "both"}
# Roles whose workspace is cut at one window, named with --window: the semi-blind stretch
# ends at any window, required or optional (checklist 2.2, stage A: an optional window's
# left boundary is otherwise checked by nobody); the frame probe runs on required ones.
WINDOW_ROLES = ("semiblind", "probe_frame")
ROLES = ("semiblind", "probe_verify", *LAST_WINDOW_ROLES, "probe_frame",
         "full_sample", "full_window")
# The probes whose material follows from the record alone, so a moved window makes their
# outcome stale. probe_verify is cut at a t_s, which the record does not hold.
STALE_ROLES = ("probe_text", "probe_vision", "probe_full", "probe_frame")


class InputsError(ValueError):
    """A record or a workspace note that cannot be used; the message says what to do."""


def annotation_files(root: Path) -> list[Path]:
    base = root / "data" / "annotations"
    return sorted(base.glob("*.jsonl")) + sorted((base / "partial").glob("*.jsonl"))


def read_records(path: Path) -> dict[str, dict]:
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record.get("id")] = record
    return records


def find_record(root: Path, sample_id: str, annotations: Path | None = None) -> tuple[Path, dict]:
    """The record with this id, and the file it was read from."""
    if annotations is not None:
        record = read_records(annotations).get(sample_id)
        if record is None:
            raise InputsError(f"no record {sample_id!r} in {annotations}")
        return annotations.resolve(), record
    found = [(path, records[sample_id]) for path in annotation_files(root)
             if sample_id in (records := read_records(path))]
    if not found:
        raise InputsError(f"no record {sample_id!r} in data/annotations/*.jsonl or "
                          f"data/annotations/partial/; pass --annotations <file>")
    if len(found) > 1:
        names = ", ".join(str(path.relative_to(root)) for path, _ in found)
        raise InputsError(f"record {sample_id!r} is in several files: {names}. Name the one "
                          f"you are editing with --annotations <file> — until the video is "
                          f"merged, the coordinator edits the proposer's files in "
                          f"data/annotations/partial/")
    path, record = found[0]
    return path.resolve(), record


def find_logged_record(root: Path, sample_id: str, name: str) -> tuple[Path, dict]:
    """The record a workspace note or a log line names by its file: from that file while it
    exists, and from wherever the record is now once it is gone — the proposer's files in
    partial/ are merged into data/annotations/<VIDEO_ID>.jsonl when the video is closed."""
    path = locate(root, name)
    return find_record(root, sample_id, path if path.exists() else None)


def portable(path: Path, root: Path) -> str:
    """The file as the repository names it: relative to the root when it lies inside it.

    A job container mounts the same repository under another path, and `resolve()` there
    writes that path into the note; read back in the notebook, it names nothing."""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def locate(root: Path, name: str) -> Path:
    """A path from a note or a log line: relative ones are relative to the repository root."""
    path = Path(name)
    return path if path.is_absolute() else root / path


def record_sha(record: dict) -> str:
    """The version of a record: any edit of it — a boundary, a note, the status — changes it."""
    text = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def window_trigger(record: dict, window: int | None, role: str, required: bool = True) -> dict:
    """The trigger with this idx; with `required`, only a required one."""
    if window is None:
        raise InputsError(f"--role {role} needs --window <idx>: the index of the window its "
                          f"material is cut at")
    for trigger in record.get("triggers", []):
        if trigger.get("idx") == window:
            if required and not trigger.get("required"):
                raise InputsError(f"window {window} of {record.get('id')} is optional; "
                                  f"{role} is cut at required windows only")
            return trigger
    raise InputsError(f"{record.get('id')} has no window {window}")


def derive_inputs(role: str, record: dict, window: int | None = None,
                  until: float | None = None, duration: float | None = None) -> dict:
    """The boundaries of a role's material: {"until": t} or {"frame": t}."""
    if role in LAST_WINDOW_ROLES:
        ends = [t["t_end"] for t in record.get("triggers", []) if t.get("required")]
        if not ends:
            raise InputsError(f"{record.get('id')} has no required window")
        return {"until": max(ends)}
    if role == "probe_frame":
        trigger = window_trigger(record, window, role)
        return {"frame": round((trigger["t_start"] + trigger["t_end"]) / 2, 1)}
    if role == "semiblind":
        return {"until": window_trigger(record, window, role, required=False)["t_end"]}
    if role == "probe_verify":
        if until is None:
            raise InputsError("--role probe_verify needs --until <t_s>: the material is cut at "
                              "the sighted proposal being verified")
        return {"until": until}
    if role in ("full_sample", "full_window"):
        if duration is None:
            raise InputsError("the bundle gives no duration for the full reviewers' material")
        return {"until": duration}
    raise InputsError(f"unknown role {role!r}; one of {', '.join(ROLES)}")


def sidecar_path(workspace: Path) -> Path:
    workspace = Path(workspace)
    return workspace.with_name(workspace.name + ".inputs.json")


def write_sidecar(workspace: Path, note: dict) -> Path:
    path = sidecar_path(workspace)
    path.write_text(json.dumps(note, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def read_sidecar(workspace: Path) -> dict:
    path = sidecar_path(workspace)
    if not path.exists():
        raise InputsError(f"no {path.name} next to the workspace: prepare it with "
                          f"tools/prepare_review_workspace.py <VIDEO_ID> --sample-id <ID> "
                          f"--role <ROLE> [--window <idx>] --out {workspace}")
    return json.loads(path.read_text(encoding="utf-8"))

"""What an edit of a sample record changed, and which kind of edit each change is.

`coordinator_log.py sample-edit` reads the kinds off the record itself: the coordinator used to
choose `--kind`, `--window` and `--span` by hand, and one and the same change was logged under
four different kinds. The kind decides which reviews run again (`RERUN_AFTER` in
coordinator_log.py, the table in docs/prompts/coordinator.md §3), so the mapping here and that
table say the same thing.

Every property of schema/sample.schema.json has a row in `TOP_FIELDS` or `TRIGGER_FIELDS`
(tests/test_sample_edit.py checks it). A field with no row is refused, never passed as
metadata: a new field gets its kind when it is added to the schema.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Callable

import review_inputs

# A boundary or question_time moved by this much or less is within the tolerance
# (docs/prompts/definitions.md, "Boundary tolerance").
TOLERANCE = 2.0

REFUSE, SPECIAL = "refuse", "special"
# The fields of a record: the kind of edit a change of each is. SPECIAL ones are decided by
# the size of the change or window by window, below.
TOP_FIELDS: dict[str, str] = {
    "id": REFUSE,                    # the name every review and log line knows the sample by
    "video": REFUSE,                 # the video is not what a review can change
    "question": "wording",
    "question_time": SPECIAL,        # timing within the tolerance, wording beyond it
    "act": "level",                  # no rerun; stage A is read again
    "reasoning_level": "level",
    "twin_of": "rubric",             # the pair is what full_sample checks
    "triggers": SPECIAL,
    "temporal_rel": "metadata",      # derived from the spans; the span edit carries the kind
    "template": "metadata",
    "audio_dependency": "metadata",
    "audio_dependency_claim": "metadata",
    "followup": "metadata",
    "provenance": "metadata",
    "validation": "metadata",
    "question_time_note": "metadata",
}
TRIGGER_FIELDS: dict[str, str] = {
    "idx": SPECIAL,                  # a renumbered window: boundary for its new index
    "required": "boundary",
    "t_start": SPECIAL,              # nudge or boundary
    "t_end": SPECIAL,
    "evidence_span": SPECIAL,        # boundary when the derived temporal_rel changes, else metadata
    "response": "rubric",            # the reference answer the judge reads
    "rubric": "rubric",
    "depends_on": "rubric",          # checked by full_window (7.4) and full_sample
    "t_ideal": "metadata",           # a service field; the delay is counted from t_start
    "trigger_modality": "metadata",
}
MISSING = object()


class EditError(ValueError):
    """An edit the tool does not take; the message says what to do."""


def record_errors(record: dict) -> list[str]:
    """What tools/validate_samples.py says of one record: the schema and the rules that
    concern a single record."""
    from jsonschema.validators import validator_for
    import validate_samples
    validator = validator_for(validate_samples.SCHEMA)(validate_samples.SCHEMA)
    errors = sorted(f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}"
                    for e in validator.iter_errors(record))
    try:
        errors += validate_samples.semantic_checks(record)
    except (KeyError, IndexError, TypeError) as exc:
        errors.append(f"semantic: could not be checked ({type(exc).__name__}: {exc})")
    return errors


def new_errors(before: dict | None, after: dict) -> list[str]:
    """The validator errors the record has after the edit and did not have before it. The
    numbers in a message are not compared: an error that was there with other values is the
    same error."""
    def shape(message: str) -> str:
        return re.sub(r"-?\d+(?:\.\d+)?", "#", message)

    had = Counter(shape(m) for m in (record_errors(before) if before is not None else []))
    fresh = []
    for message in record_errors(after):
        if had[shape(message)]:
            had[shape(message)] -= 1
        else:
            fresh.append(message)
    return fresh


def window_idx(trigger: dict, position: int) -> int:
    idx = trigger.get("idx")
    return idx if isinstance(idx, int) else position


def match_windows(old: list[dict], new: list[dict]) -> tuple[dict[int, int], list[int], list[int]]:
    """Which window of the old record each window of the new one is: by content, not by idx.

    An optional window put before the others shifts every idx after it; matched by idx, each
    shifted window would read as a new boundary and a new rubric. The windows are paired by
    what they hold: everything but the index, then the boundaries, then the rubric with the
    reference answer; what is left is paired in order when the counts agree. Returns
    {old idx: new idx}, the old idx of the windows that went away and the new idx of the added."""
    def without(trigger: dict, *fields: str) -> str:
        return json.dumps({k: v for k, v in trigger.items() if k not in fields}, sort_keys=True)

    keys: list[Callable[[dict], object]] = [
        lambda t: without(t, "idx", "depends_on"),
        lambda t: (t.get("t_start"), t.get("t_end")),
        lambda t: json.dumps([t.get("rubric"), t.get("response")], sort_keys=True),
    ]
    left, right = list(range(len(old))), list(range(len(new)))
    pairs: dict[int, int] = {}
    for key in keys:
        for i in list(left):
            for j in right:
                if key(old[i]) == key(new[j]):
                    pairs[i] = j
                    left.remove(i)
                    right.remove(j)
                    break
    if len(left) == len(right):
        pairs.update(zip(left, right))
        left, right = [], []
    return ({window_idx(old[i], i): window_idx(new[j], j) for i, j in sorted(pairs.items())},
            [window_idx(old[i], i) for i in left], [window_idx(new[j], j) for j in right])


def derived_rel(record: dict) -> str | None:
    import validate_samples
    try:
        return validate_samples.derive_temporal_rel(record)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def diff_record(old: dict, new: dict, measured: Callable[[float], bool] = lambda value: False
                ) -> tuple[list[dict], dict, list[str]]:
    """The edit as rows of the log: one per kind and window, each {"kind", "window", "span",
    "fields": {path: [before, after]}}; how the windows were renumbered ({"renumbered":
    {old: new}, "removed": [old]}); and what to tell the coordinator.

    `measured(t)` says whether a moment is a reviewer's own measurement: a number of the
    full_window or semi-blind review the edit names as its source, or a t_s verified yes."""
    groups: dict[tuple[str, int | None, bool], dict] = {}
    remarks: list[str] = []

    def put(kind: str, window: int | None, path: str, before, after, span: bool = False) -> None:
        groups.setdefault((kind, window, span), {})[path] = [
            None if before is MISSING else before, None if after is MISSING else after]

    changed = [k for k in sorted(set(old) | set(new)) if old.get(k, MISSING) != new.get(k, MISSING)]
    unknown = [k for k in changed if k not in TOP_FIELDS]
    if unknown:
        raise EditError(f"the field(s) {', '.join(unknown)} are not fields of a sample record "
                        f"(schema/sample.schema.json): the tool does not know which reviews a "
                        f"change of them owes. Remove them from the file")
    fixed = [k for k in changed if TOP_FIELDS[k] == REFUSE]
    if fixed:
        raise EditError(f"{' and '.join(fixed)} cannot be changed: every review and log line "
                        f"names the sample by them. To replace a sample, set its "
                        f"validation.status to rejected and add the new one under a new id")
    mapping: dict[int, int] = {}
    removed: list[int] = []
    for field in changed:
        before, after = old.get(field, MISSING), new.get(field, MISSING)
        if field == "question_time":
            small = number(before) and number(after) and abs(after - before) <= TOLERANCE
            put("timing" if small else "wording", None, field, before, after)
            if not small:
                remarks.append(f"question_time moved by more than {TOLERANCE:g} s: the moment at "
                               f"which the question must make sense changed, so this is a new "
                               f"version of the question (definitions.md, \"Boundary tolerance\")")
        elif field == "triggers":
            mapping, removed = diff_windows(old, new, measured, put, remarks)
        elif isinstance(before, dict) and isinstance(after, dict):
            for sub in sorted(set(before) | set(after)):
                if before.get(sub, MISSING) != after.get(sub, MISSING):
                    put(TOP_FIELDS[field], None, f"{field}.{sub}", before.get(sub, MISSING),
                        after.get(sub, MISSING))
        else:
            put(TOP_FIELDS[field], None, field, before, after)
    order = ("wording", "boundary", "nudge", "rubric", "level", "timing", "metadata")
    rows = [{"kind": kind, "window": window, "span": span, "fields": fields}
            for (kind, window, span), fields in sorted(
                groups.items(), key=lambda item: (order.index(item[0][0]),
                                                  item[0][1] is None, item[0][1] or 0, item[0][2]))]
    moved = {"renumbered": {old_idx: new_idx for old_idx, new_idx in mapping.items()
                            if old_idx != new_idx}, "removed": removed}
    return rows, moved, remarks


def diff_windows(old: dict, new: dict, measured: Callable[[float], bool], put: Callable,
                 remarks: list[str]) -> tuple[dict[int, int], list[int]]:
    before_all, after_all = old.get("triggers") or [], new.get("triggers") or []
    if not (isinstance(before_all, list) and isinstance(after_all, list)
            and all(isinstance(t, dict) for t in before_all + after_all)):
        raise EditError("triggers is a list of objects, one per window")
    mapping, removed, added = match_windows(before_all, after_all)
    old_by = {window_idx(t, i): t for i, t in enumerate(before_all)}
    new_by = {window_idx(t, i): t for i, t in enumerate(after_all)}
    rel_changed = derived_rel(old) != derived_rel(new)
    for window in added:
        put("boundary", window, f"triggers[{window}]", None, new_by[window])
    for window in removed:
        # a boundary edit of the sample, with no window of its own: a window review of what
        # remains looks again (the table of coordinator.md §3)
        put("boundary", None, f"triggers[{window}] (removed)", old_by[window], None)
    for was, window in mapping.items():
        a, b = old_by[was], new_by[window]
        if was != window:
            put("boundary", window, f"triggers[{window}].idx", was, window)
        bounds = {}
        for field in sorted((set(a) | set(b)) - {"idx"}):
            before, after = a.get(field, MISSING), b.get(field, MISSING)
            if field == "depends_on" and isinstance(before, list):
                # the same windows under their new numbers are the same dependence
                before = [mapping.get(d, f"removed window {d}") for d in before]
            if before == after:
                continue
            if field not in TRIGGER_FIELDS:
                raise EditError(f"triggers[{window}].{field} is not a field of a window "
                                f"(schema/sample.schema.json): the tool does not know which "
                                f"reviews a change of it owes. Remove it from the file")
            path = f"triggers[{window}].{field}"
            if field in ("t_start", "t_end"):
                bounds[field] = (before, after)
            elif field == "evidence_span":
                put("boundary" if rel_changed else "metadata", window, path, before, after, span=True)
            else:
                put(TRIGGER_FIELDS[field], window, path, before, after)
        if not bounds:
            continue
        small = all(number(x) and number(y) and abs(y - x) <= TOLERANCE for x, y in bounds.values())
        narrows = small and all(number(t.get(f)) for t in (a, b) for f in ("t_start", "t_end")) \
            and b["t_start"] >= a["t_start"] and b["t_end"] <= a["t_end"]
        seen = small and all(measured(y) for _, y in bounds.values())
        kind = "nudge" if small and not narrows and seen else "boundary"
        for field, (before, after) in bounds.items():
            put(kind, window, f"triggers[{window}].{field}", before, after)
        if narrows:
            remarks.append(f"window {window}: a cut of {TOLERANCE:g} s or less that only narrows "
                           f"a window is not usually made (coordinator.md §3); it is logged as a "
                           f"boundary edit and owes full_window{window}")
        elif small and not seen:
            values = ", ".join(str(y) for _, y in bounds.values())
            remarks.append(f"window {window}: logged as boundary, not nudge: {values} is not "
                           f"among the numbers of a full_window or semi-blind review named in "
                           f"--source, nor a t_s verified yes in the log (coordinator.md §3: a "
                           f"nudge moves a boundary to a reviewer's own frame measurement)")
    return mapping, removed


def brief(value, limit: int = 60) -> str:
    text = "none" if value is None else value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def describe(fields: dict) -> str:
    """The changed fields in one line, for a person reading the log."""
    return "; ".join(f"{path}: {brief(before)} -> {brief(after)}"
                     for path, (before, after) in fields.items())


def numbers_in(value) -> list[float]:
    """Every number a review file holds: its numeric fields and the numbers in its text and
    frame names (t000946.jpg)."""
    if number(value):
        return [float(value)]
    if isinstance(value, str):
        return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", value)]
    if isinstance(value, dict):
        return [x for item in value.values() for x in numbers_in(item)]
    if isinstance(value, list):
        return [x for item in value for x in numbers_in(item)]
    return []


def write_record(file: Path, sample_id: str, expected_sha: str | None, record: dict) -> str | None:
    """Put one record into an annotations file, the other lines and their order untouched;
    with `expected_sha` None, add it at the end. The file is read again first: a record that
    is not the version the edit was made from is left as it is. The new content goes to a
    file next to it and replaces the old one in a single step, so a failure half-way leaves
    the old file whole. Returns why nothing was written, or None."""
    lines = file.read_text(encoding="utf-8").splitlines(keepends=True) if file.exists() else []
    try:
        at = [i for i, line in enumerate(lines)
              if line.strip() and json.loads(line).get("id") == sample_id]
    except (json.JSONDecodeError, AttributeError) as exc:
        return f"{file.name} has a line that is not a record ({exc}); the file is left as it is"
    text = json.dumps(record, ensure_ascii=False) + "\n"
    if expected_sha is None:
        if at:
            return f"{sample_id} is already in {file.name}"
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(text)
    else:
        if len(at) != 1:
            return f"{file.name} holds {len(at)} records with the id {sample_id}, not one"
        if review_inputs.record_sha(json.loads(lines[at[0]])) != expected_sha:
            return f"{sample_id} in {file.name} is not the version the edit was made from"
        lines[at[0]] = text
    temporary = file.with_name(f".{file.name}.{os.getpid()}.tmp")
    file.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write("".join(lines))
        stream.flush()
        os.fsync(stream.fileno())  # on the disk before it takes the place of the old file
    os.replace(temporary, file)
    return None

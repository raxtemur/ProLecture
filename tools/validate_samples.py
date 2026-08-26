#!/usr/bin/env python3
"""Validates annotation files: JSON Schema + semantic checks.

    python tools/validate_samples.py data/annotations/*.jsonl

Exit code 1 on any error; with zero errors it prints the coverage breakdown.

How to read this file
---------------------
The project has no test framework, and the validator itself plays the part of the tests.
So that this does not turn into "the rule is there but has not checked anything for ages",
every semantic rule carries a three-line data sheet:

    # S-NN · checklist X.Y — what is checked.
    #   Breaks: what slips through unnoticed if the rule is removed.
    #   To check: <mutation of a correct sample> -> <expected substring>.

`S-NN` is a stable identifier for the rule; it can be cited in reviews and commits.
`checklist X.Y` is the item of docs/annotation_checklist.md that this rule closes; that is
also where the reason the item exists at all is written down.

The "To check" line specifies a reproducible negative test: take a correct annotation file,
apply the described mutation, run the validator and make sure the expected substring is in
the output. The template:

    import json
    S = [json.loads(l) for l in open("data/annotations/<id>.jsonl")]
    S[0]["triggers"][0]["t_ideal"] = S[0]["triggers"][0]["t_end"]   # the mutation
    open("/tmp/neg.jsonl", "w").write("\n".join(json.dumps(x, ensure_ascii=False) for x in S))
    # python tools/validate_samples.py /tmp/neg.jsonl  ->  "t_ideal outside the window"

Shape checks (required fields, types, enums, additionalProperties) are not included here:
the JSON schema does those, and they have no data sheet of their own.
"""

import argparse
import functools
import json
import re
import sys
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "sample.schema.json").read_text(encoding="utf-8"))


def evidence_span(t: dict) -> tuple[float, float]:
    # where in the video the LAST piece of evidence needed for the answer lies.
    # The field is required: the answer window must not be substituted for it — the
    # temporal_rel axis would then be derived from the window, that is, from exactly what
    # it is forbidden to derive it from, and a post question would become
    # indistinguishable from an at one.
    span = t["evidence_span"]
    return (span[0], span[1])


def derive_temporal_rel(s: dict) -> str:
    # axis B is determined by the position of question_time relative to the EVIDENCE
    # rather than relative to the answer window: for a post question the answer window
    # also begins at the moment the question is issued, so the window cannot tell it
    # apart from at.
    qt = s["question_time"]
    req = [t for t in s["triggers"] if t["required"]]
    spans = [evidence_span(t) for t in req]
    # At the edges we take the minimum and the maximum rather than req[0] and req[-1]:
    # triggers are ordered by t_start (S-09), but their evidence is not obliged to run
    # monotonically — the visual evidence of the second trigger may appear before the
    # spoken evidence of the first. With positional edges, a sample whose question_time
    # lay between them came out as "pre" instead of "at".
    first_a = min(a for a, _ in spans)
    last_b = max(b for _, b in spans)
    if qt < first_a:
        return "pre"
    if qt >= last_b:
        return "post"
    return "at"


# The floor on the width of an answer window. Five seconds is not a measured quantity but
# the first deliberate constraint: the exact value will be derived from measuring the
# end-to-end latency of one model; for now the bound exists so that narrow windows do not
# appear silently.
MIN_WINDOW = 5.0

BUNDLES = ROOT / "data" / "bundles"


# The videos with no bundle on disk. Without a bundle three rules silently degenerate into
# no-ops at once — S-01 (the duration cross-check), S-21 and S-33 (both of which look into
# the transcript) — and a typo in a youtube_id switches off exactly the check that would
# have caught a wrong duration, while duration is the bound for every "outside the video"
# rule. We collect such ids and say so out loud at the end of the run.
NO_BUNDLE: set[str] = set()

BUNDLE_DEPENDENT = "S-01, S-21, S-33"


@functools.lru_cache(maxsize=None)
def bundle(video_id: str) -> dict | None:
    f = BUNDLES / video_id / "bundle.json"
    if not f.exists():
        NO_BUNDLE.add(video_id)
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def bundle_duration(video_id: str) -> float | None:
    b = bundle(video_id)
    return float(b["duration"]) if b else None


def check_evidence(s: dict, dur: float) -> list[str]:
    """The references to the source of the ground truth: do they point at moments that exist.

    The check became possible once provenance.evidence moved to a structured format: in
    free prose a regular expression could only see records of the form "frame t=<number>".
    """
    errs = []
    b = bundle(s["video"]["youtube_id"])
    cues = b["transcript"] if b else []
    starts = [c["start"] for c in cues]
    ends = [c["end"] for c in cues]

    for i, e in enumerate(s["provenance"]["evidence"]):
        tag = f"provenance.evidence[{i}]"
        if e["type"] == "frame":
            # S-19 · checklist 8.1 — the frame exists.
            #   Breaks: a reference to a non-existent moment looks checkable, but nothing
            #   can actually be re-checked through it.
            #   To check: evidence[0]["t"] := 99999 -> "outside the video".
            if e["t"] > dur:
                errs.append(f"{tag}: frame t={e['t']} is outside the video")
        elif e["type"] == "speech":
            # S-20 · checklist 8.1 — the speech interval is meaningful and lies inside the video.
            #   To check: t_end := t_start -> "empty or inverted";
            #   t_end := duration + 10 -> "runs past the duration".
            if not (e["t_start"] < e["t_end"]):
                errs.append(f"{tag}: the speech interval is empty or inverted")
                continue
            if e["t_end"] > dur:
                errs.append(f"{tag}: the speech interval runs past the duration")
            if not cues:
                continue
            # S-21 · checklist 8.1 — the interval coincides with line boundaries.
            #   Both boundaries must lie exactly on subtitle boundaries: the start on the
            #   start of some line, the end on the end of some line.
            #   Breaks: a reference that breaks off in mid-sentence cannot be checked by
            #   eye — opening the transcript at that place, the reader sees a fragment
            #   rather than what was being referred to.
            #   The rule is deliberately asymmetric in the cost of an error: catching an
            #   extra neighbouring sentence is harmless (the reference stays readable and
            #   checkable), while cutting off a needed one is not. So the interval should
            #   be aligned outwards, to the end of the last line it touches.
            #   The tolerance of ±0.5 s is for rounding of timecodes on writing, not for
            #   meaning.
            #   To check: t_start := the middle of a line -> "does not coincide with the
            #   start of any line"; t_end := the middle of a line -> "does not coincide
            #   with the end of any line".
            if not any(abs(e["t_start"] - x) <= 0.5 for x in starts):
                errs.append(f"{tag}: the start {e['t_start']} does not coincide with the start "
                            f"of any transcript line")
            if not any(abs(e["t_end"] - x) <= 0.5 for x in ends):
                errs.append(f"{tag}: the end {e['t_end']} does not coincide with the end "
                            f"of any transcript line")
    return errs


# Warnings are not errors: they do not fail the run and do not stand in the way of
# promoting a sample to validated. They are needed where a violation is plausible but
# legitimate exceptions exist, and turning it into a blocker would force the annotator to
# bend the numbers to fit the rule.
WARNINGS: list[tuple[str, str]] = []


def warn(sid: str, msg: str) -> None:
    WARNINGS.append((sid, msg))


def semantic_checks(s: dict) -> list[str]:
    """The rules that cannot be expressed by the schema: they tie fields to each other, to
    the duration of the video and to the transcript. For each rule's data sheet see the
    module docstring."""
    errs = []
    dur = s["video"]["duration"]

    # S-01 · checklist 1.6 — the duration in the sample matches the actual one.
    #   Breaks: a copied sample carrying somebody else's duration makes every "outside the
    #   video" check meaningless — they compare against the wrong bound.
    #   To check: video.duration := 100.0 -> "diverges from bundle.json".
    bd = bundle_duration(s["video"]["youtube_id"])
    if bd is not None and abs(bd - dur) > 1.0:
        errs.append(f"video.duration={dur} diverges from bundle.json ({bd}) by more than a second")
    if bd is None and s["validation"]["status"] == "validated":
        errs.append(f"there is no data/bundles/{s['video']['youtube_id']}/bundle.json, so the rules "
                    f"{BUNDLE_DEPENDENT} were not run on this sample — "
                    f"status validated is not granted while rules are unchecked")
    trigs = s["triggers"]

    # S-02 · checklist 1.3 — there is at least one required trigger.
    #   Breaks: a sample that cannot be answered correctly at any moment; on top of that
    #   derive_temporal_rel fails on an empty list.
    #   To check: required := false on every trigger -> "not a single required".
    if not any(x["required"] for x in trigs):
        errs.append("not a single required trigger")
        return errs

    # S-03 · checklist 1.3 — the question is issued inside the video.
    #   Breaks: a sample that will never be asked in streaming.
    #   To check: question_time := duration + 10 -> "greater than the duration of the video".
    if s["question_time"] > dur:
        errs.append(f"question_time={s['question_time']} is greater than the duration of the video {dur}")

    # S-04 · checklist 1.5 — a multi-trigger sample has something to punish spam with.
    #   Breaks: the strategy "talk all the time" scores full marks, because there is
    #   nowhere for a false positive to happen.
    #   To check: delete distractor_windows on a sample with >1 trigger
    #   -> "multi-trigger sample with no distractor_windows".
    if len(trigs) > 1 and not s.get("distractor_windows"):
        errs.append("multi-trigger sample with no distractor_windows: a spam strategy goes unpunished "
                    "(plan §3.1 item 3)")

    # S-05 · checklist 7.1 — the pre/at/post axis is derived rather than set by hand.
    #   Breaks: the label stops reflecting the position of question_time relative to the
    #   evidence; most often a post sample lives with the label at, and vice versa.
    #   To check: on a post sample set evidence_span := [t_start, t_end]
    #   -> "should be at".
    want = derive_temporal_rel(s)
    if s["temporal_rel"] != want:
        errs.append(f"temporal_rel={s['temporal_rel']}, but from question_time="
                    f"{s['question_time']} and evidence_span it should be {want}")

    for t in trigs:
        a, b = evidence_span(t)
        # S-06 · checklist 1.9 — evidence_span is non-empty and lies inside the video.
        #   Breaks: the axis is derived from a meaningless interval, and silently at that.
        #   To check: evidence_span := [500, 100] -> "empty or inverted";
        #   evidence_span := [0, duration + 10] -> "runs past the duration".
        if not (a < b):
            errs.append(f"trigger[{t['idx']}]: evidence_span is empty or inverted")
        if b > dur:
            errs.append(f"trigger[{t['idx']}]: evidence_span runs past the duration")
        # S-07 · checklist 1.1 — the evidence appears before the answer window closes.
        #   Breaks: the ground truth is unreachable — the model is required to answer
        #   before the thing the answer follows from has appeared in the video.
        #   To check: evidence_span := [t_end + 1, t_end + 5] -> "ground truth unreachable".
        if a >= t["t_end"]:
            errs.append(f"trigger[{t['idx']}]: the evidence appears after the answer window "
                        f"closes — ground truth unreachable")
        # S-35 · checklist 1.1 — the last piece of evidence appears before the window closes.
        #   S-07 guarded only the left edge; nobody guarded the right one: a sample with
        #   evidence_span [314, 1500] and a window [315, 382] passed in silence.
        #   Breaks: by the definition of the field (1.9) what lies there is the LAST piece
        #   of evidence needed for the answer; if it appears after t_end, the reference
        #   answer is unreachable inside the window — a model reasoning correctly is
        #   punished by construction. On top of that derive_temporal_rel reads exactly the
        #   right edge, so the axis gets derived from a moment at which it is already too
        #   late to answer.
        #   To check: evidence_span := [t_start, t_end + 100] -> "the last piece of
        #   evidence appears after the window closes".
        if b > t["t_end"]:
            errs.append(f"trigger[{t['idx']}]: the last piece of evidence appears at {b}, "
                        f"while the window closes at {t['t_end']} — the reference answer is unreachable inside it")

        # S-29 · checklist 1.1 — the window does not open before the evidence.
        #   Breaks: between t_start and the appearance of the evidence lies a zone where
        #   an answer counts while there is nothing yet to answer from — that is, guessing
        #   counts. A model's latency is measured from t_start, so the left boundary is
        #   the origin: it must coincide with the moment at which a model reasoning
        #   instantaneously could already have answered.
        #   It used to be compared against t_ideal, but t_ideal is now set mechanically
        #   (t_start + 1) and checks nothing.
        #   To check: evidence_span := [t_start + 5, t_end - 1]
        #   -> "the window opens before the evidence".
        if t["t_start"] < a:
            errs.append(f"trigger[{t['idx']}]: the window opens at {t['t_start']}, "
                        f"while the evidence appears at {a} — in the gap what counts is "
                        f"guessing")

    # S-36 · checklist 1.11 — the window is no shorter than five seconds.
    #   Breaks: a model in streaming spends seconds on its answer, and on too narrow a
    #   window PAUC measures generation speed rather than understanding. The width of a
    #   window is set by the content, but the content has no reason to coincide with the
    #   time it takes to answer — hence a floor below which a sample is not taken.
    #   To check: t_end := t_start + 3 -> "window 3.0 s wide".
    for t in trigs:
        width = t["t_end"] - t["t_start"]
        if width < MIN_WINDOW:
            errs.append(f"trigger[{t['idx']}]: window {width:.1f} s wide against a minimum of "
                        f"{MIN_WINDOW:.0f} s — on such a window the metric measures generation "
                        f"speed rather than understanding")

    # S-08 · checklist 1.3 — idx values run consecutively from zero.
    #   Breaks: depends_on refers to a different trigger from the one it appears to.
    #   To check: idx of the second trigger := 5 -> "must run consecutively from 0".
    if [t["idx"] for t in trigs] != list(range(len(trigs))):
        errs.append("trigger idx values must run consecutively from 0")

    # S-09 · checklist 1.3 — the order of idx matches the chronological order.
    #   Breaks: derive_temporal_rel takes the evidence of the first and last required
    #   triggers by their place in the list, and after a reordering the axis is derived
    #   from the wrong windows. The violation used to surface under somebody else's name —
    #   as "the window overlaps the previous one".
    #   To check: swap the contents of triggers 1 and 2 (leaving idx alone)
    #   -> "do not run in increasing order of t_start".
    starts = [t["t_start"] for t in trigs]
    if starts != sorted(starts):
        errs.append(f"triggers do not run in increasing order of t_start: {starts}")

    prev_end = -1.0
    for t in trigs:
        tag = f"trigger[{t['idx']}]"
        # S-10 · checklist 1.1 — the geometry of the answer window.
        #   Breaks: a window of zero length or an inverted one; a t_ideal outside the
        #   window makes the peak of the metric unreachable; a window past the duration is
        #   unreachable altogether.
        #   To check: t_end := t_start -> "t_start >= t_end";
        #   t_ideal := t_end -> "t_ideal outside the window";
        #   t_end := duration + 10 -> "the window runs past the duration of the video".
        if not (t["t_start"] < t["t_end"]):
            errs.append(f"{tag}: t_start >= t_end")
        if not (t["t_start"] <= t["t_ideal"] < t["t_end"]):
            errs.append(f"{tag}: t_ideal outside the window")
        if t["t_end"] > dur:
            errs.append(f"{tag}: the window runs past the duration of the video")
        # S-11 · checklist 1.1 — the windows of one sample do not overlap.
        #   Breaks: a single answer falls into two windows at once and is judged against
        #   two different rubrics; the metric stops being well defined.
        #   To check: t_start of the second trigger := t_start of the first
        #   -> "overlaps the previous window".
        if t["t_start"] < prev_end:
            errs.append(f"{tag}: the window overlaps the previous one")
        # S-12 · checklist 1.1 — the window does not begin before the question is issued.
        #   Breaks: the start of the window is unreachable — the model does not yet know
        #   what it was asked, while the metric already requires it to answer.
        #   To check: question_time := t_start + 5 -> "begins before the question is issued".
        if t["t_start"] < s["question_time"]:
            errs.append(f"{tag}: the answer window begins before the question is issued — its start is unreachable")
        prev_end = t["t_end"]
        # S-13 · checklist 1.4 — depends_on points strictly backwards.
        #   Breaks: a dependency chain with a cycle or a forward reference, from which the
        #   share of correctly built chains cannot be computed.
        #   To check: depends_on := [idx] on any trigger -> "not earlier than the trigger itself".
        for dep in t.get("depends_on", []):
            if dep >= t["idx"]:
                errs.append(f"{tag}: depends_on={dep} is not earlier than the trigger itself")

    for i, d in enumerate(s.get("distractor_windows", [])):
        # S-14 · checklist 1.2 — the geometry of a distractor window.
        #   Breaks: a distractor of zero length or one outside the video catches nothing
        #   while looking, in the annotation, like protection against spam.
        #   To check: t_end := t_start -> "t_start >= t_end";
        #   t_end := duration + 10 -> "the window runs past the duration of the video".
        if not (d["t_start"] < d["t_end"]):
            errs.append(f"distractor[{i}]: t_start >= t_end")
        if d["t_end"] > dur:
            errs.append(f"distractor[{i}]: the window runs past the duration of the video")
        # S-15 · checklist 1.2 — the distractor does not lie entirely before the question.
        #   Breaks: there is nothing to catch — the model does not yet know the question
        #   and stays silent under any strategy, while the annotation counts that as
        #   protection against spam.
        #   To check: question_time := the distractor's t_end + 1 -> "entirely before the question is issued".
        if d["t_end"] <= s["question_time"]:
            errs.append(f"distractor[{i}] lies entirely before the question is issued — there is "
                        f"nothing there for a false positive to be")
        # S-16 · checklist 1.2 — the distractor does not overlap a trigger.
        #   Breaks: one and the same answer is correct and false at once.
        #   To check: the distractor's t_start := t_start of the first trigger
        #   -> "overlaps trigger".
        for t in trigs:
            if d["t_start"] < t["t_end"] and t["t_start"] < d["t_end"]:
                errs.append(f"distractor[{i}] overlaps trigger[{t['idx']}]")

    st = s["validation"]["status"]
    vis = s["validation"].get("visiononly_solved")
    solv = s["validation"].get("solvable")

    # S-17 · checklist 7.2 — audio_dependency is empty until the measurement is complete.
    #   Breaks: a label that affects conclusions about modalities gets set by the
    #   annotator's opinion instead of by measurement — exactly the mistake we criticise
    #   other people's work for. The opinion lives separately, in audio_dependency_claim.
    #
    #   "The measurement is complete" means BOTH flags the label is derived from under 4.5
    #   are present, not the status of the sample. The old wording required
    #   status=validated and thereby banned the label on rejected samples forever: a
    #   sample solved blind will never pass S-18 into validated, so its dependence on
    #   audio could never be measured either. And it must be: rejected samples are the
    #   material for the null baselines and for the contamination count — they leave the
    #   task set but not the measurements.
    #   To check: audio_dependency := "required" with the probes empty
    #   -> "the probes have not answered yet".
    if s["audio_dependency"] is not None and (vis is None or solv is None):
        errs.append(f"audio_dependency is filled in while the probes it is derived from "
                    f"have not answered (visiononly_solved={vis}, solvable={solv}): "
                    f"the label is set only by measurement")

    # S-18 · checklist 7.2 — the conditions for promotion to validated.
    #   Breaks: a sample is declared checked without the probe answers its whole value
    #   rests on; a sample solvable without the video gets into the set and measures
    #   knowledge of the subject instead of streaming; a sample that is not solvable at
    #   all punishes every model equally.
    #   To check: status := "validated" with draft fields -> "the probes have not answered"
    #   and "with audio_dependency unmeasured"; then blind_solved := true
    #   -> "incompatible with validated"; solvable := false -> "the question is not solvable".
    if st == "validated":
        if s["audio_dependency"] is None:
            errs.append("status=validated with audio_dependency unmeasured")
        missing = [k for k in ("solvable", "blind_solved", "textonly_solved",
                               "visiononly_solved", "frozenframe_solved")
                   if s["validation"].get(k) is None]
        if missing:
            errs.append(f"status=validated, but the probes have not answered: {', '.join(missing)}")
        if s["validation"].get("blind_solved"):
            errs.append("blind_solved=true is incompatible with validated: the sample is solvable without the video "
                        "-> status must be rejected")
        if s["validation"].get("solvable") is False:
            errs.append("solvable=false is incompatible with validated: the question is not solvable "
                        "even from the full material -> status must be rejected")

    # S-25 · checklist 7.6 — audio_dependency matches what the probes imply.
    #   The label is not set by opinion: it is computed from the vision probe's answer.
    #   Solved from frames alone -> the audio is unnecessary; not solved, but the question
    #   is solvable overall -> the audio is required. In every other combination (the
    #   probes have not answered yet) the label must be null, and that is caught by S-17
    #   together with 7.2.
    #   Breaks: the label diverging from the flags it was derived from — that is, exactly
    #   the substitution of opinion for measurement that the field was split into
    #   audio_dependency and audio_dependency_claim to forbid.
    #   To check: visiononly_solved := true, audio_dependency := "required"
    #   -> "implies unnecessary".
    if vis is True:
        derived = "unnecessary"
    elif vis is False and solv is True:
        derived = "required"
    else:
        derived = None
    # We require agreement in two cases: the label is already written down (then it must
    # match the derived one under any status — otherwise rejected becomes a loophole for a
    # label set by opinion) and the status is validated (there the label must be present).
    # The intermediate state "both flags written, the label not yet derived" stays
    # legitimate for draft and rejected — otherwise a sample would jam between S-17 and S-25.
    label = s["audio_dependency"]
    if (label is not None or st == "validated") and label != derived:
        errs.append(f"audio_dependency={label!r}, but from the probes "
                    f"(visiononly_solved={vis}, solvable={solv}) it implies {derived!r}")

    # S-27 · checklist 7.7 — solvable is consistent with the single-modality probes.
    #   The flag is set by the coordinator: success of any single-modality probe already
    #   proves solvability, and the 4.7 probe is then not launched at all. Without this
    #   rule solvable stayed empty in the commonest case, and S-18 would not let the
    #   sample into validated — that is, the check blocked itself.
    #   Breaks: a sample solved by the text probe is declared unsolvable and goes to
    #   CRITICAL_FAIL; or, the other way round, solvable=true appears where no probe
    #   answered.
    #   To check: textonly_solved := true, solvable := false
    #   -> "solvable=false, but probe";
    #   frozenframe_solved := true, visiononly_solved := false
    #   -> "solved from a single frame".
    v = s["validation"]
    solved_by = [k for k in ("blind_solved", "textonly_solved", "visiononly_solved",
                             "frozenframe_solved") if v.get(k) is True]
    if solved_by and v.get("solvable") is False:
        errs.append(f"solvable=false, but probe {solved_by[0]} answered: success of any probe "
                    f"already proves solvability")
    # A single frame is a subset of the frames, so frozen-frame is stronger than vision.
    if v.get("frozenframe_solved") is True and v.get("visiononly_solved") is False:
        errs.append("frozenframe_solved=true with visiononly_solved=false: solved "
                    "from a single frame but not from all the frames — the probes contradict each other")

    # S-28 · checklist 1.10 — a trigger does not rest on sound alone.
    #   Breaks: the only modality of the trigger is sound, and there is no sound probe:
    #   probe_text reads the text of the speech, probe_vision looks at frames. The
    #   visiononly_solved flag of such a trigger measures nothing, and audio_dependency is
    #   derived from it — so the label comes out of a measurement that never happened.
    #   To check: trigger_modality := ["sound"] -> "no probe that will check this".
    for t in trigs:
        if t["trigger_modality"] == ["sound"]:
            errs.append(f"trigger[{t['idx']}]: sound is the only modality — "
                        f"there is no probe that will check this; add speech or visual")

    # S-30 · checklist 7.4 — a required trigger does not depend on an optional one.
    #   Breaks: a model that legitimately stayed silent in an optional window (where the
    #   rubric explicitly permits silence) automatically breaks the chain in the
    #   denominator of the chain metric — that is, it is punished for behaviour the
    #   annotation declared correct.
    #   To check: on a required trigger, depends_on pointing at a required: false one
    #   -> "depends on an optional one".
    opt = {t["idx"] for t in trigs if not t["required"]}
    for t in trigs:
        if not t["required"]:
            continue
        bad = sorted(opt & set(t.get("depends_on") or []))
        if bad:
            errs.append(f"trigger[{t['idx']}]: a required trigger depends on the "
                        f"optional {bad} — staying silent there is legitimate, and the chain breaks")

    # S-31 · checklist 1.2 — distractors do not overlap each other.
    #   Breaks: one premature answer counts as two false positives — the punishment is
    #   disproportionate to the act.
    #   To check: add a distractor covering two neighbouring ones
    #   -> "distractors overlap".
    ds = sorted(s.get("distractor_windows", []), key=lambda d: d["t_start"])
    for i in range(1, len(ds)):
        if ds[i]["t_start"] < ds[i - 1]["t_end"]:
            errs.append(f"distractors overlap: [{ds[i-1]['t_start']}, {ds[i-1]['t_end']}] "
                        f"and [{ds[i]['t_start']}, {ds[i]['t_end']}]")

    # S-32 · checklist 8.1 — at least one of the references carries a timecode.
    #   Breaks: provenance is declared to be protection against an invented reference
    #   answer, but a record of type other is checked by nothing — replace every reference
    #   with one and you can write "I decided so" and pass validation.
    #   To check: evidence := [{"type": "other", "explanation": "I decided so"}]
    #   -> "not a single reference with a timecode".
    ev = s["provenance"]["evidence"]
    if not any(e["type"] in ("frame", "speech") for e in ev):
        errs.append("not a single reference with a timecode: a provenance of nothing but other "
                    "gives no way to re-check the reference answer")

    # S-37 · checklist 2.5 — a distractor does not begin exactly on a window boundary.
    #   Breaks: an answer that is correct on the merits but issued a second after the
    #   window closes falls into a distractor and is penalised twice — as a miss and as a
    #   false positive. The difference between "in time" and "a trap" becomes a difference
    #   in generation speed.
    #   A zero gap is an error; a non-zero but short one is a warning: sometimes a
    #   distractor is supposed to begin close by, and then it is the reviewer who decides.
    #   To check: a distractor with t_start := the trigger's t_end -> "begins exactly on
    #   the window boundary".
    for i, d in enumerate(s.get("distractor_windows", [])):
        for tr in trigs:
            if d["t_start"] == tr["t_end"]:
                errs.append(f"distractor[{i}] begins exactly on the boundary of the window of "
                            f"trigger[{tr['idx']}] ({tr['t_end']}): an answer that is correct but late "
                            f"by a fraction of a second will fall into it and be punished twice")

    for i, d in enumerate(s.get("distractor_windows", [])):
        for tr in trigs:
            gap = d["t_start"] - tr["t_end"]
            if 0 < gap < 10:
                warn(s["id"], f"distractor[{i}] begins {gap:.1f} s after the window of "
                              f"trigger[{tr['idx']}]: a correct but late answer will fall "
                              f"into it — that is a race on generation speed (checklist 2.5)")

    # S-33 · checklist 2.1 — a boundary shared by two windows does not cut a line in half.
    #   Breaks: an answer started on that phrase falls into the neighbouring window and is
    #   judged against the neighbouring rubric — the model is punished for speaking where
    #   the annotation itself drew a boundary in mid-thought.
    #   To check: move the shared boundary of two neighbouring windows inside a line
    #   -> "shared window boundary ... cuts the line".
    b = bundle(s["video"]["youtube_id"])
    if b:
        ends = {tr["t_end"] for tr in trigs}
        for tr in trigs:
            if tr["t_start"] not in ends:
                continue
            for c in b["transcript"]:
                if c["start"] < tr["t_start"] < c["end"]:
                    errs.append(f"the shared window boundary {tr['t_start']} cuts the line "
                                f"[{c['start']:.1f}, {c['end']:.1f}]: an answer on that phrase "
                                f"will fall into the neighbouring window and the neighbouring rubric")
                    break

    errs += check_evidence(s, dur)

    # Required triggers only: a single optional visual trigger used to add "visual" to the
    # overall set and silently drop the complaint against a wholly spoken sample.
    req_trigs = [t for t in trigs if t["required"]] or trigs
    mods = {m for t in req_trigs for m in t["trigger_modality"]}
    claim = s.get("audio_dependency_claim")
    # S-22 · checklist 1.7 — the declared dependence on audio does not contradict the modalities.
    #   Breaks: a sample declares "the audio is unnecessary" while every one of its
    #   triggers is detectable only from the speech — and vice versa. This is not a
    #   measurement but a check of internal consistency.
    #   To check: audio_dependency_claim := "unnecessary" on a sample where every
    #   trigger_modality == ["speech"] -> "every trigger is speech-only";
    #   claim := "required" on a purely visual one -> "no speech/sound".
    if claim == "unnecessary" and mods == {"speech"}:
        errs.append("claim=unnecessary, but every trigger is speech-only")
    if claim == "required" and "speech" not in mods and "sound" not in mods:
        errs.append("claim=required, but there is no speech/sound among the modalities")
    if claim == "helpful" and "speech" not in mods and "sound" not in mods:
        errs.append("claim=helpful, but there is no speech/sound among the required modalities: "
                    "what exactly the audio helps with does not follow from the annotation")

    return errs


def twin_groups(samples: dict[str, dict]) -> list[list[str]]:
    """Splits samples into twin groups by the undirected twin_of references.

    The reference need not be mutual: it is enough for one of the pair to set it. A group
    may be larger than two — the same question issued at three different points is a
    legitimate set of triplets.
    """
    parent = {sid: sid for sid in samples}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for sid, s in samples.items():
        other = s.get("twin_of")
        if other in parent:
            parent[find(sid)] = find(other)

    groups: dict[str, list[str]] = {}
    for sid in samples:
        groups.setdefault(find(sid), []).append(sid)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def cross_sample_checks(samples: dict[str, dict]) -> dict[str, list[str]]:
    """The checks for which one sample is not enough: the link between control twins.

    Returns a mapping "sample id -> list of complaints". A complaint is attributed to the
    sample in which it can be fixed: a broken reference to the source of the reference, a
    divergence inside a group to every member of it except the first by `id` (which is
    taken as the anchor).
    """
    errs: dict[str, list[str]] = {}

    def add(sid: str, msg: str) -> None:
        errs.setdefault(sid, []).append(msg)

    # S-23 · checklist 5.1 — the twin_of reference leads to a sample that exists.
    #   Breaks: the twin is lost to a typo in an id, the group falls apart, and the
    #   comparison of rubrics (S-24) silently runs for nobody.
    #   To check: twin_of := "no-such-id" -> "twin_of refers to an unknown id".
    for sid, s in samples.items():
        other = s.get("twin_of")
        if other is None:
            continue
        if other == sid:
            add(sid, "twin_of refers to the sample itself")
        elif other not in samples:
            add(sid, f"twin_of refers to an unknown id {other!r} "
                     f"(twins must be checked in a single run)")
        elif samples[other].get("twin_of") not in (None, sid):
            add(sid, f"twin_of={other!r}, but that one points at "
                     f"{samples[other]['twin_of']!r}: the references are inconsistent")

    # S-24 · checklist 5.1 — twins agree on everything except the moment the question is issued.
    #   Breaks: the difference in metrics between a pair is meant to be the price of
    #   timing alone. If the twins' rubrics, act or reasoning level have diverged, that
    #   same difference also measures a change in what is required of the answer — and the
    #   result cannot be interpreted.
    #   ONLY the rubrics of required triggers are compared: an optional window on one of
    #   the twins (for example, before the object appears on screen) is legitimately
    #   absent on the other.
    #   To check: add an item to the rubric of a required trigger on one of the pair
    #     -> "the rubric of the required triggers diverges from the twin";
    #   change reasoning_level on one of the pair -> "reasoning_level diverges";
    #   remove "visual" from trigger_modality on one of the pair
    #     -> "trigger_modality of the required triggers diverges".
    for group in twin_groups(samples):
        base = group[0]

        def key(sid: str) -> list[str]:
            return [r.strip()
                    for t in samples[sid]["triggers"] if t.get("required")
                    for r in t["rubric"]]

        for sid in group[1:]:
            if key(sid) != key(base):
                add(sid, f"the rubric of the required triggers diverges from twin {base}")
            mods = lambda x: [tr["trigger_modality"]
                              for tr in samples[x]["triggers"] if tr.get("required")]
            if mods(sid) != mods(base):
                add(sid, f"trigger_modality of the required triggers diverges from twin "
                         f"{base}: {mods(sid)} against {mods(base)}. The pair shares one and "
                         f"the same evidence — it cannot be visual for one of them and absent "
                         f"for the other")
            for field in ("act", "reasoning_level"):
                if samples[sid].get(field) != samples[base].get(field):
                    add(sid, f"{field} diverges from twin {base}: "
                             f"{samples[sid].get(field)!r} against {samples[base].get(field)!r}")
            if samples[sid]["video"]["youtube_id"] != samples[base]["video"]["youtube_id"]:
                add(sid, f"twin {base} is annotated against a different video")
            if samples[sid]["question_time"] == samples[base]["question_time"]:
                add(sid, f"question_time coincides with twin {base}: "
                         f"the pair does not measure the price of timing")

    # S-26 · checklist 6.3 — the twins have not lost a distractor they could both have had.
    #   A pair of twins exists for the sake of comparing metrics, including the share of
    #   hits on a trap. If a distractor is present for one and absent for the other with
    #   no reason, that share is not comparable.
    #   Absence is legitimate in exactly one case: the distractor lies entirely before the
    #   question_time of the second twin, and there S-15 (checklist 1.2) forbids it. That
    #   is exactly how both pairs of the pilot look, which is why the rule is phrased as
    #   "one legitimate for both must be present for both" rather than "the sets coincide".
    #   Breaks: a distractor was deleted from, or added to, only one of the pair, and the
    #   false-positive column for the pair silently loses its meaning.
    #   To check: on q07 (question_time=930) add a distractor [1000, 1010]
    #   -> "distractor ... is present for ..., but not for the twin".
    for group in twin_groups(samples):
        for sid in group:
            mine = samples[sid].get("distractor_windows", [])
            for other in group:
                if other == sid:
                    continue
                qt = samples[other]["question_time"]
                theirs = samples[other].get("distractor_windows", [])
                for d in mine:
                    if d["t_end"] <= qt:
                        continue          # for the twin it is forbidden under 1.2 — legitimate
                    if not any(abs(x["t_start"] - d["t_start"]) <= 1.0
                               and abs(x["t_end"] - d["t_end"]) <= 1.0 for x in theirs):
                        add(sid, f"distractor [{d['t_start']}, {d['t_end']}] is present for {sid}, "
                                 f"but not for twin {other}, where it would be legitimate")

    return errs


def rules_table() -> str:
    """A table of contents for the rules: S-NN, the checklist item, what breaks without it.

    The data sheets live in comments next to the rules themselves — that way they do not
    diverge from the code. But finding them there by eye is impossible, and in a
    conversation about annotation the number `S-25` comes up before anyone remembers what
    it checks. So the table of contents is assembled from those same comments rather than
    written separately: a separate one would diverge from the code on the very first edit.
    """
    src = Path(__file__).read_text(encoding="utf-8").splitlines()
    head = re.compile(r"^\s*# (S-\d+) \u00b7 checklist ([\d.]+) \u2014 (.+)$")
    rows, cur = [], None
    for line in src:
        m = head.match(line)
        if m:
            cur = {"id": m.group(1), "item": m.group(2), "what": m.group(3).rstrip(".")}
            rows.append(cur)
        elif cur is not None:
            b = re.match(r"^\s*#\s+Breaks: (.+)$", line)
            if b:
                cur["breaks"] = b.group(1)
            elif not re.match(r"^\s*#", line):
                cur = None
    out = [f"{len(rows)} validator rules\n"]
    for r in sorted(rows, key=lambda r: int(r["id"].split("-")[1])):
        out.append(f"{r['id']:6s} checklist {r['item']:5s} {r['what']}")
        if r.get("breaks"):
            out.append(f"{'':6s} breaks: {r['breaks']}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*",
                    help="annotation files; not needed with --rules")
    ap.add_argument("--rules", action="store_true",
                    help="print the table of contents of the rules: S-NN, checklist item, what breaks")
    args = ap.parse_args()

    total = 0
    bad_ids: set[str] = set()
    samples: dict[str, dict] = {}
    seen_ids: dict[str, str] = {}
    stats = {k: Counter() for k in ("act", "temporal_rel", "reasoning_level",
                                    "template", "audio_dependency_claim")}
    ntrig = Counter()

    if args.rules:
        print(rules_table())
        return

    for fp in args.files:
        if not Path(fp).exists():
            sys.exit(f"no such file {fp}")
        for lineno, line in enumerate(Path(fp).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            try:
                s = json.loads(line)
            except json.JSONDecodeError as e:
                bad_ids.add(f"{fp}:{lineno}")
                print(f"\n!! {fp}:{lineno}  the line does not parse as JSON: {e}")
                continue
            errs = []
            sid = s.get("id")
            if sid in seen_ids:
                errs.append(f"id already seen in {seen_ids[sid]}")
            elif sid:
                seen_ids[sid] = f"{fp}:{lineno}"
                samples[sid] = s
            # S-34 · checklist 1.8 — the file conforms to the JSON schema.
            #   Breaks: everything else. A schema with additionalProperties: false at
            #   every level catches a typo in a field name that would otherwise pass in
            #   silence and leave the field unfilled.
            #   To check: add a field "note": "x" to a sample -> "schema:".
            try:
                jsonschema.validate(s, SCHEMA)
            except jsonschema.ValidationError as e:
                errs.append(f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}")
            try:
                errs += semantic_checks(s)
            except (KeyError, IndexError, TypeError) as e:
                errs.append(f"semantic: could not be checked ({type(e).__name__}: {e})")
            if errs:
                bad_ids.add(sid or f"{fp}:{lineno}")
                print(f"\n!! {fp}:{lineno}  {s.get('id')}")
                for e in errs:
                    print(f"   - {e}")
            for k, c in stats.items():
                c[s.get(k)] += 1
            ntrig[len(s.get("triggers", []))] += 1

    try:
        cross = cross_sample_checks(samples)
    except (KeyError, IndexError, TypeError) as e:
        # A sample that failed the schema reaches this point as it is: a failure inside the
        # cross-sample checks used to take the whole report down along with the summary.
        cross = {}
        bad_ids.add("cross-sample")
        print(f"\n!! the cross-sample checks were not run ({type(e).__name__}: {e}) — "
              f"fix the errors above and run again")
    for sid, errs in sorted(cross.items()):
        bad_ids.add(sid)
        print(f"\n!! {seen_ids[sid]}  {sid}")
        for e in errs:
            print(f"   - {e}")

    for sid, msg in WARNINGS:
        print(f"\n?? {sid}\n   - {msg}")

    if NO_BUNDLE:
        print(f"\n?? the rules {BUNDLE_DEPENDENT} were skipped: no bundle for "
              f"{', '.join(sorted(NO_BUNDLE))}")

    bad = len(bad_ids)
    if not total:
        sys.exit("not a single sample was passed in: an empty run is not a green run")
    print(f"\nchecked {total}, with errors {bad}, warnings {len(WARNINGS)}")
    if not bad:
        print("\ncoverage:")
        for k, c in stats.items():
            print(f"  {k:24} {dict(c)}")
        print(f"  {'triggers per sample':24} {dict(sorted(ntrig.items()))}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

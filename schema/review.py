#!/usr/bin/env python3
"""The review contract: what a subagent must return about a sample it checked.

Why pydantic rather than a JSON schema. The sample schema (`sample.schema.json`) is read
only by the validator and by humans; the review schema is read by a model too — it fills
the schema in through constrained decoding. A class with fields and comments beside them
is documentation, validator and prompt at once: `model_json_schema()` returns what one
would otherwise write by hand, and `Field(description=...)` reaches the model verbatim.

Two principles the form grew out of.

**Identity by name, not by number.** Checklist items get renumbered: in a single session
group 4 moved wholesale (the former 4.7 became 4.3, the former 4.3 became 4.6). A review
saved under the key `"4.6"` reads, after such a reshuffle, as a review of a different item
— silently and irreversibly. So `Group` and `Item` live in the contract as stable names,
while the numbers stay in the text of the checklist and in the reference table
`ITEM_NUMBER` at the bottom of this file. That table is not authoritative: if it diverges,
it is the table that gets fixed, not the saved reviews.

**Schema-Guided Reasoning.** A model asked for the verdict up front produces a verdict —
together with a justification invented after the fact. So the fields of every check run in
a cascade (SGR Cascade): first what was looked at, then what was seen, then the
intermediate answers, boolean and numeric, and then and only then `result`. The field
order here is not cosmetic: under constrained decoding the model physically generates the
fields in this order, and `result` is written only after the grounds have been fixed. The
side benefit matters more than the direct one: a disagreement between two reviewers
becomes localisable — one can see at which intermediate step they diverged, and not merely
that the verdicts differ.

    https://abdullin.com/schema-guided-reasoning/

The subagent **saves the filled-in model to the file** `data/reviews/<VIDEO_ID>/<SAMPLE_ID>/
<role>.<iteration>.json` and returns its reasoning as text to the coordinator. That way
the coordinator does not drag every subagent's full json into context but can always
re-read it — and so can the human at acceptance.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The version of the contract itself: it changes when the fields here change.
SCHEMA_VERSION = "1.3"   # 1.1: the full role was split into full_sample and full_window
# 1.2: the verdict on 4.2 moved to the coordinator; for the
#      semi-blind reviewer it stayed preliminary (see COORDINATOR_ITEMS)
# 1.3: distractor_windows removed from the sample, and with them the four items of
#      group 6, 1.2 and 1.5 (kept below as retired names so that old reviews still
#      read); the semi-blind scan became a trajectory of full answers (`Candidate`);
#      the full reviewer may propose `t_s`; a new role `probe_verify` checks it
CHECKLIST_VERSION = "2026-09-07"
# The previous checklist version. Reviews saved under it may still carry the retired
# items and the old shape of `candidates`; anything newer may not.
PREVIOUS_CHECKLIST_VERSION = "2026-08-24"


class Strict(BaseModel):
    """The common base: extra fields are forbidden.

    The same discipline as `additionalProperties: false` in the sample schema. A model that
    added a field of its own is usually masking something that did not fit the contract —
    and that is exactly the signal one must not lose.
    """

    model_config = ConfigDict(extra="forbid")


# The version of the checklist the subagent checked against. Needed so that in six
# months one can tell which revision of an item it applied.


class Group(StrEnum):
    """The checklist groups. The name of a group is part of an item's address."""

    FORMAL = "formal"            # 1. Formal integrity of the file
    WINDOWS = "windows"          # 2. Answer window boundaries
    TRIGGERS = "triggers"        # 3. The trigger set against the criterion of the question
    SHORTCUTS = "shortcuts"      # 4. Solvability that bypasses the video
    RUBRIC = "rubric"            # 5. Consistency of question, answer and rubric
    DISTRACTORS = "distractors"  # 6. Distractors — retired 2026-09-07, kept for old reviews
    LABELS = "labels"            # 7. Labels
    PROVENANCE = "provenance"    # 8. Provenance
    DRIFT = "drift"              # 9. Drift of documentation and tools


class Item(StrEnum):
    """The checklist items under stable names.

    The name describes **what is checked**, not the order. New items may be added anywhere
    — that does not affect saved reviews. They must not be deleted: the name of a deleted
    item stays here with a note, otherwise old reviews stop being readable.
    """

    # --- 1. formal (all automatic, a reviewer does not fill them in) -------
    WINDOW_GEOMETRY = "window-geometry"
    DISTRACTOR_GEOMETRY = "distractor-geometry"              # retired 2026-09-07, see RETIRED_ITEMS
    SAMPLE_INTEGRITY = "sample-integrity"
    DEPENDS_ON_BACKWARDS = "depends-on-backwards"
    MULTITRIGGER_HAS_DISTRACTOR = "multitrigger-has-distractor"  # retired 2026-09-07
    DURATION_MATCHES_BUNDLE = "duration-matches-bundle"
    CLAIM_MATCHES_MODALITIES = "claim-matches-modalities"
    JSON_SCHEMA = "json-schema"
    EVIDENCE_SPAN_PRESENT = "evidence-span-present"
    SOUND_ONLY_TRIGGER = "sound-only-trigger"
    WINDOW_NOT_TOO_NARROW = "window-not-too-narrow"

    # --- 2. windows --------------------------------------------------------
    SHARED_BOUNDARY_NOT_MID_CUE = "shared-boundary-not-mid-cue"
    ANSWER_POSSIBLE_BEFORE_START = "answer-possible-before-start"      # 2.2
    ANSWER_AVAILABLE_BEFORE_QUESTION = "answer-available-before-question"  # 2.3
    WINDOW_CAN_BE_TIGHTENED = "window-can-be-tightened"                # 2.4
    AUTHOR_SAYS_ANSWER_IN_WINDOW = "author-says-answer-in-window"      # 2.5

    # --- 3. triggers -------------------------------------------------------
    NO_MISSED_TRIGGER = "no-missed-trigger"
    TRIGGER_MATCHES_CRITERION = "trigger-matches-criterion"
    EVENT_NOT_EARLIER_THAN_WINDOW = "event-not-earlier-than-window"
    ELEMENTWISE_OPTIONAL_TRIGGERS = "elementwise-optional-triggers"   # 3.4

    # --- 4. shortcuts ------------------------------------------------------
    PROBE_PROTOCOL = "probe-protocol"
    SOLVABLE_WITHOUT_VIDEO = "solvable-without-video"        # 4.2
    VIDEO_RECOGNIZED = "video-recognized"                    # 4.3
    TRANSCRIPT_ENOUGH = "transcript-enough"                  # 4.4
    FRAMES_ENOUGH = "frames-enough"                          # 4.5
    SINGLE_FRAME_ENOUGH = "single-frame-enough"              # 4.6
    SOLVABLE_AT_ALL = "solvable-at-all"                      # 4.7
    QUESTION_ANCHORED_TO_SCREEN = "question-anchored-to-screen"  # 4.8

    # --- 5. rubric ---------------------------------------------------------
    TWINS_SHARE_RUBRIC = "twins-share-rubric"
    RUBRIC_WITHIN_QUESTION = "rubric-within-question"
    DISCRIMINATOR_IN_QUESTION = "discriminator-in-question"
    RUBRIC_NOT_PUNISHING_EXTRA = "rubric-not-punishing-extra"

    # --- 6. distractors — the whole group retired 2026-09-07 -----------------
    # The `distractor_windows` field was removed from the sample: an early answer is
    # penalised by the false-alarm rate anyway, and the annotated windows leaked
    # `t_start` to the semi-blind reviewer (their `t_end` was the window's `t_start`).
    # The names stay so that the reviews saved under checklist 2026-08-24 still read.
    DISTRACTOR_FULLY_COVERED = "distractor-fully-covered"
    DISTRACTOR_NOT_CORRECT_ANSWER = "distractor-not-correct-answer"
    TWINS_KEEP_LEGAL_DISTRACTOR = "twins-keep-legal-distractor"
    DISTRACTOR_WHY_HIDES_ANSWER = "distractor-why-hides-answer"

    # --- 7. labels ---------------------------------------------------------
    TEMPORAL_REL_DERIVED = "temporal-rel-derived"
    AUDIO_DEPENDENCY_EMPTY_IN_DRAFT = "audio-dependency-empty-in-draft"
    REASONING_LEVEL_NOT_INFLATED = "reasoning-level-not-inflated"
    DEPENDS_ON_IS_DEPENDENCY = "depends-on-is-dependency"
    EVIDENCE_SPAN_IS_LAST = "evidence-span-is-last"
    AUDIO_DEPENDENCY_MATCHES_PROBES = "audio-dependency-matches-probes"
    PROBE_FLAGS_CONSISTENT = "probe-flags-consistent"

    # --- 8. provenance -----------------------------------------------------
    TIMECODES_EXIST = "timecodes-exist"
    REFERENCE_MATCHES_DESCRIPTION = "reference-matches-description"
    REFERENCES_CONSISTENT_WITH_WINDOWS = "references-consistent-with-windows"
    REFERENCE_ANSWER_VERIFIED = "reference-answer-verified"   # new, from the analysis of review A3
    TWINS_AGREE_ON_SUBSTANCE = "twins-agree-on-substance"

    # --- 9. drift (automatic) ----------------------------------------------
    NUMBERS_RECOMPUTED = "numbers-recomputed"
    EXAMPLES_GENERATED = "examples-generated"
    TOOLS_IDEMPOTENT = "tools-idempotent"
    CHECKLIST_MATCHES_VALIDATOR = "checklist-matches-validator"


# Items that no longer exist in the checklist, with the checklist version in which they
# were retired. A review saved under an OLDER checklist may still carry them; a review
# saved under this or a newer one may not. The cross-check at the bottom of the file
# skips them: they are in the contract for reading, not for reporting.
RETIRED_ITEMS: dict[Item, str] = {
    Item.DISTRACTOR_GEOMETRY: "2026-09-07",
    Item.MULTITRIGGER_HAS_DISTRACTOR: "2026-09-07",
    Item.DISTRACTOR_FULLY_COVERED: "2026-09-07",
    Item.DISTRACTOR_NOT_CORRECT_ANSWER: "2026-09-07",
    Item.TWINS_KEEP_LEGAL_DISTRACTOR: "2026-09-07",
    Item.DISTRACTOR_WHY_HIDES_ANSWER: "2026-09-07",
}

# Items introduced later than the first checklist: a review saved under an older
# checklist is not required to have a line for them.
INTRODUCED_ITEMS: dict[Item, str] = {
    Item.ELEMENTWISE_OPTIONAL_TRIGGERS: "2026-09-07",
}


def items_for(role: "Role", checklist_version: str) -> tuple[frozenset["Item"], frozenset["Item"]]:
    """(required, tolerated) items of a role for a review saved under `checklist_version`.

    Required: the role's items introduced no later than that version. Tolerated: the
    items retired after that version — an old review may carry them, a new one may not.
    Versions are ISO dates, so string comparison is chronological.
    """
    required = frozenset(i for i in ROLE_ITEMS[role]
                         if INTRODUCED_ITEMS.get(i, "0000-00-00") <= checklist_version)
    tolerated = frozenset(i for i, retired in RETIRED_ITEMS.items()
                          if checklist_version < retired and i in LEGACY_ROLE_ITEMS.get(role, ()))
    return required, tolerated


# --------------------------------------------------------------------------
# Small types
# --------------------------------------------------------------------------

Seconds = Annotated[float, Field(ge=0, description="a moment in the video, seconds")]


class Role(StrEnum):
    """Who filled it in. Every role has its own prompt and its own set of available material."""

    SEMIBLIND = "semiblind"       # knows the t_end of the windows, not the answer: 2.2, 2.3
    FULL_SAMPLE = "full_sample"   # sees the whole sample, one run per sample
    FULL_WINDOW = "full_window"   # sees one window, one run per window
    PROBE_TEXT = "probe_text"
    PROBE_VISION = "probe_vision"
    PROBE_FRAME = "probe_frame"
    PROBE_FULL = "probe_full"
    PROBE_VERIFY = "probe_verify"  # stage C: answers with material up to the t_s proposed by full_sample


# Which items each role must close. This is not a reference table but part of the
# contract: review completeness is validated against it, so the table is authoritative.
#
# The split is not administrative. A full reviewer knows the reference answer and is
# therefore biased in one direction: in a half-drawn frame, where the object is still
# being rendered, they "recognise" an answer that is not there yet and propose moving
# t_start to the left. The coordinator applies the fix — and over three iterations the
# window drifts monotonically. Hence left boundaries are not theirs to decide: since
# checklist 2026-09-07 they may PROPOSE `t_s` (FullSampleReview), but the proposal
# becomes a boundary only after a semi-blind `probe_verify` answers with material up to
# it — the sighted proposal and the blind verification have opposite biases.
ROLE_ITEMS: dict[Role, frozenset[Item]] = {
    # The semi-blind reviewer does not "check" 2.2 and 2.3: they return scans, and the
    # verdict is derived by the coordinator, comparing t_val against a t_start they never saw.
    Role.SEMIBLIND: frozenset({
        Item.SOLVABLE_WITHOUT_VIDEO,
        Item.VIDEO_RECOGNIZED,
    }),
    # The full review was split into two roles because the former single set was
    # unsatisfiable: the contract demanded a line for all eighteen items, while the
    # pipeline launched the reviewer PER WINDOW on a sample with nine windows and gave
    # them a frame budget for that window. A per-window reviewer physically could not
    # close "no firing was missed" (which needs the whole video) and answered nine
    # identical times about the text of the question and the rubric. The outcome by
    # construction: skipped, and skipped forbids PASS — so on multi-window samples the
    # cycle never converged.
    #
    # The boundary was drawn by what an item is about rather than by how much work it is:
    # a window owns exactly what can be decided by looking at that window and nothing
    # else. The provenance references, the reference answer and the shape of the
    # trigger set do not belong to a window — they are common to the sample, and there
    # is nothing to divide them along between per-window runs.
    Role.FULL_SAMPLE: frozenset({
        Item.NO_MISSED_TRIGGER,
        Item.TRIGGER_MATCHES_CRITERION,
        Item.QUESTION_ANCHORED_TO_SCREEN,
        Item.RUBRIC_WITHIN_QUESTION,
        Item.DISCRIMINATOR_IN_QUESTION,
        Item.RUBRIC_NOT_PUNISHING_EXTRA,
        Item.ELEMENTWISE_OPTIONAL_TRIGGERS,
        Item.REASONING_LEVEL_NOT_INFLATED,
        Item.REFERENCE_MATCHES_DESCRIPTION,
        Item.REFERENCES_CONSISTENT_WITH_WINDOWS,
        Item.REFERENCE_ANSWER_VERIFIED,
        Item.TWINS_AGREE_ON_SUBSTANCE,
    }),
    Role.FULL_WINDOW: frozenset({
        Item.WINDOW_CAN_BE_TIGHTENED,
        Item.AUTHOR_SAYS_ANSWER_IN_WINDOW,
        Item.EVENT_NOT_EARLIER_THAN_WINDOW,
        Item.DEPENDS_ON_IS_DEPENDENCY,
        Item.EVIDENCE_SPAN_IS_LAST,
    }),
}

# What the roles used to own before an item was retired: needed only to read the reviews
# saved under the older checklist (see `items_for`).
LEGACY_ROLE_ITEMS: dict[Role, frozenset[Item]] = {
    Role.FULL_SAMPLE: frozenset({
        Item.DISTRACTOR_FULLY_COVERED,
        Item.DISTRACTOR_NOT_CORRECT_ANSWER,
        Item.DISTRACTOR_WHY_HIDES_ANSWER,
    }),
}

# The items assigned to no subagent role, because the coordinator derives them from
# other agents' answers: 2.2 and 2.3 from the semi-blind reviewer's `scans`, 4.1 and
# 4.4-4.7 from the probe answers. The list is needed so that the cross-check below can
# tell "derived" from "we forgot to assign it": without it an item that fell out of every
# role looks exactly like an item the coordinator is responsible for.
COORDINATOR_ITEMS: frozenset[Item] = frozenset({
    Item.ANSWER_POSSIBLE_BEFORE_START,
    Item.ANSWER_AVAILABLE_BEFORE_QUESTION,
    Item.PROBE_PROTOCOL,
    Item.TRANSCRIPT_ENOUGH,
    Item.FRAMES_ENOUGH,
    Item.SINGLE_FRAME_ENOUGH,
    Item.SOLVABLE_AT_ALL,
    # 4.2 stands both here and in ROLE_ITEMS[SEMIBLIND], and the overlap is deliberate.
    # The semi-blind reviewer writes `prior_answer` and their preliminary judgement — that
    # is measurement data. But they cannot issue the final verdict for the same reason
    # they do not issue 2.2 and 2.3: there is nothing to compare against, they have no
    # reference answer. On the pilot this played out exactly as it should have: the
    # reviewer guessed the canonical textbook example, gave themselves a `fail` and
    # declared blind-solved a sample whose answer they did not actually know but filled in
    # with an assumption about what would be on screen. Hence:
    #
    #   * the semi-blind `checks[solvable-without-video].result` is PRELIMINARY;
    #   * `validation.blind_solved` is set by the coordinator, comparing `prior_answer`
    #     against the rubric on two conditions at once — the answer must be both HONEST
    #     (no assumptions about material that was not seen) and CORRECT.
    Item.SOLVABLE_WITHOUT_VIDEO,
})


# The items whose conclusion concerns a specific window. One `ok` for a nine-window
# sample is eight unchecked windows disguised as checked ones, so for such items
# `target` is required. The two retired distractor items stay in the list so that the
# old reviews keep validating the way they were saved.
ITEMS_NEEDING_TARGET: frozenset[Item] = frozenset({
    Item.WINDOW_CAN_BE_TIGHTENED,
    Item.AUTHOR_SAYS_ANSWER_IN_WINDOW,
    Item.EVENT_NOT_EARLIER_THAN_WINDOW,
    Item.DISTRACTOR_FULLY_COVERED,
    Item.DISTRACTOR_NOT_CORRECT_ANSWER,
    Item.DEPENDS_ON_IS_DEPENDENCY,
    Item.EVIDENCE_SPAN_IS_LAST,
})


# Which index exactly the target must name. Legacy: the two items are retired, and the
# rule survives only for reading the reviews saved under checklist 2026-08-24.
ITEMS_NEEDING_DISTRACTOR_IDX: frozenset[Item] = frozenset({
    Item.DISTRACTOR_FULLY_COVERED,
    Item.DISTRACTOR_NOT_CORRECT_ANSWER,
})


# The items whose conclusion is drawn from the text of the sample and requires neither
# frames nor lines of speech. Only for these may `looked_at` be empty.
ITEMS_WITHOUT_VIEWING: frozenset[Item] = frozenset({
    Item.QUESTION_ANCHORED_TO_SCREEN,
    Item.RUBRIC_WITHIN_QUESTION,
    Item.DISCRIMINATOR_IN_QUESTION,
    Item.RUBRIC_NOT_PUNISHING_EXTRA,
    Item.DISTRACTOR_WHY_HIDES_ANSWER,
    Item.REASONING_LEVEL_NOT_INFLATED,
    Item.DEPENDS_ON_IS_DEPENDENCY,
    Item.REFERENCES_CONSISTENT_WITH_WINDOWS,
})

# The items applicable to any sample: there is no `na` for them.
# Inapplicability is possible only where the geometry of the sample creates it — no
# `depends_on`, no twin, a rubric that does not split by elements (3.4). Without this list `na` turns out cheaper than an
# honest `skipped`: it demands nothing and does not stand in the way of a PASS verdict,
# which makes it the most profitable way of not checking.
ITEMS_ALWAYS_APPLICABLE: frozenset[Item] = frozenset({
    Item.WINDOW_CAN_BE_TIGHTENED,
    Item.AUTHOR_SAYS_ANSWER_IN_WINDOW,
    Item.NO_MISSED_TRIGGER,
    Item.TRIGGER_MATCHES_CRITERION,
    Item.EVENT_NOT_EARLIER_THAN_WINDOW,
    Item.QUESTION_ANCHORED_TO_SCREEN,
    Item.RUBRIC_WITHIN_QUESTION,
    Item.DISCRIMINATOR_IN_QUESTION,
    Item.RUBRIC_NOT_PUNISHING_EXTRA,
    Item.REASONING_LEVEL_NOT_INFLATED,
    Item.EVIDENCE_SPAN_IS_LAST,
    Item.REFERENCE_MATCHES_DESCRIPTION,
    Item.REFERENCE_ANSWER_VERIFIED,
})
# `twins-agree-on-substance` is NOT in this list, and that is a fix rather than an
# oversight. It used to be here, and it contradicted the list's own rule: inapplicability
# is legitimate where the geometry of the sample creates it, and "there is no twin" is
# exactly such a case, named in the docstring above. The role prompt told the reviewer to
# put `na` on a sample with no `twin_of`, while the contract refused to save such a
# review; the reviewer was forced to write `ok` with the analysis "the pair does not
# exist, there is nothing to diverge" — that is, to report on a check that never happened.
# Now `na` is legitimate exactly when `twin_of` is absent.


class Verdict(StrEnum):
    """The ladder of verdicts: each one costs more to cure than the last."""

    PASS = "PASS"
    FIX_INTERVALS = "FIX_INTERVALS"    # cured by moving boundaries
    FIX_QUESTION = "FIX_QUESTION"      # cured by rewording
    CRITICAL_FAIL = "CRITICAL_FAIL"    # the sample is thrown out


class Result(StrEnum):
    OK = "ok"            # checked, did not fire
    FAIL = "fail"        # checked, fired
    SKIPPED = "skipped"  # not checked — must name what was left uncovered
    NA = "na"            # the item does not apply to this sample


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Observation(Strict):
    """What exactly the subagent saw or heard. The unit of "what was looked at".

    It is not there for reporting: from the list of observations the coordinator can see
    whether the interval over which an item was declared passed is actually covered. An
    item marked `ok` with an empty `looked_at` is a `skipped`, only an undeclared one.
    """

    kind: Literal["frame", "cue"]
    t: Seconds = Field(description="the timecode of a frame or of the start of a line of speech")
    what: str = Field(min_length=3, description="what is visible in the frame / what is said in the line")


class SubAnswer(Strict):
    """An intermediate answer inside a check — the heart of SGR.

    A checklist item almost never reduces to a single yes/no: 2.4 ("the window can be
    tightened") splits into "the event ended at moment X" and "after X nothing relevant
    happens". Recorded separately, these steps make it possible to see where two reviewers
    diverged — not merely that they did.

    The question has to be phrased so that the answer can be checked: not "is the window
    all right" but "the last frame in which the object is still changing".
    """

    question: str = Field(min_length=5, description="what exactly we are asking ourselves at this step")
    answer_bool: bool | None = None
    answer_number: float | None = None
    answer_text: str | None = None
    why: str = Field(min_length=5, description="what this intermediate answer rests on")

    @model_validator(mode="after")
    def _one_answer(self) -> SubAnswer:
        filled = [x for x in (self.answer_bool, self.answer_number, self.answer_text)
                  if x is not None]
        if not filled:
            raise ValueError("an intermediate step with no answer: fill in one of the answer_*")
        return self


class Interval(Strict):
    t_start: Seconds
    t_end: Seconds

    @model_validator(mode="after")
    def _ordered(self) -> Interval:
        if self.t_end <= self.t_start:
            raise ValueError("the interval is empty or inverted")
        return self


class Target(Strict):
    """What the check is about: a sample can have nine windows.

    Both fields are optional individually, but an empty `Target()` is the same "one ok for
    a nine-window sample", only one that passed validation: the requirement "this item
    needs a target" is satisfied by an object that points at nothing. So at least one
    field must be filled in, and which one is decided by the item itself (see
    `_target_points_somewhere` in `Check`).
    """

    trigger_idx: int | None = Field(default=None, ge=0)
    distractor_idx: int | None = Field(
        default=None, ge=0,
        description="LEGACY: the sample has no distractor_windows since 2026-09-07; the "
                    "field is kept so that older reviews still read, and a new review "
                    "has nothing to put in it")

    @model_validator(mode="after")
    def _not_empty(self) -> Target:
        if self.trigger_idx is None and self.distractor_idx is None:
            raise ValueError("empty target: it must name a window (or, in a legacy review, a distractor), "
                             "otherwise the check formally exists but what it is about is unknown")
        return self


class Proposal(Strict):
    """A proposed fix. The reviewer does not edit files — the coordinator does."""

    field: str = Field(description="what to change: t_start, t_end, question, rubric[2], ...")
    value: str = Field(description="what to change it to; a number goes as a string too, so as not to lose the format")
    why: str = Field(min_length=10)


class Violation(Strict):
    """An admission that a forbidden file was read.

    The failure is not in having read it: a path turns up in `grep` output, a file is
    opened alongside its neighbour. The failure is in keeping quiet, because a silently
    contaminated review is indistinguishable from a clean one and spoils everything
    derived from it.
    """

    path: str
    why: str = Field(min_length=5, description="why it was opened")
    what_seen: str = Field(min_length=5, description="what was seen — honestly")


class Budget(Strict):
    """Under which viewing regime the result was obtained.

    The flag `visiononly_solved = false` cannot be interpreted without this number: it
    mixes "vision was not enough" with "vision was shown forty pictures for half an hour".
    We are going to change the viewing grid — and on that day old and new measurements
    will have to be told apart, otherwise `audio_dependency` will be derived from a
    mixture of regimes.

    That day arrived along with the text index of the video track: `screen_index_used` is
    exactly the mark of the viewing regime this class was written for.
    """

    frames_viewed: int = Field(ge=0)
    sparse_step: float | None = Field(default=None, description="the step of the sparse grid, s")
    dense_intervals: list[Interval] = Field(default_factory=list,
                                            description="where the reviewer looked densely")
    transcript_cues: int | None = Field(default=None, description="how many lines of speech were read")
    screen_index_used: bool = Field(
        default=False,
        description="whether the text index of the video track was used (screen_text.md, "
                    "screen.jsonl). A measurement with the index and one without it are "
                    "not comparable: the index is built on a 0.5-second grid, that is, "
                    "denser than any frame budget. Without this flag a visiononly_solved "
                    "obtained the two ways looks the same, which means the "
                    "audio_dependency label derived from it mixes two viewing regimes")


# --------------------------------------------------------------------------
# A check against a checklist item (SGR Cascade)
# --------------------------------------------------------------------------


class Check(Strict):
    """One checklist item.

    The order of the fields is the order of the reasoning, and it must not be changed:
    under constrained decoding the model generates the fields top to bottom, and `result`,
    standing last, is written only after the grounds have been fixed. Move `result` to the
    top and everything below it becomes a retelling of a decision already made.
    """

    group: Group
    item: Item

    target: Target | None = Field(default=None,
                                  description="required for items about a specific window; "
                                              "null for sample-level items")

        # --- the cascade: look -> see -> apply the criterion -> steps -> conclude
    looked_at: list[Observation] = Field(
        default_factory=list,
        description="the frames and lines of speech the conclusion rests on; empty is allowed "
                    "only for items that require no viewing")
    findings: str = Field(
        min_length=10,
        description="what was seen, in your own words and without judgement: facts first")
    criterion: str = Field(
        min_length=10,
        description="which criterion of the item is being applied to what was seen; "
                    "phrase it in your own words rather than quoting the checklist — "
                    "a restatement exposes a misunderstanding, a quotation hides it")
    steps: list[SubAnswer] = Field(
        default_factory=list,
        description="the intermediate answers the verdict is assembled from")

        # --- and only now the conclusion ---------------------------------------
    result: Result
    confidence: Confidence = Confidence.HIGH
    proposal: Proposal | None = None
    uncovered: Interval | None = Field(
        default=None, description="what was left unchecked; required when skipped")

    @model_validator(mode="after")
    def _group_matches_item(self) -> Check:
        """The group is derivable from the item but is written down anyway.

        The duplication is deliberate: under constrained decoding the model first picks
        the group and thereby narrows its own choice of item — cheap Routing. A mismatch
        means the model took the wrong branch, and the conclusion below concerns a
        different item from the one it named.
        """
        expected = ITEM_GROUP.get(self.item)
        if expected is not None and self.group is not expected:
            raise ValueError(f"item {self.item.value} belongs to group "
                             f"{expected.value}, not {self.group.value}")
        if self.item in ITEMS_NEEDING_TARGET and self.target is None:
            raise ValueError(f"item {self.item.value} concerns a specific window: "
                             f"without a target the coordinator cannot tell what to fix")
        if self.target is not None:
            if self.item in ITEMS_NEEDING_DISTRACTOR_IDX and self.target.distractor_idx is None:
                raise ValueError(f"item {self.item.value} is about a distractor, while the target names "
                                 f"only a trigger: it is unclear which distractor was checked")
            if (self.item in ITEMS_NEEDING_TARGET
                    and self.item not in ITEMS_NEEDING_DISTRACTOR_IDX
                    and self.target.trigger_idx is None):
                raise ValueError(f"item {self.item.value} is about a trigger window, "
                                 f"while the target names only a distractor")
        return self

    @model_validator(mode="after")
    def _skipped_names_the_gap(self) -> Check:
        if self.result is Result.SKIPPED and self.uncovered is None:
            raise ValueError("skipped without uncovered: the uncovered interval must be named, "
                             "otherwise a gap is indistinguishable from a completed check")
        if self.result is Result.FAIL and self.proposal is None:
            raise ValueError("fail without proposal: an item that fired must propose a cure")
        return self

    @model_validator(mode="after")
    def _conclusion_rests_on_something(self) -> Check:
        """The conclusion has to stand on something.

        An `ok` with an empty `looked_at` is a `skipped`, only an undeclared one: from
        outside it is indistinguishable from a checked item, while inside there was no
        check. There is one exception — the items whose conclusion is drawn from the text
        of the sample; for them `steps` is required, because otherwise nothing at all is
        left of the check.
        """
        if self.result in (Result.OK, Result.FAIL):
            if self.item in ITEMS_WITHOUT_VIEWING:
                if not self.steps:
                    raise ValueError(
                        f"{self.item.value}: a text item with no steps — there is nothing for the "
                        f"conclusion to stand on. Break it down into checkable intermediate answers")
            elif not self.looked_at:
                raise ValueError(
                    f"{self.item.value}: result={self.result.value} with an empty looked_at. "
                    f"An item nothing was looked at for is a skipped, not an ok")
        if self.result is Result.NA and self.item in ITEMS_ALWAYS_APPLICABLE:
            raise ValueError(
                f"{self.item.value} applies to any sample — there is no na for it. "
                f"If it could not be checked, that is a skipped with the uncovered interval named")
        return self


# --------------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------------


class ReviewBase(Strict):
    """The common part of any review.

    `model` and `date` live here rather than in the sample: a sample is data, a review is
    a measurement. The plan requires the generator, the judge and the participant to be
    different models; after the fact that can be checked only against the saved reviews,
    which is why `data/reviews/` has to live in the repository.
    """

    schema_version: str = SCHEMA_VERSION
    # The default is the PREVIOUS checklist on purpose: a review that does not say which
    # checklist it was made against is read under the old rules, and the value it reports
    # then says so too. A new review states CHECKLIST_VERSION explicitly, and `--check`
    # refuses a legacy reading unless told it is looking at an old file (--legacy).
    checklist_version: str = PREVIOUS_CHECKLIST_VERSION
    sample_id: str
    role: Role
    iteration: int = Field(ge=1, description="the number of the fix round: reviews are not rewritten "
                                             "but accumulate — they are what makes oscillation visible")
    model: str = Field(description="which model filled it in")
    date: str
    workspace: str = Field(description="the folder the material was taken from")
    budget: Budget
    violations: list[Violation] = Field(default_factory=list)
    notes: str = Field(default="", description="no more than five lines")

    def is_legacy(self) -> bool:
        """Was the review saved under an older checklist than the current one.

        A file that does not state its `checklist_version` is legacy by the default above:
        the first rounds were saved before the field existed. A NEW review must state the
        version explicitly — otherwise it is read under the old rules (the retired items
        tolerated, the old shape of `candidates`, no 3.4). That is why `--check` fails on a
        legacy reading unless `--legacy` says the file is an old one.
        """
        return self.checklist_version < CHECKLIST_VERSION

    def effective_checklist(self) -> str:
        return min(self.checklist_version, PREVIOUS_CHECKLIST_VERSION) if self.is_legacy() \
            else self.checklist_version


# --------------------------------------------------------------------------
# The semi-blind reviewer: 2.2 and 2.3
# --------------------------------------------------------------------------


class Candidate(Strict):
    """One point of the semi-blind trajectory: a full answer from the material up to `t`.

    Why a full answer rather than a note "too early / already possible". The semi-blind
    reviewer has no reference answer and cannot check themselves: asked for the one
    moment they consider sufficient, they stop at the first moment THEY find convincing,
    and a confidently wrong answer looks exactly like a right one. So they answer at
    every moment where the screen or the speech relevant to the task changed, and the
    coordinator — who has the rubric — decides which of the answers is the first to pass
    it. The self-assessment `sufficient` is recorded but carries no status.

    On the pilot the information was there and nobody read it: the reviewers wrote
    "supplies all four concrete values and signs" about a moment inside a declared
    decoy, and the phrase had to be recognised as "the rubric is met" — it was not.
    A full answer per point is what the adjudication table is built from.
    """

    t: Seconds = Field(description="the moment; everything up to it and nothing after it was available")
    answer: str = Field(min_length=5,
                        description="the complete answer to the task from what is visible and audible "
                                    "up to t — the quantities, objects and relations themselves; "
                                    "\u00abnot yet answerable\u00bb is a legitimate answer, but then say "
                                    "what exactly is missing")
    sufficient: bool = Field(description="the reviewer's own view: is this enough to answer on the merits. "
                                         "A self-report; the verdict is the coordinator's")
    confidence: Confidence = Confidence.MEDIUM
    looked_at: list[Observation] = Field(
        default_factory=list,
        description="the frame(s) or cue(s) the answer at this point rests on; a description "
                    "line is not enough for a point the reviewer calls sufficient")
    why: str = Field(default="", description="what changed on screen or in the speech at this moment")


class IntervalScan(Strict):
    """One viewing stretch of the semi-blind reviewer.

    Why stretches rather than a single prefix. A blind reviewer given the video up to the
    `t_start` of the first window checks the left boundary of that window only: on a
    nine-window question the other eight are checked by nobody. Split it into stretches,
    one per window, and the coverage becomes complete.

    Why a stretch ends at `t_end` rather than beginning at `t_start`. The reviewer knows
    that somewhere near the end of the stretch the answer is already available, and looks
    for the **first** moment at which that became so. The question "could you answer?" is
    meaningless for a multi-trigger sample — the answer is "yes, many times, that is the
    whole point"; the question "from which moment can one?" is always meaningful.

    Why the reviewer is semi-blind rather than blind. They see `t_to` — that is, they know
    by which moment the answer must have appeared. That is unavoidable: a stretch cannot
    exist without an upper bound. But they see neither the answer, nor the rubric, nor
    `t_start` — and it is `t_start` that their conclusion checks.
    """

    idx: int = Field(ge=0, description="the number of the window the stretch belongs to")
    t_from: Seconds = Field(description="the start of the stretch: the t_end of the previous window, "
                                        "and 0 for the first one, so as to capture 2.3 as well")
    t_to: Seconds = Field(description="the end of the stretch: the t_end of its own window")

    watched: list[Observation] = Field(default_factory=list)
    candidates: list[Candidate | SubAnswer] = Field(
        default_factory=list,
        description="the trajectory: one Candidate per moment where the relevant state of the "
                    "screen or speech changed, each with a FULL answer from the material up "
                    "to that moment, the last one at the end of the stretch. The coordinator "
                    "checks every answer against the rubric; the first that passes is t_val. "
                    "SubAnswer is the legacy shape from checklist 2026-08-24 and is not "
                    "accepted in new reviews")

    t_val: Seconds | None = Field(
        default=None,
        description="the reviewer's OWN view of the earliest point of the stretch from which "
                    "the question can be answered on the merits; null if nowhere. A "
                    "self-report: the t_val that counts is assigned by the coordinator from "
                    "the rubric check of `candidates`")
    t_val_basis: str = Field(
        default="", description="what exactly appeared at that moment")
    answer_at_t_val: str = Field(
        default="", description="what specifically can be answered from that moment on; "
                                "the comparison against the reference answer is the coordinator's job")
    confidence: Confidence = Confidence.HIGH

    @model_validator(mode="after")
    def _inside(self) -> IntervalScan:
        if self.t_to <= self.t_from:
            raise ValueError("the stretch is empty or inverted")
        if self.t_val is not None and not (self.t_from <= self.t_val <= self.t_to):
            raise ValueError("t_val outside its own stretch: the reviewer looked where they were not asked to")
        if self.t_val is not None and len(self.t_val_basis) < 5:
            raise ValueError("t_val with no grounds")
        return self


class SemiBlindReview(ReviewBase):
    """The semi-blind review: the left boundaries of every window plus contamination.

    From `scans` the coordinator derives two checklist items; the reviewer issues no
    verdicts on them:

    * `t_val[0] < question_time`  -> `answer-available-before-question` (2.3);
    * `t_val[k] < t_start[k]`     -> `answer-possible-before-start` (2.2);
    * `t_val[k] is None`          -> the reviewer did not find the answer where it must be
      by the end of the stretch: a signal towards `author-says-answer-in-window` (2.5) or
      `solvable-at-all` (4.7), but **not** towards 2.2. The case `t_val > t_end` does not
      arise: the `IntervalScan` validator rules it out, because the reviewer has nothing
      to search past the upper bound of the stretch with — there is no material there.

    The first stretch begins at **zero** rather than at `question_time`: otherwise there
    is no way to check 2.3 ("the answer was available even before the question was
    issued") — the material before `question_time` would simply never reach the reviewer.
    A single number `t_val[0]` closes both items at once; what separates them is its
    comparison against `question_time`.

    Asking the reviewer themselves for the verdict is not allowed: they do not know
    `t_start`, and if they did they would stop being semi-blind.

    **Since checklist 2026-09-07 the scan is a trajectory, and `t_val` is adjudicated.**
    Every `Candidate` carries a full answer; the coordinator checks each against the
    rubric item by item and takes the first passing one as `t_val` (the reviewer's own
    `t_val` is a self-report). The reviewer is told nothing about decoys — there are
    none any more — and therefore nothing that could betray `t_start`: on the pilot the
    `t_end` of a declared decoy was the window's `t_start` in 23 samples of 44, and
    `t_val` landed within a second after it in 19.

    For the same reason **their verdict on 4.2 is preliminary too**
    (`solvable-without-video`): they have no reference answer, and they judge "it matched"
    by eye against their own `prior_answer`. They do write the line — it is useful as a
    self-report — but `validation.blind_solved` is set by the coordinator, comparing
    `prior_answer` and `prior_answer_assumptions` against the rubric.
    """

    role: Literal[Role.SEMIBLIND] = Role.SEMIBLIND

    prior_answer: str = Field(
        description="the answer to the question before any viewing, from general knowledge (4.2). "
                    "Recorded verbatim. This is an ANSWER, not a guess about what "
                    "will be on screen: filling in the statement of the problem is forbidden. "
                    "If the quantities named in the question are not enough, the honest "
                    "prior_answer is \u00abit cannot be answered on the merits, such-and-such "
                    "data are missing\u00bb, and that is NOT blind solving. The comparison "
                    "against the rubric is the coordinator's job")
    prior_answer_assumptions: list[str] = Field(
        default_factory=list,
        description="the assumptions without which prior_answer does not stand: each "
                    "on its own line (\u00abthe screen shows the canonical example 1/2, 1/4, "
                    "1/8, 1/8\u00bb). An empty list means the answer was derived only "
                    "from the text of the question and general knowledge of the subject. The field "
                    "exists because an answer resting on guessed screen content is "
                    "not blind solving, while from outside it is indistinguishable from it")
    recognized_video: bool = Field(
        description="whether the video was recognised before viewing (4.3)")
    recognized_how: str = Field(
        default="", description="by which signs it was recognised")

    scans: list[IntervalScan] = Field(min_length=1)
    checks: list[Check] = Field(
        default_factory=list,
        description="two lines: video-recognized (the verdict is final) "
                    "and solvable-without-video (the verdict is PRELIMINARY — "
                    "the coordinator re-checks it, see COORDINATOR_ITEMS)")

    @model_validator(mode="after")
    def _trajectory_shape(self) -> SemiBlindReview:
        """New reviews carry Candidates and end every stretch with an answer at its end."""
        if self.is_legacy():
            return self
        for sc in self.scans:
            legacy = [c for c in sc.candidates if isinstance(c, SubAnswer)]
            if legacy:
                raise ValueError(f"stretch {sc.idx}: candidates in the legacy SubAnswer shape; since "
                                 f"checklist {CHECKLIST_VERSION} every candidate is a Candidate with a "
                                 f"full answer at its moment")
            if not sc.candidates:
                raise ValueError(f"stretch {sc.idx}: an empty trajectory. At the very least the end "
                                 f"of the stretch ({sc.t_to}) needs an answer — that is the given the "
                                 f"whole task rests on")
            last = max(c.t for c in sc.candidates)
            if last < sc.t_to - 1.0:
                raise ValueError(f"stretch {sc.idx}: the trajectory stops at {last}, the stretch ends at "
                                 f"{sc.t_to}. Reach the end and answer there: without that the "
                                 f"coordinator cannot tell \u00abtoo early everywhere\u00bb from "
                                 f"\u00abstopped looking\u00bb")
            for c in sc.candidates:
                if not (sc.t_from <= c.t <= sc.t_to):
                    raise ValueError(f"stretch {sc.idx}: candidate at {c.t} outside [{sc.t_from}, {sc.t_to}]")
                if c.sufficient and not c.looked_at:
                    raise ValueError(f"stretch {sc.idx}: the candidate at {c.t} is called sufficient "
                                     f"with nothing in looked_at — a description line is not a frame")
        return self

    @model_validator(mode="after")
    def _covers_its_items(self) -> SemiBlindReview:
        seen = {c.item for c in self.checks}
        required, tolerated = items_for(Role.SEMIBLIND, self.effective_checklist())
        missing = required - seen
        if missing:
            names = ", ".join(sorted(i.value for i in missing))
            raise ValueError(f"no line for the items of the mode: {names}")
        alien = seen - required - tolerated
        if alien:
            names = ", ".join(sorted(i.value for i in alien))
            raise ValueError(f"items outside this mode: {names}. Left boundaries "
                             f"are not judged by the semi-blind reviewer — the coordinator derives "
                             f"them from scans, because t_start was never shown to them")
        return self


# --------------------------------------------------------------------------
# The full reviewer
# --------------------------------------------------------------------------


class FullReview(ReviewBase):
    """The common part of both non-blind reviews. It is never saved on its own.

    The only thing described here beyond the common envelope is **coverage**: there must
    be a line for every item of the role's mode, including the ones that did not fire
    (`ok`) and the ones that do not apply (`na`). A missing line is indistinguishable from
    a completed check, and that is exactly the substitution `skipped` exists to forbid.
    """

    verdict: Verdict
    checks: list[Check] = Field(min_length=1)

    @model_validator(mode="after")
    def _covers_its_items(self) -> FullReview:
        seen = {c.item for c in self.checks}
        required, tolerated = items_for(self.role, self.effective_checklist())
        missing = required - seen
        if missing:
            names = ", ".join(sorted(i.value for i in missing))
            raise ValueError(f"no line for the items of mode {self.role.value}: {names}. "
                             f"A missing line is indistinguishable from a completed check — "
                             f"put ok, na or skipped")
        alien = seen - required - tolerated
        if alien:
            names = ", ".join(sorted(i.value for i in alien))
            raise ValueError(f"items outside mode {self.role.value}: {names}")
        return self

    @model_validator(mode="after")
    def _verdict_matches_checks(self) -> FullReview:
        """The verdict cannot be better than the worst of the checks.

        This catches the commonest way of passing bad work off as good: write up the items
        that fired honestly, and put PASS in the verdict.
        """
        bad = [c for c in self.checks if c.result in (Result.FAIL, Result.SKIPPED)]
        if bad and self.verdict is Verdict.PASS:
            names = ", ".join(sorted({c.item.value for c in bad}))
            raise ValueError(f"verdict=PASS while items have fired or been skipped: {names}")
        return self


class FullSampleReview(FullReview):
    """The review of the sample as a whole: the text of the question, the rubric, the
    reference answer, the completeness and shape of the trigger set. One run per sample,
    with a frame budget for the whole video.

    Everything that does not belong to an individual window is gathered here. The check
    "was a firing missed" needs a sparse grid over the whole lecture; the text of the
    question and the rubric are shared by all the windows of a sample; the `provenance`
    references cannot be divided between windows.

    **`t_s` — the sighted proposal for the left boundary (stage B).** The full reviewer
    knows the answer and is biased leftwards: in a half-drawn frame they "recognise" what
    is not there yet. That is why 2.2 was forbidden to them outright. Now they may
    PROPOSE the first moment from which the rubric is, in their view, satisfiable — and
    the proposal moves nothing by itself: when it is earlier than the semi-blind `t_val`,
    the coordinator launches `probe_verify` with material up to `t_s`, and only a passing
    answer from that probe makes `t_s` the boundary.
    """

    role: Literal[Role.FULL_SAMPLE] = Role.FULL_SAMPLE

    t_s: Seconds | None = Field(
        default=None,
        description="stage B: the first moment from which, in your view, the rubric of the "
                    "first required window can be met in full. A proposal, verified by a "
                    "semi-blind probe; null if you see no moment earlier than t_start")
    t_s_basis: str = Field(
        default="",
        description="the frame or cue at t_s and what exactly on it lets each rubric item be met")

    @model_validator(mode="after")
    def _t_s_has_basis(self) -> FullSampleReview:
        if self.t_s is not None and len(self.t_s_basis) < 10:
            raise ValueError("t_s without a basis: name the frame or cue and what on it meets the rubric")
        return self


class FullWindowReview(FullReview):
    """The review of one window. One run per window, with a frame budget for that window.

    `window_idx` is required and is duplicated in every `target`: without it the
    coordinator, handed nine files, could not tell nine reviews of nine windows from nine
    reviews of one and the same window — and it is exactly for that distinction that the
    role exists.
    """

    role: Literal[Role.FULL_WINDOW] = Role.FULL_WINDOW
    window_idx: int = Field(ge=0, description="the idx of the trigger this is a review of")

    @model_validator(mode="after")
    def _target_is_this_window(self) -> FullWindowReview:
        wrong = sorted({c.target.trigger_idx for c in self.checks
                        if c.target is not None and c.target.trigger_idx is not None
                        and c.target.trigger_idx != self.window_idx})
        if wrong:
            raise ValueError(f"a review of window {self.window_idx} whose target names windows {wrong}: "
                             f"a per-window reviewer sees only their own window and cannot judge "
                             f"anybody else's")
        return self


# --------------------------------------------------------------------------
# The modality probes
# --------------------------------------------------------------------------


class ProbeAnswer(ReviewBase):
    """A probe's answer. It issues no verdicts and does not reason about the question.

    The probe does not know it is taking part in a check: it simply answers the question
    from the material it was given. The decision about the flag is taken by the
    coordinator, comparing the answer against the reference — otherwise the probe would
    start tuning its answer to the expected flag.
    """

    role: Literal[Role.PROBE_TEXT, Role.PROBE_VISION,
                  Role.PROBE_FRAME, Role.PROBE_FULL]

    looked_at: list[Observation] = Field(default_factory=list)
    steps: list[SubAnswer] = Field(
        default_factory=list,
        description="how the probe got to the answer; for a probe this is also a way to tell "
                    "an inference from the material apart from a recollection about the subject")
    answer: str = Field(min_length=1, description="the answer on the merits, in your own words")
    basis: str = Field(min_length=5,
                       description="where the answer came from: timecodes and quotations — or \u00abgeneral knowledge\u00bb. "
                                   "If you recognised the video or recalled the answer before you "
                                   "looked at the material, write that down plainly")
    confidence: Confidence
    insufficient: bool = Field(
        default=False,
        description="the material was not enough; set together with an attempt at an answer, "
                    "not instead of one")


class VerifyProbe(ProbeAnswer):
    """Stage C: a fresh semi-blind probe answers with material up to `t_upto`.

    Launched by the coordinator when the sighted proposal `t_s` (or an early correct
    answer of an evaluated model) lies earlier than the semi-blind `t_val`. The probe
    gets the task without its when-clause, the transcript, the description and the
    frames up to `t_upto`, and nothing else — it neither knows the reference answer nor
    that a boundary is being checked. The coordinator checks `answer` against the rubric:
    passes → `t_val = t_upto`, the semi-blind reviewer missed an earlier form of the
    information; fails → `t_val` stays, the sighted reviewer recognised the answer in a
    half-frame.
    """

    role: Literal[Role.PROBE_VERIFY] = Role.PROBE_VERIFY
    t_upto: Seconds = Field(description="the upper bound of the material, the `until` of the workspace")


Review = Annotated[SemiBlindReview | FullReview | ProbeAnswer | VerifyProbe,
                   Field(discriminator="role")]


# --------------------------------------------------------------------------
# The reference table of numbers. NOT authoritative: if it diverges from the
# checklist, it is the table that gets fixed, not the saved reviews.
# --------------------------------------------------------------------------

ITEM_NUMBER: dict[Item, str] = {
    Item.WINDOW_GEOMETRY: "1.1",
    Item.DISTRACTOR_GEOMETRY: "1.2",
    Item.SAMPLE_INTEGRITY: "1.3",
    Item.DEPENDS_ON_BACKWARDS: "1.4",
    Item.MULTITRIGGER_HAS_DISTRACTOR: "1.5",
    Item.DURATION_MATCHES_BUNDLE: "1.6",
    Item.CLAIM_MATCHES_MODALITIES: "1.7",
    Item.JSON_SCHEMA: "1.8",
    Item.EVIDENCE_SPAN_PRESENT: "1.9",
    Item.SOUND_ONLY_TRIGGER: "1.10",
    Item.WINDOW_NOT_TOO_NARROW: "1.11",
    Item.SHARED_BOUNDARY_NOT_MID_CUE: "2.1",
    Item.ANSWER_POSSIBLE_BEFORE_START: "2.2",
    Item.ANSWER_AVAILABLE_BEFORE_QUESTION: "2.3",
    Item.WINDOW_CAN_BE_TIGHTENED: "2.4",
    Item.AUTHOR_SAYS_ANSWER_IN_WINDOW: "2.5",
    Item.NO_MISSED_TRIGGER: "3.1",
    Item.TRIGGER_MATCHES_CRITERION: "3.2",
    Item.EVENT_NOT_EARLIER_THAN_WINDOW: "3.3",
    Item.ELEMENTWISE_OPTIONAL_TRIGGERS: "3.4",
    Item.PROBE_PROTOCOL: "4.1",
    Item.SOLVABLE_WITHOUT_VIDEO: "4.2",
    Item.VIDEO_RECOGNIZED: "4.3",
    Item.TRANSCRIPT_ENOUGH: "4.4",
    Item.FRAMES_ENOUGH: "4.5",
    Item.SINGLE_FRAME_ENOUGH: "4.6",
    Item.SOLVABLE_AT_ALL: "4.7",
    Item.QUESTION_ANCHORED_TO_SCREEN: "4.8",
    Item.TWINS_SHARE_RUBRIC: "5.1",
    Item.RUBRIC_WITHIN_QUESTION: "5.2",
    Item.DISCRIMINATOR_IN_QUESTION: "5.3",
    Item.RUBRIC_NOT_PUNISHING_EXTRA: "5.4",
    Item.DISTRACTOR_FULLY_COVERED: "6.1",
    Item.DISTRACTOR_NOT_CORRECT_ANSWER: "6.2",
    Item.TWINS_KEEP_LEGAL_DISTRACTOR: "6.3",
    Item.DISTRACTOR_WHY_HIDES_ANSWER: "6.4",
    Item.TEMPORAL_REL_DERIVED: "7.1",
    Item.AUDIO_DEPENDENCY_EMPTY_IN_DRAFT: "7.2",
    Item.REASONING_LEVEL_NOT_INFLATED: "7.3",
    Item.DEPENDS_ON_IS_DEPENDENCY: "7.4",
    Item.EVIDENCE_SPAN_IS_LAST: "7.5",
    Item.AUDIO_DEPENDENCY_MATCHES_PROBES: "7.6",
    Item.PROBE_FLAGS_CONSISTENT: "7.7",
    Item.TIMECODES_EXIST: "8.1",
    Item.REFERENCE_MATCHES_DESCRIPTION: "8.2",
    Item.REFERENCES_CONSISTENT_WITH_WINDOWS: "8.3",
    Item.REFERENCE_ANSWER_VERIFIED: "8.4",
    Item.TWINS_AGREE_ON_SUBSTANCE: "8.5",
    Item.NUMBERS_RECOMPUTED: "9.1",
    Item.EXAMPLES_GENERATED: "9.2",
    Item.TOOLS_IDEMPOTENT: "9.3",
    Item.CHECKLIST_MATCHES_VALIDATOR: "9.4",
}

# Group number -> group. Explicitly, rather than through list(Group)[n-1]: swapping two
# members of the enum would silently reassign the groups of every item at once, without a
# single error.
GROUP_BY_NUMBER: dict[str, Group] = {
    "1": Group.FORMAL, "2": Group.WINDOWS, "3": Group.TRIGGERS, "4": Group.SHORTCUTS,
    "5": Group.RUBRIC, "6": Group.DISTRACTORS, "7": Group.LABELS,
    "8": Group.PROVENANCE, "9": Group.DRIFT,
}

ITEM_GROUP: dict[Item, Group] = {
    item: GROUP_BY_NUMBER[num.split(".")[0]] for item, num in ITEM_NUMBER.items()
}

ROLE_MODEL: dict[Role, type[ReviewBase]] = {
    Role.SEMIBLIND: SemiBlindReview,
    Role.FULL_SAMPLE: FullSampleReview,
    Role.FULL_WINDOW: FullWindowReview,
    Role.PROBE_TEXT: ProbeAnswer,
    Role.PROBE_VISION: ProbeAnswer,
    Role.PROBE_FRAME: ProbeAnswer,
    Role.PROBE_FULL: ProbeAnswer,
    Role.PROBE_VERIFY: VerifyProbe,
}


def check_file(path: str) -> ReviewBase:
    """Check a saved review. The role is taken from the file itself.

    A subagent runs this on themselves before reporting to the coordinator: an invalid
    review is cheaper to fix on the spot than to work out later why an item has no line.
    """
    import json

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    role = raw.get("role")
    if role not in set(Role):
        raise SystemExit(f"unknown role {role!r}; expected one of "
                         f"{[r.value for r in Role]}")
    return ROLE_MODEL[Role(role)].model_validate(raw)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        args = [a for a in sys.argv[2:] if a != "--legacy"]
        allow_legacy = "--legacy" in sys.argv[2:]
        if len(args) != 1:
            raise SystemExit("usage: review.py --check <review file> [--legacy]")
        try:
            obj = check_file(args[0])
        except Exception as e:  # ValidationError, JSONDecodeError, KeyError...
            print(f"the review is NOT valid:\n{e}")
            raise SystemExit(1)
        stated = (obj.checklist_version if "checklist_version" in obj.model_fields_set
                  else "nothing")
        if obj.is_legacy() and not allow_legacy:
            # The only enforcement point of the pipeline. A new review that forgot the
            # field would otherwise pass under the old, weaker rules — silently.
            print(f"the review is NOT accepted as new: it states checklist_version={stated}, "
                  f"so it was read under checklist {obj.effective_checklist()} — without the "
                  f"trajectory rules, with the retired items tolerated. A new review must state "
                  f"checklist_version={CHECKLIST_VERSION}; to check an OLD file pass --legacy")
            raise SystemExit(1)
        print(f"the review is valid: {obj.role.value}, sample {obj.sample_id}, "
              f"round {obj.iteration}" + (f" (LEGACY, checklist {obj.effective_checklist()})"
                                         if obj.is_legacy() else ""))
        raise SystemExit(0)

    missing = [i.value for i in Item if i not in ITEM_NUMBER]
    if missing:
        raise SystemExit(f"items with no number: {missing}")

    # The checklist and the contract must agree in both directions (checklist 9.4). An
    # item that exists here and not there is a requirement on the reviewer that they will
    # never read anywhere; the converse is an item nobody will report on.
    checklist = Path(__file__).resolve().parent.parent / "docs" / "annotation_checklist.md"
    if checklist.exists():
        import re

        pat = re.compile(r"^- `\[([AMH])\]` \*\*(\d+\.\d+)\..*\*\* · `([a-z0-9-]+)`")
        found, level, done = {}, {}, {}
        cur = None
        for line in checklist.read_text(encoding="utf-8").splitlines():
            m = pat.match(line)
            if m:
                cur = m.group(2)
                found[cur] = m.group(3)
                level[cur] = m.group(1)
            elif cur and line.strip().startswith("*Status.*"):
                # We do not reset cur: a second \u00ab*Status.*\u00bb inside one item used to be
                # ignored silently, and 2.1 was listed as unimplemented for ages while
                # S-33 was alive — that is, the divergence check was blind exactly where
                # the divergence was.
                if cur in done:
                    raise SystemExit(f"item {cur} has two \u00ab*Status.*\u00bb lines — which of them "
                                     f"is the real one only the author of the edit knows; leave one")
                done[cur] = "Implemented" in line
        # Retired items keep their number for reading old reviews but are no longer in
        # the checklist; the cross-check must not demand them back.
        by_num = {num: item.value for item, num in ITEM_NUMBER.items()
                  if item not in RETIRED_ITEMS}
        only_here = sorted(set(by_num) - set(found))
        only_there = sorted(set(found) - set(by_num))
        renamed = {n: (by_num[n], found[n]) for n in set(by_num) & set(found)
                   if by_num[n] != found[n]}
        problems = []
        if only_here:
            problems.append(f"in the contract, not in the checklist: {only_here}")
        if only_there:
            problems.append(f"in the checklist, not in the contract: {only_there}")
        if renamed:
            problems.append(f"the names diverged: {renamed}")
        # An item marked [A] and declared implemented must have a rule in the
        # validator; an item marked [M] must have a role that reports on it. Otherwise the
        # level tag takes the item out from under anybody's responsibility: the status is
        # honest, there is no code, there is no role, and there is nobody to notice.
        validator = Path(__file__).resolve().parent.parent / "tools" / "validate_samples.py"
        coded = set()
        if validator.exists():
            src = validator.read_text(encoding="utf-8")
            passports = re.findall(r"# (S-\d+) \u00b7 checklist ([\d.]+) \u2014", src)
            coded = {num for _, num in passports}
            # The other side of 9.4: a rule that referred to a non-existent item
            # looks documented but leads nowhere — and that can only be noticed by a
            # cross-check, because the data sheet reads as prose.
            stray = sorted({f"{rule}->{num}" for rule, num in passports
                            if num not in found})
            if stray:
                problems.append(f"rules refer to items that do not exist: {stray}")
        assigned = {ITEM_NUMBER[i] for items in ROLE_ITEMS.values() for i in items}
        assigned |= {ITEM_NUMBER[i] for i in COORDINATOR_ITEMS}
        # Group 9 is process hygiene (the numbers in the documentation, the
        # idempotence of the tools, this very cross-check). Its `[A]` means "done by
        # code", but not by the validator's code: the S-NN rules check a sample, not the
        # repository.
        for num in sorted(level, key=lambda n: [int(x) for x in n.split(".")]):
            if num.startswith("9."):
                continue
            if level[num] == "A" and done.get(num) and num not in coded:
                problems.append(f"{num} is marked [A] and \u00abImplemented\u00bb, but there is no S-NN "
                                f"rule for it in the validator")
            if level[num] == "M" and num not in assigned:
                problems.append(f"{num} is marked [M] but belongs to no role "
                                f"and is not derived by the coordinator")
        if problems:
            raise SystemExit("the checklist and the contract have diverged:\n  " + "\n  ".join(problems))
        n_a = sum(1 for v in level.values() if v == "A")
        print(f"checklist cross-checked: {len(found)} items ({n_a} automatic), "
              f"the names agree, every one has an owner")
    roles = sorted(ROLE_ITEMS)
    for i, a in enumerate(roles):
        for b in roles[i + 1:]:
            overlap = ROLE_ITEMS[a] & ROLE_ITEMS[b]
            if overlap:
                raise SystemExit(f"item assigned to both {a.value} and {b.value}: "
                                 f"{[i.value for i in overlap]}")
    print(f"review contract {SCHEMA_VERSION}, checklist {CHECKLIST_VERSION}")
    print(f"items: {len(Item)}, groups: {len(Group)}")
    for role, items in ROLE_ITEMS.items():
        nums = sorted(ITEM_NUMBER[i] for i in items)
        print(f"  {role.value:10s} {len(items):2d} items: {', '.join(nums)}")

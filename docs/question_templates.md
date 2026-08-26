# Question templates: anti-examples

The catalogue of templates is in [plans/general.md](plans/general.md), section 2.1. Here
each template gets two **anti-examples**: a question that looks like that template but is
broken. The plan (Phase 1) considers them more important than examples, and here is why:
the review cycle costs more than generation. A proposer who has written a broken question
spends three rounds of edits and the time of two reviewers; a proposer who learns the shape
of the breakage in advance does not write it at all.

Every anti-example is tagged with the slug of the checklist item that catches it — so that it
is visible that this is a known class of error rather than a matter of taste.

The material for the examples is the video `l6DKRf-fAAM` (entropy and compression), the same
one the pilot was made on.

---

## 1. Natural-error alert

Report a mistaken or incomplete piece of reasoning **at the moment it is presented**, earlier
than the author takes it apart himself.

**✗ "Tell me when the author points out the mistake in the naive code."**
The trigger is placed where the author names the mistake, not where it is presented. The model
notices nothing — it waits for a line and repeats after it.
Caught by `author-says-answer-in-window` (2.5).

**✗ "As soon as you see the naive code 00/01/10/11, say that it is not optimal."**
The answer does not require the video: "a fixed-length code is not optimal when the
probabilities are unequal" is a textbook fact. A model that understood nothing in the video
will score a point.
Caught by `solvable-without-video` (4.2) and `question-anchored-to-screen` (4.8).

---

## 2. Premature-answer trap

An early plausible but incomplete answer, with the full one later; the early one is penalised
by a distractor.

**✗ "Name Shannon's estimate for English" with a distractor on the first mention of the number
and the trigger on the second.**
If the same number is spoken both times, there is nothing to tell the windows apart: a model
that answered early answered correctly and was penalised for something it was not warned about.
Caught by `discriminator-in-question` (5.3) and `distractor-not-correct-answer` (6.2).

**✗ A distractor `[t_end, t_end + 40]`, right behind the window, with the reason "further on the
author tells it himself".**
A streaming model spends seconds on generation: having started to answer on time, it will land
in the decoy. A caveat in the question ("be quicker than the author") does **not** cure this —
the warning does not change what is measured, and what is measured is generation speed. The only
cure is headroom: between `t_end` and the moment where the author gives the answer there must
lie noticeably more time than generation takes.
Caught by `author-says-answer-in-window` (2.5); the validator warns about a decoy starting
closer than ten seconds to `t_end`.

---

## 3. Prediction-ahead

The problem has been posed — name the method of solution before the author applies it.

**✗ "Predict what the next chapter will be about."**
There is no checkable answer: a dozen formulations will do, and the rubric turns into the
judge's taste. A question is obliged to have an answer of which one can say "right" or "wrong".
Caught by `reference-answer-verified` (8.4) and `rubric-within-question` (5.2).

**✗ "When the author poses the problem of the average number of bits, say that he will apply
Shannon's formula."**
The answer follows from the title of the video and general knowledge of the subject, not from
what was seen.
Caught by `solvable-without-video` (4.2).

---

## 4. Counterfactual on-appearance

An object has appeared — compute for yourself what would happen under changed conditions.

**✗ "When the table of codes appears, compute the average length if the code words are
swapped" — with a rubric requiring the result to be compared against the naive 2 bits.**
The question asks for a number, the rubric demands a comparison on top, which was not asked
for. A model that answered the question asked loses a point.
Caught by `rubric-within-question` (5.2). *This is a live defect of the pilot, not an invention.*

**✗ "Compute what the average number of bits would be under uniform probabilities."**
It is computed from a single formula off the top of one's head, the video is not needed at all —
counterfactuality does not save the question if the input data are common knowledge.
Caught by `solvable-without-video` (4.2).

---

## 5. Step-dependency

Report when a previously obtained result is **applied**.

**✗ A required trigger with `depends_on` on an optional one whose rubric says "silence is also
correct".**
A model that lawfully kept silent in the first window automatically loses the second: the chain
in the denominator of the metric breaks over behaviour the annotation declared correct.
Caught by `depends-on-is-dependency` (7.4). *Also a live defect of the pilot.*

**✗ "Report when the author mentions the robot's code again."**
A mention is not an application. There turn out to be twice as many firings as windows, and half
the correct answers are counted as false alarms.
Caught by `trigger-matches-criterion` (3.2) and `no-missed-trigger` (3.1).

---

## 6. Symbol-binding / notation tracking

Report when a symbol has been redefined or has changed meaning.

**✗ "Report every time the letter p appears on the screen."**
This is not tracking meaning but recognising a glyph: it is solved with a single frame and
requires neither memory nor understanding.
Caught by `single-frame-enough` (4.6) and `reasoning-level-not-inflated` (7.3).

**✗ "How many different values did the variable H take by the end of the video?"**
A tally: the answer is given once, in full, and a single omission breaks all of it. There is no
proactivity here — there is bookkeeping.
Caught by the ban on tallies in [prompts/proposer.md](prompts/proposer.md).

---

## 7. Cross-modal conflict

A moment where speech and picture diverge.

**✗ "Say when the author misspeaks."**
The criterion is not operational: anything can be counted as a slip, and the set of triggers
cannot be checked for completeness — the reviewer will not be able to say whether a firing was
missed or was never there.
Caught by `no-missed-trigger` (3.1) and `trigger-matches-criterion` (3.2).

**✗ A trigger with `trigger_modality: ["sound"]` on "the characteristic error sound".**
There is nothing to check it with: there is no sound probe, and `probe_text` reads the text of
the speech.
Caught by `sound-only-trigger` (1.10).

---

## 8. Injected-error alert

The error is injected by re-rendering a manim scene. Phase 6.

**✗ An injected error that is not mentioned in `provenance`.**
The sample becomes uncheckable: the reviewer compares the annotation against the video, sees a
mismatch with the original material and declares an annotation error what is in fact its intent.
Caught by `reference-matches-description` (8.2).

**✗ An injected error on a video that lies entirely in pre-training, with no control.**
The model may know the correct version of the scene and "fix" it from memory — and we will count
that as detecting the error. What is needed is a measurement, not an assumption: a control twin
on the unmodified scene.
Caught by `video-recognized` (4.3).

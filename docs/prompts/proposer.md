# Prompt: the proposer agent

The prompt is handed over whole, with two values substituted in: `<VIDEO_ID>` and
`<INTERVAL>` (a stretch of the video when the work is split by chapters; otherwise the whole
video).

---

Before you start, read `docs/prompts/definitions.md`, next to this prompt. It defines the
terms this prompt uses, and its definitions are binding.

## The role

You are writing questions for a benchmark of **proactive** understanding of mathematical
and scientific lectures. The model under test watches the video in real time and must
decide for itself **when** the stream gives enough to answer. Your work is to invent the
questions and to state exactly the moments at which an answer will count as correct.

Most questions are asked before the video shows what the answer needs, and these are the ones
this benchmark is for. When a question is good scientifically but does not make a good `pre`
— nothing ahead brings what it needs — keep it as a question about what is on the screen when
it is asked (`at`) or about what has already gone by (`post`); its axis follows from where
the evidence lies (`temporal_rel` in `definitions.md`).

Every question has a scientific target: the participant reads a quantity or a relation,
compares states, computes, derives or checks a claim. A joke, a biographical quotation, the
look of a caption, or the wording of a caption, of a title or of a challenge to the viewer is
not a target, however exactly it can be timed.

You are working on the video `<VIDEO_ID>`, interval `<INTERVAL>`. About ten questions are
expected from a whole video, proportionally fewer from an interval. That is an average over
videos, not a target for this one: if the material gives more good questions, write them
all; if it gives fewer, hand in fewer — other videos make up the difference — and zero is
better than one invented. But do not stop at the first few. When you have gone through the
interval, go once more through the episodes that gave no candidate — a derivation, a
computed table, a comparison of two cases, a change of representation — and for each either
find a candidate or say in your report, in one line, why there is none.

Across the set, aim at roughly one `L1` question in five, two in five `L2` and two in five
`L3`. Reading questions are the easiest to find, and without this aim a set ends up mostly
`L1`. The aim directs where you search, not how you label: the level is the work left to
the participant (`definitions.md`), and a label raised to reach the proportion makes the
sample wrong. A set without a single `L3` candidate calls for the second pass, not for
relabelling; if the material still yields mostly `L1`, hand in mostly `L1`. Nor is the aim
reached by adding work to a reading question: an item that exists only to leave something to
compute — recovering in another form what the screen already shows, say — is not part of the
question's target. Do not add such an item; the question stays `L1`. There are no shares to meet per act or
template.

## Materials and the order of work

- `data/bundles/<VIDEO_ID>/transcript.md` — the transcript with timecodes;
- `data/bundles/<VIDEO_ID>/screen_text.md` — the text recognised on the screen, each line
  once, at the second it first appears;
- `data/bundles/<VIDEO_ID>/description.md` — a model's description of the screen in windows
  of a few seconds (`description.jsonl` is the same, structured);
- `data/bundles/<VIDEO_ID>/formulas.md` — the formulas extracted from the source code of the
  scenes;
- `data/bundles/<VIDEO_ID>/bundle.json` — the transcript, the chapters and the list of
  frames, structured;
- `data/bundles/<VIDEO_ID>/frames/` — frames captured in advance;
- `data/videos/<VIDEO_ID>/<VIDEO_ID>.mp4` — the source video, for a frame that is not in the
  bundle:

```bash
ffmpeg -v error -ss <t> -i data/videos/<VIDEO_ID>/<VIDEO_ID>.mp4 \
       -frames:v 1 -q:v 4 <out>.jpg -y
```

**Read the transcript in full; read the screen through its text description; open the few
frames that matter, and others only when the description fails.**

- `transcript.md` — read it whole for your interval and sketch the candidates from it;
- `screen_text.md` — read it whole: it shows when a formula, a number or a label came up;
- `description.md` is long: read the stretch around each candidate, from half a minute
  before the window to ten seconds after it, not the whole file.

The description is written by a model from the frames of each window. It may be a second
or two off about *when*; that does not matter, the review tolerates it. It also confuses
similar digits, misses what is shown in passing and sometimes completes what is not there
yet. **Three frames per window are worth opening.** The frame at `t_start`: the state the
question relies on is complete and readable on it. The two frames of the `evidence_span`
test (see "How to set the times"). Cite the frames you opened in `provenance.evidence`. Open
any other frame only where the description is inaccurate, incomplete or silent about what
you need: a value it does not give, two windows of the description that contradict each
other. Do not pull frames densely and do not chase the exact second.

**Before you write anything, read [docs/question_templates.md](../question_templates.md) in
full:** three worked examples of how a question is built, then seven ways to build a
question, each with a working example and the broken questions that look like it. Start from
them, but the list is not closed.

The format of a sample and the meaning of every field are in sections 1–7 of
[data/annotations/README.md](../../data/annotations/README.md). Two complete samples,
invented and in the form you hand them in, are in
[docs/sample_examples.jsonl](../sample_examples.jsonl): read them before your first sample.

## What makes a good question

A good question meets three requirements, and none follows from another: it has a
**scientific target**; its answer **needs what this video gives**; and it is **unanswerable
before its window and answerable inside it**. Decide the first two before you spend time on
windows: name the operation the participant performs and the content of the video it needs.

Every sample is labelled along three axes, all defined in `definitions.md`: `act`,
`temporal_rel` and `reasoning_level`. Three things about them are easy to get wrong:

- **`act` matches the video.** A `predict` only where the author later says or shows the
  answer. Where he never does, going further with the premises unchanged is an `extend`, and
  changing a premise is a `counterfact`. An `alert` states its condition as a condition
  ("if…"), never as a fact about this video, and does not say where the defect is.
  `predict`, `counterfact` and `extend` are never `L1`.
- **`temporal_rel` is derived, not chosen:** from the earliest start and the latest end of
  `evidence_span` over all required windows, not from the first and the last window of the
  list (`definitions.md`). The validator recomputes it and rejects a mismatch.
- **`reasoning_level` is the cheapest route,** not the one you designed the question around.

**A `pre` question waits for an event that brings something the answer needs:** a value, a
relation or a transition (a substantive when-clause, `definitions.md`). Do not write empty
when-clauses. If the answer was available before the event, the review will open the window
where the answer first becomes possible, and the axis will be derived from it: `at` or
`post` if the answer was available by `question_time`, `pre` if it still comes later.

### What to avoid

- **Questions whose answer does not need this video.** Such a question is not built; see
  "The answer must need this video" below.
- **Counting.** "How many times did the object appear", "name all the terms mentioned" —
  that is bookkeeping over the whole video, not reasoning: the answer is a number or a list,
  is given once and in full, and a single omission breaks all of it.

  Do not confuse this with a question that promises to react to **every** matching event
  ("every time the author changes a parameter of the model, give its new value and what it
  changes"). There the participant counts nothing: it answers at each event, on the merits,
  and each window is scored on its own. Such questions are good, but they need careful
  annotation (see the end of "How to set the times"). Accumulated state ("name the forces
  acting on the block so far and say which one the new arrow stands for") is not counting
  either, as long as the answer has content rather than an enumeration alone.
- **Multiple-choice questions.** The answer is open-ended and the rubric scores it.
- **A check whose outcome is fixed in advance.** A `verify` question checks a claim that
  could have come out false for other content of the video. A check that passes for any
  input — an identity, a definition, a property every such object has — verifies nothing:
  the only work left is to read the inputs.

### The answer must need this video

The participant is expected to know the subject: the laws, the standard formulas, the
textbook and historical facts. A question fails when its own text together with that
knowledge already fixes the whole substantive answer. The video then supplies only the
moment, and a question that measures only the moment is a waiting-only task; such tasks are
not built (`definitions.md`).

Knowing a method is not knowing the answer. The formula for a time constant does not tell
which resistance and capacitance are on the screen; a conservation law does not tell the
initial conditions of this demonstration. A question that applies a known law to a value, a
configuration, a condition, a relation or an assumption that only this video gives is a
good question. So is an explanation "why", when the reason lies in something only this
configuration has, so that the general textbook reason alone would not meet the rubric.

**The check**, on the draft question, before you annotate its windows. Keep the question
whole, with its references to the video: they say which object the question is about. Write
down the answer and mark where each part of it comes from:

- the text of the question, including its when-clause and its descriptions: "when the 2 kΩ
  resistor and the 100 µF capacitor appear, give the time constant" hands over both values;
- the subject — a law, a standard formula, a standard explanation or derivation, a textbook
  or historical fact, even if this video states it;
- this video only — its numbers, its example, its configuration, the conditions and
  assumptions it sets, and whatever is computed or concluded from them.

When you are not sure about a part, ask whether someone who knows the subject and has read
the question, but has never seen this video, could give it: if so, it is not of the third
kind. Drop the parts of the third kind and compare what is left with what the rubric will
ask for, item by item: an item that asks for a concrete result is not met by the general
method alone. If every substantive item is met, the question is broken. An unknown moment
("wait until the author says…") does not save it, and neither does a rubric item about the
look of the screen — a colour, the choice of symbols, the layout: such an item is not
substantive. This is a check of your wording, not a measurement: `blind_solved` is set
later, by other roles.

**The repair.** Make the substantive answer depend on something only this video gives — a
value, a configuration, a condition, a relation or an assumption — that the participant
reads there, compares with an earlier state, computes with, or reasons further from. The law
or the method may be known; what it is applied to must come from this video. The level is
whatever `reasoning_level` in `definitions.md` gives for the work that remains. Do not repair
a question by asking for a detail that could be different without changing the claim — a
colour, the choice of symbols, the layout — and do not add a rubric item that rejects
answers which do not name it: an answer that is already known does not start to depend on
the video because the rubric also demands such a detail, and such items are not counted
when `blind_solved` is decided. If the material gives nothing the answer could depend on,
drop the question.

**The test of the repair.** With the question left as it is: if the author had taken other
numbers, another example or another configuration, could the correct answer come out
different? If it could, the question rests on the video. If nothing would differ, or only
details that leave the claim unchanged, it rests on the textbook.

An invented pair, from a lecture on charging a capacitor:

- Broken: "When the author says what fraction of the supply voltage the capacitor reaches
  after one time constant, name the fraction." About 63 % is in every textbook; the video
  supplies the moment.
- Working: "When the resistance and the capacitance of the second circuit are both on the
  screen, give its time constant and say whether it is shorter than the first circuit's."
  The formula is known; the two values, and the first circuit's time constant, are not.

## How to search

**Work one question at a time:** draft it, run the self-check on it, fix it, and only then
start the next one. A batch of drafts checked at the end is checked worse, and a question
dropped by the checks should not have cost you the annotation of its windows.

**Look for work the author leaves undone.** For each episode with scientific content — a
derivation, a computed table, a comparison, an algorithm — try in turn: a changed input,
parameter or law (`counterfact`); the next terms, the same method on a new case, the
exercise the author leaves open (`extend`); a further consequence of what was shown; a check
of a step or of an assumption (`verify`); a change of representation — from a formula to
its graph, from a diagram to the equation; the effect of a structural change — what breaks
if a part is removed or reordered. Solve the candidate and note what is left to the
participant after everything the stream gives. A prediction of the author's next step is
rarely the way to an `L3`: the author usually shows the steps, and what remains is reading.

**Solve the candidate in full before you annotate it.** Work through the reference answer
step by step — numbers, signs, units, conventions, domains, every intermediate equality —
not only the final result. A reference with a wrong intermediate step is a wrong reference
even when its last line is right; the review reads it as a derivation. Check every rubric
item the same way: each is a true statement about the answer.

**Try to keep the question short.** Ask for the operation and name its object. Add a
condition on time only where it removes a real ambiguity — which of two similar objects,
which of two showings — and prefer a mathematical property of the object to its colour or
position. A chain of conditions is not precision: each link is one more thing the
participant can be punished for, and none of them is the task.

Check that a new candidate does not repeat the ones you already have for this video: the
same object is fine, the same work is not.

## How to set the times

`question_time` is the moment the question is issued: **the latest moment at which the
question still makes sense, and no later than the window opens** — earlier than the window
for a question that waits for its evidence; an `at` or `post` question opens its window at
`question_time`. Zero is used only when the question is comprehensible from the start of the
video. Three constraints:

- the question can be understood at that moment: every term, name and formula it uses is
  common vocabulary, has been introduced by the video, or is explained by the question itself
  (the self-check "The question can be understood at `question_time`");
- the tempting stretch — the early plausible-but-wrong value the question is designed
  around, if it has one — is still ahead: a question issued after it tests nothing;
- if all the information for the answer has already gone by, the question is `post`, and it
  is annotated as `post`.

`[t_start, t_end)` is the answer window. `t_start` is **the first moment the answer is
possible by the route the sample's level describes**. An earlier stretch where the answer is
possible only by a harder route gets an optional window (`definitions.md`, "Optional window":
the angle is shown first and its sine later; the required window of an `L1` reading starts
with the sine). If an `L2` window fits between the earlier showing and the later one — at
least five seconds long and closing ten seconds before the later showing — build the `L2`
sample instead. Look for `t_start` in the picture rather than in the speech: the author often
shows a table or the values tens of seconds before speaking them, and often re-animates them
as he speaks, so the frames around his line can look less complete than the first showing.
`t_end` is the moment after which it is too late to answer: the object has left the screen. A
window is at least five seconds long.

**The author's answer and the window.** On a question of level `L2` or `L3`, every window,
required or optional, leaves at least one rubric item to the participant and closes at least
ten seconds before the author says or shows a rubric item the window has not already given,
or something such an item follows from without any work. No window of such a question opens
after the author has said or shown the answer it asks for: an answer there repeats him. On
`predict`, no window, required or optional, contains the author's reveal of the answer or of
any rubric item of it, or ends less than ten seconds before it. A streaming model spends
several seconds on its answer: with `t_end` right against the author's line it starts in time
and finishes with that line in its context — formally inside the window, in fact repeating
the author. What the author gives in those ten seconds does not lower the level; it means the
window is wrong. Close the window earlier, if the shortened window still contains what the
answer is worked out from and stays at least five seconds long, or change the question so
that the author's line no longer gives the item. An optional window that allows neither is
removed. If the required window allows neither, an `L2`/`L3` question or a `predict` cannot
be built on this place.

**An `L1` question reads its answer from the stream inside its window;** its required window
opens where the answer can first be read. The author's line or the label that appears is
then its evidence, not a leak. The slack is needed on the other side: the window runs at
least five seconds past the end of that line, or past the moment the label is complete —
the time a model needs to produce the answer. A fact that stays on the screen keeps the
window open while it is there.

**When a boundary is uncertain within two seconds,** set the window wider rather than
narrower: `t_start` at the early edge, with `evidence_span[0]` no later than it (the
validator rejects a window that opens before its evidence), `t_end` at the late one, as long
as the ten-second rule still holds.

`t_ideal` is a service field: set it to `t_start + 1`. Latency is measured from `t_start`.

`evidence_span` is where the **last** piece of evidence the answer needs lies. Do not
confuse it with the confirmation: what establishes that your reference answer is correct
goes into `provenance.evidence` and may lie after the window (for `predict` the author tells
the answer only after the participant was to predict it) or outside the video altogether
(for `counterfact` the author never gives the answer). The field is required. Fill it in on
the merits rather than as a copy of the window: `temporal_rel` is derived from it.

For a picture the span runs from the appearance to the end of its availability inside the
window: the graph stays on the screen, and as long as it is there
the evidence is available. If a visual piece of evidence is treated as instantaneous, a
question asked five seconds after the graph appears comes out as `post`, "answer from
memory", though the graph is still in front of the participant.

The commonest mistakes in this field:

- a span **copied from the window** without checking: `[t_start, t_end]` is right only
  when the last fact appears at `t_start` and stays on the screen to `t_end`; a span
  **ending at the window's own `t_start`** while the fact is still on the screen is the
  same mistake;
- a span **copied from another window** of the same sample: each window has its own last
  fact;
- a span anchored on the frame you used to **check** the answer (a summary line, the
  author's own evaluation) rather than on the frame where the last fact the answer needs
  appears;
- a span running **past a scene cut**, or into the next window's evidence, because it was
  written as "until the window ends" without checking that the fact is still on the screen
  there.

The test, for a fact shown on the screen: on the frame at `evidence_span[1]` the last fact
the answer needs is legible, and on the frame one second before `evidence_span[0]` it is not
there yet. For a fact that is spoken no frame is needed: the span is the transcript line
that says it, from the start of the line to its end.

There is **no field for decoys**. An answer outside the windows counts against the
participant whether or not anybody annotated the place, so a premature-answer trap is a
property of the wording — an early plausible but *wrong* value before the correct one — and
nothing more. If you designed the question around such a place, say so in one sentence in
`provenance.trap_note`: it is a record of intent, it is not validated, scored or shown to
reviewers. Do not describe the run-up to the window ("not yet complete", "still being
assembled") as a trap: incomplete information is not a wrong answer.

**Elements that appear one by one.** If the task is a mapping over N elements the author
draws in sequence (the parts of a figure and the terms they stand for) and the rubric splits
into one item per element, do not open the only window at "all N complete": the best
proactive behaviour is to report each element as it appears, and such an annotation counts
those answers as outside the windows. Give every element whose appearance precedes the last
one an **optional** window from its appearance to the appearance of the next element, with
the rubric item it makes answerable, and keep the required window on the completion with the
full rubric. "All complete" is legitimate only when the joint state is needed for the
answer — a comparison between the elements. On an `L2`/`L3` sample each such window also
closes as "The author's answer and the window" says; an element left with under five
seconds gets none.

For questions with several windows ("every time…") **walk the transcript in full, line by
line**, rather than searching for keywords: the author expresses the same condition in
different words, and a missed firing turns a correct answer into an answer outside the
windows. Windows do not overlap: in such a question a window closes, at the latest, where the
next firing's window opens.

## The rubric

For each window, a `response` (the reference answer) and a `rubric` (the list of criteria by
which the judge scores an answer). The requirements:

- the model being evaluated sees **only the text of the question** — no rubric, no notes;
  everything that tells a correct answer from an incorrect one must be in the question;
- every rubric item corresponds to an explicit requirement of the question;
- the rubric does not penalise a correct detail beyond what was expected; the penalty is for
  what is incorrect;
- the rubric scores the content of the answer, not the route to it: an item of the form
  "read from the screen, not derived" cannot be checked. Accept mathematically equivalent
  expressions and paraphrases. Do not add a demand for a notation, a colour or the form of an
  entry in order to tell reading from deriving: when both give the same answer, the level is
  that of the cheaper of the two, and the rubric stays as it is. A sign, an index, a unit, or
  which coefficient goes with which quantity is content when changing it changes the claim.

## Self-check before handing in

Each check is a short test that catches a class of defects the review would otherwise send
back.

1. **The frame at `t_start` shows the state.** The state the question relies on is complete
   and readable on it. If the frame shows a transition, take the next second. What this
   catches is not the second but the tens of seconds: a window opened before the state
   exists, or a state that is on the screen for only part of the window. Then the window is
   wrong, not the wording.

2. **Recurrences of the condition.** Search the whole video, not only your
   interval, for every other moment at which the condition of the question
   holds: a recap, the same formula redrawn later. Deal with each one:

   - If the answer is already possible there, before your window, that is
     where the answer starts, not a recurrence: set `t_start` or an optional
     window as "How to set the times" says.
   - On `L2`, `L3` and `predict`, a recurrence whose answer the author has
     already said or shown needs nothing: an answer there repeats him and
     counts as an answer outside the windows.
   - In a question about every occurrence ("every time…"), any other
     recurrence is a firing: give it its own required window, or an optional
     one if a reasonable annotator might skip it.
   - Otherwise pin the question to your window's occurrence by a word that
     discriminates — a property of the object first, its order ("the first
     time", "the second time") next — and check that the word really does: a
     term on the screen for minutes is not newly added.
   - Only if no short word pins it, give the recurrence an optional window
     with the same rubric, as "The author's answer and the window" allows; on
     a `predict`, never after the last required window.

   A state that stays on the screen after your window is not a recurrence:
   the window runs while it is there, unless the ten-second rule closes it.

3. **The question names exactly one thing.** For each noun phrase in the question, list the
   candidates visible on the frame at `t_start`. "The larger coefficient" when two are equal,
   "the earlier estimate" when two stand side by side, an instruction that cannot be carried
   out as worded — a phrase with two referents, or with none, is a question with two right
   answers or with none.

4. **The question can be understood at `question_time`.** Whatever the question says the
   video has already shown or said must have happened by `question_time`. List the terms,
   names, notation and formulas the question uses. Each is common vocabulary of the subject,
   or has been introduced by the video before `question_time`, or is explained by the
   question itself in words understood at that moment: "the variable the author will
   introduce for the distance travelled, which he will call x". A name the video introduces
   later, used as if known — "when x reaches its maximum" — cannot be understood until then:
   explain it or describe the thing in general terms. Whatever the question names, it gives
   away nothing the answer needs: do not write out a formula or a value that the video
   derives or shows later, and in a `predict` do not name the concept or the method the
   participant is to foresee.

5. **What the author gives away, inside the window and after it.** For each window, read the
   transcript lines over `[t_start, t_end + 10]` and the description of the screen over the
   same stretch. Sort the rubric items and write the split into a `provenance.evidence`
   record of `type: other`:

   - **given inside the window** — between `t_start` and `t_end` the stream contains the
     item's value as it stands (it is read off, `definitions.md`). Count the question's own
     statements together with the stream: an item that follows from them without any work by
     the participant is given. An item whose line ends, or whose label is completed, after
     `t_end` is not given inside the window;
   - **left to the participant** — every other item, including those given after the window;
   - among the left items, mark those **given after the window** — in the ten seconds after
     `t_end` the author says or shows the item, or something it follows from without any
     work.

   An item given after the window never lowers the level and never makes the sample `L1`. On
   `L2`, `L3` and `predict` it means the window is wrong; on `predict` so does the author's
   reveal of an item inside the window. Fix the window as "The author's answer and the
   window" says, then sort again. If nothing is left in an optional window of an `L2` or `L3`
   sample — a recap of the result, say — close it as that paragraph says, or remove it. Do
   not add it back or pin the question against it. If a later required window scores the
   items it gives away, that window repeats the author: treat it as a required window with
   nothing left, below.

   The level is set by the work left in the required window, not by your design. On `L1`
   nothing may be left there: if an item is, either the window sits before the item can be
   read — move it to where the last item can first be read, and make the stretch before it
   an optional window if the answer can already be worked out there — or the level is
   higher. If nothing is left in the required window of an `L2` or `L3` sample, the stream
   hands over the whole answer there. Then:

   - close the window earlier, as "The author's answer and the window" says, if the
     shortened window still contains what the answer is worked out from and is still at
     least five seconds long, and sort again;
   - or rebuild the question on something the author does not say;
   - or make it an `L1` reading, if its own wording does not give the answer (a legitimate
     `L1` task, `definitions.md`): open the required window on the author's line or label,
     with its `evidence_span` there, and run it at least five seconds past the line's end or
     the label's completion; make the stretch before it an optional window if the answer can
     already be worked out there;
   - otherwise drop it.

   A `predict` is never `L1`: with nothing left it is rebuilt or dropped.

6. **Every rubric item traces to a sentence of the question.** Strike each item that demands
   a notation, a unit or a form the question never asks for: a correct value in other units
   meets the item. Check that each "do NOT count" line rejects only a *wrong* answer and not
   a correct one with an extra detail: "not 2 ms" fails a participant that names 2 ms as an
   intermediate value alongside the requested 4 ms. Then check that the item does not live
   only in the when-clause: a demand the participant is charged for must be stated as a
   demand.

7. **What work is left to the participant** (`reasoning_level` in `definitions.md`). The
   transcript and the description of the screen are enough for this check; no frame is
   needed. For each rubric item say what the stream gives inside the window: the item
   itself, the intermediate steps, or only the inputs and the method. Count what was shown or
   said earlier too: a result worked out two minutes ago is a shortcut the participant may
   take. Label the cheapest remaining work by the definition, not the route you designed.
   Inputs in the stream are not the answer: a table of given values leaves the computation
   to the participant, a table of results leaves nothing.

8. **Provenance says where each fact comes from.** A `type: frame` record is a frame you
   opened and describes what is on it. What you took from the description is a
   `type: other` record that says so. A transition frame is not evidence of either state.

9. **What the question gives away, on the final wording.** Repeat the check of the section
   "The answer must need this video" on the final text of the question and the final rubric.
   Then write into `validation.notes` one line per substantive rubric item (rubric items are
   numbered from 1, in list order, in each window separately): `item <N> needs: <what this
   item needs from this video>` — for example, for the working question of that section:
   `item 1 needs: the resistance and the capacitance shown for the second circuit`; `item 2
   needs: the same two values and the first circuit's time constant, given earlier in the
   video`. The validator rejects a draft without these lines. Judge by what the rubric
   accepts, not by what is on the screen: an item that also accepts the general form (`τ =
   RC` without the number) needs nothing from this video. If the honest line for an item is
   "nothing", that item is given away by the question or by the subject; that alone does not
   break the question. If every substantive item is like that, the question is an exam
   problem with a timer: rebuild it or drop it.

10. **What the when-event gives.** Write one line into `validation.notes`: `the when-event
    gives: item <N> — <the value, relation or transition the event brings>`, where N is the
    number of a rubric item of a required window. The validator rejects a `pre` draft without
    it. Before you write the line, search the transcript, `screen_text.md` and the
    description before the event for the same content: a value shown earlier is not made new
    by being shown again, by a caption added beside it or by another object next to it. If
    the event gives no item, it only marks a moment, and a participant who knows the answer
    is right to speak as soon as it can: the event gives the question no right to `pre`.
    Rewrite it for the moment the answer first becomes possible — its axis then follows from
    where that evidence lies — or rebuild it on an event that brings something the answer
    needs. "When the curve turns red, explain why the voltage never exceeds the supply" is
    the pattern: the colour brings nothing, and the explanation is available the moment the
    question is asked. A `pre` question does not describe as already shown or said what it
    waits for.

11. **The act matches the video.** For a `predict`, find in the transcript, in
    `screen_text.md` or in `description.md` the moment after the last window where the
    author says or shows the answer, and cite it in `provenance.evidence` as the
    confirmation of the reference answer. If the author never says or shows it, the
    question is not a `predict`: going further with the premises unchanged is an `extend`,
    changing a premise is a `counterfact`; then check the level again (check 7). If he says
    or shows it inside a window, check 5 applies. If he does it less than ten seconds after
    a window, or between two windows, that window is wrong: fix it as "The author's answer
    and the window" says. If he does it before the first window, the answer is already in
    the stream and the question is not a `predict`. For an `alert`, check that the question
    says neither that the condition holds in this video nor where.

Do not write interpretations of metrics or review rules into `validation.notes` or
`provenance`; they are read by reviewers.

None of this replaces the review; it removes the round that would have been spent telling
you what a frame shows.

## What to return

Write **into your own file** `data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl` rather
than into the shared `<VIDEO_ID>.jsonl`: proposers working on other intervals run in
parallel with you, and you would overwrite the shared file. The partials are merged by the
coordinator, who also assigns the end-to-end `id`s of the form `3b1b__<VIDEO_ID>__q<NN>`;
inside your own file number them however you like, as long as the numbers do not repeat.

Do not make control twins (the same question with a different `question_time`): the
coordinator creates them at merge time and fills in their `twin_of` field.

The `jsonl` lines follow the schema `schema/sample.schema.json`, `validation.status: draft`,
`audio_dependency: null` (it is the result of a measurement, not an opinion; your own
opinion goes into `audio_dependency_claim`).

`template` is a free string: the name of the template in `question_templates.md` you started
from, in snake_case (`premature_answer_trap`), or a short name of your own when none fits.

Before handing in, run:

```bash
/home/user/conda/bin/python3 tools/validate_samples.py \
    data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl
```

and fix everything it complains about. The validator checks the arithmetic and the format
of the notes lines; its silence does not mean the annotation is correct, but its complaints
always mean it is not.

In `provenance.evidence` state where each reference answer came from. The records are
structural, one per source:

```json
{"type": "frame",  "t": 946.0, "explanation": "what is visible in the frame"}
{"type": "speech", "t_start": 1822.0, "t_end": 1829.4, "explanation": "\"quotation\""}
{"type": "other",  "explanation": "source <path in the scene code>: ..."}
```

Both boundaries of a speech reference coincide exactly with the boundaries of transcript
lines: the start with the start of some line, the end with the end of some line. If the
fragment you need ends in the middle of a sentence, widen the interval **outwards**, to the
end of that sentence: catching one extra sentence is harmless, cutting off a needed one is
not. The description must match what is in the frame at the stated moment rather than what
you remember about what is going on: this annotation will be re-checked through these
references.

When you finish, reply with a short report: the file you wrote, the number of samples, and
for each episode of the second pass that gave no candidate, one line saying why.

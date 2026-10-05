# Question templates: what works and what breaks

Three worked examples of how a question is built, then seven ways to build a question from
a lecture, each with one working example and the broken ones that look like it. A broken question costs a round of review; knowing the
shape of the breakage in advance costs nothing. The list is a search aid, not a quota
and not a closed set.

**All examples are invented.** The three worked examples use three different subjects. The
examples of the seven templates use one lecture that is not in this benchmark, on charging a
capacitor through a resistor. In it the author draws a circuit with a 9 V
supply, one resistor and a capacitor and gives its time constant; estimates that the
capacitor is full after one time constant and corrects himself two minutes later; builds a
table of the capacitor voltage after one to five time constants, using that time constant;
adds a second resistor in series and gives the new time constant; then introduces a second
circuit with other values and works out when it reaches half the supply voltage. Along the
way the letter V passes from the supply voltage to the capacitor voltage, and once the
author says a value that differs from the one on the screen. Do not reuse these lectures,
their numbers or their wording in your questions.

**The axis and the level are not part of a template.** Most of these questions are
naturally `pre`: they wait for an event that brings something the answer needs, and such
questions are what this benchmark is for. But `temporal_rel` is derived from where the
evidence lies, and the level from the work that is left (`definitions.md`). If nothing
the answer needs lies ahead, the question is `at` or `post`; attaching an event to it
does not make it `pre`.

---

## How a question is built: three examples

Each example settles the three things to settle for every candidate: the moment of the
question, what the awaited event brings, and the cheapest route to the answer.

*A — `pre`, `L2`, `extend`: an earlier value, a new value, a short calculation.* A lecture
on bacterial growth has given the doubling time of the first culture, 20 minutes. Question,
issued after that: "When the doubling time of the second culture is shown, say how many
times more cells the first culture has after one hour, if both start from one cell."
Answer: the second doubles every 30 minutes; after an hour the first has 8 cells and the
second 4 — twice as many; the lecture itself does not make this comparison. The answer
becomes possible when "30 minutes" appears. Cheapest route: recall 20, read 30, two powers
of two.

*B — `at`, `L2`, `counterfact`: a changed premise over what is on the screen.* The screen
shows an urn with 3 red and 2 blue balls and a tree for two draws without replacement.
Question: "For the urn now on the screen, suppose the first ball were put back before the
second draw. What is the probability of two reds?" Answer: (3/5)² = 9/25. Everything
needed is on the screen when the question is asked: an honest `at`; do not invent a future
event to make it a `pre`. Cheapest route: read the composition, one multiplication.

*C — `pre`, `L3`, `extend`: the shown method on a new case.* A lecture on loans has built,
row by row, the table of monthly balances for a loan of 1000 at 1 % a month with a payment
of 100, and announces a second borrower who pays more. Question, issued then: "When the
second borrower's monthly payment is shown, give that loan's balance, to the nearest whole
unit, after each of the first six months; the amount and the rate are the same." Answer,
for a payment of 150: 860, 719, 576, 432, 286, 139. The payment comes from the video; the video
itself gives only the month in which the loan is paid off. Cheapest route: six steps of the
recurrence shown for the first loan — a substantial computation the video does not do.

---

## 1. Natural-error alert

The author presents a mistaken or incomplete line of reasoning and corrects it later. The
participant reports the mistake when it is presented, before the correction.

**✓ "If a step of the author's estimate of the charging time does not follow from the
values on the screen, say which step it is and what voltage, in volts, the capacitor has
really reached by that time."**
The condition is stated as a condition: whether there is a mistake is for the participant
to decide. Which step it is and the voltage in volts both need this video: its estimate
and its supply voltage. The window opens where the estimate is presented and closes at least ten seconds
before the author corrects it.

**✗ "Tell me when the author points out the mistake in the first estimate of the charging
time."**
It asks only for a moment: the whole answer is "now". That is a waiting-only task. It also
says, as a fact, that the estimate contains a mistake. Worded as a condition and with
content — "If the author takes back a step of his estimate, say which step and what he puts
in its place" — it becomes a legitimate question, but a different one: the participant
repeats the author's correction, an `L1` reading, and notices nothing itself.

**✗ "The first estimate on the screen treats the capacitor as full after one time
constant. As soon as you see it, say that it is wrong."**
The question itself says that there is a mistake and what it is, so nothing is left to
decide. And the correction — about 63 %, not full — is a textbook fact: the answer does
not need this video.

---

## 2. Premature-answer trap

The video shows an early value that is plausible but wrong for the question, and the
correct one later. An answer given on the early value falls outside the window, and the
metric penalises an answer outside the windows.

**✓ "Once a second resistor is connected in series with the first, give the time constant
of the circuit."**
The time constant shown earlier, for one resistor, is the trap; "a second resistor" is what
tells the two apart, and the second resistance is what the event brings. The question
describes the second resistor in words, so it can be understood when it is issued, before
the first time constant appears. Note
the intent in `provenance.trap_note`.

**✗ "Name the time constant of the circuit" — with the window on the second showing of the
value, while the first showing, forty seconds earlier, gives the same value.**
The early answer is correct and is penalised as an answer outside the windows. A trap has to be a
*different* value, and the question has to say what tells the two apart.

**✗ "…and answer before the author does" — added to a question whose window closes a
second before the author names the answer.**
A caveat does not move a window. A streaming model spends seconds on its answer, so the
window itself has to close well before the author's line.

---

## 3. Prediction-ahead

A problem has been posed; the participant says what the author will obtain next, before he
does. The author gives the answer later, at least ten seconds after the window. If he
never gives it, the question is not a prediction.

**✓ "When the resistance and the capacitance of the second circuit are both on the screen,
say what time the author will find for it to reach half the supply voltage."**
The event brings the two values the answer needs; the author works the time out himself
later, which is what the reference answer is checked against.

**✗ "Predict what the next chapter will be about."**
There is no checkable answer: a dozen formulations fit, and the rubric becomes the judge's
taste.

**✗ "When the author asks how the capacitor voltage grows with time, name the function he
will write."**
An exponential approach to the supply voltage is in every textbook: the answer does not
need this video.

**✗ "Predict the capacitor voltage after seven time constants" — in a lecture whose table
stops at five.**
Nobody in the video gives this answer, so it is not a `predict`. The question may stand,
but as an `extend` — going further with the premises unchanged: label it so and do not word
it as a prediction.

---

## 4. Counterfactual on-appearance

An object has appeared; the participant changes a premise — an input, a parameter, a law —
and works out the result. The video does not give the answer.

**✓ "For the table now on the screen: if the resistance were doubled, at what time, in
seconds, would the capacitor reach the voltage of the third row?"**
Nothing is waited for: the table is on the screen when the question is asked, and the axis
comes out as `at`. The answer needs the time constant of this circuit and what the third
row stands for.

**✗ "When the table of voltages appears, give the voltage after two time constants if the
supply were 12 V" — with a rubric that also requires a comparison with the value in the
table.**
The question asks for a number and the rubric demands a comparison nobody asked for: a
participant that answers the question loses a point. This one fails a second time: with
the supply given in the question, the answer needs nothing from the video.

**✗ "Say what happens to the time constant if the resistance is doubled."**
It doubles — from the formula alone. A changed premise does not save a question whose
inputs are common knowledge.

---

## 5. Step-dependency

A result obtained earlier is applied later. The participant reports the application and
says which result is used and for what.

**✓ "Every time the author uses the time constant of the one-resistor circuit in a later
calculation, say which quantity he computes with it."**
Each firing has content of its own, and each needs the earlier result to be recognised.
Walk the transcript line by line for the firings: a missed one turns a correct answer into
an answer outside the windows.

**✗ "Report when the author mentions the time constant again."**
A mention is not an application: with the windows set on the applications, every other
mention is a correct answer outside the windows. And "report when" alone asks only for the
moment.

---

## 6. Symbol-binding

A symbol is redefined or changes meaning. The participant reports the change and says what
the symbol means now.

**✓ "Every time the letter V on the screen starts to denote a different voltage than
before, say which voltage it denotes now."**
The answer is the new meaning, taken from this video, and it needs the previous meaning to
be remembered.

**✗ "Report every time the letter τ appears on the screen."**
The whole answer is "it appeared": a waiting-only task. And it follows a glyph, not a
meaning: nothing about what the symbol stands for is asked.

**✗ "How many different values did V take by the end of the video?"**
A tally: the answer is given once, in full, and a single omission breaks all of it.

---

## 7. Cross-modal conflict

Speech and picture diverge: the author says one thing and the screen shows another.

**✓ "Every time a value the author says differs from the value on the screen for the same
quantity, give both values and say which quantity it is."**
The condition is stated as a condition, and both values come from this video. Use the
template only where the video really has such places: do not invent a divergence.

**✗ "Say when the author misspeaks."**
The criterion is not operational: anything can be called a slip, and nobody can check
whether a firing was missed. It also asks only for the moment.

**✗ A window whose only evidence is a sound — "the click of the switch".**
There is nothing to check it with: no role of the review hears the sound, and the
transcript holds only the speech.

---

## 8. Injected-error alert

Questions about an error injected by re-rendering a scene are made by a separate pipeline.
Do not write them.

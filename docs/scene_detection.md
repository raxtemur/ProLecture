# Cutting frames: scene change detection

The tool is [`tools/detect_scenes.py`](../tools/detect_scenes.py); it is switched on automatically
in the pipeline: `tools/make_bundle.py` cuts frames with it and nothing else.

## Why we needed our own

`make_bundle.py` originally cut frames with a uniform ffmpeg grid (every 15 s plus the chapter
boundaries). On 3Blue1Brown videos such a grid errs in two directions at once: on a static stretch
it produces several identical frames, while a scene that lived ten seconds between the nodes of the
grid is not shown at all.

The off-the-shelf detectors (`ffmpeg -vf select='gt(scene,…)'`, `ContentDetector` from
PySceneDetect) compare a frame with the **previous** one. Manim breaks that: its typical transition
is a smooth travel of an object across the screen over 2–4 seconds, where the difference between
neighbouring frames is always below any reasonable threshold while the total change is complete.

## The algorithm

1. We probe the video `--probe-fps` times per second (**4** by default).
2. The frame is shrunk to **192×108** and cut into a grid of **9×12 = 108 blocks**.
3. We compute the **accumulated drift** — the per-block mean absolute difference against the last
   **captured** frame rather than the previous one probed. A smooth travel accumulates drift and
   sooner or later steps over the threshold; static material accumulates nothing, and an
   oscillation "there and back" cancels itself out.
4. From the drift we subtract the block's **noise floor**: the median difference between
   neighbouring probed frames over a sliding window `--noise-window` (8 s), multiplied by
   `--noise-k` (1.5). This is needed precisely because of 3b1b: a ribbon of random bits or a
   crawling line of example text runs constantly on top of the scene. Such a block changes every
   frame and means nothing — a high floor switches it out of the vote.
5. The frame's score is the power mean of the cleaned drift over the blocks with exponent
   `--agg-power` (**2.0**). At exponent 1 this is simply the share of the area that changed, and
   then a single extra line of a formula in an empty corner drowns: it occupies one block out of
   108. An exponent >1 shifts the weight towards the few strongly changed blocks, so that "a line
   was added" and "the whole picture moved" fall into one threshold.
6. Once the score steps over `--threshold` (**0.010**), we capture the frame and it becomes the new
   reference. Between frames we keep `--min-gap` (2 s), and if the picture has not changed for
   `--max-gap` (45 s) we capture one by force. The `--max-gap` insurance **never fired once** across
   three videos (`of them by max-gap 0` in the output), that is, on this domain it is not tested
   against material. The actual minimum gap comes out larger than nominal: in the pilot it is
   **2.66 s**, because after a firing the wait for quiet is added (point 7). The probing is also a
   little sparser than declared: the next moment is counted from the time of the frame obtained, so
   at an original 30 fps it comes to ≈3.75 probes per second rather than 4.
7. We capture not at the moment of firing but once the animation has **settled**: we wait until the
   per-frame stirring falls below `SETTLE_EPS`, but no longer than `--settle-max` (2 s). Otherwise
   half-written formulas systematically get into the sample.

   A single quiet probe is **not enough** for this, and that cost a separate error. Manim writes a
   formula over several seconds and pauses in the middle of writing: the stirring dropped below the
   threshold of 0.004 mid-writing, the frame was captured — and it showed
   `P(any n-bit message) −` with no fraction, exactly the defect we hold against the ffmpeg grid.
   So the end of an animation is taken to be `--settle-quiet` (**2**) quiet probes in a row; at the
   same place the detector now captures **902.4 s**, where the formula is finished.

The only dependency is OpenCV; decoding goes through `cv2.VideoCapture` with `grab()`/`retrieve()`
(a full pass over a 32-minute video takes about 20 s). PySceneDetect was not needed: its detectors
solve a different problem than ours (see above), and its video-reading wrapper is replaced by ten
lines on `cv2`.

```bash
/home/user/conda/bin/python3 -m pip install opencv-python-headless              # base conda
/home/jovyan/.mlspace/envs/rah_manim/bin/python -m pip install opencv-python-headless openai
```

Both environments will do: OpenCV and `openai` have been added to `rah_manim` (`cv2` 5.0.0,
`openai` 3.3.1) without touching anything in the manim stack — `numpy` stayed at 2.5.0, `manim`
0.20.1 imports. So the detector and the description can be launched from there too; verified by a
run over 900–930 s and a trial fragment of the description.

## The constant-rate mode (`--every`)

The second mode is needed by the description of the video track: holes are not allowed there,
because the description is per-second. The video is cut into slots of fixed length (`--every 0.5`
— two frames per second), and within a slot the **quietest frame from the middle of the slot** is
taken. Quiet for the same reason as in the main mode: a half-frame with an unfinished formula is
harmful. From the middle because otherwise neighbouring slots pick frames at their own edges, 0.1 s
apart: in the pilot that produced 306 pairs of nearly identical images, each of which costs a full
prefill (~900 visual tokens). After restricting to the middle, the minimum gap is 0.2 s and the
share of gaps ≤0.2 s fell from 13.9% to 3.7% (counted over all 3878 frames of the pilot, not over
a trial window).

The threshold, the noise floor and the wait for quiet take no part in this mode: the slot
guarantees the rate by construction.

## How the parameters were chosen

The tuning was done on **three** videos, deliberately from different eras (3b1b's animation style
has changed noticeably over nine years):

| video | date | what it is |
|---|---|---|
| `l6DKRf-fAAM` | 2026-06 | Reinventing Entropy — the pilot annotation video |
| `GlYgs6v2YfU` | 2026-07 | But what is Cross-Entropy — the second part of the same series |
| `3d6DsjIBzJ4` | 2017-05 | Taylor series — the contamination control video |

The method: on two stretches of the pilot video a dense cut was made (once a second over 887–917 s,
once every two or three seconds over 918–1011 s and 1470–1558 s), and from it a list was written
out **by eye** of the screen states an annotator is obliged to see. Then `agg-power` × `threshold`
× resolution × grid were swept, and for each pair it was counted how many states from the list got
into the sample.

The key forks that were settled by measurement rather than taste:

* **the averaging exponent.** At `power=1`, over the stretch 887–1011, the whole derivation chain
  `p = 2^-n` → `log₂(p) = −n` → `−log₂(p) = n` was lost: each line occupies one block. `power=2`
  catches it in full with the same number of frames.
* **the grid.** 6×8 against 9×12, all else equal: the 9×12 grid picks up small text edits without
  inflating the sample. There is no point raising the frame resolution above 192×108 — the gain
  comes from the granularity of the grid, not from the number of pixels.
* **one threshold per domain.** The hypothesis held: `threshold=0.010` gives 13.5 / 13.0 / 10.1
  frames per minute across the three videos. The spread is explained by the material itself — the
  2017 video really is slower (verified against a dense cut of the stretch 600–720 s: there are 18
  substantive states there, and the detector captured 18 frames). Before the 9×12 grid the spread
  was noticeably worse (14.6 / 14.0 / **9.3**).

The rule of thumb "about 2 frames per 10 seconds" = 12/min; across three videos the average is
12.2/min.

## What it came to in numbers

The pilot video `l6DKRf-fAAM` (1939 s, 32 min):

| | the ffmpeg grid | scene detection |
|---|---|---|
| frames | 136 | 437 |
| per minute | 4.2 | 13.5 |
| median interval | 15.0 s | 4.3 s |
| 90th percentile of the interval | 15.0 s | 6.4 s |
| maximum interval | 15.0 s | 18.4 s |
| size | 3.3 MB | 15 MB |

The distribution over chapters is even (11–17 frames/min), that is, the detector does not "eat" the
budget on one stretch.

The three longest gaps of the detection were checked by eye and turned out to be legitimate:

* 976.8 → 995.2 — the graph of `−log₂(p)`, with a point travelling along the curve;
* 844.3 → 861.9 — the table of codes, with one highlighted cell moving inside it;
* 99.2 → 116.8 — the motionless dial "1.0 bits/ch" with a crawling line of example text underneath
  (exactly the case the noise floor damps).

## A frame-by-frame comparison

### The stretch 887–1011 s ("Defining information")

From the dense cut, 18 mandatory states were written out. The detection captured 24 frames over
this stretch and caught **18 out of 18**.

The times below are taken **from the assembled bundle** (`data/bundles/l6DKRf-fAAM/bundle.json`,
mode `scenes`) rather than from a separate run over the stretch: a run with `--start` sets up its
own reference frame and gives different capture moments, so the table must be compared against what
actually lies in `frames/`. A tick marks the rows where that file from the bundle was opened and
looked at:

| moment | state | detection | the ffmpeg grid |
|---|---|---|---|
| 888 | a new scene: the robot, the ribbon of bits, the probability bars | 888.8 | 889 |
| 903 | `P(any n-bit message) = 1/2ⁿ` | 902.4 ✔ | — (900 — a half-formula) |
| 907 | the line `p = 2⁻ⁿ` | 906.4 ✔ | **missed** |
| 910 | the line `log₂(p) = −n` | 910.7 ✔ | **missed** |
| 912 | `−log₂(p) = n` | 916.0 ✔ | 915 |
| 918 | the same formula in a green frame | 920.0 | — |
| 923 | the pi creatures appear at the bottom | 924.3 | **missed** |
| 930 | "Random Noise is incompressible" + the lattice of bits | 926.9 | 930 |
| 936 | "Random Noise" with arrows | 931.2 ✔ | **missed** |
| 942 | the pie lattices `(1/2)ⁿ`, the first two | 942.1 | — |
| 948 | the 3rd and 4th lattices added | 946.1 ✔ | 945 |
| 957 | the transition to the axes, grey bars | 957.6 | **missed** |
| 960 | the graph of `−log₂(p)` with blue bars | 960.3 | 960 |
| 963 | `= log₂(1/p)` written in | 968.3 (merged) | **missed** |
| 969 | `= log_{1/2}(p)` written in | 968.3 | **missed** |
| 975 | back to `−log₂(p)`, a point on the curve | 976.8 | 975 |
| 996 | `Information := −log₂(p)` — the definition | 995.2 ✔ | **missed** |
| 999 | a bar plus a pie appeared on the right | 999.2 | 1005 |

The ffmpeg grid over the same stretch gave 10 frames and lost **8 states out of 18**, including the
whole derivation chain for `−log₂(p)` and the very moment `Information` is defined.

### The stretch 1470–1558 s ("Defining Entropy")

A dense cut every two seconds gives ~28 states. The detection captured 23 frames and covered them
practically in full: the 3D staircase (1470.1), the "Compression / A.I." circles (1474.4), the list
of formulas `I, H(p), H(p,q), D_KL` (1481.9), the histograms captioned Entropy / Cross-entropy / KL
(1489.9–1496.8), the fade-out (1504.3–1506.9), the scene with the boxes `S₀…S₁₅` (1512.0), the row
of pies (1515.2), the arrows and "NATURAL LANGUAGE" (1517.9), the "Average Information" bars
(1521.9), the Random Noise lattice (1526.1), `−log₂(P("INFORMATION THEORY"))` (1533.3), the
expansion into a sum of logarithms (1538.1), the compressed bit string (1545.1), the table of codes
(1551.5), the total `= 1.75 bits` (1556.8).

One intermediate state was missed (1554 — the captions `1/2·1, 1/4·2, …` above the table before the
expression appears).

**A caveat about how far this paragraph can be trusted.** The frame-by-frame comparison here was
made before the `settle-quiet` fix; afterwards the stretch was recomputed with the final
configuration, and the correspondence of the states was restored **from the timecodes, not by eye**
— unlike the stretch 887–1011, where the ticked frames were opened afresh.

The ffmpeg grid over this window gave 8 frames (1470, 1471, 1485, 1500, 1515, 1530, 1545, 1560) and
lost entirely: the "Compression / A.I." scene, the assembly of the entropy and KL formulas,
"NATURAL LANGUAGE", the derivation of `−log₂(P("INFORMATION THEORY"))` and the final table of codes
with the answer of 1.75 bits.

## What the detector does not catch

An honest caveat, not a tweaked threshold.

**Dim edits of small text in place.** In the 2017 control video, over 654–657 s a value is
substituted in four lines (`−sin(x)` → `−sin(0) = 0` and so on). The text is small, greyish dark
red, and a few glyphs change per line. The detector does not capture this edit: the interval runs
650.5 → 669.7. Lowering the threshold **does not help** — even at `threshold=0.004`, where the
frame budget nearly doubles, the moment still goes uncaught: the change lies below the noise
boundary rather than below the threshold.

A mitigating circumstance: **the screen state itself does not vanish from the sample** — frame
669.7 already shows the substituted values. What is lost is not the picture but the exact moment of
the transition. For annotation, where `evidence_span` is set by hand from the transcript anyway,
this is acceptable; but if an exact anchoring of such edits is ever needed, a different feature is
required (for example a difference over edges/contours rather than over brightness).

**Merged events.** Two changes within `--min-gap` (2 s) are glued into one frame: thus 1517.9 shows
both the row of arrows and "NATURAL LANGUAGE" at once, and 968.3 shows both alternative notations
of the logarithm. `min-gap` can be reduced, but that directly multiplies the number of frames.

**Frames in the middle of an animation.** The wait for quiet is bounded by `--settle-max` (2 s): if
an animation does not stop for longer, the frame is captured anyway and may turn out half-written.
After the introduction of `--settle-quiet` no such frames remained in the checked windows of the
pilot, but there is no guarantee — under continuous motion the ceiling will fire.

## The cost and the cleaning of the directory

There is no uniform grid in `make_bundle.py` any more: the detector is the only way of cutting. The
price is paid knowingly — 3.2 times more frames (437 against the previous 136 in the pilot) and a
dependency on OpenCV. It restricts nothing: OpenCV is installed both in base conda and in
`rah_manim`.

The capture times depend on the detector's parameters, so `make_bundle.py` removes **all** the old
frames before writing: a run with a different threshold would otherwise leave its files next to the
new ones. That is exactly what happened with `GlYgs6v2YfU` — the directory held 839 frames from two
runs while `bundle.json` listed 438: the annotator would have seen a mixture and the index half
of it.

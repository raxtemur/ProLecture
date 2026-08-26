# Frames and the description of the video track: what appeared and what was removed, 2026-08-25

Two new tools and one amputation in `make_bundle.py`. The common motive: the frames a model gets
must be chosen by content, not by a timer.

## 1. `tools/detect_scenes.py` — our own scene change detection

The off-the-shelf detectors (`ffmpeg -vf select='gt(scene,…)'`, `ContentDetector` from
PySceneDetect) compare a frame with the **previous** one. Manim breaks that: the typical transition
is a smooth travel of an object over 2–4 seconds, where neighbouring frames differ by less than any
reasonable threshold while the total change is complete.

The algorithm computes the **accumulated drift from the last captured frame**: probing 4 times a
second, the frame shrunk to 192×108 and cut into a 9×12 grid, the noise floor (the median stirring
of a block over an 8 s window) subtracted from the per-block difference, and the score being the
power mean with exponent 2. The noise floor is needed precisely because of 3b1b: a ribbon of random
bits runs constantly on top of the scene, and such a block must not vote. Exponent 2 is needed so
that a single line added to a formula does not drown among the 108 blocks.

A frame is captured not at the moment of firing but once the animation has settled — after
`--settle-quiet` (2) quiet probes in a row. One is not enough: manim writes a formula over several
seconds and pauses in the middle, and at that pause the frame came out half-written — the very
defect we hold against the uniform grid.

The second mode is `--every SEC`: slots of fixed length, with the quietest frame taken within a
slot. It leaves no holes by construction, and no half-frames either. The description of the video
track uses it.

The numbers: a single threshold of `0.010` per domain gives 13.5 / 13.0 / 10.1 frames per minute on
the videos from 2026-06, 2026-07 and 2017-05. On the control stretch 887–1011 s it catches 18
mandatory states out of 18 against the former grid's 10. The details, the frame-by-frame comparison
table and the section "what the detector does not catch" are in
[scene_detection.md](../scene_detection.md).

## 2. `tools/describe_video.py` — a dense description of the video track

A document like subtitles, only instead of utterances it holds what is happening on the screen. It
is needed so that at most steps of the annotation one can read text instead of looking through
dozens of frames.

The frames are taken from the detector in slot mode (two frames per second, each of them "quiet",
from the middle of the slot) — that is the default source. The request window is 5 seconds with a
shift of 4: a second (two frames) of overlap with the left and the right neighbour, three seconds
of its own. The edge seconds are described by both neighbouring fragments, and those descriptions
can be cross-checked against each other.

The model's answer is **strict JSON against a schema** held by the server itself (vLLM, guided
decoding): `begin`, `events` (one record per second), `screen_text` (`{t, text, location}` with the
position out of nine cells), `end`. Before this the fields were pulled out of free text with
regular expressions, and a single Latin letter in a heading was enough for a whole block to end up
in the wrong field.

**The video's subtitles are not shown to the describing model** — only the frames go into the
request. The reason lies in the pipeline: the finished description is given to the vision-only
probe instead of a dense cut of frames, and that is legitimate precisely because there is no sound
in the description. Were the model to hear the speech, the index would stop being a function of the
visual channel and the `audio_dependency` label would start measuring the wrong thing.

The run on the pilot (1939 s): 3878 frames, 485 fragments, **20 minutes** on two A100s with
`Qwen3.6-35B-A3B` (bf16, vLLM 0.27.1). The result: 1939 seconds out of 1939 covered by events, 6950
elements of on-screen text (3 without a second), 0 errors, 0 truncations, 0 degenerate answers.
With the overlap each frame goes to the server 1.29 times, which is ~4.5 million image tokens on
prefill alone.

The model was chosen as an MoE not out of economy but because of the load profile: it is almost
entirely prefill, and 3B active parameters against 27B dense ones decide more here than the
difference in the benchmarks. We do not take the FP8 versions — the A100 has no FP8 tensor cores,
and vLLM decompresses such weights into bf16 on the fly.

What can be trusted: large formulas and captions are reproduced verbatim. Small tick labels the
previous model **substituted plausible ones** for instead of reading (at 1206 s it described the
scale `0.17 … 0.23` as `0.0 … 1.0`); the new one reads the same row as `0.17, 0.18, … 0.25` — that
is, the step and the start are right, but the last tick still missed. The order of the error is
different, but checking against the frame is still mandatory. The root cause is the 360p source;
1080p is unavailable without a PO token and account cookies.

Useful flags: `--range` for a trial on a stretch, `--redo-bad` to re-request only the spoiled
fragments instead of the whole video (it checks that the cut is the same).

## 3. What was removed from `make_bundle.py`

The uniform ffmpeg grid (a frame every 15 seconds plus the chapter boundaries) has been **removed
entirely**, together with the `--frame-interval` flag and the `extract_frames` function. The frames
are now cut by the scene detector alone, and of the flags only `--no-frames` and
`--scene-threshold` remain.

The reason is not aesthetics: the grid erred in two directions at once — it duplicated static
material and lost whole scenes. In the pilot, over the window 887–1011 s, it missed 8 substantive
states out of 18, including the whole derivation chain
`p = 2⁻ⁿ → log₂(p) = −n → −log₂(p) = n` and the moment where the definition
`Information := −log₂(p)` is introduced. Keeping it as the default meant handing annotators
knowingly holey material.

The price of the amputation: 3.2 times more frames (437 against 136 on a 32-minute video) and a
dependency on OpenCV. It is installed in both environments, so the choice of interpreter is not
narrowed by this:

```bash
/home/user/conda/bin/python3 -m pip install opencv-python-headless
/home/jovyan/.mlspace/envs/rah_manim/bin/python -m pip install opencv-python-headless openai
```

Along the way, `make_bundle.py` now removes **all** the old frames before writing, not only the
frames of a different mode: the capture times depend on the detector's parameters, and a run with a
different threshold left its files next to the new ones. That is exactly what happened with
`GlYgs6v2YfU` — 839 frames from two runs in the directory against 438 in `bundle.json`.

`--no-frames` has been kept: it leaves the cut as it is and does not touch the list of frames in
`bundle.json`.

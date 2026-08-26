# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Two independent lines of work under one roof:

1. **ProLecture** — a benchmark of proactive tasks for streaming VLMs on 3Blue1Brown videos.
   This is the main line: `tools/`, `data/`, `schema/`, `docs/`, `articles/`.
2. **The manim sandbox** — animation experiments and two home-grown scene quality checks:
   `demo/`, `scripts/`.

The design intent of ProLecture is described in full in [docs/plans/general.md](docs/plans/general.md),
the annotation format in [data/annotations/README.md](data/annotations/README.md), the cutting of
frames by scene change in [docs/scene_detection.md](docs/scene_detection.md),
the run of the video-track description in [docs/video_description.md](docs/video_description.md),
the classes of annotation error and who catches them in
[docs/annotation_checklist.md](docs/annotation_checklist.md), the working order of the annotator
and reviewer agents in [docs/annotation_pipeline.md](docs/annotation_pipeline.md) together with the
draft prompts in [docs/prompts/](docs/prompts/) and the anti-examples by question template in
[docs/question_templates.md](docs/question_templates.md).
The contract the reviewer subagents report against is [schema/review.py](schema/review.py)
(pydantic, not a JSON schema: a model reads it too).
Read them before any edit to the annotation or the metrics: they record decisions that have a
non-obvious "why".

## Two environments — the main snag

`python3` in the shell resolves now to one, now to the other. **Always name the interpreter
explicitly.**

| Environment | Path | What it has | What it lacks |
|---|---|---|---|
| `rah_manim` | `/home/jovyan/.mlspace/envs/rah_manim/bin/python` | manim CE 0.20.1, manim-voiceover, yt-dlp, cv2, openai | matplotlib, pandas, jupyter, jsonschema |
| base conda | `/home/user/conda/bin/python3` | matplotlib, pandas, jsonschema, cv2, jupyter | yt-dlp, manim |

`tools/fetch_video.py` looks for an interpreter with `yt_dlp` itself (the list is in
`CANDIDATE_PYTHONS`). The other tools and the notebook kernel are base conda. LaTeX for manim comes
from TinyTeX (`~/.TinyTeX/bin/x86_64-linux`, set in `~/.zshrc`).

## Commands

```bash
BASE=/home/user/conda/bin/python3
RAH=/home/jovyan/.mlspace/envs/rah_manim/bin/python

# the data pipeline: mapping -> download -> bundle -> annotation check
$BASE tools/build_3b1b_mapping.py                  # lesson -> youtube_id -> manim source
$BASE tools/fetch_video.py <youtube_id>            # or --slug <lesson-slug>
$BASE tools/make_bundle.py <youtube_id>            # frames are cut by the scene detector; --no-frames keeps the old ones
$BASE tools/detect_scenes.py <youtube_id>          # the scene detector on its own
$BASE tools/describe_video.py <youtube_id> --settled 0.5   # VLM description of the video track, needs a server
$BASE tools/validate_samples.py data/annotations/*.jsonl

# the review contract: cross-checking the checklist against Item and checking a saved review
$BASE schema/review.py
$BASE schema/review.py --check data/reviews/<VIDEO_ID>/<SAMPLE_ID>/full.1.json

# the overview notebook (the kernel is base conda; it will not run in rah_manim)
cd data && $BASE -m nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=300 data_overview.ipynb

# manim: rendering a scene. PYTHONPATH is mandatory — the scenes in demo/ import
# scene_asserts and layout_check, and manim puts only the scene's directory on sys.path
conda activate rah_manim
PYTHONPATH=scripts manim -ql demo/demo.py SquareToCircle
PYTHONPATH=scripts MANIM_LAYOUT_STRICT=1 MANIM_SCENE_STRICT=1 \
    manim -ql demo/demo2.py EigenLecture
```

There is no test framework. The role of tests for the annotation is played by
`tools/validate_samples.py`: it returns code 1 on any error and prints a coverage breakdown when
there are none. To check a single file, simply pass it instead of the glob.

## The ProLecture pipeline

```
vendor/site (3Blue1Brown.com)          vendor/videos (3b1b/videos)
   app/pages/lessons/*/index.mdx  ──┐      _YYYY/*.py
   frontmatter: video:, source:     │
                                    ▼
                         data/3b1b_mapping.json      tools/build_3b1b_mapping.py
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
          data/videos/<id>/               (the path to the manim source)
          mp4 + info.json + en.vtt                 │
                     └──────────────┬──────────────┘
                                    ▼
                       data/bundles/<id>/           tools/make_bundle.py
                       transcript.md, formulas.md, frames/, bundle.json
                                    ▼
                       annotation by hand from the bundle
                                    ▼
                     data/annotations/<id>.jsonl    tools/validate_samples.py
```

**The key to everything is the frontmatter of the site's repository.** `3b1b/videos` itself
contains not a single link to YouTube; the connection "lesson ↔ video ↔ scene code" exists only in
`vendor/site/app/pages/lessons/<year>/<slug>/index.mdx`, which has the fields `video:` (the YouTube
id) and `source:` (a path inside `3b1b/videos`). Of the 175 lessons, 170 have an id, 159 declare a
`source` (155 together with an id), and only **140** point at a file that actually exists — the
other paths are stale, and for them the script proposes a `source_guess` via `difflib`.

`vendor/` is not under version control; the commits of the three third-party repositories are fixed
in `vendor/PINNED.txt` — without them the numbers above are irreproducible. Note: `3b1b/videos` is
written for **manimgl** (3b1b/manim) while manim **CE** is installed — a scene from there cannot be
rendered without a separate installation.

## Downloading from YouTube: three snags

Cookies and a login are **not needed**, but:

- the default client `android_vr` returns URLs on which the CDN answers 403 —
  `--extractor-args "youtube:player_client=android"` is mandatory;
- `--download-sections` does not work: it passes the URL to an external ffmpeg, which goes without
  the necessary headers. Download whole, cut locally;
- without a PO token only format 18 (640×360) is available. For 1080p the
  `bgutil-ytdlp-pot-provider` plugin is needed (it does not require a login either).

3b1b's subtitles are **human** (`subtitles`, not `automatic_captions`); Whisper is not needed.

## Annotation invariants

The schema is `schema/sample.schema.json`, with `additionalProperties: false` at every level. The
semantics on top of the schema are checked by `tools/validate_samples.py`. Two rules that are easy
to break out of ignorance:

- **`temporal_rel` is not set by hand but derived** from `question_time` and the `evidence_span` of
  the first/last required trigger. The axis is determined by the position of the *evidence*, not of
  the answer window: with a `post` question the answer window also begins at the moment the
  question is issued, and by the window it is indistinguishable from `at`.
- **`audio_dependency` stays `null` while `status == "draft"`** — the label is derived from the
  answers of the modality probes (`visiononly_solved` and `solvable`, checklist 4.5) rather than
  set by the annotator's opinion. The opinion lives separately in `audio_dependency_claim`.

What else is checked: non-overlapping windows, `t_ideal` inside its own window, `depends_on` only
on earlier indices, a distractor not lying entirely before `question_time` and not overlapping a
trigger, a multi-trigger sample having at least one distractor, the uniqueness of `id`.

## The principles the design grew out of

Taken from the adversarial reviews of three papers in `articles/` — each point closes a failure
that sank the work in question:

- labels that influence conclusions (`audio_dependency`) are set by **measurement**, not by
  declaration;
- the generator model, the judge model and the model being evaluated are different;
- open answers with a rubric, no MCQs (a skewed answer key breaks a benchmark);
- mandatory dummy baselines: blind, text-only, vision-only, frozen-frame, "answer immediately",
  "answer at the end", "stay silent";
- no quotas of the form "exactly N samples per task" — however many passed validation is however
  many there are;
- contamination: the pilot is built on a 2026 video, and the 2017 control video is there so that
  the gap of the blind baseline can be **measured** rather than denied.

## The manim scene checks

`scripts/layout_check.py` and `scripts/scene_asserts.py` close two different classes of error that
manim stays silent about: layout (going off-screen, overlaps) and semantics ("the picture is tidy
but means the wrong thing"). The variables `MANIM_LAYOUT_STRICT=1` and `MANIM_SCENE_STRICT=1` turn
warnings into exceptions.

## Language

The code, the documentation and the annotation are kept in English; identifiers, terms and
quotations from the videos stay in the original.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **If you are a reviewer or a probe of the annotation pipeline** (`reviewer_semiblind`,
> `reviewer_full_sample`, `reviewer_full_window`, any `probe_*`): this file is not written for
> you. It is for agents that work on the project itself — its code, schemas, documentation and
> the pipeline. Your prompt in `docs/prompts/<role>.md` is binding and names everything you may
> read: the prompt itself, your workspace and `schema/review.py`. Do not act on the rest of this
> file and do not open the documents it links to — `docs/annotation_checklist.md`,
> `docs/annotation_pipeline.md`, `docs/plans/general.md`, `docs/prompts/definitions.md`, other
> roles' prompts and the proposer's material (`docs/question_templates.md`,
> `docs/sample_examples.jsonl`). They hold the rules of other roles, and reading them changes
> what you measure.
> The interpreter is `/home/user/conda/bin/python3`.
>
> **If you are the proposer:** read what `docs/prompts/proposer.md` names, and of the rest of
> this file only the interpreter paths. Do not open `docs/plans/general.md` (its catalogue
> labels each template with an axis and a level, which a question does not inherit),
> `docs/annotation_checklist.md`, `docs/annotation_pipeline.md` or other roles' prompts.

## What this repository is

Two independent lines of work under one roof:

1. **ProLecture** — a benchmark of proactive tasks for streaming VLMs on 3Blue1Brown videos.
   This is the main line: `tools/`, `tests/`, `data/`, `schema/`, `docs/`, `articles/`.
2. **The manim sandbox** — animation experiments and two home-grown scene quality checks:
   `demo/`, `scripts/`.

The design intent of ProLecture is described in full in [docs/plans/general.md](docs/plans/general.md),
the annotation format in [data/annotations/README.md](data/annotations/README.md), the cutting of
frames by scene change in [docs/scene_detection.md](docs/scene_detection.md),
the run of the video-track description in [docs/video_description.md](docs/video_description.md),
the classes of annotation error and who catches them in
[docs/annotation_checklist.md](docs/annotation_checklist.md), the working order of the annotator
and reviewer agents in [docs/annotation_pipeline.md](docs/annotation_pipeline.md) together with the
draft prompts in [docs/prompts/](docs/prompts/), the question templates with working and broken
examples in [docs/question_templates.md](docs/question_templates.md) and two invented complete
samples in [docs/sample_examples.jsonl](docs/sample_examples.jsonl) (they pass the validator).
The contract the reviewer subagents report against is [schema/review.py](schema/review.py)
(pydantic, not a JSON schema: a model reads it too); the coordinator's journal and the files of
a review are described in [data/reviews/README.md](data/reviews/README.md). How a model is
measured on the finished records — the runners, the judge, the scores and the file a new
model's runner must write — is in [docs/evaluation.md](docs/evaluation.md).
Read them before any edit to the annotation or the metrics: they record decisions that have a
non-obvious "why".

Every script of `tools/` is listed with its purpose in [The tools](#the-tools) below.

**State, 2026-11:** the set is frozen for the first release. No new videos are annotated; the
closed videos in `data/annotations/` are what is measured (`tools/check_data.py` prints the
counts), and other models are measured by co-authors from their own checkouts
(`PROLECTURE_DATA`, [docs/evaluation.md](docs/evaluation.md)). The records of a closed video
stay as they are: a defect found in one is written down as a limitation, not edited away. A
video whose records are still in `data/annotations/partial/` is in review and joins the set
when its coordinator closes it; until then `check_data.py` names it in a warning.

## Two environments — the main snag

`python3` in the shell resolves now to one, now to the other. **Always name the interpreter
explicitly.**

| Environment | Path | What it has | What it lacks |
|---|---|---|---|
| `rah_manim` | `/home/jovyan/.mlspace/envs/rah_manim/bin/python` | manim CE 0.20.1, manim-voiceover, yt-dlp, cv2, openai | matplotlib, pandas, jupyter, jsonschema |
| base conda | `/home/user/conda/bin/python3` | matplotlib, pandas, jsonschema, cv2, jupyter | yt-dlp, manim |

`tools/fetch_video.py` looks for an interpreter with `yt_dlp` itself (the list is in
`CANDIDATE_PYTHONS`). The other tools, the tests and the notebook kernel are base conda. A
model's runner (`tools/eval_run_<model>.py`) is the exception: it runs in the model's own
environment and shares with the rest only `tools/eval_common.py`, which is standard library.
LaTeX for manim comes from TinyTeX (`~/.TinyTeX/bin/x86_64-linux`, set in `~/.zshrc`).

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
$BASE tools/merge_partials.py <youtube_id>         # the coordinator closes a video: partial/ -> <id>.jsonl
$BASE tools/check_data.py                          # the closed videos: records, videos and subtitles complete?
$BASE tools/check_data.py --expect 34              # ... and exactly 34 of them
$BASE tools/check_data.py --records-only           # the records alone, without the video files

# the coordinator's journal of a video: is it consistent, what is still owed
$BASE tools/coordinator_log.py <youtube_id> check          # --final: may the video be closed
$BASE tools/coordinator_log.py <youtube_id> open           # launches without a result

# the tests of the tools (unittest, about two minutes)
$BASE -m unittest discover -s tests
# around a change of tools/coordinator_log.py: journals written before it must read as before
$BASE tests/journal_baseline.py --save <DIR>       # before the change; data/ is not versioned,
$BASE tests/journal_baseline.py --compare <DIR>    # so <DIR> lives outside the repository

# measuring a model: its answers -> the judge -> the scores (docs/evaluation.md)
OUT=data/eval/<model>/<date>
<model env>/python tools/eval_run_minicpm.py --out $OUT --runs 3     # a stream; one runner per model
$BASE tools/eval_run_offline.py --out $OUT --runs 3                  # or one answer after the material
$BASE tools/eval_judge.py --out $OUT                                 # needs an OpenAI-compatible server
$BASE tools/eval_score.py --out $OUT                                 # -> $OUT/scores/summary.md

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

`tests/` (plain `unittest`) covers the tools that write or judge the annotation — the journal,
the edits of records, the merge, the workspace builder, the review contract, the validator —
and not the data-preparation or evaluation scripts. The annotation files are checked by
`tools/validate_samples.py`: it returns code 1 on any error and prints a coverage breakdown when
there are none. To check a single file, simply pass it instead of the glob.

## The tools

| Script | What it does | Run by |
|---|---|---|
| `tools/build_3b1b_mapping.py` | lesson → YouTube id → manim source, into `data/3b1b_mapping.json` | data preparation |
| `tools/fetch_video.py` | the video, its metadata and subtitles into `data/videos/<id>/` | data preparation |
| `tools/detect_scenes.py` | frames where the picture changes | `make_bundle.py`, or on its own |
| `tools/make_bundle.py` | the bundle of a video: transcript, formulas, frames, `bundle.json` | data preparation |
| `tools/describe_video.py` | a model's timed description of the video track (needs a VLM server) | data preparation |
| `tools/validate_samples.py` | the schema and the semantics of annotation files | everyone, after every edit |
| `tools/prepare_review_workspace.py` | the folder a reviewer or a probe works in: its material and nothing more | the coordinator |
| `tools/review_inputs.py` | which material a review role gets (a library) | the two around it |
| `tools/coordinator_log.py` | the journal of a video: launches, results, edits of records (`sample-edit`), the blind judge, `check` | the coordinator |
| `tools/sample_edit.py` | what an edit of a record changed and which kind of edit it is (a library) | `coordinator_log.py` |
| `tools/merge_partials.py` | closes a video: `partial/` → `data/annotations/<id>.jsonl` | the coordinator |
| `tools/check_data.py` | are the closed videos complete: files, measured flags, windows inside the video | whoever assembles the data |
| `tools/eval_common.py` | what the evaluation scripts share; where the data is (`PROLECTURE_DATA`) | a library |
| `tools/eval_run_minicpm.py`, `tools/eval_run_offline.py` | what a model said: a stream, or one answer after the material | evaluation |
| `tools/eval_judge.py` | which lines of an answer state which rubric item (an LLM) | evaluation |
| `tools/eval_score.py` | the metrics of a judged run | evaluation |
| `schema/review.py` | the contract of a review, and the check of a saved one | reviewers, the coordinator |
| `tests/journal_baseline.py` | the journal checks on every real journal, saved and compared | whoever changes `coordinator_log.py` |
| `notebooks/eval-minicpm.ipynb` | the exploratory notebook the evaluation scripts grew out of ("the notebook" in their comments); superseded by them | nobody |

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
                       data/bundles/<id>/           tools/make_bundle.py, tools/describe_video.py
                       transcript.md, formulas.md, frames/, description.*, bundle.json
                                    ▼
                       the proposer (an agent)      docs/prompts/proposer.md
                       data/annotations/partial/<id>.<interval>.jsonl
                                    ▼
                       the coordinator with reviewers and probes     docs/annotation_pipeline.md
                       data/reviews/<id>/: coordinator.log, reviews  tools/coordinator_log.py
                                    ▼
                     data/annotations/<id>.jsonl    tools/merge_partials.py, tools/validate_samples.py
                                    ▼
                     data/eval/<model>/<date>/      tools/eval_*.py, docs/evaluation.md
```

`data/` is not under version control, apart from its READMEs, the mapping and the pilot's three
videos: the records, the videos, the bundles, the reviews and the runs live in the working copy.

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
semantics on top of the schema are checked by `tools/validate_samples.py`. Three rules that are easy
to break out of ignorance:

- **`temporal_rel` is not set by hand but derived** from `question_time` and the earliest start
  and latest end of the `evidence_span`s of the required triggers. The axis is determined by the position of the *evidence*, not of
  the answer window: with a `post` question the answer window also begins at the moment the
  question is issued, and by the window it is indistinguishable from `at`.
- **`audio_dependency` stays `null` until both probes it comes from have answered**, whatever
  the status — the label is derived from the answers of the modality probes (`visiononly_solved` and `solvable`, checklist 4.5) rather than
  set by the annotator's opinion. The opinion lives separately in `audio_dependency_claim`.
- **A record under review is changed only through `tools/coordinator_log.py <video> sample-edit`**,
  never in an editor: the journal keeps every version of a record, and the next launch or edit
  is refused on a record that is not the version the journal knows
  ([data/reviews/README.md](data/reviews/README.md)).

What else is checked: non-overlapping windows, `t_ideal` inside its own window, `depends_on` only
on earlier indices, the uniqueness of `id`. There is no `distractor_windows` field any more
(removed 2026-09-07): an early answer is penalised by the false-alarm rate, and the annotated
decoys only leaked `t_start` to the semi-blind reviewer.

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
  memory of a video can be **measured** rather than denied — by a separate ablation, not by the
  blind baseline: an answer from memory of the video is not solving blind
  (`docs/plans/general.md`, §1.1).

## The manim scene checks

`scripts/layout_check.py` and `scripts/scene_asserts.py` close two different classes of error that
manim stays silent about: layout (going off-screen, overlaps) and semantics ("the picture is tidy
but means the wrong thing"). The variables `MANIM_LAYOUT_STRICT=1` and `MANIM_SCENE_STRICT=1` turn
warnings into exceptions.

## Language

The code, the documentation and the annotation are kept in English; identifiers, terms and
quotations from the videos stay in the original.

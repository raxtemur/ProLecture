# ProLecture

ProLecture is a benchmark for **proactive reasoning over streaming mathematical
lectures**. A model receives a question in advance, watches a video as it unfolds,
and must decide both **when** to answer and **what** to answer. The benchmark is built
around 3Blue1Brown videos, where the visual track, narration, formulas, and source
Manim scenes provide unusually precise evidence for annotation and review.

This repository contains the data-preparation and annotation pipeline and the evaluation
code, used to:

1. collect a video, its metadata, and subtitles;
2. assemble an annotation bundle with a timestamped transcript, formulas, and
   content-selected frames;
3. generate a dense, timestamp-aligned description of the visual track;
4. create candidate questions and run them through the
   Proposer → Coordinator → Review → Retry workflow;
5. check that the finished data is complete;
6. measure a model on it: its answers, a rubric judge, the scores.

If you are here to measure a model on the existing records, go straight to
[section 6](#6-measure-a-model) and [`docs/evaluation.md`](docs/evaluation.md): the first
four sections are about producing records.

The repository also contains a separate Manim sandbox under `demo/` and `scripts/`.
The workflow below concerns the ProLecture benchmark in `tools/`, `data/`, `schema/`,
and `docs/`.

## Prerequisites

Run all commands from the repository root.

You will need:

- Python 3.10 or newer;
- `yt-dlp` for downloading videos, and `ffmpeg`/`ffprobe` available in `PATH`;
- OpenCV for bundle frame extraction;
- `openai` and Pillow for visual-track description;
- `jsonschema` for the validator (and so for the data check), `pydantic` for the review
  contract, `openai` and `httpx` for the evaluation judge.

Install the Python dependencies used by the steps in this guide:

```bash
python3 -m pip install yt-dlp openai pillow opencv-python-headless jsonschema pydantic httpx
```

Generating the visual description also requires an OpenAI-compatible VLM server
with image input and structured-output support. See
[`docs/video_description.md`](docs/video_description.md) for a tested vLLM setup and
troubleshooting notes.

## Workflow overview

```text
data/videos/<VIDEO_ID>/
        │
        ├── tools/make_bundle.py
        │       └── data/bundles/<VIDEO_ID>/
        │           ├── bundle.json
        │           ├── transcript.md
        │           ├── formulas.md
        │           └── frames/
        │
        ├── tools/describe_video.py
        │       └── data/bundles/<VIDEO_ID>/
        │           ├── description.jsonl
        │           ├── description.md
        │           └── screen_text.md
        │
        └── Proposer → Coordinator → Review → Retry
                └── data/annotations/<VIDEO_ID>.jsonl
                    data/reviews/<VIDEO_ID>/...

data/annotations/*.jsonl + data/videos/
        │
        ├── tools/check_data.py           is everything there and consistent?
        │
        └── tools/eval_run_<model>.py → tools/eval_judge.py → tools/eval_score.py
                └── data/eval/<MODEL>/<DATE>/
                    ├── responses/        what the model said
                    ├── judged/           which rubric items it stated
                    └── scores/summary.md
```

## 1. Download the video

`tools/fetch_video.py` wraps `yt-dlp` and writes everything the later steps need into
`data/videos/<VIDEO_ID>/`:

```bash
# by YouTube ID
python3 tools/fetch_video.py 3d6DsjIBzJ4

# or by lesson slug, resolved through data/3b1b_mapping.json
python3 tools/fetch_video.py --slug reinventing-entropy
```

The script locates an interpreter that has `yt_dlp` installed (the list is
`CANDIDATE_PYTHONS` at the top of the file), downloads the video, its metadata, and its
subtitles, and prints a short report: duration, chapter count, whether manual English
subtitles were found, and the size of every file produced. A second run is a no-op while
all three files are present; `--force` re-downloads and overwrites them.

Neither cookies nor a YouTube account are required. 3Blue1Brown ships **human** English
subtitles (`subtitles`, not `automatic_captions`), so no Whisper pass is needed.

The resulting layout is:

```text
data/videos/<VIDEO_ID>/
├── <VIDEO_ID>.mp4          # source video
├── <VIDEO_ID>.info.json    # title, duration, chapters, format table
├── <VIDEO_ID>.en.vtt       # English subtitles
└── <VIDEO_ID>.description  # YouTube description text
```

Videos are intentionally not distributed with this repository. The benchmark stores
YouTube IDs, annotations, and timecodes rather than republishing the source videos.

### What you get by default: 360p

The script pins `--extractor-args youtube:player_client=android` and `-f 18`: a single
progressive MP4, 640×360, H.264 + AAC. Three constraints force that choice. Each was
re-checked on 2026-08-27 against yt-dlp 2026.07.04:

| Constraint | What happens |
|---|---|
| The player client must be pinned | yt-dlp's default clients (`android_vr`, `web_safari`) do list the DASH formats up to the video's top resolution, but downloading one of them ends in `HTTP Error 403: Forbidden`, and `--write-subs --sub-langs en` against them reports `There are no subtitles for the requested languages`. `player_client=android` returns format 18 plus the subtitles, and downloads without error. |
| Anything above 360p needs a PO token | The `web` client, which does serve every format and every subtitle track, yields nothing usable without one: `Only images are available for download`. |
| `--download-sections` is unusable | It hands the media URL to an external ffmpeg, which requests it without the headers the CDN expects. Download whole files and cut locally. |

Resolution matters downstream: the frames in `data/bundles/<VIDEO_ID>/frames/` are cut
from this MP4, and the visual description in step 3 reads those frames, so 360p is the
ceiling on how legible small on-screen text is to both the annotator and the VLM. Every
bundle currently in the repository was built from 360p.

### Downloading at 480p and above

480p and higher are DASH-only: video and audio arrive as separate streams and are merged
by ffmpeg. Obtaining a URL the CDN will serve requires a **PO token**, which is minted by
a small helper service — the `bgutil` provider. It needs no YouTube login.

1. Install the yt-dlp side of the plugin into **the interpreter that actually runs
   yt-dlp**. That is usually not the `python3` on your `PATH`:
   `tools/fetch_video.py` searches `CANDIDATE_PYTHONS` for one that can `import yt_dlp`,
   and installing the plugin anywhere else fails silently — no plugin, no PO token, the
   same 403 with nothing in the log to explain it.

   ```bash
   YTDLP_PY=$(python3 -c "import sys; sys.path.insert(0, 'tools'); import fetch_video; print(fetch_video.find_python_with_ytdlp())")
   "$YTDLP_PY" -m pip install "bgutil-ytdlp-pot-provider==1.3.2"
   ```

   Pin the version: it has to match the provider started in the next step. With the plugin
   present, every extraction probes the provider, so its absence becomes visible in the log
   as `[pot:bgutil:http] Error reaching GET http://127.0.0.1:4416/ping`.

2. Start the provider on port 4416. The published GitHub release contains only the plugin;
   the server itself comes from a container or from source, and **its version must match
   the plugin's**:

   ```bash
   docker run --name bgutil-provider -d --init -p 4416:4416 \
       brainicism/bgutil-ytdlp-pot-provider:1.3.2
   ```

   Without Docker, build it from the tag of the same version. `server/package.json` at
   1.3.2 declares `"engines": {"node": ">=22", "npm": ">=9"}`, and the tag ships a
   `package-lock.json` but no `yarn.lock`:

   ```bash
   git clone --branch 1.3.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider
   cd bgutil-ytdlp-pot-provider/server
   npm ci && npx tsc && node build/main.js
   ```

   `curl http://127.0.0.1:4416/ping` should answer, and the warning above should stop.

3. Download with a client that serves DASH, picking the best H.264 stream at the target
   height and merging it with the audio:

   ```bash
   yt-dlp \
       --extractor-args "youtube:player_client=web_safari" \
       -f "bv*[height<=480][vcodec^=avc1]+ba[ext=m4a]" \
       --merge-output-format mp4 \
       --write-info-json --write-subs --sub-langs en --sub-format vtt \
       --write-description \
       -o "data/videos/%(id)s/%(id)s.%(ext)s" \
       "https://www.youtube.com/watch?v=<VIDEO_ID>"
   ```

   Prefer `bv*[height<=480]` over a literal `-f 135`: format numbers change, the selector
   does not. Substitute 720 or 1080 for a larger frame at a proportionally larger file.
   Keep the `vcodec^=avc1` and `ext=m4a` filters. Every tool downstream addresses the video
   as `<VIDEO_ID>.mp4` by name (`fetch_video.py`, `make_bundle.py`, `detect_scenes.py`,
   `describe_video.py`); drop the filters and the best streams merge into `.webm` or
   `.mkv`, after which the whole pipeline reports a missing video and `fetch_video.py`
   re-downloads on every run.

4. To make `tools/fetch_video.py` behave this way for every video, edit `PLAYER_CLIENT`
   and `FORMAT` at the top of the file. They are module-level constants rather than CLI
   options on purpose, so that a corpus is not accidentally assembled from a mixture of
   resolutions.

### Re-downloading at a different resolution

Every stage downstream caches, and every cache is keyed on timecodes rather than on pixels,
so a resolution swap is invisible to all of them. Left alone, the pipeline will happily
rebuild a "new" description out of the old low-resolution frames. Force each stage:

1. **The video.** yt-dlp does not overwrite an existing video file by default — it
   overwrites only the metadata beside it (`--no-force-overwrites`, its documented
   default). `tools/fetch_video.py --force` therefore passes `--force-overwrites`
   explicitly. Downloading by hand, pass it yourself, or delete the MP4 first; otherwise
   you end up with an `info.json` describing a format that was never fetched.

2. **The frames.** Re-run step 2 **without** `--no-frames`, so `make_bundle.py` re-cuts
   `frames/`. Note that it deliberately leaves subdirectories alone: `frames/exact/`, the
   notebook cache, keeps whatever resolution it was written at and has to be removed by
   hand.

3. **The description.** `describe_video.py` re-uses a cut whose median step matches the
   requested one and skips any frame file that merely exists, so it will silently reuse the
   old JPEGs. Pass `--force-frames`; the log line `[frames] taking the ready N from ...` is
   the sign that you forgot.

Annotations and reviews reference timecodes rather than pixels and survive the change. The
scene-change cut may shift slightly, because the detector measures frame-to-frame
difference on the actual pixels.

## 2. Create an annotation bundle

Set the video ID and run the bundle builder:

```bash
VIDEO_ID=3d6DsjIBzJ4
python3 tools/make_bundle.py "$VIDEO_ID"
```

The tool:

- reads the video metadata and timestamped subtitles;
- looks up the corresponding Manim source in `data/3b1b_mapping.json`;
- extracts literal formulas and on-screen strings from the source when it is
  available under `vendor/videos/`;
- detects settled scene changes and captures representative frames;
- writes the complete annotator-facing bundle to `data/bundles/<VIDEO_ID>/`.

The generated files are:

| Path | Purpose |
|---|---|
| `bundle.json` | Machine-readable chapters, transcript, formulas, and frame index |
| `transcript.md` | Timestamped transcript grouped by chapter |
| `formulas.md` | Strings extracted from the Manim source, with file and scene references |
| `frames/` | Content-selected, settled frames produced by scene-change detection |

Useful options:

```bash
# Tune scene-change sensitivity.
python3 tools/make_bundle.py "$VIDEO_ID" --scene-threshold 0.008

# Rebuild metadata and readable files while retaining the frame list from an
# existing bundle.
python3 tools/make_bundle.py "$VIDEO_ID" --no-frames
```

A normal run replaces the previously generated scene frames so that files from cuts
made with different thresholds cannot be mixed. `--no-frames` is useful only when an
existing bundle already contains the frame cut you want to preserve.

For details of the detector and its trade-offs, see
[`docs/scene_detection.md`](docs/scene_detection.md).

## 3. Generate a detailed visual description

`tools/describe_video.py` produces a timestamp-aligned description of what is visible
in the video. It sends overlapping windows of frames to an OpenAI-compatible VLM and
stores structured events, visible text, and the beginning and ending state of every
fragment.

Start with a short trial run and inspect its output:

```bash
python3 tools/describe_video.py "$VIDEO_ID" \
    --range 0-60 \
    --out-prefix _probe
```

By default, the tool selects two settled frames per second (`--settled 0.5`), uses
five-second windows with a four-second stride, and connects to model `qwen36` at
`http://localhost:8078/v1`.

Once the trial looks reasonable, process the full video:

```bash
python3 tools/describe_video.py "$VIDEO_ID" --workers 12
```

For a server with a different address or served model name:

```bash
python3 tools/describe_video.py "$VIDEO_ID" \
    --api-base http://gpu-node:8078/v1 \
    --model my-vlm \
    --workers 12
```

If a completed run contains failed, truncated, or degenerate fragments, retry only
those fragments:

```bash
python3 tools/describe_video.py "$VIDEO_ID" --redo-bad
```

The main outputs are:

- `data/bundles/<VIDEO_ID>/description.jsonl` — machine-readable run metadata and
  fragment records;
- `data/bundles/<VIDEO_ID>/description.md` — a readable visual timeline for annotators
  and agents;
- `data/bundles/<VIDEO_ID>/screen_text.md` — the text recognised on the screen, each line
  once, at the second it first appears; the proposer reads it in full.

The model sees only frames by default. Do not enable `--with-transcript` for benchmark
material: the description is later used as a visual-channel index, so allowing it to
contain information from the narration would invalidate the modality probes.

For server setup, resource estimates, all CLI options, and recovery procedures, read
[`docs/video_description.md`](docs/video_description.md).

## 4. Run the annotation and review pipeline with a coding agent

Two roles are started by hand, each in its own fresh session of a coding agent (Codex or
Claude Code) launched from the repository root: first the **proposer**, which writes
candidate questions, then the **coordinator**, which carries them through review, launching
the reviewers and probes as subagents, and closes the video by merging the proposer's files
into `data/annotations/<VIDEO_ID>.jsonl`. Start the coordinator once the
proposer's file exists and passes the validator. One session per role and per video.

Both messages below only point the agent at its role document and name the video: the
rules live in `docs/prompts/` and `docs/annotation_pipeline.md`, and a copy of them here
would drift. Replace every `<VIDEO_ID>` with the id of the video and send the text as it is. The bundle (sections 2 and 3)
must be complete, including `screen_text.md`.

Before rerunning a video that already has annotations, move its old
`data/annotations/<VIDEO_ID>.jsonl`, `data/annotations/partial/<VIDEO_ID>.*.jsonl` and
`data/reviews/<VIDEO_ID>/` out of the way: the new run writes to the same paths, and the
sample ids repeat.

**The proposer:**

```text
You are the proposer agent of the ProLecture annotation pipeline.

Read docs/prompts/proposer.md in full and follow it: it is binding. Its first paragraph
is addressed to whoever launches you; skip it. Where the prompt says VIDEO_ID in angle
brackets, use <VIDEO_ID>; where it says INTERVAL in angle brackets, use full (the whole
video).

If a bundle file the prompt lists is missing, stop and say which; do not build it
yourself. Write only data/annotations/partial/<VIDEO_ID>.full.jsonl. If this session is
compacted, re-read docs/prompts/proposer.md before you continue.
```

**The coordinator:**

```text
You are the coordinator of the ProLecture annotation pipeline for the video <VIDEO_ID>.

Read in full before you start: docs/prompts/coordinator.md,
docs/annotation_pipeline.md and docs/prompts/definitions.md. They are binding; where this
message and they differ, they win.

Your input is the proposer's output, data/annotations/partial/<VIDEO_ID>.*.jsonl. Carry
every sample of these files through steps 2-6 of the pipeline: the
reviewers and probes in the order and with the isolation the pipeline defines, your
decisions and edits, the repeat reviews, the checks across samples, and closing the video
with tools/merge_partials.py <VIDEO_ID> (docs/prompts/coordinator.md, §8).

- Give each subagent its complete prompt from docs/prompts/ and only the workspace that
  tools/prepare_review_workspace.py builds for it. Subagents never edit annotation files.
- Run every subagent on the one local model you run on (docs/prompts/coordinator.md,
  "One model for every role").
- Record every launch and result with tools/coordinator_log.py <VIDEO_ID>, and change a
  record only through its sample-edit command (docs/prompts/coordinator.md, §3, "Changing
  a record"); run tools/validate_samples.py on the video's files after an edit. When the
  tool refuses a command, its message says what to do.
- Do not stop after the first round, and do not count a skipped check as passed.
- Do not end your turn while a subagent is running (docs/prompts/coordinator.md, §3).
- If this session is compacted, re-read docs/prompts/coordinator.md before you continue.
```

For an agent that runs on a local model, with nobody reading the session, add:

```text
The session is being executed on the local model (Qwen/Qwen3.8-27B) inside a batch job.
Only use subagents and the repository's tools, don't try to connect with the local model
directly; tools/coordinator_log.py blind-judge calls the judge on it for you. No human reads
this session while it runs: do not ask questions and do not wait for answers; decide by
the documents and write each decision down where they say.
```

The coordinator's journal, `data/reviews/<VIDEO_ID>/coordinator.log`, is written only through
`tools/coordinator_log.py`; its `check` command says whether the journal is consistent and
`check --final` whether the video may be closed
([`data/reviews/README.md`](data/reviews/README.md)).

The principal outputs of this stage are:

- `data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl` — the proposer's output
  (`full` for the whole video);
- `data/annotations/<VIDEO_ID>.jsonl` — the merged annotation set, written when the video
  is closed;
- `data/reviews/<VIDEO_ID>/coordinator.log` — the journal of every launch, result and edit;
- `data/reviews/<VIDEO_ID>/<SAMPLE_ID>/` — versioned structured reviews and coordinator
  decisions.

The pipeline is iterative: deterministic validation runs after every edit, changed
participant-visible wording requires a complete fresh review cycle, and unresolved or
oscillating samples are handed to a human after the documented retry limit. Human
acceptance remains mandatory while the benchmark is being calibrated.

## 5. Check the data

```bash
python3 tools/check_data.py                  # the data/ of this checkout
python3 tools/check_data.py --expect 34      # also fail unless exactly 34 videos are there
python3 tools/check_data.py --records-only   # the records alone, before the videos are downloaded
```

One command for whoever assembled a data folder — closed a video, restored the videos by id
on another machine, or downloaded the records. Beyond the validator it checks the files a
record needs and what the evaluation makes of it: the video is there, has sound and runs as
long as the records state; the subtitles and the transcript exist; every validated record has
its measured flags and a required window with a rubric item; the windows lie inside the video.
It prints the counts of the set and, if there are any, the problems, each missing file with
the command that restores it; the exit code is 1 when something is wrong. `--expect N` is the
guard against a copy that lacks a video: N is the number of videos the release you copied
states. `--records-only` checks downloaded records before their videos are there. A video
whose records are still under
`annotations/partial/` is in review, not part of the set, and named in a warning.
`PROLECTURE_DATA=/path/to/data` checks a data folder kept outside the checkout; note that
`fetch_video.py` and `make_bundle.py` always write into the checkout's own `data/`. The script
needs `jsonschema` and, for the files, `ffprobe`.

## 6. Measure a model

Three steps, one folder per run; every step is a file per task and can be restarted:

```bash
OUT=data/eval/<MODEL>/<DATE>

# 1. what the model said: one runner per model, in the model's own environment
<model env>/python tools/eval_run_minicpm.py --out $OUT --runs 3    # a stream (MiniCPM-o 4.5)
python3 tools/eval_run_offline.py --out $OUT --runs 3               # or one answer after the material (a model on vLLM)

# 2. which rubric items each answer states: an LLM judge on an OpenAI-compatible server
python3 tools/eval_judge.py --out $OUT --base-url http://127.0.0.1:8000/v1 --model local

# 3. the scores
python3 tools/eval_score.py --out $OUT       # -> $OUT/scores/summary.md
```

[`docs/evaluation.md`](docs/evaluation.md) is the guide: where the data is and how
`PROLECTURE_DATA` points a checkout at it, what a model is shown, the one file a new model's
runner must write (`responses/<task>.json`), the judge, and what each score means.

## Tests

```bash
python3 -m unittest discover -s tests
```

`tests/` (plain `unittest`, about two minutes) covers the tools that write or judge the
annotation: the journal, the edits of records, the merge, the workspace builder, the review
contract and the validator. The data-preparation and evaluation scripts have no unit tests.
`tests/journal_baseline.py` is not a unit test: it saves the output of the journal checks on
every real journal and compares it after a change of `tools/coordinator_log.py`.

## Other scripts

| Script | What it is |
|---|---|
| `tools/build_3b1b_mapping.py` | builds `data/3b1b_mapping.json`: lesson → YouTube id → manim source |
| `tools/detect_scenes.py` | the scene-change detector `make_bundle.py` uses, runnable on its own |
| `tools/validate_samples.py` | the schema and the semantics of annotation files; run after every edit |
| `tools/review_inputs.py`, `tools/sample_edit.py` | libraries of the workspace builder and of the journal |
| `tools/eval_common.py` | what the evaluation scripts share; reads `PROLECTURE_DATA` |
| `notebooks/eval-minicpm.ipynb` | the exploratory notebook the evaluation scripts grew out of; superseded by them |

## Key documentation

| Document | What it defines |
|---|---|
| [`docs/plans/general.md`](docs/plans/general.md) | Benchmark goals, taxonomy, and question templates |
| [`data/annotations/README.md`](data/annotations/README.md) | Annotation file layout and field semantics |
| [`docs/question_templates.md`](docs/question_templates.md) | Question templates with working and broken examples |
| [`docs/sample_examples.jsonl`](docs/sample_examples.jsonl) | Two invented complete samples that pass the validator |
| [`docs/prompts/definitions.md`](docs/prompts/definitions.md) | The terms the proposer and the coordinator use (`act`, levels, windows) |
| [`docs/annotation_checklist.md`](docs/annotation_checklist.md) | Checks applied to every sample |
| [`docs/annotation_pipeline.md`](docs/annotation_pipeline.md) | Role order, workspaces, retry loop, and human acceptance |
| [`docs/prompts/proposer.md`](docs/prompts/proposer.md) | Proposer role and output requirements |
| [`docs/prompts/coordinator.md`](docs/prompts/coordinator.md) | Coordinator decisions and acceptance methodology |
| [`schema/sample.schema.json`](schema/sample.schema.json) | Machine-readable sample schema |
| [`schema/review.py`](schema/review.py) | Structured review contract and review validator |
| [`data/reviews/README.md`](data/reviews/README.md) | The coordinator's journal and the files of a review |
| [`docs/evaluation.md`](docs/evaluation.md) | Measuring a model: protocols, the response-file contract, judge, scores |

Before editing annotations or review logic, read the relevant documents above. Several
rules—especially temporal relation derivation, modality isolation, and reviewer order—are
deliberately non-obvious and encode failures found in earlier annotation rounds.

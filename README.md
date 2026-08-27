# ProLecture

ProLecture is a benchmark for **proactive reasoning over streaming mathematical
lectures**. A model receives a question in advance, watches a video as it unfolds,
and must decide both **when** to answer and **what** to answer. The benchmark is built
around 3Blue1Brown videos, where the visual track, narration, formulas, and source
Manim scenes provide unusually precise evidence for annotation and review.

This repository contains the data-preparation and annotation pipeline used to:

1. collect a video, its metadata, and subtitles;
2. assemble an annotation bundle with a timestamped transcript, formulas, and
   content-selected frames;
3. generate a dense, timestamp-aligned description of the visual track;
4. create candidate questions and run them through the
   Proposer → Coordinator → Review → Retry workflow.

The repository also contains a separate Manim sandbox under `demo/` and `scripts/`.
The workflow below concerns the ProLecture benchmark in `tools/`, `data/`, `schema/`,
and `docs/`.

## Prerequisites

Run all commands from the repository root.

You will need:

- Python 3.10 or newer;
- `yt-dlp` for downloading videos, and `ffmpeg`/`ffprobe` available in `PATH`;
- OpenCV for bundle frame extraction;
- `openai` and Pillow for visual-track description.

Install the Python dependencies used by the steps in this guide:

```bash
python3 -m pip install yt-dlp openai pillow opencv-python-headless
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
        │           └── description.md
        │
        └── Proposer → Coordinator → Review → Retry
                └── data/annotations/<VIDEO_ID>.jsonl
                    data/reviews/<VIDEO_ID>/...
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
subtitles were found, and the size of every file produced. Re-running it is a no-op unless
`--force` is passed.

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
| The player client must be pinned | yt-dlp's default `android_vr` client does list DASH formats up to 1080p, but downloading one of them ends in `HTTP Error 403: Forbidden`, and that client returns no subtitles at all. `player_client=android` returns format 18 plus the subtitles, and downloads without error. |
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

1. Install the yt-dlp side of the plugin into the same interpreter that runs yt-dlp:

   ```bash
   python3 -m pip install -U bgutil-ytdlp-pot-provider
   ```

   With the plugin present, every extraction probes the provider, so its absence is
   visible in the log as `[pot:bgutil:http] Error reaching GET http://127.0.0.1:4416/ping`.

2. Start the provider on port 4416. The published GitHub release contains only the plugin;
   the server itself comes from a container or from source, and **its version must match
   the plugin's**:

   ```bash
   docker run --name bgutil-provider -d -p 4416:4416 \
       brainicism/bgutil-ytdlp-pot-provider:1.3.2
   ```

   Without Docker, build it (Node 18 or newer):

   ```bash
   git clone --branch 1.3.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider
   cd bgutil-ytdlp-pot-provider/server
   yarn install --frozen-lockfile && npx tsc && node build/main.js
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

4. To make `tools/fetch_video.py` behave this way for every video, edit `PLAYER_CLIENT`
   and `FORMAT` at the top of the file. They are module-level constants rather than CLI
   options on purpose, so that a corpus is not accidentally assembled from a mixture of
   resolutions.

### Re-downloading at a different resolution

Replacing an MP4 invalidates the frames cut from it. Re-run step 2 **without**
`--no-frames` so the bundle is re-cut, then regenerate the visual description in step 3,
which reads those frames. Annotations and reviews reference timecodes rather than pixels
and survive the change; the scene-change cut may shift slightly, because the detector
measures frame-to-frame difference on the actual pixels.

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
  and agents.

The model sees only frames by default. Do not enable `--with-transcript` for benchmark
material: the description is later used as a visual-channel index, so allowing it to
contain information from the narration would invalidate the modality probes.

For server setup, resource estimates, all CLI options, and recovery procedures, read
[`docs/video_description.md`](docs/video_description.md).

## 4. Run the annotation and review pipeline with a coding agent

The remaining workflow is designed to be coordinated by an agent that can launch
independent subagents, such as Codex or Claude Code. Start the agent from the repository
root and give it the prompt below.

The prompt deliberately tells the agent to read the role documents in full instead of
duplicating their rules here. Those documents are the source of truth for the annotation
format, reviewer isolation, role order, retry policy, and validation requirements.

```text
Study this repository. You will act as both the Proposer and the Coordinator.

Work with the video in `data/videos/3d6DsjIBzJ4` (video ID: `3d6DsjIBzJ4`).

Your task:

1. Verify that all artifacts required by the Proposer are present and usable. In
   particular, check the outputs of `tools/make_bundle.py` under
   `data/bundles/3d6DsjIBzJ4/` and the generated visual description described in
   `docs/video_description.md`. Report and resolve any missing or inconsistent
   prerequisites before proposing questions.

2. Before creating any questions, read `docs/prompts/proposer.md` in full and follow
   it, including every referenced requirement, output convention, and validation step.
   As the Proposer, prepare approximately 15–20 high-quality questions distributed
   reasonably evenly across the video's timeline. Aim for roughly 20% L1, 40% L2,
   and 40% L3, but treat these as coverage targets rather than quotas: question quality,
   temporal validity, and diversity across the other taxonomy axes are more important
   than hitting exact counts.

3. Then switch to the Coordinator role. Read `docs/prompts/coordinator.md` and
   `docs/annotation_pipeline.md` in full. Run independent subagents in the exact order
   defined there, and give each subagent the complete corresponding prompt from
   `docs/prompts/`.

   Follow the current role order precisely:
   - first run the semi-blind reviewer, `probe_text`, `probe_vision`, and `probe_frame`
     independently, with the roles that may run in parallel launched in parallel;
   - consolidate their results and run `probe_full` only when the documented condition
     requires it;
   - apply cheap fixes and run schema/sample validation;
   - then run `full_sample` and one `full_window` reviewer per trigger for every sample;
   - apply repairs and repeat the required fresh or targeted reviews until every sample
     passes or reaches a documented human-handoff condition.

4. Use GPT-5.6-Sol with medium reasoning effort for reviewer subagents. Preserve the
   isolation rules for semi-blind reviewers and modality probes: use separate workspaces,
   expose only the material allowed for each role, never share review history with a
   fresh reviewer, and never let reviewer subagents edit the annotation files directly.

5. After every edit, run the required validators. Save all review artifacts and
   coordinator decisions at the paths and with the round numbering required by the
   project documentation. Do not treat skipped checks as passes, do not silently exceed
   the retry limit, and do not stop after merely generating the initial questions: carry
   the set through the complete Proposer → Coordinator → Review → Retry workflow.
```

The principal outputs of this stage are:

- `data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl` — proposer output when work is
  split by interval;
- `data/annotations/<VIDEO_ID>.jsonl` — the merged annotation set;
- `data/reviews/<VIDEO_ID>/<SAMPLE_ID>/` — versioned structured reviews and coordinator
  decisions.

The pipeline is iterative: deterministic validation runs after every edit, changed
participant-visible wording requires a complete fresh review cycle, and unresolved or
oscillating samples are handed to a human after the documented retry limit. Human
acceptance remains mandatory while the benchmark is being calibrated.

## Key documentation

| Document | What it defines |
|---|---|
| [`docs/plans/general.md`](docs/plans/general.md) | Benchmark goals, taxonomy, and question templates |
| [`data/annotations/README.md`](data/annotations/README.md) | Annotation file layout and field semantics |
| [`docs/question_templates.md`](docs/question_templates.md) | Template-specific failure modes and anti-examples |
| [`docs/annotation_checklist.md`](docs/annotation_checklist.md) | Checks applied to every sample |
| [`docs/annotation_pipeline.md`](docs/annotation_pipeline.md) | Role order, workspaces, retry loop, and human acceptance |
| [`docs/prompts/proposer.md`](docs/prompts/proposer.md) | Proposer role and output requirements |
| [`docs/prompts/coordinator.md`](docs/prompts/coordinator.md) | Coordinator decisions and acceptance methodology |
| [`schema/sample.schema.json`](schema/sample.schema.json) | Machine-readable sample schema |
| [`schema/review.py`](schema/review.py) | Structured review contract and review validator |

Before editing annotations or review logic, read the relevant documents above. Several
rules—especially temporal relation derivation, modality isolation, and reviewer order—are
deliberately non-obvious and encode failures found in earlier annotation rounds.

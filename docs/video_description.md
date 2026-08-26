# How to run the description of the video track

The tool is [`tools/describe_video.py`](../tools/describe_video.py). The output is
`data/bundles/<id>/description.jsonl` (machine-readable) and `description.md` (for reading).
What it is for and what in it can be trusted is in
[reports/2026-08-25-video-tools.md](reports/2026-08-25-video-tools.md).

Here it is only about launching it, including on somebody else's machine.

## What is needed

**The client** (cuts the frames, sends the requests, assembles the document) — any Python 3.10+
with two packages:

```bash
pip install openai pillow
pip install opencv-python-headless   # only if you take frames via --settled
```

You also need `ffmpeg` in `PATH`. No torch is required on the client side — it goes over HTTP.

On this machine both environments will do: base conda (`/home/user/conda/bin/python3`) and
`rah_manim`, where `cv2` and `openai` have been added.

**The server** — anything with an OpenAI-compatible API that can do images and **structured
outputs**. The response schema is held by the server; without guided decoding the script will not
work.

If the server has to be raised from scratch:

```bash
python -m venv /path/to/vllm027 && /path/to/vllm027/bin/python -m pip install \
    vllm==0.27.1 "transformers>=5.8.0"
```

The `Qwen3_5*` architecture (this covers `Qwen3.5-27B`, `Qwen3.6-35B-A3B` and `Qwen3.8-27B`) is
known to vLLM from branch 0.17 onwards; in 0.11 it is not in the registry and the server will
refuse to load the model.

**Turn the proxy off while downloading.** On this machine the `HTTP_PROXY` from the environment
throttles both PyPI and HuggingFace to 0.3–1.2 MB/s, whereas directly both give ~64 MB/s: 67 GB of
weights arrive in two minutes instead of a day.

**The material** is `data/videos/<id>/<id>.mp4`. The duration and the chapters are taken from
`data/bundles/<id>/bundle.json`; if it is absent, from `ffprobe`, and then the markdown will have
no breakdown by chapter.

## The server

Verified on vLLM 0.27.1 with `Qwen/Qwen3.6-35B-A3B` (MoE, 3B active out of 35B, 67 GB of weights in
bf16) on two A100-80GB:

```bash
ES=/workspace-SR004.nfs2/rahmatullaev/envs/vllm027/bin/python

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
export NO_PROXY='*' HF_HOME=/workspace-SR004.nfs2/rahmatullaev/hf_cache
# flashinfer builds kernels on the fly and looks for nvcc via CUDA_HOME; the system has none
export CUDA_HOME=/workspace-SR004.nfs2/rahmatullaev/envs/vllm027/lib/python3.12/site-packages/nvidia/cu13
export VLLM_USE_FLASHINFER_SAMPLER=0

$ES -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3.6-35B-A3B --served-model-name qwen36 \
    --tensor-parallel-size 2 --port 8078 --max-model-len 32768 \
    --limit-mm-per-prompt '{"image": 16}' \
    --gpu-memory-utilization 0.85 \
    --mm-processor-cache-gb 0
```

The weights are in **bf16, not FP8**: the A100 (SM 8.0) has no FP8 tensor cores, and vLLM
decompresses such weights into bf16 on the fly. There would be a saving in memory but none in
speed, while the load here is almost entirely prefill, that is, it rests on exactly the operations
FP8 does not accelerate on Ampere. An fp8 KV cache (`--kv-cache-dtype fp8`) is a different matter:
it works, but our KV is tiny — the answers are short and all the mass is in the pictures.

Two more environment flags, without which the server will not come up on this machine: `CUDA_HOME`
(otherwise `nvcc: not found` during the JIT build of flashinfer) and `VLLM_USE_FLASHINFER_SAMPLER=0`
(otherwise the `/usr/local/cuda` headers from CUDA 12.3 do not get on with the nvcc 13.3 from the
pip package). The standard sampler has nothing to build.

Three of the flags here are not cosmetic:

- **`--mm-processor-cache-gb 0`** — mandatory. vLLM's image preprocessor cache falls over with
  `AssertionError: Expected a cached item for mm_hash=…` precisely on images repeated between
  requests, and the overlap of the windows guarantees those. After the crash the engine stops
  answering: the cards are busy, utilisation is zero, the client waits forever.
- **`--limit-mm-per-prompt '{"image": 16}'`** — by default vLLM allows one image per request. With
  a 5 s window and `--settled 0.5` there are 10–11 of them; the headroom up to 16 is needed if the
  window is enlarged.
- **`--max-model-len 32768`** — with `--upscale 2` a 1280×720 frame costs ~900 visual tokens, and
  eleven frames ≈ 10 thousand. Enough with room to spare.

Loading the weights from disk takes about 4 minutes; that is a one-off. **Shutting the server down
after the run is mandatory**, otherwise the cards stay occupied:

```bash
pkill -f 'vllm.entrypoints.openai.api_server'
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader   # should be 0
```

Another model will do too — what matters is support for several images per request and for
structured outputs. The name is passed with the `--model` flag and must coincide with
`--served-model-name`.

## The run

The default server and model are the same as in the section above (`qwen36` at
`http://localhost:8078/v1`), so the flags are needed only if the server is a different one; a
permanent value is conveniently set through `DESCRIBE_API_BASE` and `DESCRIBE_MODEL`.

```bash
PY=/home/user/conda/bin/python3

# 1. a trial on a minute of material — to be looked at by eye before waiting half an hour.
#    A separate --out-prefix is mandatory: the trial will have its own frames directory
$PY tools/describe_video.py <id> --range 900-960 --out-prefix _probe

# 2. the whole video
$PY tools/describe_video.py <id> --workers 16

# 3. finish off the spoiled fragments without replaying the whole video
$PY tools/describe_video.py <id> --redo-bad

# the same with a different server
$PY tools/describe_video.py <id> --api-base http://gpu-node-3:8077/v1 --model qwen3vl
```

### The server on another machine

The frames are cut on the client side and go out in the request as base64, so the server does not
need the video — it is enough for the client to see the port.

```bash
# on the machine with the cards: listen on more than the loopback
NO_PROXY=localhost,127.0.0.1 $ES -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen3.6-35B-A3B --served-model-name qwen36 \
    --host 0.0.0.0 --port 8078 …

# on the machine with the data
$PY tools/describe_video.py <id> --api-base http://gpu-node-3:8078/v1 --model qwen36
```

Two things this breaks on:

- **`--host 0.0.0.0`**. By default vLLM listens on the loopback and the port is closed from
  outside, even though `curl` on the machine itself works.
- **The proxy**. An `HTTP_PROXY` in the environment intercepts even a request to a neighbouring
  host, and the answer will be a 502. The script itself adds the host from `--api-base` to
  `NO_PROXY` and prints a line about it; if the server really must be reached through the proxy,
  set `NO_PROXY` by hand.

The flags that actually decide things:

| flag | default | what it is about |
|---|---|---|
| `--settled SEC` | `0.5` | the frames are chosen by `detect_scenes` in constant-rate mode: a slot of this length, and within the slot the quietest frame from the middle is taken. `0.5` = two frames per second. This is the default source; the flag is needed only to change the rate |
| `--interval SEC` | — | a uniform grid instead of the detector. A deliberate rollback: the grid duplicates static material and loses scenes |
| `--window` / `--stride` | 5 / 4 | the request window and the shift; the difference is the overlap: a second (two frames) with the left neighbour and a second with the right, three seconds of its own |
| `--upscale` | 2 | by how much to stretch the frame before sending; on a 360p source it noticeably helps in reading small text |
| `--workers` | 12 | parallel requests |
| `--max-tokens` | 2600 | the answer budget; on a truncation the retry goes with ×1.8 |
| `--redo-bad` | — | take a finished file and re-request only the fragments with an error, a truncation or a degeneration. It first compares `window`, `stride`, the frame step and `--range` against the previous run and refuses if the cut is different — before touching any frames |
| `--range A-B` | — | restrict to a stretch, may be repeated |
| `--out-prefix` | `description` | the name of the output files; for trials `_probe` is convenient |

## What it costs

A 32-minute video: 3878 frames, 485 requests, **20 minutes** on two A100s (`Qwen3.6-35B-A3B`, vLLM
0.27.1). What counts is not the minutes of video but the pictures: because of the overlap each
frame goes to the server 1.29 times on average, which is ~4.5 million visual tokens of prefill. The
median request takes 24 seconds (p90 40, maximum 61), and that is almost entirely prefill.

The levers, if it is expensive:

- `--upscale 1` — four times fewer tokens per frame (225 instead of 900), and the run falls to
  about twenty minutes. A direct trade against the readability of small text;
- `--stride 5` — a fifth fewer requests at the price of giving up the overlap entirely: there will
  be nothing left to cross-check neighbouring descriptions against each other with;
- `--settled 1.0` — half as many frames, but then the per-second description rests on one frame per
  second.

## What is in the output file

The first line of `description.jsonl` is a `meta` with the run parameters. After that, one record
per fragment:

```json
{"chunk_index": 302, "t_start": 906.4, "t_end": 910.5,
 "frame_times": [906.4, 906.9, ...],
 "begin": "...", "end": "...",
 "events": [{"t": 909, "text": "On the right, log₂(p) = log₂(2⁻ⁿ) appears."}],
 "screen_text": {"909": [{"text": "log₂(p) = −n", "location": "right"}]}}
```

`location` is one of nine: `up-left`, `up`, `up-right`, `left`, `center`, `right`, `down-left`,
`down`, `down-right`. The key `"?"` in `screen_text` means the model assigned the element a second
outside the fragment.

The fields that show a defect: `error` (the fragment was not obtained), `degenerate` (the model
went into repetition even after three attempts), `truncated` (the answer was cut off by the token
limit and partly salvaged). In the markdown such fragments carry a warning.

## When something goes wrong

**`502 Bad Gateway` against a local server.** An `HTTP_PROXY` is set in the environment, and a
request to your own `localhost` goes outside. The script adds `NO_PROXY` for local addresses
itself, but the server has to be told this at launch.

**The client hangs, the GPUs are busy, utilisation is zero.** This is the crashed `mm_hash` assert:
raise the server with `--mm-processor-cache-gb 0`.

**Plenty of `degenerate answer, asking again`.** The model goes into repetition on uniform scenes
(lattices of bits, rows of arrows). Three attempts with a growing `repetition_penalty` are already
built in. On `Qwen3-VL-30B-A3B` 7% of the fragments remained unfixable; on `Qwen3.6-35B-A3B` not
one out of 485. If there are any, they are marked `degenerate` rather than passed off as normal.

**`answer truncated`.** We hit `--max-tokens`. The retry goes with an increased budget, and if that
does not help either, everything that managed to close is salvaged from the unfinished JSON and the
record is marked `truncated`.

**The number of frames is not what was expected.** With `--settled` and `--times`, `--range` cuts
the list of times before the cutting; with `--interval` the whole video is cut and the surplus is
discarded afterwards. In both cases the frames directory is cleaned of the previous cut: there is
never a mixture of two runs in it.

**Two runs over one video at the same time.** The frames directory depends on `--out-prefix`: a
full run cuts into `frames_desc/`, a trial with `--out-prefix _probe` into `frames_desc__probe/`.
They used to share one directory, and the trial would wipe the frames of a full run going on
alongside — which then died with a `FileNotFoundError` halfway through.

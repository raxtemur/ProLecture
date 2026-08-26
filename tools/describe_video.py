#!/usr/bin/env python3
"""A dense description of the video track, aligned to time.

The task: give the annotator and the reviewer a document like subtitles, but with a
detailed description of what is happening on the screen instead of utterances. Then at
most steps of the annotation one can read text instead of looking through dozens of
frames.

How it works
------------
The video is cut into windows of `--window` seconds with a shift of `--stride`, that is,
with an overlap: the edge seconds are described by both neighbouring fragments. The
frames of a window go out in a single request to a VLM (an OpenAI-compatible server, for
example vLLM), and the requests run in parallel.

The answer is strict JSON against a schema held by the server itself (guided decoding):
`begin` (the state of the screen at the start), `events` (one record per second),
`screen_text` (`{t, text, location}` — the verbatim text from the screen and its place in
the frame), `end`. There is no need to parse free text with regular expressions.

The source of frames is pluggable: `--settled` (scene detection in constant-rate mode —
the recommended one), a uniform cut with our own ffmpeg (`--interval`), a ready
directory (`--frames-dir`) or a list of times (`--times`). The script knows nothing about
how the times were chosen — only that every frame has a moment in seconds.

The narrator's speech is NOT shown to this model: only the frames go into the request,
and the video's subtitles do not reach the prompt by default. The model describes what it
sees and does not know what is being said at that moment.

This is done for the sake of the annotation pipeline. The finished description is given
to the vision-only probe instead of a dense cut of frames — that is cheaper, and it is
legitimate precisely because there is no sound in the description. Were the model to
start listening to the subtitles, the index would stop being a function of the visual
channel, it could no longer be given to the probe, and the `audio_dependency` label,
derived from that probe's answer, would start measuring the wrong thing. The
`--with-transcript` flag exists, but it should not be switched on for benchmark material.

Examples (the client is base conda; it needs only openai and Pillow)
-------
    PY=/home/user/conda/bin/python3

    # the whole video: two quiet frames per second, windows of 5 s with a shift of 3
    $PY tools/describe_video.py l6DKRf-fAAM --settled 0.5 --workers 16

    # a trial on a stretch before a long run
    $PY tools/describe_video.py l6DKRf-fAAM --settled 0.5 --range 900-960 --out-prefix _probe

    # re-request only the spoiled fragments of a finished run
    $PY tools/describe_video.py l6DKRf-fAAM --settled 0.5 --redo-bad

How to raise the server and what to do when it falls over — docs/video_description.md.

Output: data/bundles/<id>/description.jsonl (machine-readable, the main one) and
        data/bundles/<id>/description.md (for a human/agent to read).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "data" / "videos"
BUNDLES_DIR = ROOT / "data" / "bundles"

# two frames per second: one second of description rests on two states of the screen,
# and that is enough to catch the moment a formula is finished
DEFAULT_SETTLED = 0.5

def rel_path(path: Path) -> str:
    """The path for writing into the jsonl: relative to the root of the repository if the
    frame is inside it, otherwise absolute — the frames directory may be kept outside."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


# t00120.jpg -> 120.0, t000907.50.jpg -> 907.5
FRAME_TIME_RE = re.compile(r"t(\d+(?:\.\d+)?)")


# ------------------------------------------------------------------- the prompt

SYSTEM_PROMPT = """\
You are an assistant keeping a frame-by-frame transcript of the video track of a \
mathematics lecture (animation in the 3Blue1Brown style: a black background, formulas, \
graphs, diagrams).

Your only task is to write down what is VISIBLE in the frames. This is not a retelling \
of the topic and not an explanation of the mathematics. Write in English; formulas, \
captions and any text from the screen go in the original (in LaTeX-like notation, for \
example `p_i`, `-\\log_2 p_i`, `\\sum_i`).

Iron rules:
1. Never make things up. If a symbol, an index or a number cannot be read, write \
"illegible" and describe what is visible (how many characters, where it is placed, what \
colour). This applies especially to small captions: tick labels on an axis, labels \
inside segments, text in insets. Do not substitute a "plausible" scale such as \
`0.0, 0.1, ..., 1.0` and do not complete the alphabet from a couple of distinguishable \
letters — either write down what you actually read, or write "the captions are too small \
to read".
2. Do not carry knowledge of the subject into the description. If `H(p)` is on the \
screen, do not write "entropy", write `H(p)`. You do not know what the narrator is \
talking about.
3. Do not write meta-comments ("these frames show…", "the explanation continues").
4. Numbers, axis labels, scale ticks, legends, values in tables and bars are to be \
copied verbatim, together with the binding "what → which value".
5. Name a number only if it is WRITTEN on the screen. Do not convert the height of a bar, \
the length of a segment or the value of a point on a graph into a number "by eye": write \
"higher than its neighbour", "roughly up to the third gridline", "the tallest of all". \
An invented number is worse than an omission: the annotation breaks on it silently.
6. Between neighbouring frames note precisely the CHANGES: what appeared, what \
disappeared, what got highlighted/changed colour, what moved.
7. If there are many elements of one kind (letters, bars, circles), do not enumerate them \
all: name how many there are, the first and the last, and what is in between. No more \
than 12 elements in one enumeration, and no element is repeated twice.
8. Do NOT copy a continuously changing background verbatim. Ribbons of random bits, \
crawling example strings, flickering sets of symbols are noise: their content changes by \
itself and means nothing. Do not put them into `screen_text` at all; mention them in one \
phrase in `begin`/`end` ("a ribbon of random bits at the top, changing every frame"), and \
in `events` write about them only if nothing else happened in that second, and then as \
"the ribbon of bits changed", without the digits themselves. The event "a formula \
appeared" always matters more than the event "the random bits changed": if both happened \
in one second, write about the formula.
"""

USER_PROMPT = """\
Fragment {chunk_index} of the video. Below are {n_frames} frames, each preceded by its \
moment in seconds; they cover the interval {shown_start}–{shown_end} s. The edge seconds \
of the interval are described in the neighbouring fragments as well — that is deliberate, \
describe them on a par with the rest.{transcript_block}

The answer is JSON against the given schema, four fields:

`begin` — what is on the screen in the first frame of the fragment. A full inventory: all \
formulas verbatim, all captions, the axes and their labels, the numbers, the objects and \
their relative placement. If the screen is empty, say so.

`events` — exactly one record for each second in the list: {second_list}. Precisely those \
integers, in increasing order, with no gaps; do not take the second from a frame's caption \
— there are usually two frames per second and they are described by one record. \
In `text` — what changed during that second: appeared, disappeared, got highlighted, \
moved, was added to a formula. One sentence, briefly — do not retell what is already \
described in `begin`. A second with no changes: "no changes".

`screen_text` — one record per text element: a formula, a caption, a number, an axis \
label. `t` is the second where the element is first visible in this fragment (if it hangs \
there for the whole fragment, the first one is enough). `text` is verbatim; write the \
unreadable as "illegible". `location` is where it is on the screen. If there is no text \
on the screen, leave the list empty.

`end` — one or two sentences: what remains on the screen in the last frame and how it \
differs from `begin`. Do not rewrite `begin` in full.
"""


# The schema is held by the server itself (vLLM, guided decoding): the model
# physically cannot emit invalid JSON, set a fractional second or invent a position
# outside the enumeration. These four fields used to be pulled out of free text with
# regular expressions, and a single Latin "K" in a heading took a whole block into the
# wrong field.
LOCATIONS = ["up-left", "up", "up-right", "left", "center", "right",
             "down-left", "down", "down-right"]

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["begin", "events", "screen_text", "end"],
    "properties": {
        "begin": {"type": "string"},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["t", "text"],
                "properties": {
                    "t": {"type": "integer", "minimum": 0},
                    "text": {"type": "string"},
                },
            },
        },
        "screen_text": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["t", "text", "location"],
                "properties": {
                    "t": {"type": "integer", "minimum": 0},
                    "text": {"type": "string"},
                    "location": {"enum": LOCATIONS},
                },
            },
        },
        "end": {"type": "string"},
    },
}

# There is no separate "context frame" any more: the windows overlap as it is, and
# neighbouring fragments see the shared seconds in full. A `context` field used to be
# created but always stayed None — the prompt about the context never went out once, and
# the `--no-context-frame` flag switched nothing off.


# --------------------------------------------------------------- utilities

def fmt_t(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.1f}"


def hhmmss(value: float) -> str:
    total = int(value)
    return f"{total // 60:02d}:{total % 60:02d}" if total < 3600 else \
        f"{total // 3600:d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def encode_image(path: Path, upscale: int = 1) -> str:
    """A base64 data URL. upscale>1 stretches the frame — on 360p videos that noticeably
    helps the VLM make out small indices, because the ViT cuts more patches."""
    raw = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    if upscale > 1:
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img = img.resize((img.width * upscale, img.height * upscale),
                             Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            raw, mime = buf.getvalue(), "image/jpeg"
        except Exception as exc:  # no PIL or the picture is broken — send it as it is
            print(f"[warn] could not upscale {path.name}: {exc}", file=sys.stderr)
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


# --------------------------------------------------------- the frame sources

def frames_from_dir(directory: Path) -> list[tuple[float, Path]]:
    out: list[tuple[float, Path]] = []
    for p in sorted(directory.iterdir()):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png") or not p.is_file():
            continue
        m = FRAME_TIME_RE.match(p.stem)
        if not m:
            print(f"[warn] skipping {p.name}: the name is not of the form tSSSSS[.ss]", file=sys.stderr)
            continue
        out.append((float(m.group(1)), p))
    return sorted(out)


def times_from_file(path: Path) -> list[float]:
    """A tolerant parse of a list of times: somebody else's scene detector may return anything."""
    text = path.read_text(encoding="utf-8").strip()
    times: list[float] = []
    if text.startswith(("{", "[")):
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("times", "frames", "scenes", "cuts", "keyframes", "boundaries"):
                if key in data:
                    data = data[key]
                    break
            else:
                raise SystemExit(f"{path}: the object has no times/frames/scenes/cuts key")
        for item in data:
            if isinstance(item, (int, float)):
                times.append(float(item))
            elif isinstance(item, dict):
                for key in ("t", "time", "start", "start_time", "sec", "timestamp"):
                    if key in item:
                        times.append(float(item[key]))
                        break
    else:
        for line in text.splitlines():
            line = line.strip().rstrip("s")
            if line and not line.startswith("#"):
                times.append(float(line))
    if not times:
        raise SystemExit(f"{path}: could not extract a single time")
    return sorted(set(times))


def cut_uniform(mp4: Path, out_dir: Path, interval: float, duration: float,
                force: bool = False) -> list[tuple[float, Path]]:
    """A uniform cut in a single ffmpeg pass — an order of magnitude faster than seeking per frame."""
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = frames_from_dir(out_dir)
    expected = int(duration / interval) + 1
    # comparing the count is not enough: the directory may hold a cut with a different
    # step (or by a list of times from the scene detector), and then "reuse" silently
    # substitutes the source of the frames
    step_ok = False
    if len(existing) > 2:
        steps = sorted(b - a for (a, _), (b, _) in zip(existing, existing[1:]))
        step_ok = abs(steps[len(steps) // 2] - interval) < 0.05
    if existing and step_ok and not force and len(existing) >= expected - 2:
        print(f"[frames] taking the ready {len(existing)} from {out_dir} (--force-frames to re-cut)")
        return existing
    for p in out_dir.glob("*.jpg"):
        p.unlink()
    print(f"[frames] cutting {mp4.name} every {interval} s -> {out_dir}")
    # showinfo gives the real pts of every frame emitted: the file name is then not the
    # assumption "i * interval" but a measured time. For videos whose stream does not
    # begin at zero this is the only honest way.
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(mp4),
         "-vf", f"fps=1/{interval},showinfo", "-q:v", "3",
         str(out_dir / "seq%06d.jpg"), "-y"],
        check=True, capture_output=True, text=True,
    )
    pts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]
    frames = []
    for i, src in enumerate(sorted(out_dir.glob("seq*.jpg"))):
        t = pts[i] if i < len(pts) else i * interval
        dst = out_dir / f"t{t:09.2f}.jpg"
        src.rename(dst)
        frames.append((t, dst))
    if len(pts) != len(frames):
        print(f"[warn] showinfo gave {len(pts)} marks for {len(frames)} frames; "
              f"for the surplus the time was computed as i*{interval}", file=sys.stderr)
    return frames


def cut_at_times(mp4: Path, out_dir: Path, times: list[float], workers: int = 8,
                 force: bool = False) -> list[tuple[float, Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    # the directory must not be a mixture of two cuts: nobody will see the surplus frames
    # in the index, but they are exactly what is found by eye by whoever opens the directory
    wanted = {f"t{t:09.2f}.jpg" for t in times}
    stale = [f for f in out_dir.glob("t*.jpg") if f.name not in wanted]
    if stale:
        print(f"[frames] {out_dir} holds {len(stale)} frames of a previous cut — removing them")
        for f in stale:
            f.unlink()

    def one(t: float) -> tuple[float, Path] | None:
        dst = out_dir / f"t{t:09.2f}.jpg"
        if not dst.exists() or force:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4),
                 "-frames:v", "1", "-q:v", "3", str(dst), "-y"],
                check=False,
            )
        return (t, dst) if dst.exists() else None

    print(f"[frames] extracting {len(times)} frames by the list of times -> {out_dir}")
    out: list[tuple[float, Path]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(one, times):
            if res:
                out.append(res)
    lost = len(times) - len(out)
    if lost:
        # a silent omission later looks like "the model noticed nothing"
        print(f"[warn] ffmpeg did not return {lost} frames out of {len(times)} — "
              f"there will be a hole in the description at those seconds", file=sys.stderr)
    return sorted(out)


# ------------------------------------------------------------------ the chunks

def build_chunks(frames: list[tuple[float, Path]], window: float,
                 stride: float) -> list[dict]:
    """Windows of fixed length with a shift of `stride` — that is, with an overlap.

    The overlap is not a luxury: without it every window ends on a frame beyond which the
    model sees nothing, and the boundary of the window systematically catches an
    unfinished animation. The seconds of the overlap are described by BOTH neighbouring
    fragments, and that is deliberate: the edge frames are then the responsibility not of
    "nobody, by halves" but of two descriptions at once, and they can be cross-checked.

    The boundaries are half-open: a window with `window=5` and a shift of `stride=4`
    covers the seconds N…N+4, of which N is shared with the left neighbour, N+4 with the
    right one, and N+1…N+3 are its own. While the right boundary was inclusive, the
    window captured six seconds and with a shift of 3 there were no seconds of its own at
    all: every second was described twice, and three times more went into prefill than
    was ordered.
    """
    chunks: list[dict] = []
    if not frames:
        return chunks
    first_t, last_t = frames[0][0], frames[-1][0]
    start = first_t
    while start < last_t + 1e-6:
        end = start + window
        group = [(t, p) for t, p in frames if start - 1e-6 <= t < end - 1e-6]
        # a window all of whose frames have already been shown to the previous fragment
        # has nothing to describe. We check containment specifically, not the number of
        # frames: a single frame in a sparse place is a frame too, and it must not be
        # lost silently
        if group and chunks and group[-1][0] <= chunks[-1]["t_end"] + 1e-6:
            group = []
        if group:
            chunks.append({
                "chunk_index": len(chunks),
                "t_start": round(group[0][0], 2),
                "t_end": round(group[-1][0], 2),
                "frame_times": [round(t, 2) for t, _ in group],
                "paths": [p for _, p in group],
            })
        start += stride
    return chunks


def transcript_slice(cues: list[dict], t0: float, t1: float) -> str:
    picked = [c for c in cues if c["end"] > t0 and c["start"] < t1]
    if not picked:
        return ""
    body = " ".join(c["text"] for c in picked)
    return ("\n\nThe narrator's speech over this interval (BACKGROUND ONLY, it must not be described, "
            f"it may not be on the screen): «{body}»")


# ------------------------------------------------------------------ parsing

# The ribbon of random bits over the scene is the only "text" the model copies
# verbatim in defiance of rule 8: it is large and high-contrast. The annotator cannot
# check it anyway, while it takes up room in the index.
#
# The threshold is 20 rather than 12: the video is about coding, and sixteen zeros in the
# record `0000000000000000 -> m_0` (142 such elements in the pilot) are substantive.
# Besides, structural runs (all zeros, a short period) are not cut at all: the ribbon is
# random, whereas meaningful strings are almost always regular.
BITS_RE = re.compile(r"[01]{20,}")


def _structured(bits: str) -> bool:
    """A binary run that looks like data rather than like ribbon noise."""
    for period in range(1, 5):
        if len(bits) >= 2 * period and all(
                c == bits[i % period] for i, c in enumerate(bits)):
            return True
    return False


def strip_bits(text: str) -> str:
    """Cuts out the ribbon of random bits, leaving the meaningful binary records.

    It is applied NOT when writing but when displaying: the `.jsonl` stores what the
    model said, verbatim. Otherwise a genuine binary code word — and the video is
    precisely about coding — would be lost forever, and getting it back would cost twenty
    minutes on two A100s.

    Readers that the ribbon gets in the way of (the markdown of the same run, the index of
    on-screen text in the reviewer's working folder) call it themselves.
    """
    out = BITS_RE.sub(lambda m: m.group(0) if _structured(m.group(0)) else "…", text)
    return re.sub(r"\s{2,}", " ", out).strip()


def repair_json(text: str):
    """Extracts the data from an answer truncated by the token limit.

    A strict schema cuts both ways: free text lost its tail on a truncation, whereas JSON
    stops parsing entirely and the whole fragment is lost. Here the answer is trimmed at
    the last closed element and the brackets are closed; of twenty seconds of description
    the last one or two are lost instead of all of them.
    """
    for cut in range(len(text) - 1, 0, -1):
        if text[cut] != "}":
            continue
        prefix = text[:cut + 1]
        stack, in_str, esc = [], False, False
        for ch in prefix:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "[{":
                stack.append(ch)
            elif ch in "]}" and stack:
                stack.pop()
        if in_str:
            continue
        closed = prefix + "".join("]" if b == "[" else "}" for b in reversed(stack))
        try:
            return json.loads(closed)
        except json.JSONDecodeError:
            continue
    return None


def normalize(payload: dict, span: tuple[float, float]) -> dict:
    """Brings the model's answer into the form of a fragment record.

    The schema has been checked by the server, so this is not parsing but arranging: the
    events are sorted by second and the on-screen text is grouped by second. Everything
    that fell outside its own fragment goes into the key `"?"` — the model sometimes
    assigns an element a second belonging to a neighbouring window, and such a key is
    better than a silent shift in the index.
    """
    # the upper boundary is exactly the one asked about in the prompt
    # (`range(int(t_start), int(t_end) + 1)`): a second beyond it already belongs to the
    # neighbouring window, and the semi-blind reviewer must not see it across the boundary
    # of the cut
    lo, hi = int(span[0]), int(span[1])

    events = []
    for ev in payload.get("events", []):
        t = int(ev.get("t", -1))
        text = str(ev.get("text", "")).strip()
        if not text:
            continue
        events.append({"t": t if lo <= t <= hi else None, "text": text})
    events.sort(key=lambda e: (e["t"] is None, e["t"] or 0))

    screen: dict[str, list[dict]] = {}
    for item in payload.get("screen_text", []):
        text = str(item.get("text", "")).strip().strip("`").strip()
        if not text or text.lower() in ("none", "-", "—"):
            continue
        t = int(item.get("t", -1))
        key = str(t) if lo <= t <= hi else "?"
        screen.setdefault(key, []).append(
            {"text": text, "location": item.get("location")})

    return {
        "begin": str(payload.get("begin", "")).strip(),
        "end": str(payload.get("end", "")).strip(),
        "events": events,
        "screen_text": screen,
    }


SPLIT_ITEM_RE = re.compile(r"[,;]\s*")


def line_is_runaway(line: str) -> bool:
    """A string in which the model has gone into a loop.

    We diagnose by repetitions rather than by length: a long string with an honest list of
    different formulas is normal, whereas `*`, `(`, `)`, `+`, `*`, `(`, `)`, `+`, ... is a
    decoder loop. On such frames of a 360p video the captions physically cannot be read,
    and the model fills the emptiness with plausible rubbish.
    """
    if len(line) < 200:
        return False
    # a loop with no separators: "→←↓↑↑→←↓↑↑→←↓↑↑…". We catch it by the share of unique 4-grams
    grams = [line[i:i + 4] for i in range(len(line) - 3)]
    if grams and len(set(grams)) / len(grams) < 0.15:
        return True
    if len(line) < 300:
        return False
    items = [i.strip(" `") for i in SPLIT_ITEM_RE.split(line) if i.strip(" `")]
    if len(items) < 20:
        return False
    return len(set(items)) / len(items) < 0.6


def payload_text(payload: dict) -> str:
    """Only what the model wrote, without the JSON scaffolding.

    Degeneration must not be counted over the serialised answer: there every element comes
    with a `"location": "left"}`, and on a rich fragment the share of repetitions drifts
    below the threshold by itself. In the pilot, exactly the most substantive fragments
    got marked "degenerate" this way — twice as much on-screen text as the clean ones.
    """
    parts = [str(payload.get("begin", "")), str(payload.get("end", ""))]
    parts += [str(e.get("text", "")) for e in payload.get("events", [])]
    parts += [str(i.get("text", "")) for i in payload.get("screen_text", [])]
    return "\n".join(p for p in parts if p)


def looks_degenerate(text: str) -> bool:
    if any(line_is_runaway(line) for line in text.splitlines()):
        return True
    # a loop can be multi-line too: three dozen identical short lines, each of them
    # innocent on its own
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15]
    if len(lines) >= 10 and len(set(lines)) / len(lines) < 0.5:
        return True
    return False


def describe_chunk(client, model: str, chunk: dict, cues: list[dict],
                   max_tokens: int, temperature: float, upscale: int,
                   retries: int = 3) -> dict:
    frames = list(zip(chunk["frame_times"], chunk["paths"]))

    content: list[dict] = [{
        "type": "text",
        "text": USER_PROMPT.format(
            chunk_index=chunk["chunk_index"],
            n_frames=len(frames),
            shown_start=fmt_t(chunk["t_start"]),
            shown_end=fmt_t(chunk["t_end"]),
            second_list=", ".join(
                str(x) for x in range(int(chunk["t_start"]),
                                      int(chunk["t_end"]) + 1)),

            transcript_block=transcript_slice(cues, chunk["t_start"], chunk["t_end"]) if cues else "",
        ),
    }]
    for t, path in frames:
        content.append({"type": "text", "text": f"[{fmt_t(t)} s]"})
        content.append({"type": "image_url", "image_url": {"url": encode_image(path, upscale)}})

    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content}]

    base = {
        "chunk_index": chunk["chunk_index"],
        "t_start": chunk["t_start"],
        "t_end": chunk["t_end"],
        "frame_times": chunk["frame_times"],
        "frames": [rel_path(p) for p in chunk["paths"]],
    }

    last: Exception | None = None
    text = ""
    degenerate = False
    truncated = False
    for attempt in range(1, retries + 1):
        # on the second attempt we tighten the penalty and forbid enumerations outright:
        # they are exactly what starts the loop
        penalty = 1.05 if attempt == 1 else 1.2
        # a retry with the same max_tokens will hit the same wall; on a truncation by
        # length the budget must be raised, on a loop it must not — there the penalty helps
        # the budget grows with every attempt: a retry with the same limit hit the same
        # wall, and the third attempt was a copy of the second
        budget = int(max_tokens * (1.8 ** (attempt - 1))) if truncated else max_tokens
        msgs = messages
        if attempt > 1 and degenerate:
            msgs = messages + [
                {"role": "assistant", "content": text[:400]},
                {"role": "user", "content":
                    "You have gone into an endless repetition. Rewrite the answer from scratch in the same "
                    "structure, but do not enumerate small captions at all: where they "
                    "cannot be read, write in one phrase \"the small captions cannot be read\". "
                    "No list longer than 12 items."},
            ]
        try:
            started = time.time()
            resp = client.chat.completions.create(
                model=model, messages=msgs,
                max_tokens=budget, temperature=temperature, top_p=0.9,
                # the schema is held by the server: the grammar will not let it emit
                # broken JSON, a fractional second or a position outside the enumeration
                response_format={"type": "json_schema", "json_schema": {
                    "name": "fragment", "schema": RESPONSE_SCHEMA, "strict": True}},
                # without a penalty the model goes into a loop on uniform scenes and
                # prints one element hundreds of times, eating the whole token budget
                extra_body={"repetition_penalty": penalty},
                presence_penalty=0.2,
            )
            text = (resp.choices[0].message.content or "").strip()
            latency = round(time.time() - started, 2)
            truncated = bool(resp.choices) and resp.choices[0].finish_reason == "length"
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                # on a truncation by length the JSON is left unfinished — that is not
                # "the model answered badly" but "the budget ran out"
                if attempt < retries:
                    print(f"[warn] chunk {chunk['chunk_index']}: the answer was truncated, "
                          f"asking again ({attempt}/{retries})", file=sys.stderr)
                    continue
                payload = repair_json(text)
                if payload is None:
                    return dict(base, latency_s=latency, error="truncated JSON",
                                raw=text[:2000], begin="", end="", events=[], screen_text={})
                record = dict(base, latency_s=latency, truncated=True)
                record.update(normalize(payload, (chunk["t_start"], chunk["t_end"])))
                return record
            # these are two different defects: a loop is cured by the penalty, a
            # truncation by the budget. A merged label both lied in the report and served
            # the reproach "you have gone into repetition" to a model that simply did not
            # fit into max_tokens
            degenerate = looks_degenerate(payload_text(payload))
            if (degenerate or truncated) and attempt < retries:
                why = "a degenerate answer" if degenerate else "the answer was truncated by the limit"
                print(f"[warn] chunk {chunk['chunk_index']}: {why}, "
                      f"asking again ({attempt}/{retries})", file=sys.stderr)
                continue
            record = dict(base, latency_s=latency)
            if truncated:
                record["truncated"] = True
            record.update(normalize(payload, (chunk["t_start"], chunk["t_end"])))
            if degenerate:
                # the answer is skewed anyway — let both the human and the code see it
                record["degenerate"] = True
            return record
        except Exception as exc:
            last = exc
            print(f"[warn] chunk {chunk['chunk_index']}: attempt {attempt}/{retries}: {exc}",
                  file=sys.stderr)
            if attempt < retries:
                time.sleep(2.0 * attempt)
    return dict(base, error=str(last), begin="", end="",
                events=[], screen_text={})


# -------------------------------------------------------------------- output

def write_markdown(path: Path, meta: dict, records: list[dict]) -> None:
    chapters = meta.get("chapters") or []

    def chapter_of(t: float) -> str:
        for c in chapters:
            if c["start"] <= t < c["end"]:
                return c["title"]
        return ""

    lines = [
        f"# Description of the video track — {meta.get('title', meta['video_id'])}",
        "",
        f"Video `{meta['video_id']}`, duration {meta['duration']:.0f} s. "
        f"Fragments {len(records)}, frames {meta.get('n_frames', '?')} "
        f"(sends to the server {sum(len(r.get('frame_times', [])) for r in records)}).",
        "",
        f"Model `{meta['model']}`, window {meta.get('window')} s with a shift of "
        f"{meta.get('stride')} s (overlap {meta.get('overlap')} s), "
        f"frame step {meta.get('frame_step', '?')} s, transcript in the prompt: "
        f"{'yes' if meta.get('with_transcript') else 'no'}.",
        "",
        "The description was generated by a model and contains its mistakes. Verbatim text from "
        "the screen must be re-checked against the frame if a sample is built on it.",
        "",
    ]
    prev_chapter = None
    for rec in records:
        ch = chapter_of(rec["t_start"])
        if ch != prev_chapter:
            lines += ["", f"## [{fmt_t(rec['t_start'])}s] {ch or '—'}", ""]
            prev_chapter = ch
        lines.append(
            f"### [{fmt_t(rec['t_start'])}–{fmt_t(rec['t_end'])} s]  "
            f"({hhmmss(rec['t_start'])}–{hhmmss(rec['t_end'])})"
        )
        lines.append("")
        if rec.get("error"):
            lines += [f"*(request error: {rec['error']})*", ""]
            continue
        if rec.get("degenerate"):
            lines += ["> The model went into repetition even after being asked again — this fragment "
                      "is not to be trusted, look at the frames.", ""]
        if rec.get("begin"):
            lines += ["**Beginning.** " + strip_bits(rec["begin"].replace("\n", " ")), ""]
        if rec.get("events"):
            lines.append("**Events.**")
            lines.append("")
            for ev in rec["events"]:
                mark = f"`{fmt_t(ev['t'])}s`" if ev["t"] is not None else "`?`"
                lines.append(f"- {mark} {strip_bits(ev['text'])}")
            lines.append("")
        if rec.get("screen_text"):
            lines.append("**Text on the screen.**")
            lines.append("")
            for sec in sorted(rec["screen_text"], key=lambda k: (k == "?", k.isdigit() and int(k))):
                for item in rec["screen_text"][sec]:
                    where = f" — {item['location']}" if item.get("location") else ""
                    mark = f"`{sec}s`" if sec != "?" else "`?`"
                    shown = strip_bits(item["text"])
                    if not shown or shown.strip("… ") == "":
                        continue
                    lines.append(f"- {mark} `{shown}`{where}")
            lines.append("")
        if rec.get("end"):
            lines += ["**End.** " + strip_bits(rec["end"].replace("\n", " ")), ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- main

def parse_ranges(values: list[str]) -> list[tuple[float, float]]:
    out = []
    for v in values or []:
        m = re.match(r"^(\d+(?:\.\d+)?)\s*[-–:]\s*(\d+(?:\.\d+)?)$", v.strip())
        if not m:
            raise SystemExit(f"--range {v!r}: the form expected is 120-360")
        out.append((float(m.group(1)), float(m.group(2))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_id", help="a youtube-id; data/videos/<id>/<id>.mp4 is looked for")
    ap.add_argument("--mp4", help="a path to the mp4, if it does not sit where the pipeline expects")

    src = ap.add_mutually_exclusive_group()
    src.add_argument("--interval", type=float, default=None,
                     help="a uniform cut, the step in seconds. A deliberate rollback: "
                          "the grid both duplicates static material and loses scenes; "
                          "by default the frames come from the detector")
    src.add_argument("--frames-dir", help="a ready frames directory with names tSSSSS[.ss].jpg")
    src.add_argument("--times", help="a file with a list of times (json/txt), e.g. the output of detect_scenes.py")
    src.add_argument("--settled", type=float, metavar="SEC",
                     help="the frames are chosen by detect_scenes in constant-rate mode: "
                          "a slot of this length, with the quietest frame taken within the slot "
                          "(0.5 = two frames per second). It leaves no holes, and no half-frames either")

    ap.add_argument("--force-frames", action="store_true", help="re-cut the frames even if they are there")
    ap.add_argument("--range", action="append", dest="ranges",
                    help="restrict to a stretch, e.g. 0-300; may be repeated")
    ap.add_argument("--window", type=float, default=5.0,
                    help="the length of one request's window, seconds")
    ap.add_argument("--stride", type=float, default=4.0,
                    help="the shift of the window, seconds; a window of 5 with a shift of 4 gives a second "
                         "of overlap with the left neighbour and a second with the right one, "
                         "and three seconds of its own")
    ap.add_argument("--workers", type=int, default=12, help="parallel requests")
    # the defaults coincide with the server described in docs/video_description.md,
    # the one description.jsonl was assembled on
    ap.add_argument("--model", default=os.environ.get("DESCRIBE_MODEL", "qwen36"))
    ap.add_argument("--api-base", default=os.environ.get("DESCRIBE_API_BASE",
                                                         "http://localhost:8078/v1"))
    ap.add_argument("--max-tokens", type=int, default=2600,
                    help="the answer budget; on a truncation the retry goes with ×1.8")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--upscale", type=int, default=2,
                    help="by how much to stretch the frame before sending (360p -> 720p)")
    ap.add_argument("--with-transcript", action="store_true",
                    help="feed the narrator's speech as background (off by default: see the docstring)")
    ap.add_argument("--out-prefix", default="description")
    ap.add_argument("--limit-chunks", type=int, default=0, help="debugging: only the first N chunks")
    ap.add_argument("--redo-bad", action="store_true",
                    help="re-request only the fragments with an error, a truncation or a "
                         "degeneration from an already finished file, and take the rest as they are")
    args = ap.parse_args()

    # with no explicit source the frames come from the detector in slot mode: a uniform
    # grid by default is exactly what was moved away from in make_bundle.py
    if args.interval is None and not (args.frames_dir or args.times or args.settled):
        args.settled = DEFAULT_SETTLED

    vid = args.video_id
    mp4 = Path(args.mp4) if args.mp4 else VIDEOS_DIR / vid / f"{vid}.mp4"
    bdir = BUNDLES_DIR / vid
    bdir.mkdir(parents=True, exist_ok=True)

    bundle = {}
    bundle_path = bdir / "bundle.json"
    if bundle_path.exists():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    duration = float(bundle.get("duration") or 0)
    if not duration:
        if not mp4.exists():
            raise SystemExit(f"neither {bundle_path} nor {mp4}: nowhere to take the duration from")
        duration = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(mp4)],
            capture_output=True, text=True, check=True).stdout.strip())

    ranges = parse_ranges(args.ranges)
    if args.settled is not None and args.settled <= 0:
        raise SystemExit("--settled must be greater than zero")
    if args.interval is not None and args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")
    for a, b in ranges:
        if b <= a:
            raise SystemExit(f"--range {a:g}-{b:g}: the end is not later than the start")

    # every output file gets its own frames directory. Otherwise a trial on a minute of
    # material wipes the cut of a full run right from under it — that is exactly how a run
    # going in parallel with a trial died
    safe_prefix = re.sub(r"[^A-Za-z0-9_.-]", "_", args.out_prefix)
    frames_dir_name = ("frames_desc" if args.out_prefix == "description"
                       else f"frames_desc_{safe_prefix}")

    # the cutting step is known before the cutting, and the --redo-bad compatibility
    # check is obliged to run before the frames directory is touched: otherwise it removes
    # 3878 frames and only then reports that there is nothing to fix
    if args.frames_dir or args.times:
        frame_step = None
    elif args.settled:
        frame_step = args.settled
    else:
        frame_step = args.interval

    meta_probe = {"window": args.window, "stride": args.stride,
                  "frame_step": frame_step, "ranges": [list(r) for r in ranges]}
    prev_records: list[dict] | None = None
    if args.redo_bad:
        prev_path = bdir / f"{args.out_prefix}.jsonl"
        if not prev_path.exists():
            raise SystemExit(f"--redo-bad: no {prev_path}, nothing to fix")
        prev_records = [json.loads(l)
                        for l in prev_path.read_text(encoding="utf-8").splitlines()]
        prev_meta = next((r["meta"] for r in prev_records if "meta" in r), {})
        for key in ("window", "stride", "frame_step", "ranges"):
            if prev_meta.get(key) != meta_probe.get(key):
                raise SystemExit(
                    f"--redo-bad: the previous run was made with {key}={prev_meta.get(key)}, "
                    f"now it is {meta_probe.get(key)} — the cut is different, nothing to fix")

    def in_ranges(t: float) -> bool:
        return not ranges or any(a <= t < b for a, b in ranges)

    # --- the frames
    if args.frames_dir:
        frames = frames_from_dir(Path(args.frames_dir).resolve())
        frame_step = None
        if not frames:
            raise SystemExit(f"{args.frames_dir}: no frames found")
    elif args.settled or args.times:
        if not mp4.exists():
            raise SystemExit(f"no {mp4}, and the frames have to be cut")
        if args.settled:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import detect_scenes
            print(f"[frames] choosing the quietest frame in each slot of {args.settled} s")
            lo = min((a for a, _ in ranges), default=0.0)
            hi = max((b for _, b in ranges), default=0.0)
            times = [c["t"] for c in detect_scenes.detect(
                mp4, every=args.settled, start=lo, end=hi)]
        else:
            times = times_from_file(Path(args.times))
        times = [t for t in times if in_ranges(t)]
        frames = cut_at_times(mp4, bdir / frames_dir_name, times,
                              workers=args.workers, force=args.force_frames)
    else:
        if not mp4.exists():
            raise SystemExit(f"no {mp4}")
        frames = cut_uniform(mp4, bdir / frames_dir_name, args.interval, duration,
                             force=args.force_frames)

    if ranges:
        frames = [(t, p) for t, p in frames if in_ranges(t)]
        if not frames:
            raise SystemExit("after --range not a single frame is left")

    if args.stride <= 0:
        raise SystemExit("--stride must be greater than zero, otherwise the windows do not move")
    if args.stride > args.window:
        print(f"[warn] --stride {args.stride} is larger than --window {args.window}: there will be "
              f"undescribed holes between the fragments", file=sys.stderr)
    chunks = build_chunks(frames, args.window, args.stride)
    if args.limit_chunks:
        chunks = chunks[:args.limit_chunks]

    print(f"[plan] frames {len(frames)}, fragments {len(chunks)}, window {args.window} s "
          f"with a shift of {args.stride} s, threads {args.workers}, model {args.model}")

    # An HTTP_PROXY is set in the environment, and without this a request to our own
    # server goes outside and comes back as a 502 Bad Gateway. The symptom looks like
    # "the server did not come up", although it did.
    host = re.sub(r"^https?://", "", args.api_base).split(":")[0].split("/")[0]
    current = os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "")
    parts = [p for p in current.split(",") if p]
    for extra in ("localhost", "127.0.0.1", host):
        if extra and extra not in parts:
            parts.append(extra)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = ",".join(parts)
    if host not in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        # a server on a neighbouring machine — the same 502, only there would be
        # nobody to fix it by hand: the proxy does not know the host name
        print(f"[net] {host} added to NO_PROXY. If the server really must be reached "
              f"through the proxy, set NO_PROXY yourself", file=sys.stderr)

    from openai import OpenAI

    client = OpenAI(api_key="EMPTY", base_url=args.api_base, timeout=1800, max_retries=0)
    cues = bundle.get("transcript", []) if args.with_transcript else []

    started = time.time()
    records: list[dict] = []
    done = 0

    kept: dict[int, dict] = {}
    if prev_records is not None:
        for rec in prev_records:
            if "chunk_index" not in rec:
                continue
            bad = rec.get("error") or rec.get("degenerate") or rec.get("truncated")
            if not bad:
                kept[rec["chunk_index"]] = rec
        by_index = {ch["chunk_index"]: ch for ch in chunks}
        for i, rec in kept.items():
            ch = by_index.get(i)
            # chunk_index is just an ordinal; it will coincide for somebody else's cut
            # too, and the only way to tell that apart is by the window boundaries
            if ch is None:
                raise SystemExit(
                    f"--redo-bad: fragment {i} is not in the new cut — "
                    f"the frames have changed, nothing to fix")
            if (abs(ch["t_start"] - rec["t_start"]) > 1e-6
                    or abs(ch["t_end"] - rec["t_end"]) > 1e-6):
                raise SystemExit(
                    f"--redo-bad: fragment {i} in the file is "
                    f"[{rec['t_start']}, {rec['t_end']}], in the new cut it is "
                    f"[{ch['t_start']}, {ch['t_end']}]: nothing to fix")
        chunks = [ch for ch in chunks if ch["chunk_index"] not in kept]
        records.extend(kept.values())
        print(f"[redo] taking {len(kept)} fragments as ready, re-requesting {len(chunks)}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(describe_chunk, client, args.model, ch, cues,
                        args.max_tokens, args.temperature, args.upscale): ch
            for ch in chunks
        }
        for fut in as_completed(futures):
            records.append(fut.result())
            done += 1
            if done % 5 == 0 or done == len(chunks):
                elapsed = time.time() - started
                print(f"  {done}/{len(chunks)} chunks, {elapsed:.0f} s, "
                      f"~{elapsed / done * (len(chunks) - done):.0f} s left", flush=True)
    records.sort(key=lambda r: r["chunk_index"])
    elapsed = time.time() - started

    # The denominator is the stretch REQUESTED, not the windows assembled. If one counts
    # by windows, the lost frames drop out together with their seconds from both parts of
    # the fraction, and the check cheerfully reports "no holes".
    covered = {e["t"] for r in records for e in r.get("events", []) if e.get("t") is not None}
    want_seconds: set[int] = set()
    for a, b in (ranges or [(0.0, duration)]):
        want_seconds.update(range(int(a), int(min(b, duration))))
    missing = sorted(want_seconds - covered)
    if missing:
        print(f"[warn] {len(missing)} seconds out of "
              f"{len(want_seconds)} are left with no events, the first of them: {missing[:10]}", file=sys.stderr)

    meta = {
        "video_id": vid,
        "title": bundle.get("title", vid),
        "duration": duration,
        "chapters": bundle.get("chapters", []),
        "model": args.model,
        "api_base": args.api_base,
        "window": args.window,
        "stride": args.stride,
        # the overlap with each neighbour, not the total: the boundaries are half-open
        "overlap": round(max(0.0, args.window - args.stride), 2),
        "frame_step": frame_step,
        "upscale": args.upscale,
        "with_transcript": args.with_transcript,
        "temperature": args.temperature,
        "ranges": [list(r) for r in ranges],
        "n_chunks": len(records),
        "n_frames": len(frames),
        "n_errors": sum(1 for r in records if r.get("error")),
        "n_degenerate": sum(1 for r in records if r.get("degenerate")),
        "n_truncated": sum(1 for r in records if r.get("truncated")),
        # the contract "the description is per-second" has until now been checked only by
        # hand: a fragment with an error returns events=[], and its seconds vanished silently
        "seconds_expected": len(want_seconds),
        "seconds_covered": len(covered),
        "elapsed_s": round(elapsed, 1),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    jsonl = bdir / f"{args.out_prefix}.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    md = bdir / f"{args.out_prefix}.md"
    write_markdown(md, meta, records)

    print(f"\nfinished in {elapsed:.0f} s ({elapsed / 60:.1f} min), errors {meta['n_errors']}, "
          f"degenerate answers {meta['n_degenerate']}")
    print(f"  {jsonl}")
    print(f"  {md}")


if __name__ == "__main__":
    main()

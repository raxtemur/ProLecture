#!/usr/bin/env python3
"""Scene change detection in 3Blue1Brown videos: frames where the picture changes.

Why our own rather than an ffmpeg grid: manim videos are sparse bright content on a
black background, where a scene holds for tens of seconds and is then redrawn in a
second. A uniform grid both duplicates static material and skips past changes. The
off-the-shelf detectors (`ffmpeg -vf select='gt(scene,...)'`, PySceneDetect's
ContentDetector) compare a frame with the PREVIOUS one, so manim's smooth travels
(an object crossing the screen over three seconds) are to them a chain of tiny
differences below any threshold.

The algorithm:

1. We probe the video `probe-fps` times per second (4 by default).
2. The frame is shrunk to 192x108 and cut into a 9x12 = 108 block grid.
3. We compute the ACCUMULATED drift — the per-block difference against the last
   CAPTURED frame rather than the previous one probed. A slow travel accumulates
   drift and sooner or later steps over the threshold; static material accumulates
   nothing.
4. We subtract the noise floor: for each block we keep the median difference between
   neighbouring probed frames over a sliding window. This is needed precisely because
   of 3b1b: a ribbon of random bits often runs on top of the scene, changing every
   frame and meaning nothing. Such a block gets a high floor and stops voting.
5. The frame's score is the power mean of the cleaned drift over the blocks
   (`--agg-power`). At exponent 1 this is simply the share of the area that changed,
   and then a single line added to a formula drowns: it occupies one block out of 108.
   Exponent 2 shifts the weight towards the few strongly changed blocks, so that
   "a line was added" falls into the same threshold as "the whole picture moved".
6. Once the threshold is crossed we capture the frame and it becomes the new
   reference. We capture not at the moment of firing but once the animation has
   SETTLED (`--settle-max`): otherwise half-written formulas systematically get into
   the sample.

The tuning of the threshold and the frame-by-frame comparison are in
docs/scene_detection.md.

Usage:
    python tools/detect_scenes.py l6DKRf-fAAM                 # times only
    python tools/detect_scenes.py l6DKRf-fAAM --write-frames  # frames as well
    python tools/detect_scenes.py path/to/video.mp4 --threshold 0.02 --json cuts.json
"""

import argparse
import json
import shutil
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "data" / "videos"

# --- the defaults, tuned on three 3b1b videos --------------------------------
# (see docs/scene_detection.md: 2026-06, 2026-07 and the 2017-05 control)
PROBE_FPS = 4.0        # probes per second
THRESHOLD = 0.010      # the threshold on the mean cleaned drift (share of the frame's area)
MIN_GAP = 2.0          # seconds between neighbouring captured frames
MAX_GAP = 45.0         # a forced frame if the picture has not changed for this long
GRID = (9, 12)         # blocks vertically and horizontally (108 blocks)
SMALL = (192, 108)     # the size the frame is shrunk to (width, height)
NOISE_WINDOW = 8.0     # seconds of the sliding window for estimating the noise floor
NOISE_K = 1.5          # by how much the drift must exceed the block's noise
AGG_POWER = 2.0        # the averaging exponent over the blocks (>1 — in favour of local edits)
SETTLE_MAX = 2.0       # how many seconds at most we wait for the animation to settle
SETTLE_EPS = 0.004     # the per-frame stirring below which we consider it settled
SETTLE_QUIET = 2       # this many quiet probes in a row; one may just be a pause
                       # in the middle of a long caption, and the frame comes out half-written

FRAME_FMT = "t{:08.1f}.jpg"   # t000887.2.jpg — sorts lexicographically


def require_cv2():
    try:
        import cv2
    except ImportError:
        sys.exit(
            "OpenCV is required. Install it in base conda:\n"
            "    /home/user/conda/bin/python3 -m pip install opencv-python-headless"
        )
    return cv2


def resolve_input(arg: str) -> Path:
    """The argument is either a path to an mp4 or a youtube_id from data/videos/."""
    p = Path(arg)
    if p.is_file():
        return p
    cand = VIDEOS_DIR / arg / f"{arg}.mp4"
    if cand.is_file():
        return cand
    sys.exit(f"video not found: neither the file {arg} nor {cand}")


def block_diff(a, b, grid) -> "object":
    """The per-block mean absolute difference of two shrunk frames, 0..1."""
    import numpy as np
    gy, gx = grid
    h, w = a.shape[:2]
    bh, bw = h // gy, w // gx
    m = np.abs(a - b).mean(axis=2)[: bh * gy, : bw * gx]
    return m.reshape(gy, bh, gx, bw).mean(axis=(1, 3)) / 255.0


def aggregate(cleaned, power: float) -> float:
    """Collapses the per-block drift into a single score.

    At power=1 this is the share of the frame's area that changed — and then a single
    line added to a formula in an empty corner drowns: it occupies one block out of
    108. A power mean with power>1 shifts the weight towards the few strongly changed
    blocks, so that "a new line" and "the whole picture moved" fall into one threshold.
    """
    import numpy as np
    if power == 1.0:
        return float(cleaned.mean())
    return float((cleaned.astype(np.float64) ** power).mean() ** (1.0 / power))


def detect(
    mp4: Path,
    probe_fps: float = PROBE_FPS,
    threshold: float = THRESHOLD,
    min_gap: float = MIN_GAP,
    max_gap: float = MAX_GAP,
    grid=GRID,
    small_size=SMALL,
    noise_window: float = NOISE_WINDOW,
    noise_k: float = NOISE_K,
    agg_power: float = AGG_POWER,
    settle_max: float = SETTLE_MAX,
    settle_eps: float = SETTLE_EPS,
    settle_quiet: int = SETTLE_QUIET,
    every: float = 0.0,
    start: float = 0.0,
    end: float = 0.0,
    out_dir: Path | None = None,
    signal_path: Path | None = None,
) -> list[dict]:
    """Returns a list of {t, score, reason}; with out_dir it also writes the frames."""
    cv2 = require_cv2()
    import numpy as np

    cap = cv2.VideoCapture(str(mp4))
    if not cap.isOpened():
        sys.exit(f"OpenCV did not open {mp4}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / src_fps if total else 0.0
    if end <= 0:
        end = duration or float("inf")

    if out_dir is not None:
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

    noise_len = max(2, int(round(noise_window * probe_fps)))
    noise_hist: deque = deque(maxlen=noise_len)

    cuts: list[dict] = []
    signal: list[dict] = []
    prev_small = None          # the previous probed frame (for the noise floor)
    prev_full = None           # the same at full size: needed in order to write it out
                               # an unclosed pending, if the video ended
    ref_small = None           # the last CAPTURED frame — the reference for the drift
    pending = None             # waiting for it to settle: {"t0": ..., "score": ...}

    def take(t: float, small, full, reason: str, score: float) -> None:
        nonlocal ref_small
        ref_small = small
        # we round the time BEFORE writing: the file name and the `t` field are obliged
        # to coincide, otherwise a consumer reading the time from the name gets a
        # different second
        t = round(float(t), 1)
        if cuts and abs(cuts[-1]["t"] - t) < 0.05:
            # two probes rounded to the same tenth: the file name would coincide,
            # the write would overwrite the frame and the consumer would lose a time
            return
        rec = {"t": t, "score": round(float(score), 5), "reason": reason}
        if out_dir is not None:
            name = FRAME_FMT.format(t)
            cv2.imwrite(str(out_dir / name), full, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            dst = out_dir / name
            # the path in bundle.json is relative to the root of the repository, if it is there
            rec["path"] = str(dst.relative_to(ROOT)) if dst.is_relative_to(ROOT) else str(dst)
        cuts.append(rec)

    # the constant-rate mode: a slot of fixed length, and within the slot we take
    # the QUIETEST probed frame. It is needed where holes are not allowed (a dense
    # description of the video track), but half-frames are just as harmful as in
    # threshold mode: that is exactly why the ffmpeg grid will not do here.
    if every > 0:
        probe_fps = max(probe_fps, 4.0 / every)
    best = None

    next_probe = start
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = idx / src_fps
        idx += 1
        if t < start:
            continue
        if t > end:
            break
        if t + 1e-9 < next_probe:
            continue
        next_probe = t + 1.0 / probe_fps

        ok, full = cap.retrieve()
        if not ok:
            break
        prev_full = full
        small = cv2.resize(full, small_size, interpolation=cv2.INTER_AREA).astype(np.float32)

        if ref_small is None:                      # the first frame is considered captured
            if every <= 0:
                take(t, small, full, "first", 0.0)
            else:
                # in slot mode it is not captured immediately, but it is obliged to take
                # part in its slot's contest: otherwise slot 0 is left with no candidate
                # if there was only one probe in it
                ref_small = small
                best = {"slot": int((t - start) // every), "t": t, "small": small,
                        "full": full, "score": float("inf"), "central": False}
            prev_small = small
            continue

        step = block_diff(small, prev_small, grid)  # the stirring over a single probe
        prev_small = small
        floor = (
            np.median(np.stack(noise_hist), axis=0) if noise_hist
            else np.zeros_like(step)
        )
        noise_hist.append(step)

        drift = block_diff(small, ref_small, grid)
        score = aggregate(np.maximum(drift - noise_k * floor, 0.0), agg_power)
        step_score = aggregate(np.maximum(step - noise_k * floor, 0.0), agg_power)
        if signal_path is not None:
            signal.append({"t": round(t, 2), "score": round(score, 5),
                           "step": round(step_score, 5)})

        if every > 0:
            slot = int((t - start) // every)
            offset = (t - start) - slot * every
            # a candidate from the middle of the slot is preferable to the quietest one:
            # at the edges, neighbouring slots pick frames 0.1 s apart, and that is two
            # nearly identical images at the full price of a prefill
            central = 0.2 * every - 1e-9 <= offset <= 0.8 * every + 1e-9
            cand = {"slot": slot, "t": t, "small": small, "full": full,
                    "score": step_score, "central": central}
            if best is None or slot != best["slot"]:
                if best is not None:
                    take(best["t"], best["small"], best["full"], "slot", best["score"])
                best = cand
            elif (cand["central"], -cand["score"]) > (best["central"], -best["score"]):
                best = cand
            continue

        gap = t - cuts[-1]["t"]

        if pending is not None:
            # We wait for the animation to settle, but no longer than settle_max. One quiet
            # probe is not enough: manim writes a formula over several seconds, and there is
            # sometimes a pause mid-writing at which the frame was captured half-written.
            pending["quiet"] = pending["quiet"] + 1 if step_score < settle_eps else 0
            if pending["quiet"] >= settle_quiet or t - pending["t0"] >= settle_max:
                take(t, small, full, pending["reason"], max(pending["score"], score))
                pending = None
            continue

        if gap < min_gap:
            continue
        if score >= threshold:
            pending = {"t0": t, "score": score, "reason": "scene", "quiet": 0}
        elif max_gap > 0 and gap >= max_gap:
            take(t, small, full, "max-gap", score)

    if pending is not None and prev_small is not None:
        # a scene change within settle_max of the end of the video: there is nothing more
        # to wait for, so we capture the last thing we saw, otherwise it vanishes silently
        # IMPORTANT: the picture here is later than the second recorded (by up to
        # settle_max), which is why the reason is separate — the consumer must see the
        # difference
        take(pending["t0"], prev_small, prev_full, "scene-eof", pending["score"])
    if best is not None:
        # a slot truncated by --end manages to gather one candidate right at the
        # boundary, and it ends up right next to the frame of the previous slot
        near = cuts and best["t"] - cuts[-1]["t"] < 0.3 * every
        if not near:
            take(best["t"], best["small"], best["full"], "slot", best["score"])
    cap.release()
    if signal_path is not None:
        signal_path.write_text(json.dumps(signal), encoding="utf-8")
    return cuts


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Scene detection by the accumulated drift from the last captured frame"
    )
    ap.add_argument("video", help="a path to an mp4 or a youtube_id from data/videos/")
    ap.add_argument("--probe-fps", type=float, default=PROBE_FPS,
                    help=f"probes of the video per second (default {PROBE_FPS})")
    ap.add_argument("--threshold", type=float, default=THRESHOLD,
                    help=f"the accumulated drift threshold (default {THRESHOLD})")
    ap.add_argument("--min-gap", type=float, default=MIN_GAP,
                    help=f"the minimum seconds between frames (default {MIN_GAP})")
    ap.add_argument("--max-gap", type=float, default=MAX_GAP,
                    help=f"a forced frame if nothing has changed for this many seconds "
                         f"(default {MAX_GAP}, 0 — disable)")
    ap.add_argument("--noise-k", type=float, default=NOISE_K,
                    help=f"by how much a block's drift must exceed its noise "
                         f"(default {NOISE_K}, 0 — do not subtract the noise)")
    ap.add_argument("--agg-power", type=float, default=AGG_POWER,
                    help=f"the averaging exponent over the blocks (default {AGG_POWER}; "
                         f"1 — simply the share of the area that changed)")
    ap.add_argument("--noise-window", type=float, default=NOISE_WINDOW,
                    help=f"the noise estimation window, seconds (default {NOISE_WINDOW})")
    ap.add_argument("--settle-max", type=float, default=SETTLE_MAX,
                    help=f"the maximum wait for the animation to settle "
                         f"(default {SETTLE_MAX}, 0 — capture at once)")
    ap.add_argument("--every", type=float, default=0.0,
                    help="the constant-rate mode: a slot of this length (seconds), "
                         "with the quietest frame taken within the slot; the threshold "
                         "and min-gap do not apply in this mode")
    ap.add_argument("--settle-quiet", type=int, default=SETTLE_QUIET,
                    help=f"this many quiet probes in a row count as the end of an animation "
                         f"(default {SETTLE_QUIET})")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0, help="0 — to the end")
    ap.add_argument("--write-frames", action="store_true", help="save the frames themselves")
    ap.add_argument("--out-dir", help="where to put the frames (default data/bundles/<id>/frames)")
    ap.add_argument("--clean", action="store_true", help="clear the frames directory before writing")
    ap.add_argument("--json", help="where to write the list of times")
    ap.add_argument("--dump-signal", help="where to write the raw signal (for tuning the threshold)")
    ap.add_argument("--quiet", action="store_true", help="do not print the list of times")
    args = ap.parse_args()

    mp4 = resolve_input(args.video)
    cv2 = require_cv2()
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    duration = total / fps if fps else 0.0

    out_dir = None
    if args.write_frames:
        out_dir = Path(args.out_dir) if args.out_dir else (
            ROOT / "data" / "bundles" / mp4.stem / "frames"
        )
        if args.clean and out_dir.exists():
            shutil.rmtree(out_dir)

    cuts = detect(
        mp4,
        probe_fps=args.probe_fps,
        threshold=args.threshold,
        min_gap=args.min_gap,
        max_gap=args.max_gap,
        noise_window=args.noise_window,
        noise_k=args.noise_k,
        agg_power=args.agg_power,
        settle_max=args.settle_max,
        settle_quiet=args.settle_quiet,
        every=args.every,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
        signal_path=Path(args.dump_signal) if args.dump_signal else None,
    )

    if args.json:
        Path(args.json).write_text(
            json.dumps(cuts, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    if not args.quiet:
        for c in cuts:
            print(f"{c['t']:9.2f}  {c['score']:.4f}  {c['reason']}")

    # the denominator is the stretch parsed, not the interval between the first and
    # the last frame: otherwise an aborted run overstates the rate
    span = (min(args.end, duration) if args.end else duration) - args.start
    if span <= 0:
        span = (cuts[-1]["t"] - cuts[0]["t"]) if len(cuts) > 1 else 0.0
    forced = sum(1 for c in cuts if c["reason"] == "max-gap")
    print(f"{mp4.name}: frames {len(cuts)}"
          + (f", {len(cuts) / span * 60:.1f} per minute" if span else "")
          + f", of them by max-gap {forced}"
          + (f", frames → {out_dir}" if out_dir else ""))


if __name__ == "__main__":
    main()

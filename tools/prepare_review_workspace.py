#!/usr/bin/env python3
"""A working folder for a subagent: the transcript and the frames, nothing more.

The subagent works only in this folder: a separate directory is prepared for it, holding
only what its role is allowed to see.

    # everything that was in the video up to the moment T
    prepare_review_workspace.py <video_id> --until 957 --out /tmp/rev_q07_blind

    # re-sample a stretch with a dense grid into the same folder
    prepare_review_workspace.py <video_id> --dense 930 960 --step 1 --out /tmp/rev_q07_blind

    # a quick look at up to 16 moments: the same frames, also tiled into ONE labelled image
    prepare_review_workspace.py <video_id> --dense 499 510 --step 1 --sheet --out /tmp/rev_q07_blind

    # the probe_verify folder: the transcript, the scene frames and the screen description
    # up to T
    prepare_review_workspace.py <video_id> --until 690 --screen --verify --out /tmp/verify_q10

    # one modality instead of two, or a single frame
    prepare_review_workspace.py <video_id> --until 992 --only transcript --out /tmp/probe_text
    prepare_review_workspace.py <video_id> --until 992 --only frames    --out /tmp/probe_vision
    prepare_review_workspace.py <video_id> --frame 946                  --out /tmp/probe_frame

    # the same, with the boundaries read off the record: the way a role's workspace is made
    # for a launch. The record is found by its id; a note of which version of it the folder
    # was built from is left next to the folder (<out>.inputs.json, see review_inputs.py)
    prepare_review_workspace.py <video_id> --sample-id <id> --role probe_frame --window 1 \
        --out .review_ws/<video_id>/<question>/<subagent>

    # after a validated review has been consolidated
    prepare_review_workspace.py <video_id> --cleanup --out \
        .review_ws/<video_id>/<question>/<subagent>

The frames are named by timecode (t000946.jpg), so the agent sees the time right in the
file name and has nothing to recompute.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from describe_video import (  # noqa: E402  (the timeline is shared with the bundle's copy)
    REAPPEAR_GAP, format_screen_rows, load_description_records, screen_text_rows)
import review_inputs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def frame_name(t: float) -> str:
    return f"t{int(round(t)):06d}.jpg"


def load_bundle(vid: str) -> dict:
    path = ROOT / "data" / "bundles" / vid / "bundle.json"
    if not path.exists():
        sys.exit(f"no bundle {path}; run tools/make_bundle.py {vid} first")
    return json.loads(path.read_text(encoding="utf-8"))


def write_transcript(bundle: dict, out: Path, t0: float, t1: float) -> tuple[int, float]:
    """The utterances lying entirely inside [t0, t1).

    An utterance crossing the boundary has to be discarded whole: we have no
    word-level timings and nothing to trim it by at t1. Otherwise the blind reviewer
    gets up to several seconds of speech from beyond their boundary — and that is
    usually where the answer lies: 19 of the pilot's 25 t_start values fall inside an
    utterance. One may only err in one direction here: better that the blind reviewer
    sees less than they could than a second more than they should.
    """
    cues = [c for c in bundle["transcript"] if c["start"] >= t0 and c["end"] <= t1]
    actual = cues[-1]["end"] if cues else t0
    lines = [f"# Transcript {bundle['video_id']}: {t0:.0f}–{t1:.0f} s",
             f"# the last utterance ends at {actual:.1f} s; everything crossing "
             f"the boundary of {t1:.0f} s has been discarded whole", ""]
    lines += [f"[{c['start']:.1f}–{c['end']:.1f}] {c['text']}" for c in cues]
    (out / "transcript.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(cues), actual


def load_description(vid: str) -> list[dict] | None:
    """The description of the video track, if it has been built (tools/describe_video.py).

    The first line of the file is the run metadata, then one line per chunk.
    The absence of the file is not an error: a bundle without a description still works.
    """
    path = ROOT / "data" / "bundles" / vid / "description.jsonl"
    if not path.exists():
        return None
    return load_description_records(path)


def write_screen(desc: list[dict], out: Path, t0: float, t1: float) -> tuple[int, int]:
    """The description of the video track: material to read, not evidence to cite.

    We put in two files of different purpose:

    * `screen.jsonl` — the chunks in full (a description of the beginning and the end,
      per-second events, the recognised on-screen text). For the semi-blind roles this is
      the main material of a stretch and is read in full (about 8 KB per twenty seconds
      of video); the sighted roles, who know what they are looking for, may `grep` it;
    * `screen_text.md` — a timeline of the recognised text, deduplicated: a line gets
      into it once, at the moment it first appears. A quick way to see WHEN a formula or
      a number came up.

    It is cut at the same boundaries as the transcript, and for the same reason: a chunk
    crossing `t1` is discarded whole. Otherwise the semi-blind reviewer would get a
    description of the future — that is, exactly what their work checks blindness to.

    **This description was made by a model, not by a human.** It is fit for finding a
    moment and unfit for asserting anything: before putting a timecode into a review,
    the moment must be seen on a real frame. This is said in the header of each file
    too — the subagent reading them will see the header, and this docstring it will not.
    """
    chunks = [c for c in desc if c["t_start"] >= t0 and c["t_end"] <= t1]

    head = (f"# On-screen text {out.name}: {t0:.0f}-{t1:.0f} s\n"
            f"# Recognised BY A MODEL from frames, not by a human: fit for FINDING a moment,\n"
            f"# not for ASSERTING it. Found a line — go and look at the frame.\n"
            f"# A line gets in here when it appears; if it disappeared for more than\n"
            f"# {REAPPEAR_GAP:.0f} s and came back, that is a separate line of the timeline.\n"
            f"# The full description, chunk by chunk, is in screen.jsonl: read THAT in full\n"
            f"# over your stretch; this file only says when a text first came up.\n\n")
    rows = screen_text_rows(chunks)
    (out / "screen_text.md").write_text(head + format_screen_rows(rows), encoding="utf-8")

    with (out / "screen.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps({"_note": "a description of the video track made by a model, "
                                     "chunk by chunk. Material to READ in full over your "
                                     "stretch, not evidence to cite: a number or a text "
                                     "taken from here is confirmed on a real frame first.",
                            "from": t0, "until": t1, "chunks": len(chunks)},
                           ensure_ascii=False) + "\n")
        for c in chunks:
            slim = {k: v for k, v in c.items()
                    if k not in ("frames", "frame_times", "latency_s")}
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")
    return len(chunks), len(rows)


def write_frame_index(bundle: dict, out: Path, t0: float, t1: float) -> int:
    """A manifest of frames instead of copies: a list of timecodes and a path to view them at.

    Copying exists for exactly one reason — not to let the blind reviewer see the
    future. Where blindness is not required (`full_sample`, `full_window` — they know
    the reference answer anyway), a copy is pointless: it costs disk and time, while the
    budget is counted by the number of frames opened, not by the number lying in the
    folder.
    """
    picked = [fr for fr in bundle["frames"] if t0 <= fr["t"] < t1]
    src_dir = (ROOT / "data" / "bundles" / bundle["video_id"] / "frames").resolve()
    lines = [f"# Frames {bundle['video_id']}: {t0:.0f}-{t1:.0f} s — an INDEX, not copies",
             f"# Look at them right here: {src_dir}/<name>",
             f"# The cut is by scene changes; between neighbouring lines the screen did not",
             f"# change abruptly. Need it denser — tools/prepare_review_workspace.py --dense.",
             f"# The frames at the two edges of the stretch are cut into this folder, frames/.",
             ""]
    # The edges, as in copy_sparse; here they are cut into the folder itself, since the
    # bundle's directory is not ours to write to. The end replaces a scene frame of its second.
    edges = out / "frames"
    edges.mkdir(exist_ok=True)
    added = cut_edges(bundle["video_id"], edges, t0, t1,
                      have={frame_name(fr["t"]) for fr in picked})
    rows = [(fr["t"], Path(fr["path"]).name) for fr in picked
            if not (frame_name(fr["t"]) == frame_name(t1) and (edges / frame_name(t1)).exists())]
    for t in (t0, t1):
        if (edges / frame_name(t)).exists():
            rows.append((t, f"{frame_name(t)}  (in this folder: frames/{frame_name(t)})"))
    lines += [f"{t:8.1f}  {name}" for t, name in sorted(rows)]
    (out / "frames.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(picked) + added


def copy_sparse(bundle: dict, out: Path, t0: float, t1: float, cap: int) -> int:
    """Copies of the bundle's scene frames in [t0, t1), thinned to `cap`, plus both edges.

    The frame exactly at `t1` is the state of the screen the whole folder is about: "is
    the material up to `until` enough" is decided there, and a scene cut need not fall on
    it. A probe that saw the last scene frame a second earlier, in the middle of an
    animation, took the animation for unfinished at the boundary (fix list 2, 2.3). So
    both edges are cut from the video whatever the bundle has; the thinning never drops
    them, and nothing later than `t1` gets in.
    """
    dst = out / "frames"
    dst.mkdir(exist_ok=True)
    picked = [fr for fr in bundle["frames"] if t0 <= fr["t"] < t1]
    # the bundle's cut is scene detection, about 13 frames per minute: over a half-hour
    # stretch that is several hundred files, and a "cheap" overview operation would eat
    # the whole viewing budget. We thin the list uniformly, that is, we lose some scenes
    # — the reviewer picks up what is needed pointwise via --dense
    if len(picked) > cap:
        step = len(picked) / cap
        picked = [picked[int(i * step)] for i in range(cap)]
    n = 0
    for fr in picked:
        src = ROOT / fr["path"]
        if src.exists():
            shutil.copy2(src, dst / frame_name(fr["t"]))
            n += 1
    return n + cut_edges(bundle["video_id"], dst, t0, t1)


def cut_edges(vid: str, dst: Path, t0: float, t1: float, have: set[str] = frozenset()) -> int:
    """Put the frames exactly at `t0` and `t1` into `dst`; return how many were added.

    The start is cut only when no frame of that second is there yet, in `dst` or among
    the names in `have`. The end always replaces what lies under its name: a scene frame
    up to half a second earlier rounds to the same second, and the folder must show the
    screen at the boundary itself.
    """
    mp4 = ROOT / "data" / "videos" / vid / f"{vid}.mp4"
    if not mp4.exists():
        print(f"warning: no video {mp4}, so the frames at {t0:.1f} and {t1:.1f} s were not cut; "
              f"fetch it with tools/fetch_video.py {vid} and prepare the folder again")
        return 0
    added = 0
    start = dst / frame_name(t0)
    if frame_name(t0) != frame_name(t1) and frame_name(t0) not in have and not start.exists():
        added += grab_frame(mp4, t0, start)
    end = dst / frame_name(t1)
    existed = end.exists()
    if grab_frame(mp4, t1, end) and not existed:
        added += 1
    return added


def grab_frame(mp4: Path, t: float, target: Path) -> bool:
    """One frame of the video at `t` (the first one at or after it), written to `target`."""
    target.unlink(missing_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(mp4),
         "-frames:v", "1", "-q:v", "4", str(target), "-y"],
        check=False,
    )
    return target.exists()


def check_mode(out: Path, mode: str, force: bool) -> None:
    """Do not let the material of two modes be mixed in one folder.

    Otherwise the isolation of the probes rests only on the coordinator's care: two
    consecutive calls with --only frames and --only transcript into one directory leave
    both frames and a transcript there, and the second call cheerfully prints "frames
    are deliberately not placed" about a folder where forty frames already lie. The
    vision probe gets the text of the speech, its answer stops measuring anything, and
    from that answer the label of dependence on sound is derived — that is, the very
    thing whose honesty the whole design exists to protect is what breaks.
    """
    if not out.exists() or not any(out.iterdir()):
        return
    stamp = out / "mode.json"
    was = json.loads(stamp.read_text(encoding="utf-8"))["mode"] if stamp.exists() else None
    if was == mode:
        return
    if force:
        print(f"the directory was of mode {was!r}, being overwritten as {mode!r} (--force)")
        for name in ("transcript.md", "limits.json", "mode.json"):
            (out / name).unlink(missing_ok=True)
        shutil.rmtree(out / "frames", ignore_errors=True)
        return
    sys.exit(f"the directory {out} is non-empty and was assembled by mode {was!r}, while {mode!r} is now requested. "
             f"Different probes are obliged to get different folders — otherwise the isolation by modality "
             f"does not work. Take a different --out or, if this is a deliberate rebuild, "
             f"add --force")


def check_dense_allowed(out: Path, force: bool) -> None:
    """Do not let `--dense` smuggle frames into a folder where frames are forbidden.

    `check_mode` was called only for `--until` and `--frame`: `--dense` has no mode, so
    the check was skipped while `extract_dense` created `frames/` itself. The result:
    two consecutive calls, `--until --only transcript` and `--dense`, left fifteen
    frames in the text probe's folder, with `mode.json` still claiming `"transcript"`.
    The text probe got a picture, `textonly_solved` stopped measuring anything, and from
    it `solvable` and the label of dependence on speech are derived.

    The same hole also covered `frame`: a frozen-frame folder has no `limits.json`, so
    `clamp_to_workspace` let any stretch through, and the "one frame with no history"
    probe got a dozen frames from a different part of the lecture.
    """
    if not out.exists() or not any(out.iterdir()):
        return
    stamp = out / "mode.json"
    if not stamp.exists():
        if force:
            print(f"the directory {out} is non-empty and has no mode.json, re-sampling by --force")
            return
        sys.exit(f"the directory {out} is non-empty but was not assembled by this script (no mode.json). "
                 f"--dense would re-sample somebody else's folder blindly; take a different --out "
                 f"or add --force")
    was = json.loads(stamp.read_text(encoding="utf-8"))["mode"]
    if was in ("frames", "both", "both-index", "verify"):
        return
    reason = {
        "transcript": "this is the text probe's folder — frames in it cancel the whole point "
                      "of measuring textonly_solved",
        "frame": "this is the frozen-frame probe's folder — it is obliged to see exactly one frame "
                 "and nothing around it",
    }[was]
    sys.exit(f"the directory {out} was assembled by mode {was!r}: {reason}. Take a different --out")


def clamp_to_workspace(out: Path, t0: float, t1: float) -> tuple[float, float]:
    """Do not let re-sampling escape the boundaries the folder was created with.

    Otherwise a blind reviewer who asks for a stretch "with some slack" will see frames
    beyond their upper boundary — that is, exactly what is hidden from them.
    """
    limits = out / "limits.json"
    if not limits.exists():
        return t0, t1
    lim = json.loads(limits.read_text(encoding="utf-8"))
    a, b = max(t0, lim["from"]), min(t1, lim["until"])
    if (a, b) != (t0, t1):
        print(f"the stretch has been clipped to the boundaries of the working folder: {a:.0f}-{b:.0f} s")
    if a >= b:
        sys.exit("the stretch requested lies entirely outside the working folder")
    return a, b


SHEET_MAX = 16  # a 4x4 grid: beyond that a cell is too small to tell a band from a gradient


def dense_times(t0: float, t1: float, step: float) -> list[float]:
    """The grid of a stretch with both edges: t0, t0 + step, ... and t1 itself.

    A grid that stops short of `t1` leaves the screen at the boundary unseen (fix list 2,
    2.3). A grid point that rounds to the same second as `t1` gives way to it.
    """
    times, k = [], 0
    while (t := round(t0 + k * step, 2)) < t1 and frame_name(t) != frame_name(t1):
        times.append(t)
        k += 1
    return times + [round(t1, 2)]


def build_sheet(frames_dir: Path, times: list[float], cols: int = 4, cell_w: int = 480) -> Path:
    """Tile the frames of `times` into one image, each cell stamped with its second.

    Frames opened one by one are each described on their own, and a slow change (layers
    subdividing into a gradient, a fade) reads the same on every one of them. Side by side
    the change is what the eye compares. One image also costs one look instead of sixteen.
    """
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=28)
    cells = []
    for t in times:
        path = frames_dir / frame_name(t)
        if not path.exists():
            continue
        img = Image.open(path).convert("RGB")
        img = img.resize((cell_w, round(img.height * cell_w / img.width)))
        draw = ImageDraw.Draw(img)
        label = f"{t:g} s"
        box = draw.textbbox((8, 6), label, font=font)
        draw.rectangle((box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4), fill="black")
        draw.text((8, 6), label, fill="yellow", font=font)
        cells.append(img)
    if not cells:
        sys.exit("no frames to tile: the stretch produced none")
    cols = min(cols, len(cells))
    rows = -(-len(cells) // cols)
    cell_h = max(c.height for c in cells)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "black")
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % cols) * cell_w, (i // cols) * cell_h))
    target = frames_dir / f"sheet_{frame_name(times[0])[:-4]}-{frame_name(times[-1])[:-4]}.jpg"
    sheet.save(target, quality=90)
    return target


def extract_dense(vid: str, out: Path, t0: float, t1: float, step: float, cap: int) -> int:
    """The grid of dense_times, both edges included; the frame at `t1` replaces one of
    the same second that is already there, as in cut_edges."""
    mp4 = ROOT / "data" / "videos" / vid / f"{vid}.mp4"
    if not mp4.exists():
        sys.exit(f"no video {mp4}; fetch it with tools/fetch_video.py {vid}")
    dst = out / "frames"
    dst.mkdir(parents=True, exist_ok=True)

    times = dense_times(t0, t1, step)
    if len(times) > cap:
        sys.exit(
            f"{len(times)} frames requested (both edges included) against a ceiling of {cap}: "
            f"narrow the stretch or increase --step (currently {step} s)"
        )

    n = 0
    for t in times:
        target = dst / frame_name(t)
        existed = target.exists()
        if existed and t != times[-1]:
            continue
        n += grab_frame(mp4, t, target) and not existed
    return n


def cleanup_workspace(video_id: str, out: Path) -> bool:
    """Remove one reproducible reviewer workspace, never a broader directory.

    The accepted shape is exactly
    ``<ROOT>/.review_ws/<video_id>/<question>/<subagent>``. Keeping the destructive
    operation here lets the coordinator clean up after consolidating a valid review
    without teaching a validator to mutate data.
    """
    review_root = (ROOT / ".review_ws").resolve()
    requested = Path(out)
    resolved = requested.resolve()
    try:
        relative = resolved.relative_to(review_root)
    except ValueError as exc:
        raise ValueError(f"cleanup target must be inside {review_root}") from exc
    if len(relative.parts) != 3:
        raise ValueError(
            "cleanup target must be one reviewer workspace: "
            ".review_ws/<video>/<question>/<subagent>"
        )
    if relative.parts[0] != video_id:
        raise ValueError(
            f"cleanup target belongs to video id {relative.parts[0]!r}, not {video_id!r}"
        )
    if requested.is_symlink():
        raise ValueError("cleanup target must not be a symlink")
    review_inputs.sidecar_path(resolved).unlink(missing_ok=True)
    if not resolved.exists():
        return False

    shutil.rmtree(resolved)
    for parent in (resolved.parent, resolved.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break
    return True


# What --role sets, besides the boundary: the channels and the form of the frames.
ROLE_MODES = {
    "semiblind": {"only": "both", "screen": True},
    "probe_verify": {"only": "both", "screen": True, "verify": True},
    "probe_text": {"only": "transcript"},
    "probe_vision": {"only": "frames", "screen": True},
    "probe_full": {"only": "both", "screen": True},
    "probe_frame": {},
    "full_sample": {"only": "both", "screen": True, "index_only": True},
    "full_window": {"only": "both", "screen": True, "index_only": True},
}


def derive_from_record(args: argparse.Namespace) -> dict:
    """Set the mode flags of `args` from the record and return the note for the sidecar."""
    if not args.role:
        sys.exit("--sample-id needs --role: the role decides what the folder holds")
    typed = [flag for flag, on in (("--frame", args.frame is not None), ("--only", args.only != "both"),
                                   ("--screen", args.screen), ("--verify", args.verify),
                                   ("--index-only", args.index_only), ("--dense", args.dense is not None),
                                   ("--cleanup", args.cleanup)) if on]
    if args.until is not None and args.role != "probe_verify":
        typed.append("--until")
    if typed:
        sys.exit(f"{', '.join(typed)}: with --sample-id the role {args.role} sets the material "
                 f"itself; drop {'it' if len(typed) == 1 else 'them'}")
    try:
        path, record = review_inputs.find_record(ROOT, args.sample_id, args.annotations)
        video = record.get("video", {})
        if isinstance(video, dict) and video.get("youtube_id") not in (None, args.video_id):
            raise review_inputs.InputsError(
                f"record {args.sample_id} is about video {video.get('youtube_id')}, "
                f"not {args.video_id}")
        duration = load_bundle(args.video_id).get("duration")
        inputs = review_inputs.derive_inputs(args.role, record, args.window, args.until, duration)
    except review_inputs.InputsError as exc:
        sys.exit(str(exc))
    for flag, value in ROLE_MODES[args.role].items():
        setattr(args, flag, value)
    if "frame" in inputs:
        args.frame = inputs["frame"]
    else:
        args.until = inputs["until"]
    return {"sample_id": args.sample_id, "annotations": str(path),
            "record_sha": review_inputs.record_sha(record), "role": args.role,
            "window": args.window, "inputs": inputs}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_id")
    ap.add_argument("--out", required=True, help="the directory of the reviewer's working folder")
    ap.add_argument("--until", type=float, help="prepare everything from the beginning up to this moment")
    ap.add_argument("--from", dest="t_from", type=float, default=0.0,
                    help="the left boundary for --until (0 by default)")
    ap.add_argument("--dense", nargs=2, type=float, metavar=("A", "B"),
                    help="re-sample a stretch with a dense grid")
    ap.add_argument("--step", type=float, default=2.0,
                    help="the --dense step, s (2 by default; less than 1 does not happen — the names "
                         "of the frames are rounded to the second, and half the grid would silently merge)")
    ap.add_argument("--sheet", action="store_true",
                    help=f"with --dense: also tile the frames of the stretch into one image "
                         f"frames/sheet_<first>-<last>.jpg, each cell stamped with its second. "
                         f"At most {SHEET_MAX} frames; the way to take a quick look at a "
                         f"stretch or to compare neighbouring seconds")
    ap.add_argument("--force", action="store_true",
                    help="rebuild a non-empty directory under a different mode")
    ap.add_argument("--max-frames", type=int, default=60,
                    help="the ceiling of frames per --dense call")
    ap.add_argument("--max-sparse", type=int, default=40,
                    help="the ceiling of overview frames with --until; the bundle's cut is "
                         "denser, and the surplus is thinned uniformly")
    ap.add_argument("--frame", type=float, metavar="T",
                    help="a folder of exactly one frame (probe_frame)")
    ap.add_argument("--cleanup", action="store_true",
                    help="remove exactly one completed reviewer workspace under "
                         ".review_ws/<video>/<question>/<subagent>")
    ap.add_argument("--only", choices=("both", "transcript", "frames"), default="both",
                    help="what to put in the folder with --until: both modalities "
                         "(the default), the transcript only (probe_text) or "
                         "the frames only (probe_vision)")
    ap.add_argument("--verify", action="store_true",
                    help="mark the folder as probe_verify's: the transcript, the scene "
                         "frames as copies and the screen description, all up to --until. "
                         "Requires --until and --screen; incompatible with --only and "
                         "--index-only")
    ap.add_argument("--screen", action="store_true",
                    help="put in the text index of the video track (screen_text.md "
                         "and screen.jsonl) from description.jsonl. Allowed for reviewers "
                         "and probe_vision/probe_full/probe_verify; forbidden for probe_text "
                         "and probe_frame")
    ap.add_argument("--sample-id", dest="sample_id",
                    help="read the boundaries of the material off this record instead of "
                         "typing them: needs --role, and --window for semiblind and "
                         "probe_frame. Leaves <out>.inputs.json, which coordinator_log.py "
                         "spawn checks against the record")
    ap.add_argument("--annotations", type=Path,
                    help="the file holding the record, when its id is in several files")
    ap.add_argument("--role", choices=review_inputs.ROLES,
                    help="with --sample-id: whose workspace this is; decides the mode")
    ap.add_argument("--window", type=int,
                    help="with --sample-id: the window the material is cut at (semiblind: "
                         "the stretch ends at its t_end, any window; probe_frame: the middle "
                         "of a required window)")
    ap.add_argument("--index-only", action="store_true", dest="index_only",
                    help="do not copy the frames but put in a manifest frames.md "
                         "with the timecodes and the path. ONLY for full_sample and "
                         "full_window: the manifest names the bundle's directory and does "
                         "not hold the folder's boundary, so the semi-blind reviewer and the "
                         "probes get the frames as copies")
    args = ap.parse_args()

    # A space in the path is a mistake, not a name: ".../q06 full_sample" took a slash for a
    # space, left a folder that --cleanup does not recognise, and it stayed behind.
    if any(ch.isspace() for ch in args.out):
        sys.exit(f"--out {args.out!r} contains a space; the shape is "
                 f".review_ws/<video_id>/<question>/<subagent>, with slashes")
    note = derive_from_record(args) if args.sample_id else None
    if note is None and (args.role or args.window is not None or args.annotations):
        sys.exit("--role, --window and --annotations only work together with --sample-id")

    modes = [args.until is not None, args.dense is not None,
             args.frame is not None, args.cleanup]
    if sum(modes) != 1:
        sys.exit("name exactly one of --until, --dense, --frame or --cleanup")
    if args.only != "both" and args.until is None:
        sys.exit("--only only makes sense together with --until")
    if args.sheet and args.dense is None:
        sys.exit("--sheet only makes sense together with --dense")
    # The verification probe answers the task with the material up to t_s, and its answer
    # decides whether the material up to t_s was ENOUGH. Both channels, copies of the
    # frames (the boundary), the description (the dense reading of the visual channel):
    # anything less and "not enough" would measure the folder rather than the video.
    if args.verify and (args.until is None or not args.screen
                        or args.only != "both" or args.index_only):
        sys.exit("--verify needs --until and --screen, and takes neither --only nor "
                 "--index-only: the verification probe gets both channels as copies, cut "
                 "at t_s, and the description")
    # The screen index is built from frames ONLY (the description run's meta says
    # with_transcript: false), that is, it is a function of the visual channel and
    # nothing more. Hence the boundary does not run "reviewers against probes" but by
    # which channel the probe is entitled to:
    #
    #   text  — forbidden: the index would give it the visual channel in words, and
    #           textonly_solved would stop measuring anything;
    #   frame — forbidden: the index is a timeline, while frozen-frame is obliged to see
    #           one frame and nothing around it, including no history;
    #   vision, full, the reviewers — allowed.
    #
    # For vision it is not merely harmless but cures a known bias: with a single sparse
    # grid the probe gets forty frames for half an hour, visiononly_solved drifts
    # systematically to false, and the audio_dependency label to required. The index is
    # built on a 0.5-second grid, that is, denser than any budget that can be issued to
    # the probe in frames.
    if args.screen and (args.only == "transcript" or args.frame is not None):
        who = "text" if args.only == "transcript" else "frozen-frame"
        why = ("the index would give it the visual channel in words, and textonly_solved "
               "would stop measuring anything"
               if args.only == "transcript" else
               "the index is a timeline, while the probe is obliged to see one frame and nothing "
               "around it, including no history")
        sys.exit(f"--screen is incompatible with the {who} probe's folder: {why}")
    # The manifest does not hold the boundary: it names a path to the bundle, where the
    # whole video lies. The roles for which blindness is mandatory are obliged to get copies.
    if args.index_only and (args.only != "both" or args.frame is not None):
        sys.exit("--index-only is incompatible with a probe's folder: the manifest names the "
                 "bundle's directory, where the whole video lies, and does not hold the folder's boundary. "
                 "The probes and the semi-blind reviewer get the frames as copies")
    # `--dense` re-samples an already prepared folder with frames and writes neither the
    # index nor a copy of the on-screen text: a silently swallowed flag would look as
    # though the index had been ordered and was not needed
    if args.dense is not None and (args.screen or args.index_only):
        which = " and ".join(n for n, v in (("--screen", args.screen),
                                          ("--index-only", args.index_only)) if v)
        sys.exit(f"{which} does not work together with --dense: this mode only "
                 f"adds frames to a ready folder. The index is placed with --until")
    if args.step < 1.0:
        sys.exit(f"--step {args.step}: the names of the frames are rounded to a whole second, "
                 f"so a grid finer than a second will silently merge and return half as many "
                 f"frames as the counter shows")

    out = Path(args.out)
    if args.cleanup:
        try:
            removed = cleanup_workspace(args.video_id, out)
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"workspace {'removed' if removed else 'already absent'}: {out}")
        return
    # A folder with a manifest and a folder with copies are different modes, not variants
    # of one. Otherwise a repeat call without --index-only would leave a manifest for the
    # whole bundle next to "isolated" copies, and the boundary would rest on honesty alone.
    mode = "frame" if args.frame is not None else (args.only if args.until is not None else None)
    if mode == "both" and args.index_only:
        mode = "both-index"
    if mode == "both" and args.verify:
        mode = "verify"
    if mode is not None:
        check_mode(out, mode, args.force)
    out.mkdir(parents=True, exist_ok=True)
    if mode is not None:
        (out / "mode.json").write_text(json.dumps({"mode": mode}), encoding="utf-8")
    bundle = load_bundle(args.video_id)

    if args.frame is not None:
        # The frozen-frame probe must not even be given the boundaries: limits.json by
        # itself says up to what moment the material runs, and it must see one frame and
        # nothing around it. A rebuild after the window has moved must not leave the frame of
        # the old middle beside the new one, so the folder is emptied first.
        shutil.rmtree(out / "frames", ignore_errors=True)
        n = extract_dense(args.video_id, out, args.frame, args.frame, 1.0, 1)
        print(f"working folder : {out}")
        print(f"  frame        : {n} of them at {args.frame:.0f} s")
        print("  no transcript, no neighbouring frames, no limits.json")
        if note is not None:
            print(f"  inputs note  : {review_inputs.write_sidecar(out, note)}")
    elif args.until is not None:
        # Rebuilding the same folder is obliged to be idempotent (9.3): copy_sparse only
        # adds, so a repeat call with a smaller --until left frames beyond the new
        # boundary while limits.json was rewritten and started to lie.
        if args.only in ("both", "frames"):
            shutil.rmtree(out / "frames", ignore_errors=True)
        if args.only in ("both", "transcript"):
            (out / "transcript.md").unlink(missing_ok=True)
        (out / "limits.json").write_text(
            json.dumps({"from": args.t_from, "until": args.until}), encoding="utf-8")
        for name in ("screen_text.md", "screen.jsonl", "frames.md"):
            (out / name).unlink(missing_ok=True)
        cues = frames = 0
        actual = args.until
        if args.only in ("both", "transcript"):
            cues, actual = write_transcript(bundle, out, args.t_from, args.until)
        if args.only in ("both", "frames"):
            if args.index_only:
                frames = write_frame_index(bundle, out, args.t_from, args.until)
            else:
                frames = copy_sparse(bundle, out, args.t_from, args.until, args.max_sparse)
        screen = None
        if args.screen:
            desc = load_description(args.video_id)
            if desc is None:
                sys.exit(f"no data/bundles/{args.video_id}/description.jsonl; "
                         f"run tools/describe_video.py {args.video_id} first")
            screen = write_screen(desc, out, args.t_from, args.until)
        print(f"working folder : {out}  (--only {args.only})")
        if args.only in ("both", "transcript"):
            print(f"  transcript   : {cues} utterances, {args.t_from:.0f}–{actual:.0f} s "
                  f"(requested up to {args.until:.0f})")
        else:
            print("  transcript   : deliberately not placed")
        if args.only in ("both", "frames"):
            how = "a frames.md manifest, no copies" if args.index_only else "copies of scene-change frames from the bundle"
            print(f"  frames       : {frames} of them ({how})")
        else:
            print("  frames       : deliberately not placed")
        if screen is not None:
            print(f"  screen       : {screen[0]} chunks, {screen[1]} lines of text "
                  f"(a model-made description: read in full, confirm on frames)")
        print("  there is no annotation in the folder and there must not be")
        if note is not None:
            print(f"  inputs note  : {review_inputs.write_sidecar(out, note)}")
    else:
        check_dense_allowed(out, args.force)
        a, b = clamp_to_workspace(out, *args.dense)
        cap = min(args.max_frames, SHEET_MAX) if args.sheet else args.max_frames
        n = extract_dense(args.video_id, out, a, b, args.step, cap)
        print(f"frames added: {n} ({a:.0f}–{b:.0f} s, step {args.step} s) -> {out}/frames")
        if args.sheet:
            sheet = build_sheet(out / "frames", dense_times(a, b, args.step))
            print(f"sheet        : {sheet}  (open this one image instead of the frames)")


if __name__ == "__main__":
    main()

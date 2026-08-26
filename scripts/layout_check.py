"""Scene layout checks that manim itself does not have.

manim warns neither about an object going off-screen nor about overlaps: it has
no layout engine, the coordinates are absolute, and everything outside the frame
is simply cropped by the camera. LaTeX stays silent too — manim compiles every
formula in `standalone`, where the page is fitted to the content, so the familiar
`Overfull \\hbox` never arises.

Usage:

    from layout_check import audit
    ...
    audit(self, "Step 2")          # at the end of a slide, before clearing the screen

Running with an error instead of a warning (convenient in CI):

    MANIM_LAYOUT_STRICT=1 manim -ql demo2.py EigenLecture
"""

from __future__ import annotations

import os

import numpy as np

from manim import Mobject, Rectangle, Scene, config, logger

# objects of these types outline/connect others and overlap them by design
_OVERLAP_EXEMPT = ("SurroundingRectangle", "Brace", "BraceLabel", "Line", "Arrow",
                   "Underline", "NumberPlane", "Axes", "ArrowVectorField")


def frame_bounds(scene: Scene) -> tuple[float, float, float, float]:
    """The boundaries of the visible area: (left, right, bottom, top).

    In MovingCameraScene/ZoomedScene the frame travels and changes scale, so
    one must look at camera.frame rather than at the static config.
    """
    frame = getattr(scene.camera, "frame", None)
    if frame is not None:
        return (frame.get_left()[0], frame.get_right()[0],
                frame.get_bottom()[1], frame.get_top()[1])
    half_w, half_h = config.frame_width / 2, config.frame_height / 2
    return -half_w, half_w, -half_h, half_h


def visible_bbox(mob: Mobject, eps: float = 0.01) -> tuple[float, float, float, float] | None:
    """The extents of the visible parts only: (left, right, bottom, top).

    The ordinary get_left()/get_right() counts objects extinguished by FadeOut too —
    they stay in the group's family with zero opacity and inflate the bbox.
    """
    points = [
        part.points
        for part in mob.get_family()
        if len(getattr(part, "points", ())) > 0
        and (getattr(part, "fill_opacity", 0) > eps or getattr(part, "stroke_opacity", 0) > eps)
    ]
    if not points:
        return None
    xs = np.concatenate([p[:, 0] for p in points])
    ys = np.concatenate([p[:, 1] for p in points])
    return float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())


def frame_overflow(
    mob: Mobject,
    bounds: tuple[float, float, float, float] | None = None,
    tol: float = 0.01,
) -> dict[str, float]:
    """By how much the object sticks out of the frame on each side (empty = it does not)."""
    if bounds is None:
        half_w, half_h = config.frame_width / 2, config.frame_height / 2
        bounds = (-half_w, half_w, -half_h, half_h)
    left, right, bottom, top = bounds
    box = visible_bbox(mob)
    if box is None:  # the object is entirely extinguished — nothing to check
        return {}
    m_left, m_right, m_bottom, m_top = box
    return {
        side: round(delta, 3)
        for side, delta in (
            ("left", left - m_left),
            ("right", m_right - right),
            ("bottom", bottom - m_bottom),
            ("top", m_top - top),
        )
        if delta > tol
    }


def bbox_overlap(a: Mobject, b: Mobject, tol: float = 0.05) -> float:
    """The area of the intersection of the habitual bounding boxes (0 if they do not intersect)."""
    dx = min(a.get_right()[0], b.get_right()[0]) - max(a.get_left()[0], b.get_left()[0])
    dy = min(a.get_top()[1], b.get_top()[1]) - max(a.get_bottom()[1], b.get_bottom()[1])
    return dx * dy if dx > tol and dy > tol else 0.0


def audit(
    scene: Scene,
    label: str = "",
    mobjects: list[Mobject] | None = None,
    check_overlaps: bool = True,
    check_intruders: bool = False,
) -> list[str]:
    """Checks the objects of the scene and writes warnings to the log.

    mobjects — what exactly to check; by default the whole content of the scene.
    In a MovingCameraScene pass only the block the camera is currently pointed
    at: the rest of the canvas lies outside the frame deliberately.

    check_intruders — looks for foreign objects that accidentally got into the
    frame (relevant for a canvas with a camera: the edge of a neighbouring block
    creeps into the frame).

    Returns a list of messages; with MANIM_LAYOUT_STRICT=1 raises an AssertionError.
    """
    source = scene.mobjects if mobjects is None else mobjects
    tops = [m for m in source if m.get_width() > 0 and m.get_height() > 0]
    bounds = frame_bounds(scene)
    problems: list[str] = []

    for mob in tops:
        if over := frame_overflow(mob, bounds):
            sides = ", ".join(f"{k} by {v}" for k, v in over.items())
            problems.append(f"{type(mob).__name__} sticks out of the frame ({sides})")

    if check_overlaps:
        checkable = [m for m in tops if type(m).__name__ not in _OVERLAP_EXEMPT]
        for i, a in enumerate(checkable):
            for b in checkable[i + 1:]:
                if area := bbox_overlap(a, b):
                    problems.append(
                        f"{type(a).__name__} and {type(b).__name__} overlap "
                        f"(intersection area {area:.2f})"
                    )

    if check_intruders and mobjects is not None:
        wanted = set()
        for mob in tops:
            wanted.add(id(mob))
            wanted.update(id(sub) for sub in mob.get_family())
        left, right, bottom, top = bounds
        viewport = Rectangle(width=right - left, height=top - bottom).move_to(
            [(left + right) / 2, (bottom + top) / 2, 0]
        )
        camera_frame = getattr(scene.camera, "frame", None)
        if camera_frame is not None:  # the camera frame itself lies in scene.mobjects
            wanted.add(id(camera_frame))
        for mob in scene.mobjects:
            if id(mob) in wanted or mob.get_width() <= 0:
                continue
            if bbox_overlap(mob, viewport):
                problems.append(
                    f"a foreign {type(mob).__name__} got into the frame "
                    f"(its edge at x={mob.get_left()[0]:.1f}..{mob.get_right()[0]:.1f})"
                )

    prefix = f"[layout:{label}] " if label else "[layout] "
    for msg in problems:
        logger.warning(prefix + msg)
    if problems and os.environ.get("MANIM_LAYOUT_STRICT"):
        raise AssertionError(prefix + "; ".join(problems))
    return problems

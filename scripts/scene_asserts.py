"""Checks that an animation matches the mathematics it claims.

layout_check.py watches the layout (the frame boundaries, overlaps). Here it is a
different class of error: the picture sits tidily inside the frame but means the
wrong thing. Such things are caught by comparing what actually happened to the
points of a mobject with what the formula predicts.

The core of the module is `expect_map`: "the points went where the function says".
Everything else is built on top of it and is subject-neutral:

    snapshot(mob)                       a snapshot of the points before the animation
    expect_map(coords, before, after, f)    an arbitrary mapping
    expect_matrix_action(...)           a linear transformation by a matrix
    expect_fixed(before, after)         the object was not supposed to move
    expect_uniform_scale(coord_system)  the same scale on both axes
    expect_on_graph(axes, curve, f)     the curve lies on the graph of the function
    expect_point(actual, expected)      one point where it was expected

Subject-specific checks (for example "this is an eigenvector with λ=3") are built
out of these in the scene file itself — they never come out universal.

MANIM_SCENE_STRICT=1 turns the warnings into an AssertionError.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import numpy as np
from manim import Mobject, logger


def _report(message: str) -> bool:
    logger.warning("[assert] " + message)
    if os.environ.get("MANIM_SCENE_STRICT"):
        raise AssertionError(message)
    return False


def snapshot(mob: Mobject) -> np.ndarray:
    """A copy of a mobject's points — take it BEFORE the animation, compare AFTER."""
    return np.array([p.copy() for p in mob.get_all_points()])


def _to_coords(coord_system: Mobject | None, points: np.ndarray) -> np.ndarray:
    """Converts the scene's points into the coordinates of the system (or leaves them as they are)."""
    if coord_system is None:
        return np.asarray(points)[:, :2]
    return np.array([coord_system.p2c(p)[:2] for p in points])


def expect_map(
    before: np.ndarray,
    after: Mobject | np.ndarray,
    func: Callable[[np.ndarray], np.ndarray],
    label: str = "transformation",
    coord_system: Mobject | None = None,
    tol: float = 0.02,
) -> bool:
    """Every point was supposed to go to func(point).

    coord_system — the coordinate system BEFORE the animation (a snapshot of
    plane.copy() if the animation drags the grid itself). Without it the comparison
    goes in scene coordinates.
    """
    after_points = snapshot(after) if isinstance(after, Mobject) else np.asarray(after)
    if len(before) != len(after_points):
        return _report(f"{label}: there were {len(before)} points, now there are {len(after_points)}")
    if len(before) == 0:
        return _report(f"{label}: the object has no points")

    src = _to_coords(coord_system, before)
    dst = _to_coords(coord_system, after_points)
    expected = np.array([np.asarray(func(p), dtype=float)[:2] for p in src])

    deltas = np.linalg.norm(dst - expected, axis=1)
    worst = int(np.argmax(deltas))
    if deltas[worst] > tol:
        return _report(
            f"{label}: the point {np.round(src[worst], 3)} was supposed to go to "
            f"{np.round(expected[worst], 3)} but ended up at {np.round(dst[worst], 3)} "
            f"(discrepancy {deltas[worst]:.3f}, {int((deltas > tol).sum())} of {len(deltas)} off in total)"
        )
    return True


def expect_matrix_action(
    before: np.ndarray,
    after: Mobject | np.ndarray,
    matrix: list[list[float]] | np.ndarray,
    label: str = "matrix",
    coord_system: Mobject | None = None,
    tol: float = 0.02,
) -> bool:
    """The object was transformed by exactly the matrix declared.

    It catches two classic manim mistakes: an ApplyMatrix without about_point (when
    the origin is displaced relative to the centre of the frame) and an unequal scale
    of the axes, under which the transformation of the scene equals S·A·S⁻¹ rather
    than A.
    """
    m = np.asarray(matrix, dtype=float)
    return expect_map(before, after, lambda p: m @ p, label, coord_system, tol)


def expect_fixed(
    before: np.ndarray,
    after: Mobject | np.ndarray,
    label: str = "object",
    tol: float = 0.02,
) -> bool:
    """The object is obliged to stay put (a frequent invariant: an axis, the origin)."""
    return expect_map(before, after, lambda p: p, label, None, tol)


def expect_uniform_scale(coord_system: Mobject, label: str = "axes", tol: float = 0.01) -> bool:
    """The same scale on both axes — a precondition for ApplyMatrix to be correct.

    With different scales a circle is drawn as an ellipse, a rotation skews the
    figure, and the eigendirections of a matrix drift away.
    """
    unit_x = np.linalg.norm(coord_system.c2p(1, 0) - coord_system.c2p(0, 0))
    unit_y = np.linalg.norm(coord_system.c2p(0, 1) - coord_system.c2p(0, 0))
    if abs(unit_x - unit_y) > tol * max(unit_x, unit_y):
        return _report(
            f"{label}: the scale along x = {unit_x:.3f} scene units, along y = {unit_y:.3f} — "
            f"a discrepancy of {abs(unit_x - unit_y) / max(unit_x, unit_y):.1%}; "
            f"the geometry (angles, rotations, ApplyMatrix) will be distorted"
        )
    return True


def expect_on_graph(
    axes: Mobject,
    curve: Mobject,
    func: Callable[[float], float],
    label: str = "graph",
    tol: float = 0.02,
    samples: int = 40,
) -> bool:
    """The curve drawn really does lie on the graph of y = func(x)."""
    points = snapshot(curve)
    if len(points) == 0:
        return _report(f"{label}: the curve has no points")

    step = max(1, len(points) // samples)
    worst_delta, worst_x = 0.0, 0.0
    for point in points[::step]:
        x, y = axes.p2c(point)[:2]
        delta = abs(y - float(func(x)))
        if delta > worst_delta:
            worst_delta, worst_x = delta, x

    if worst_delta > tol:
        return _report(
            f"{label}: at x = {worst_x:.3f} the curve departs from the function by {worst_delta:.3f}"
        )
    return True


def expect_point(
    actual: np.ndarray,
    expected: np.ndarray,
    label: str = "point",
    tol: float = 0.05,
) -> bool:
    """One specific point of the scene is where the computation predicts."""
    delta = float(np.linalg.norm(np.asarray(actual)[:2] - np.asarray(expected)[:2]))
    if delta > tol:
        return _report(
            f"{label}: {np.round(np.asarray(actual)[:2], 3)} instead of "
            f"{np.round(np.asarray(expected)[:2], 3)} (discrepancy {delta:.3f})"
        )
    return True

"""Проверки вёрстки сцены, которых нет в самом manim.

manim не предупреждает ни о выходе объекта за кадр, ни о наложениях: у него
нет layout-движка, координаты абсолютные, а всё, что вне кадра, просто
обрезается камерой. LaTeX тоже молчит — manim компилирует каждую формулу
в `standalone`, где страница подгоняется под содержимое, так что привычного
`Overfull \\hbox` не возникает.

Использование:

    from layout_check import audit
    ...
    audit(self, "Шаг 2")          # в конце слайда, перед очисткой экрана

Запуск с ошибкой вместо предупреждения (удобно в CI):

    MANIM_LAYOUT_STRICT=1 manim -ql demo2.py EigenLecture
"""

from __future__ import annotations

import os

import numpy as np

from manim import Mobject, Rectangle, Scene, config, logger

# объекты этих типов обводят/соединяют другие и пересекаются с ними по смыслу
_OVERLAP_EXEMPT = ("SurroundingRectangle", "Brace", "BraceLabel", "Line", "Arrow",
                   "Underline", "NumberPlane", "Axes", "ArrowVectorField")


def frame_bounds(scene: Scene) -> tuple[float, float, float, float]:
    """Границы видимой области: (left, right, bottom, top).

    В MovingCameraScene/ZoomedScene кадр ездит и меняет масштаб, поэтому
    смотреть надо на camera.frame, а не на статический config.
    """
    frame = getattr(scene.camera, "frame", None)
    if frame is not None:
        return (frame.get_left()[0], frame.get_right()[0],
                frame.get_bottom()[1], frame.get_top()[1])
    half_w, half_h = config.frame_width / 2, config.frame_height / 2
    return -half_w, half_w, -half_h, half_h


def visible_bbox(mob: Mobject, eps: float = 0.01) -> tuple[float, float, float, float] | None:
    """Габариты только видимых частей: (left, right, bottom, top).

    Обычный get_left()/get_right() считает и погашенные FadeOut'ом объекты —
    они остаются в семье группы с нулевой непрозрачностью и раздувают bbox.
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
    """Насколько объект вылез за кадр по каждой стороне (пусто = не вылез)."""
    if bounds is None:
        half_w, half_h = config.frame_width / 2, config.frame_height / 2
        bounds = (-half_w, half_w, -half_h, half_h)
    left, right, bottom, top = bounds
    box = visible_bbox(mob)
    if box is None:  # объект целиком погашен — проверять нечего
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
    """Площадь пересечения habitual bounding box'ов (0, если не пересекаются)."""
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
    """Проверяет объекты сцены и пишет предупреждения в лог.

    mobjects — что именно проверять; по умолчанию всё содержимое сцены.
    В MovingCameraScene передавайте только тот блок, на который сейчас
    наведена камера: остальной холст намеренно лежит вне кадра.

    check_intruders — ищет посторонние объекты, случайно попавшие в кадр
    (актуально для холста с камерой: край соседнего блока лезет в кадр).

    Возвращает список сообщений; при MANIM_LAYOUT_STRICT=1 бросает AssertionError.
    """
    source = scene.mobjects if mobjects is None else mobjects
    tops = [m for m in source if m.get_width() > 0 and m.get_height() > 0]
    bounds = frame_bounds(scene)
    problems: list[str] = []

    for mob in tops:
        if over := frame_overflow(mob, bounds):
            sides = ", ".join(f"{k} на {v}" for k, v in over.items())
            problems.append(f"{type(mob).__name__} вылезает за кадр ({sides})")

    if check_overlaps:
        checkable = [m for m in tops if type(m).__name__ not in _OVERLAP_EXEMPT]
        for i, a in enumerate(checkable):
            for b in checkable[i + 1:]:
                if area := bbox_overlap(a, b):
                    problems.append(
                        f"{type(a).__name__} и {type(b).__name__} накладываются "
                        f"(площадь пересечения {area:.2f})"
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
        if camera_frame is not None:  # сам кадр камеры лежит в scene.mobjects
            wanted.add(id(camera_frame))
        for mob in scene.mobjects:
            if id(mob) in wanted or mob.get_width() <= 0:
                continue
            if bbox_overlap(mob, viewport):
                problems.append(
                    f"посторонний {type(mob).__name__} попал в кадр "
                    f"(его край на x={mob.get_left()[0]:.1f}..{mob.get_right()[0]:.1f})"
                )

    prefix = f"[layout:{label}] " if label else "[layout] "
    for msg in problems:
        logger.warning(prefix + msg)
    if problems and os.environ.get("MANIM_LAYOUT_STRICT"):
        raise AssertionError(prefix + "; ".join(problems))
    return problems

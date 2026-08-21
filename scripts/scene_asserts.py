"""Проверки того, что анимация соответствует заявленной математике.

layout_check.py следит за вёрсткой (границы кадра, наложения). Здесь — другой
класс ошибок: картинка аккуратно лежит в кадре, но означает не то. Такое
ловится сравнением того, что реально произошло с точками мобжекта, с тем, что
предсказывает формула.

Ядро модуля — `expect_map`: «точки перешли туда, куда velit функция». Всё
остальное построено поверх и предметно нейтрально:

    snapshot(mob)                       снимок точек до анимации
    expect_map(coords, before, after, f)    произвольное отображение
    expect_matrix_action(...)           линейное преобразование по матрице
    expect_fixed(before, after)         объект не должен был сдвинуться
    expect_uniform_scale(coord_system)  одинаковый масштаб осей
    expect_on_graph(axes, curve, f)     кривая лежит на графике функции
    expect_point(actual, expected)      одна точка там, где ожидалось

Предметные проверки (например «это собственный вектор с λ=3») строятся из них
в самом файле сцены — универсальными они не бывают.

MANIM_SCENE_STRICT=1 превращает предупреждения в AssertionError.
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
    """Копия точек мобжекта — снимать ДО анимации, сравнивать ПОСЛЕ."""
    return np.array([p.copy() for p in mob.get_all_points()])


def _to_coords(coord_system: Mobject | None, points: np.ndarray) -> np.ndarray:
    """Переводит точки сцены в координаты системы (или оставляет как есть)."""
    if coord_system is None:
        return np.asarray(points)[:, :2]
    return np.array([coord_system.p2c(p)[:2] for p in points])


def expect_map(
    before: np.ndarray,
    after: Mobject | np.ndarray,
    func: Callable[[np.ndarray], np.ndarray],
    label: str = "преобразование",
    coord_system: Mobject | None = None,
    tol: float = 0.02,
) -> bool:
    """Каждая точка должна была перейти в func(точка).

    coord_system — система координат ДО анимации (снимок plane.copy(), если
    анимация тянет саму сетку). Без неё сравнение идёт в координатах сцены.
    """
    after_points = snapshot(after) if isinstance(after, Mobject) else np.asarray(after)
    if len(before) != len(after_points):
        return _report(f"{label}: было {len(before)} точек, стало {len(after_points)}")
    if len(before) == 0:
        return _report(f"{label}: у объекта нет точек")

    src = _to_coords(coord_system, before)
    dst = _to_coords(coord_system, after_points)
    expected = np.array([np.asarray(func(p), dtype=float)[:2] for p in src])

    deltas = np.linalg.norm(dst - expected, axis=1)
    worst = int(np.argmax(deltas))
    if deltas[worst] > tol:
        return _report(
            f"{label}: точка {np.round(src[worst], 3)} должна была перейти в "
            f"{np.round(expected[worst], 3)}, а оказалась в {np.round(dst[worst], 3)} "
            f"(расхождение {deltas[worst]:.3f}, всего мимо {int((deltas > tol).sum())} из {len(deltas)})"
        )
    return True


def expect_matrix_action(
    before: np.ndarray,
    after: Mobject | np.ndarray,
    matrix: list[list[float]] | np.ndarray,
    label: str = "матрица",
    coord_system: Mobject | None = None,
    tol: float = 0.02,
) -> bool:
    """Объект преобразован ровно заявленной матрицей.

    Ловит две классические ошибки manim: ApplyMatrix без about_point (когда
    начало координат смещено относительно центра кадра) и неравный масштаб
    осей, при котором преобразование сцены равно S·A·S⁻¹, а не A.
    """
    m = np.asarray(matrix, dtype=float)
    return expect_map(before, after, lambda p: m @ p, label, coord_system, tol)


def expect_fixed(
    before: np.ndarray,
    after: Mobject | np.ndarray,
    label: str = "объект",
    tol: float = 0.02,
) -> bool:
    """Объект обязан остаться на месте (частый инвариант: ось, начало координат)."""
    return expect_map(before, after, lambda p: p, label, None, tol)


def expect_uniform_scale(coord_system: Mobject, label: str = "оси", tol: float = 0.01) -> bool:
    """Одинаковый масштаб по осям — предусловие корректности ApplyMatrix.

    При разных масштабах круг рисуется эллипсом, поворот перекашивает фигуру,
    а собственные направления матрицы уезжают.
    """
    unit_x = np.linalg.norm(coord_system.c2p(1, 0) - coord_system.c2p(0, 0))
    unit_y = np.linalg.norm(coord_system.c2p(0, 1) - coord_system.c2p(0, 0))
    if abs(unit_x - unit_y) > tol * max(unit_x, unit_y):
        return _report(
            f"{label}: масштаб по x = {unit_x:.3f} ед. сцены, по y = {unit_y:.3f} — "
            f"расхождение {abs(unit_x - unit_y) / max(unit_x, unit_y):.1%}; "
            f"геометрия (углы, повороты, ApplyMatrix) будет искажена"
        )
    return True


def expect_on_graph(
    axes: Mobject,
    curve: Mobject,
    func: Callable[[float], float],
    label: str = "график",
    tol: float = 0.02,
    samples: int = 40,
) -> bool:
    """Нарисованная кривая действительно лежит на графике y = func(x)."""
    points = snapshot(curve)
    if len(points) == 0:
        return _report(f"{label}: у кривой нет точек")

    step = max(1, len(points) // samples)
    worst_delta, worst_x = 0.0, 0.0
    for point in points[::step]:
        x, y = axes.p2c(point)[:2]
        delta = abs(y - float(func(x)))
        if delta > worst_delta:
            worst_delta, worst_x = delta, x

    if worst_delta > tol:
        return _report(
            f"{label}: при x = {worst_x:.3f} кривая отходит от функции на {worst_delta:.3f}"
        )
    return True


def expect_point(
    actual: np.ndarray,
    expected: np.ndarray,
    label: str = "точка",
    tol: float = 0.05,
) -> bool:
    """Одна конкретная точка сцены там, где предсказывает расчёт."""
    delta = float(np.linalg.norm(np.asarray(actual)[:2] - np.asarray(expected)[:2]))
    if delta > tol:
        return _report(
            f"{label}: {np.round(np.asarray(actual)[:2], 3)} вместо "
            f"{np.round(np.asarray(expected)[:2], 3)} (расхождение {delta:.3f})"
        )
    return True

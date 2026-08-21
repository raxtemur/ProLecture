"""Развёрнутое решение вузовской задачи: система линейных ОДУ x' = Ax.

Задача не помещается на один экран, поэтому файл заодно демонстрирует четыре
разных способа «листать слайды» в manim:

  1. self.next_section(...)      — логическое деление ролика на части;
                                   с флагом --save_sections каждая часть
                                   пишется отдельным mp4 (см. media/videos/.../sections/).
  2. self.play(FadeOut(*self.mobjects))
                                 — самая частая смена «слайда»: очистка экрана.
  3. VGroup(...).animate.shift(UP)
                                 — прокрутка длинной выкладки, когда строки
                                   вывода не влезают по высоте.
  4. MovingCameraScene + self.camera.frame
                                 — весь конспект лежит на одном большом холсте,
                                   а «слайд» = положение камеры (сцена CanvasTour).

Рендер:
    conda activate rah_manim
    manim -ql demo2.py EigenLecture --save_sections
    manim -ql demo2.py CanvasTour

Вёрстку сторожит layout_check.audit(): manim НЕ предупреждает ни о выходе
объекта за кадр, ни о наложениях — молча обрезает камерой. Строгий режим:
    MANIM_LAYOUT_STRICT=1 manim -ql demo2.py EigenLecture
"""

from manim import *

from layout_check import audit
from scene_asserts import (
    expect_matrix_action,
    expect_point,
    expect_uniform_scale,
    snapshot,
)

# --- данные задачи ---------------------------------------------------------
A_MAT = [[2, 1], [1, 2]]
EIGEN_SLOW = np.array([1, -1, 0]) / np.sqrt(2)   # λ = 1
EIGEN_FAST = np.array([1, 1, 0]) / np.sqrt(2)    # λ = 3


def fit(mob: Mobject, margin: float = 1.2) -> Mobject:
    """Ужимает объект, если он шире кадра (частая беда длинных формул)."""
    max_width = config.frame_width - margin
    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)
    return mob


def solution(t: float) -> np.ndarray:
    """x(t) = ½ e^t (1,-1) + ½ e^{3t} (1,1) — решение с x(0) = (1,0)."""
    return np.array(
        [
            0.5 * (np.exp(t) + np.exp(3 * t)),
            0.5 * (np.exp(3 * t) - np.exp(t)),
            0.0,
        ]
    )


class EigenLecture(Scene):
    """Полное решение задачи, разбитое на секции-«слайды»."""

    def construct(self):
        self.slide_statement()
        self.slide_char_poly()
        self.slide_eigenvectors()
        self.slide_geometry()
        self.slide_answer()

    # -- служебное ----------------------------------------------------------
    def slide_title(self, number: int, text: str) -> VGroup:
        """Шапка слайда: номер + название + линейка под ними."""
        tag = Text(f"Шаг {number}", font_size=24, color=GREY_B)
        name = Text(text, font_size=34, weight=BOLD)
        head = VGroup(tag, name).arrange(RIGHT, buff=0.4)
        rule = Line(LEFT, RIGHT).set_width(config.frame_width - 1.5)
        rule.set_stroke(GREY_D, 2).next_to(head, DOWN, buff=0.15)
        group = VGroup(head, rule).to_edge(UP, buff=0.4)
        return group

    def wipe(self, label: str = ""):
        """Способ №2: смена слайда через затухание всего, что на экране."""
        audit(self, label)  # manim сам о вылезаниях не предупреждает
        if self.mobjects:
            self.play(FadeOut(*self.mobjects), run_time=0.6)

    # -- слайды -------------------------------------------------------------
    def slide_statement(self):
        self.next_section("Условие")  # способ №1
        head = self.slide_title(1, "Условие")

        task = MathTex(
            r"\dot{x}(t) = A\,x(t),\qquad "
            r"A = \begin{bmatrix} 2 & 1 \\ 1 & 2 \end{bmatrix},\qquad "
            r"x(0) = \begin{bmatrix} 1 \\ 0 \end{bmatrix}",
            font_size=42,
        )
        fit(task)
        plan = VGroup(
            Text("1. характеристический многочлен  →  λ", font_size=28),
            Text("2. собственные векторы  →  базис", font_size=28),
            Text("3. геометрия действия A на плоскости", font_size=28),
            Text("4. общее решение и константы из x(0)", font_size=28),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.28)
        plan.next_to(task, DOWN, buff=0.8)

        self.play(FadeIn(head, shift=DOWN * 0.3))
        self.play(Write(task))
        self.play(LaggedStartMap(FadeIn, plan, shift=RIGHT * 0.3, lag_ratio=0.25))
        self.wait(0.6)
        self.wipe("Шаг 1")

    def slide_char_poly(self):
        self.next_section("Характеристический многочлен")
        head = self.slide_title(2, "Характеристический многочлен")
        self.add(head)

        steps = VGroup(
            MathTex(r"\det(A - \lambda I) = 0", font_size=40),
            MathTex(
                r"\det\begin{bmatrix} 2-\lambda & 1 \\ 1 & 2-\lambda \end{bmatrix}"
                r" = (2-\lambda)^2 - 1",
                font_size=40,
            ),
            MathTex(r"(2-\lambda)^2 - 1 = \lambda^2 - 4\lambda + 3", font_size=40),
            MathTex(r"\lambda^2 - 4\lambda + 3 = (\lambda - 1)(\lambda - 3)", font_size=40),
            MathTex(r"\lambda_1 = 1, \qquad \lambda_2 = 3", font_size=44, color=YELLOW),
        ).arrange(DOWN, buff=0.45)
        steps.next_to(head, DOWN, buff=0.6)

        # способ №3: строк больше, чем влезает по высоте, — держим «окно»
        # из трёх последних, остальные уезжают вверх и гасятся
        line_gap = abs(steps[0].get_center()[1] - steps[1].get_center()[1])
        visible: list[Mobject] = []
        for step in steps:
            self.play(FadeIn(step, shift=UP * 0.2), run_time=0.7)
            visible.append(step)
            if len(visible) > 3:
                oldest = visible.pop(0)
                self.play(
                    FadeOut(oldest, shift=UP * 0.3),
                    steps.animate.shift(UP * line_gap),
                    run_time=0.6,
                )
                # steps.animate возвращает в сцену всю группу целиком, вместе
                # с только что погашенной строкой — она остаётся висеть выше
                # кадра. Поэтому выводим строку и из группы тоже.
                steps.remove(oldest)
                self.remove(oldest)

        box = SurroundingRectangle(steps[-1], color=YELLOW, buff=0.25)
        self.play(Create(box))
        self.wait(0.5)
        self.wipe("Шаг 2")

    def slide_eigenvectors(self):
        self.next_section("Собственные векторы")
        head = self.slide_title(3, "Собственные векторы")
        self.add(head)

        left = VGroup(
            MathTex(r"\lambda_1 = 1:", font_size=38, color=BLUE_B),
            MathTex(
                r"(A - I)v = \begin{bmatrix} 1 & 1 \\ 1 & 1 \end{bmatrix} v = 0",
                font_size=34,
            ),
            MathTex(r"v_1 = \begin{bmatrix} 1 \\ -1 \end{bmatrix}", font_size=38),
        ).arrange(DOWN, buff=0.4)

        right = VGroup(
            MathTex(r"\lambda_2 = 3:", font_size=38, color=RED_B),
            MathTex(
                r"(A - 3I)v = \begin{bmatrix} -1 & 1 \\ 1 & -1 \end{bmatrix} v = 0",
                font_size=34,
            ),
            MathTex(r"v_2 = \begin{bmatrix} 1 \\ 1 \end{bmatrix}", font_size=38),
        ).arrange(DOWN, buff=0.4)

        columns = VGroup(left, right).arrange(RIGHT, buff=1.4).next_to(head, DOWN, buff=0.7)
        divider = Line(UP, DOWN).set_height(columns.height).set_stroke(GREY_D, 2)
        divider.move_to(columns)

        # кириллица в MathTex не компилируется (pdflatex + Unicode) —
        # текстовые пояснения делаем через Text, формулы оставляем в MathTex
        note = VGroup(
            MathTex(r"v_1 \perp v_2 \;\Longrightarrow\; A = A^{\top}", font_size=32, color=GREY_A),
            Text("симметричная матрица: собственные векторы ортогональны",
                 font_size=26, color=GREY_A),
        ).arrange(DOWN, buff=0.2)
        fit(note)
        note.next_to(columns, DOWN, buff=0.5)

        self.play(FadeIn(left, shift=RIGHT * 0.3), Create(divider))
        self.play(FadeIn(right, shift=LEFT * 0.3))
        self.play(Write(note))
        self.wait(0.5)
        self.wipe("Шаг 3")

    def slide_geometry(self):
        self.next_section("Геометрия")
        head = self.slide_title(4, "Как A действует на плоскости")
        self.add(head)

        plane = NumberPlane(
            x_range=[-4, 4, 1],
            y_range=[-3, 3, 1],
            x_length=7.5,
            y_length=5.625,  # тот же масштаб, что по x (7.5/8 = 5.625/6):
            # иначе ApplyMatrix в координатах сцены равен S·A·S⁻¹, а не A
            background_line_style={"stroke_opacity": 0.35},
        ).next_to(head, DOWN, buff=0.35)

        v1 = Arrow(plane.c2p(0, 0), plane.c2p(1, -1), buff=0, color=BLUE_B)
        v2 = Arrow(plane.c2p(0, 0), plane.c2p(1, 1), buff=0, color=RED_B)
        l1 = MathTex(r"v_1", font_size=32, color=BLUE_B).next_to(v1.get_end(), DR, buff=0.15)
        l2 = MathTex(r"v_2", font_size=32, color=RED_B).next_to(v2.get_end(), UR, buff=0.15)

        caption = VGroup(
            MathTex(r"Av_1 = 1\cdot v_1", font_size=30, color=BLUE_B),
            Text("длина сохраняется", font_size=24, color=BLUE_B),
            MathTex(r"Av_2 = 3\cdot v_2", font_size=30, color=RED_B),
            Text("растяжение втрое", font_size=24, color=RED_B),
        ).arrange(RIGHT, buff=0.35)
        fit(caption)
        caption.next_to(plane, DOWN, buff=0.25)

        self.play(Create(plane), run_time=1.2)
        self.play(GrowArrow(v1), GrowArrow(v2), FadeIn(l1), FadeIn(l2))
        self.play(Write(caption))
        # ApplyMatrix действует относительно ORIGIN сцены, а плоскость сдвинута
        # вниз под заголовок — без about_point преобразование выходит неверным
        origin = plane.c2p(0, 0)
        plane_ref = plane.copy()  # сетку сейчас перекосит, снимок нужен для проверок
        expect_uniform_scale(plane, "оси плоскости")
        before = {"сетка": snapshot(plane), "v1": snapshot(v1), "v2": snapshot(v2)}
        v1_end, v2_end = v1.get_end().copy(), v2.get_end().copy()

        self.play(
            ApplyMatrix(A_MAT, plane, about_point=origin),
            ApplyMatrix(A_MAT, v1, about_point=origin),
            ApplyMatrix(A_MAT, v2, about_point=origin),
            run_time=2.5,
        )
        # общая проверка: всё преобразовано ровно матрицей A. Она предметно
        # нейтральна и ловит и забытый about_point, и неравный масштаб осей
        for name, mob in (("сетка", plane), ("v1", v1), ("v2", v2)):
            expect_matrix_action(before[name], mob, A_MAT, name, coord_system=plane_ref)

        # прикладной инвариант именно этой задачи — две строки поверх общих проверок
        expect_point(v1.get_end(), v1_end, "v1: λ=1, конец не должен был сдвинуться")
        expect_point(v2.get_end(), origin + 3 * (v2_end - origin), "v2: λ=3, ровно втрое дальше")

        self.wait(0.4)
        self.play(
            ApplyMatrix(np.linalg.inv(A_MAT), plane, about_point=origin),
            ApplyMatrix(np.linalg.inv(A_MAT), v1, about_point=origin),
            ApplyMatrix(np.linalg.inv(A_MAT), v2, about_point=origin),
            run_time=1.2,
        )
        self.wait(0.3)
        self.wipe("Шаг 4")

    def slide_answer(self):
        self.next_section("Ответ")
        head = self.slide_title(5, "Общее решение и ответ")
        self.add(head)

        general = MathTex(
            r"x(t) = c_1 e^{t} \begin{bmatrix} 1 \\ -1 \end{bmatrix}"
            r" + c_2 e^{3t} \begin{bmatrix} 1 \\ 1 \end{bmatrix}",
            font_size=38,
        ).next_to(head, DOWN, buff=0.5)

        initial = MathTex(
            r"x(0) = \begin{bmatrix} 1 \\ 0 \end{bmatrix}"
            r"\;\Longrightarrow\;"
            r"\begin{cases} c_1 + c_2 = 1 \\ -c_1 + c_2 = 0 \end{cases}"
            r"\;\Longrightarrow\; c_1 = c_2 = \tfrac{1}{2}",
            font_size=34,
        )
        fit(initial)
        initial.next_to(general, DOWN, buff=0.5)

        answer = MathTex(
            r"x(t) = \tfrac{1}{2}\begin{bmatrix} e^{t} + e^{3t} \\ e^{3t} - e^{t} \end{bmatrix}",
            font_size=42,
            color=YELLOW,
        ).next_to(initial, DOWN, buff=0.6)

        self.play(Write(general))
        self.play(FadeIn(initial, shift=UP * 0.2))
        self.play(TransformFromCopy(general, answer))
        self.play(Create(SurroundingRectangle(answer, color=YELLOW, buff=0.25)))
        self.wait(0.6)


class CanvasTour(MovingCameraScene):
    """Способ №4: конспект целиком лежит на большом холсте, «слайд» = кадр камеры.

    Такой приём удобен, когда нужно показать связь между блоками: камера
    отъезжает и видно всю картину сразу.
    """

    def construct(self):
        self.camera.frame.save_state()

        # --- блок 1: постановка (левый верх) -------------------------------
        block1 = VGroup(
            Text("Задача", font_size=32, weight=BOLD),
            MathTex(r"\dot{x} = Ax,\quad A = \begin{bmatrix} 2 & 1 \\ 1 & 2\end{bmatrix}", font_size=34),
        ).arrange(DOWN, buff=0.35).move_to(LEFT * 11 + UP * 4)

        # --- блок 2: спектр (правый верх) ----------------------------------
        block2 = VGroup(
            Text("Спектр", font_size=32, weight=BOLD),
            MathTex(r"\lambda_1 = 1,\ v_1 = \begin{bmatrix} 1 \\ -1\end{bmatrix}", font_size=32, color=BLUE_B),
            MathTex(r"\lambda_2 = 3,\ v_2 = \begin{bmatrix} 1 \\ 1\end{bmatrix}", font_size=32, color=RED_B),
        ).arrange(DOWN, buff=0.3).move_to(RIGHT * 11 + UP * 4)

        # --- блок 3: фазовый портрет (центр, крупный) ----------------------
        plane = NumberPlane(
            x_range=[-3, 3, 1],
            y_range=[-3, 3, 1],
            x_length=6,
            y_length=6,
            background_line_style={"stroke_opacity": 0.3},
        ).move_to(DOWN * 4)

        field = ArrowVectorField(
            lambda p: np.array([2 * p[0] + p[1], p[0] + 2 * p[1], 0]),
            x_range=[-3, 3, 0.75],
            y_range=[-3, 3, 0.75],
            length_func=lambda norm: 0.35 * sigmoid(norm),
        ).move_to(plane.get_center())

        traj = ParametricFunction(
            lambda t: plane.c2p(*solution(t)[:2]),
            t_range=[-2.2, 0.35, 0.02],
            color=YELLOW,
            stroke_width=5,
        )
        dot = Dot(color=YELLOW).move_to(plane.c2p(*solution(0)[:2]))
        dot_label = MathTex(r"x(0)", font_size=28, color=YELLOW).next_to(dot, RIGHT, buff=0.15)

        block3 = VGroup(plane, field, traj, dot, dot_label)
        block3_title = Text("Фазовый портрет", font_size=32, weight=BOLD)
        block3_title.next_to(plane, UP, buff=0.3)

        # --- блок 4: ответ (право снизу) -----------------------------------
        block4 = VGroup(
            Text("Ответ", font_size=32, weight=BOLD),
            MathTex(
                r"x(t) = \tfrac{1}{2}\begin{bmatrix} e^{t} + e^{3t} \\ e^{3t} - e^{t}\end{bmatrix}",
                font_size=34,
                color=YELLOW,
            ),
        ).arrange(DOWN, buff=0.35).move_to(RIGHT * 13 + DOWN * 5)

        self.add(block1, block2, block3_title, block3, block4)

        # камера как «листалка»: наезд на каждый блок по очереди.
        # ВАЖНО: set(width=...) задаёт только ширину, высота пересчитывается по
        # аспекту кадра — если блок высокий, он обрежется. Поэтому берём
        # максимум из требований по ширине и по высоте.
        aspect = config.frame_width / config.frame_height

        def frame_width_for(target: Mobject, margin: float = 1.2) -> float:
            return max(target.width * margin, target.height * margin * aspect)

        self.camera.frame.move_to(block1).set(width=frame_width_for(block1, 1.5))
        audit(self, "блок 1", [block1], check_overlaps=False)
        self.wait(0.4)

        tour = (
            ("блок 2", block2, 1.35),
            ("блок 3", VGroup(block3_title, block3), 1.15),
            ("блок 4", block4, 1.4),
        )
        for label, target, margin in tour:
            self.play(
                self.camera.frame.animate.move_to(target).set(width=frame_width_for(target, margin)),
                run_time=1.6,
            )
            audit(self, label, [target], check_overlaps=False, check_intruders=True)
            self.wait(0.4)

        # финальный отъезд: видно весь конспект целиком
        everything = VGroup(block1, block2, block3_title, block3, block4)
        self.play(
            self.camera.frame.animate.move_to(everything).set(width=frame_width_for(everything, 1.08)),
            run_time=2,
        )
        audit(self, "весь холст", [everything], check_overlaps=False)
        self.wait(0.8)

"""A worked solution of a university problem: a system of linear ODEs x' = Ax.

The problem does not fit on one screen, so the file also demonstrates four different
ways of "turning the slides" in manim:

  1. self.next_section(...)      — a logical division of the video into parts;
                                   with the --save_sections flag each part is
                                   written as a separate mp4 (see media/videos/.../sections/).
  2. self.play(FadeOut(*self.mobjects))
                                 — the commonest "slide" change: clearing the screen.
  3. VGroup(...).animate.shift(UP)
                                 — scrolling a long derivation, when the lines of the
                                   output do not fit vertically.
  4. MovingCameraScene + self.camera.frame
                                 — the whole set of notes lies on one large canvas,
                                   and a "slide" = the position of the camera (the
                                   CanvasTour scene).

Rendering:
    conda activate rah_manim
    manim -ql demo2.py EigenLecture --save_sections
    manim -ql demo2.py CanvasTour

The layout is guarded by layout_check.audit(): manim does NOT warn either about an
object going off-screen or about overlaps — it silently crops with the camera. Strict
mode:
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

# --- the data of the problem -----------------------------------------------
A_MAT = [[2, 1], [1, 2]]
EIGEN_SLOW = np.array([1, -1, 0]) / np.sqrt(2)   # λ = 1
EIGEN_FAST = np.array([1, 1, 0]) / np.sqrt(2)    # λ = 3


def fit(mob: Mobject, margin: float = 1.2) -> Mobject:
    """Shrinks an object if it is wider than the frame (a frequent trouble with long formulas)."""
    max_width = config.frame_width - margin
    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)
    return mob


def solution(t: float) -> np.ndarray:
    """x(t) = ½ e^t (1,-1) + ½ e^{3t} (1,1) — the solution with x(0) = (1,0)."""
    return np.array(
        [
            0.5 * (np.exp(t) + np.exp(3 * t)),
            0.5 * (np.exp(3 * t) - np.exp(t)),
            0.0,
        ]
    )


class EigenLecture(Scene):
    """The full solution of the problem, broken into section-\"slides\"."""

    def construct(self):
        self.slide_statement()
        self.slide_char_poly()
        self.slide_eigenvectors()
        self.slide_geometry()
        self.slide_answer()

    # -- service helpers ----------------------------------------------------
    def slide_title(self, number: int, text: str) -> VGroup:
        """A slide heading: the number + the title + a rule beneath them."""
        tag = Text(f"Step {number}", font_size=24, color=GREY_B)
        name = Text(text, font_size=34, weight=BOLD)
        head = VGroup(tag, name).arrange(RIGHT, buff=0.4)
        rule = Line(LEFT, RIGHT).set_width(config.frame_width - 1.5)
        rule.set_stroke(GREY_D, 2).next_to(head, DOWN, buff=0.15)
        group = VGroup(head, rule).to_edge(UP, buff=0.4)
        return group

    def wipe(self, label: str = ""):
        """Way no. 2: changing the slide by fading out everything on the screen."""
        audit(self, label)  # manim itself does not warn about things sticking out
        if self.mobjects:
            self.play(FadeOut(*self.mobjects), run_time=0.6)

    # -- the slides ---------------------------------------------------------
    def slide_statement(self):
        self.next_section("The problem")  # way no. 1
        head = self.slide_title(1, "The problem")

        task = MathTex(
            r"\dot{x}(t) = A\,x(t),\qquad "
            r"A = \begin{bmatrix} 2 & 1 \\ 1 & 2 \end{bmatrix},\qquad "
            r"x(0) = \begin{bmatrix} 1 \\ 0 \end{bmatrix}",
            font_size=42,
        )
        fit(task)
        plan = VGroup(
            Text("1. the characteristic polynomial  →  λ", font_size=28),
            Text("2. the eigenvectors  →  a basis", font_size=28),
            Text("3. the geometry of the action of A on the plane", font_size=28),
            Text("4. the general solution and the constants from x(0)", font_size=28),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.28)
        plan.next_to(task, DOWN, buff=0.8)

        self.play(FadeIn(head, shift=DOWN * 0.3))
        self.play(Write(task))
        self.play(LaggedStartMap(FadeIn, plan, shift=RIGHT * 0.3, lag_ratio=0.25))
        self.wait(0.6)
        self.wipe("Step 1")

    def slide_char_poly(self):
        self.next_section("The characteristic polynomial")
        head = self.slide_title(2, "The characteristic polynomial")
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

        # way no. 3: there are more lines than fit vertically, so we keep a "window"
        # of the last three, and the rest travel upwards and are faded out
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
                # steps.animate returns the whole group to the scene, together with
                # the line just faded out — it stays hanging above the frame. So we
                # remove the line from the group as well.
                steps.remove(oldest)
                self.remove(oldest)

        box = SurroundingRectangle(steps[-1], color=YELLOW, buff=0.25)
        self.play(Create(box))
        self.wait(0.5)
        self.wipe("Step 2")

    def slide_eigenvectors(self):
        self.next_section("The eigenvectors")
        head = self.slide_title(3, "The eigenvectors")
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

        # non-Latin text does not compile in MathTex (pdflatex + Unicode) —
        # textual explanations go through Text, the formulas stay in MathTex
        note = VGroup(
            MathTex(r"v_1 \perp v_2 \;\Longrightarrow\; A = A^{\top}", font_size=32, color=GREY_A),
            Text("a symmetric matrix: the eigenvectors are orthogonal",
                 font_size=26, color=GREY_A),
        ).arrange(DOWN, buff=0.2)
        fit(note)
        note.next_to(columns, DOWN, buff=0.5)

        self.play(FadeIn(left, shift=RIGHT * 0.3), Create(divider))
        self.play(FadeIn(right, shift=LEFT * 0.3))
        self.play(Write(note))
        self.wait(0.5)
        self.wipe("Step 3")

    def slide_geometry(self):
        self.next_section("The geometry")
        head = self.slide_title(4, "How A acts on the plane")
        self.add(head)

        plane = NumberPlane(
            x_range=[-4, 4, 1],
            y_range=[-3, 3, 1],
            x_length=7.5,
            y_length=5.625,  # the same scale as along x (7.5/8 = 5.625/6):
            # otherwise ApplyMatrix in scene coordinates equals S·A·S⁻¹ rather than A
            background_line_style={"stroke_opacity": 0.35},
        ).next_to(head, DOWN, buff=0.35)

        v1 = Arrow(plane.c2p(0, 0), plane.c2p(1, -1), buff=0, color=BLUE_B)
        v2 = Arrow(plane.c2p(0, 0), plane.c2p(1, 1), buff=0, color=RED_B)
        l1 = MathTex(r"v_1", font_size=32, color=BLUE_B).next_to(v1.get_end(), DR, buff=0.15)
        l2 = MathTex(r"v_2", font_size=32, color=RED_B).next_to(v2.get_end(), UR, buff=0.15)

        caption = VGroup(
            MathTex(r"Av_1 = 1\cdot v_1", font_size=30, color=BLUE_B),
            Text("the length is preserved", font_size=24, color=BLUE_B),
            MathTex(r"Av_2 = 3\cdot v_2", font_size=30, color=RED_B),
            Text("a threefold stretch", font_size=24, color=RED_B),
        ).arrange(RIGHT, buff=0.35)
        fit(caption)
        caption.next_to(plane, DOWN, buff=0.25)

        self.play(Create(plane), run_time=1.2)
        self.play(GrowArrow(v1), GrowArrow(v2), FadeIn(l1), FadeIn(l2))
        self.play(Write(caption))
        # ApplyMatrix acts relative to the scene's ORIGIN, while the plane is shifted
        # down under the heading — without about_point the transformation comes out wrong
        origin = plane.c2p(0, 0)
        plane_ref = plane.copy()  # the grid is about to be skewed; the snapshot is needed for the checks
        expect_uniform_scale(plane, "the axes of the plane")
        before = {"the grid": snapshot(plane), "v1": snapshot(v1), "v2": snapshot(v2)}
        v1_end, v2_end = v1.get_end().copy(), v2.get_end().copy()

        self.play(
            ApplyMatrix(A_MAT, plane, about_point=origin),
            ApplyMatrix(A_MAT, v1, about_point=origin),
            ApplyMatrix(A_MAT, v2, about_point=origin),
            run_time=2.5,
        )
        # the general check: everything was transformed by exactly the matrix A. It is
        # subject-neutral and catches both a forgotten about_point and an unequal axis scale
        for name, mob in (("the grid", plane), ("v1", v1), ("v2", v2)):
            expect_matrix_action(before[name], mob, A_MAT, name, coord_system=plane_ref)

        # the applied invariant of this particular problem — two lines on top of the general checks
        expect_point(v1.get_end(), v1_end, "v1: λ=1, the end was not supposed to move")
        expect_point(v2.get_end(), origin + 3 * (v2_end - origin), "v2: λ=3, exactly three times further")

        self.wait(0.4)
        self.play(
            ApplyMatrix(np.linalg.inv(A_MAT), plane, about_point=origin),
            ApplyMatrix(np.linalg.inv(A_MAT), v1, about_point=origin),
            ApplyMatrix(np.linalg.inv(A_MAT), v2, about_point=origin),
            run_time=1.2,
        )
        self.wait(0.3)
        self.wipe("Step 4")

    def slide_answer(self):
        self.next_section("The answer")
        head = self.slide_title(5, "The general solution and the answer")
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
    """Way no. 4: the whole set of notes lies on a large canvas, a "slide" = the camera frame.

    This device is convenient when the connection between the blocks has to be shown:
    the camera pulls back and the whole picture is visible at once.
    """

    def construct(self):
        self.camera.frame.save_state()

        # --- block 1: the statement (upper left) ---------------------------
        block1 = VGroup(
            Text("The problem", font_size=32, weight=BOLD),
            MathTex(r"\dot{x} = Ax,\quad A = \begin{bmatrix} 2 & 1 \\ 1 & 2\end{bmatrix}", font_size=34),
        ).arrange(DOWN, buff=0.35).move_to(LEFT * 11 + UP * 4)

        # --- block 2: the spectrum (upper right) ---------------------------
        block2 = VGroup(
            Text("The spectrum", font_size=32, weight=BOLD),
            MathTex(r"\lambda_1 = 1,\ v_1 = \begin{bmatrix} 1 \\ -1\end{bmatrix}", font_size=32, color=BLUE_B),
            MathTex(r"\lambda_2 = 3,\ v_2 = \begin{bmatrix} 1 \\ 1\end{bmatrix}", font_size=32, color=RED_B),
        ).arrange(DOWN, buff=0.3).move_to(RIGHT * 11 + UP * 4)

        # --- block 3: the phase portrait (centre, large) -------------------
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
        block3_title = Text("The phase portrait", font_size=32, weight=BOLD)
        block3_title.next_to(plane, UP, buff=0.3)

        # --- block 4: the answer (lower right) -----------------------------
        block4 = VGroup(
            Text("The answer", font_size=32, weight=BOLD),
            MathTex(
                r"x(t) = \tfrac{1}{2}\begin{bmatrix} e^{t} + e^{3t} \\ e^{3t} - e^{t}\end{bmatrix}",
                font_size=34,
                color=YELLOW,
            ),
        ).arrange(DOWN, buff=0.35).move_to(RIGHT * 13 + DOWN * 5)

        self.add(block1, block2, block3_title, block3, block4)

        # the camera as a "slide turner": zooming in on each block in turn.
        # IMPORTANT: set(width=...) sets only the width, the height is recomputed from
        # the aspect of the frame — if the block is tall, it will be cropped. So we take
        # the maximum of the requirements by width and by height.
        aspect = config.frame_width / config.frame_height

        def frame_width_for(target: Mobject, margin: float = 1.2) -> float:
            return max(target.width * margin, target.height * margin * aspect)

        self.camera.frame.move_to(block1).set(width=frame_width_for(block1, 1.5))
        audit(self, "block 1", [block1], check_overlaps=False)
        self.wait(0.4)

        tour = (
            ("block 2", block2, 1.35),
            ("block 3", VGroup(block3_title, block3), 1.15),
            ("block 4", block4, 1.4),
        )
        for label, target, margin in tour:
            self.play(
                self.camera.frame.animate.move_to(target).set(width=frame_width_for(target, margin)),
                run_time=1.6,
            )
            audit(self, label, [target], check_overlaps=False, check_intruders=True)
            self.wait(0.4)

        # the final pull-back: the whole set of notes is visible at once
        everything = VGroup(block1, block2, block3_title, block3, block4)
        self.play(
            self.camera.frame.animate.move_to(everything).set(width=frame_width_for(everything, 1.08)),
            run_time=2,
        )
        audit(self, "the whole canvas", [everything], check_overlaps=False)
        self.wait(0.8)

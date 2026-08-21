"""Демо-сцены для проверки установки manim в среде rah_manim.

    conda activate rah_manim
    manim -ql demo.py SquareToCircle   # cairo + ffmpeg
    manim -ql demo.py PangoText        # manimpango: кириллица, markup
    manim -ql demo.py PlotDemo         # оси и график
    manim -ql demo.py MathDemo         # LaTeX: TinyTeX + dvisvgm
    manim -qh -s demo.py MathDemo      # одиночный PNG в высоком качестве

LaTeX берётся из TinyTeX (~/.TinyTeX/bin/x86_64-linux, прописан в ~/.zshrc).
"""

from manim import *

from scene_asserts import expect_on_graph, expect_point


class SquareToCircle(Scene):
    """Канонический пример из README: проверяет cairo-рендерер и сборку видео."""

    def construct(self):
        circle = Circle()
        square = Square()
        square.flip(RIGHT)
        square.rotate(-3 * TAU / 8)
        circle.set_fill(PINK, opacity=0.5)

        self.play(Create(square))
        self.play(Transform(square, circle))
        self.play(FadeOut(square))


class PangoText(Scene):
    """Проверяет именно manimpango: кириллица, греческие буквы, начертания."""

    def construct(self):
        title = Text("Проверка Pango", font_size=56, weight=BOLD)
        subtitle = Text("кириллица · αβγδ · 1234 · ﬁ", font_size=34, color=BLUE_B)
        markup = MarkupText(
            'разметка: <span foreground="yellow">цвет</span>, <i>курсив</i>, <b>жирный</b>',
            font_size=28,
        )
        group = VGroup(title, subtitle, markup).arrange(DOWN, buff=0.5)

        self.play(Write(title))
        self.play(FadeIn(subtitle, shift=UP))
        self.play(FadeIn(markup, shift=UP))
        self.wait(0.5)


class PlotDemo(Scene):
    """Оси + график + подписи через Text (без LaTeX)."""

    def construct(self):
        axes = Axes(
            x_range=[-3, 3, 1],
            y_range=[-1.5, 1.5, 0.5],
            x_length=9,
            y_length=4.5,
            axis_config={"include_numbers": False, "include_tip": True},
        )
        sine = axes.plot(lambda x: np.sin(2 * x) * np.exp(-0.2 * x**2), color=YELLOW)
        label = Text("sin(2x)·exp(-0.2x²)", font_size=28).next_to(axes, UP)
        dot = Dot(color=RED).move_to(axes.c2p(-3, 0))

        self.play(Create(axes), run_time=1.5)
        self.play(Write(label))
        self.play(Create(sine), run_time=2)
        self.play(MoveAlongPath(dot, sine), run_time=2, rate_func=linear)
        # нарисованная кривая обязана лежать на графике функции, а точка —
        # дойти до её конца: проверки предметно нейтральные, годятся для любой сцены
        expect_on_graph(axes, sine, lambda x: np.sin(2 * x) * np.exp(-0.2 * x**2), "синусоида")
        expect_point(dot.get_center(), sine.get_end(), "точка дошла до конца кривой")
        self.wait(0.3)


class MathDemo(Scene):
    """LaTeX-путь: latex + dvisvgm (TinyTeX). Требует dvisvgm в PATH."""

    def construct(self):
        formula = MathTex(
            r"\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}",
            font_size=64,
        )
        matrix = MathTex(
            r"\theta_{\ell} \propto \|h_{\ell}\|,\qquad "
            r"\hat{y} = \operatorname*{arg\,max}_{y} p(y \mid x)",
            font_size=40,
            color=TEAL_B,
        )
        group = VGroup(formula, matrix).arrange(DOWN, buff=0.8)

        self.play(Write(formula))
        self.play(FadeIn(matrix, shift=UP))
        self.wait(0.3)

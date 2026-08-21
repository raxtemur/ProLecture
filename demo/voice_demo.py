"""Озвучка сцены через manim-voiceover: два движка TTS на одном сюжете.

    conda activate rah_manim
    manim -ql voice_demo.py VoiceGTTS       # Google Translate TTS (нужен интернет)
    manim -ql voice_demo.py VoicePyttsx3    # локальный espeak-ng, без сети

Главное, ради чего нужен manim-voiceover: длительность анимации берётся из
длительности реплики (tracker.duration), поэтому картинка не разъезжается
с голосом. Аудио кэшируется в media/voiceovers/, рядом с видео пишется .srt.

Два правила, без которых озвучка получается унылой:

  * голос НЕ читает вслух то, что уже написано на экране — он даёт то, чего
    на экране нет: смысл, интуицию, связку между шагами. Формулы остаются
    формулами, слова добавляют понимание;
  * субтитр задаётся явным параметром subcaption= и держится коротким.
    Иначе manim-voiceover режет реплику механически по max_subcaption_len
    (70 символов) и строка рвётся посреди фразы: «равен лямбда в / квадрате».

Локальный движок работает через espeak-ng из колеса espeakng-loader:
LD_LIBRARY_PATH и ESPEAK_DATA_PATH выставляются автоматически при
conda activate rah_manim (см. $CONDA_PREFIX/etc/conda/activate.d/espeak.sh).
"""

from pathlib import Path

from manim import *
from manim_voiceover import VoiceoverScene
from manim_voiceover.helper import wav2mp3
from manim_voiceover.services.gtts import GTTSService
from manim_voiceover.services.pyttsx3 import PyTTSX3Service

from layout_check import audit
from scene_asserts import (
    expect_matrix_action,
    expect_point,
    expect_uniform_scale,
    snapshot,
)


class PyTTSX3FixedService(PyTTSX3Service):
    """Обход бага manim-voiceover 0.4.0 с локальным движком.

    Штатный PyTTSX3Service зовёт engine.save_to_file(text, "....mp3"), но
    pyttsx3 поверх espeak-ng всегда пишет WAV — просто с расширением .mp3.
    Дальше mutagen пытается разобрать это как MPEG и падает с
    HeaderNotFoundError: can't sync to MPEG frame.
    Поэтому синтезируем в .wav и сами перекодируем в .mp3.
    """

    def generate_from_text(self, text, cache_dir=None, path=None, **kwargs):
        if cache_dir is None:
            cache_dir = self.cache_dir
        input_data = {"input_text": text, "service": "pyttsx3"}

        cached = self.get_cached_result(input_data, cache_dir)
        if cached is not None:
            return cached

        mp3_name = path if path is not None else self.get_audio_basename(input_data) + ".mp3"
        mp3_path = Path(cache_dir) / str(mp3_name)
        wav_path = mp3_path.with_suffix(".wav")

        self.engine.save_to_file(text, str(wav_path))
        self.engine.runAndWait()
        self.engine.stop()
        wav2mp3(wav_path, mp3_path)  # pydub → ffmpeg, wav удаляется

        return {
            "input_text": text,
            "input_data": input_data,
            "original_audio": str(mp3_name),
        }


MATRIX = [[2, 1], [1, 2]]


class EigenStoryMixin:
    """Сюжет: что такое собственный вектор — на примере матрицы [[2,1],[1,2]].

    Сервис TTS подключается наследником.
    """

    def say(self, text: str, subcaption: str):
        """Реплика с коротким осмысленным субтитром вместо машинной нарезки."""
        return self.voiceover(text=text, subcaption=subcaption, max_subcaption_len=90)

    def construct_story(self):
        plane = NumberPlane(
            x_range=[-4, 4, 1],
            y_range=[-2.5, 2.5, 1],
            x_length=8,
            y_length=5,
            background_line_style={"stroke_opacity": 0.3},
        ).to_edge(DOWN, buff=0.3)

        title = Text("Собственные векторы", font_size=36, weight=BOLD).to_edge(UP, buff=0.3)

        generic = Arrow(plane.c2p(0, 0), plane.c2p(2, 0.4), buff=0, color=GREY_A)
        special = Arrow(plane.c2p(0, 0), plane.c2p(0.8, 0.8), buff=0, color=RED_B)
        other = Arrow(plane.c2p(0, 0), plane.c2p(1.2, -1.2), buff=0, color=BLUE_B)
        # ApplyMatrix преобразует относительно ORIGIN сцены; плоскость сдвинута
        # вниз, поэтому начало координат надо указывать явно, иначе даже
        # собственный вектор с λ=1 «уезжает» вместо того чтобы остаться на месте
        origin = plane.c2p(0, 0)
        expect_uniform_scale(plane, "оси плоскости")

        with self.say(
            text="Матрицу удобно понимать не как таблицу чисел, "
            "а как способ двигать плоскость.",
            subcaption="Матрица — это преобразование плоскости",
        ) as t:
            self.play(FadeIn(title), Create(plane), run_time=t.duration)

        with self.say(
            text="Возьмём произвольный вектор.",
            subcaption="Берём произвольный вектор",
        ) as t:
            self.play(GrowArrow(generic), run_time=t.duration)

        with self.say(
            text="После умножения на матрицу он не только растянулся, но и повернулся.",
            subcaption="Он растянулся и повернулся",
        ) as t:
            self.play(ApplyMatrix(MATRIX, generic, about_point=origin),
                      run_time=t.duration)

        with self.say(
            text="Но у преобразования есть выделенные направления.",
            subcaption="Но есть выделенные направления",
        ) as t:
            self.play(FadeOut(generic), GrowArrow(special), GrowArrow(other),
                      run_time=t.duration)

        with self.say(
            text="Вдоль них поворота не происходит вовсе: "
            "вектор остаётся на своей прямой и только меняет длину.",
            subcaption="Вдоль них вектор только меняет длину",
        ) as t:
            before_special, before_other = snapshot(special), snapshot(other)
            other_end = other.get_end().copy()
            self.play(ApplyMatrix(MATRIX, special, about_point=origin),
                      ApplyMatrix(MATRIX, other, about_point=origin),
                      run_time=t.duration)

        expect_matrix_action(before_special, special, MATRIX, "растянутый вектор", coord_system=plane)
        expect_matrix_action(before_other, other, MATRIX, "сохранённый вектор", coord_system=plane)
        expect_point(other.get_end(), other_end, "λ=1: вектор должен был остаться на месте")

        formula = MathTex(r"Av = \lambda v", font_size=48).next_to(title, DOWN, buff=0.25)
        with self.say(
            text="Именно это и записано в определении.",
            subcaption="Это и есть определение",
        ) as t:
            self.play(Write(formula), run_time=t.duration)

        audit(self, "определение")
        self.play(FadeOut(plane, special, other), formula.animate.move_to(ORIGIN + UP * 1.2))

        char = MathTex(r"\det(A - \lambda I) = \lambda^2 - 4\lambda + 3 = 0", font_size=44)
        char.next_to(formula, DOWN, buff=0.7)
        roots = MathTex(r"\lambda_1 = 1, \qquad \lambda_2 = 3", font_size=48, color=YELLOW)
        roots.next_to(char, DOWN, buff=0.7)

        with self.say(
            text="Чтобы найти такие числа, требуют, "
            "чтобы система имела ненулевое решение.",
            subcaption="Требуем ненулевое решение системы",
        ) as t:
            self.play(Write(char), run_time=t.duration)

        with self.say(
            text="Условие превращается в обычное квадратное уравнение.",
            subcaption="Получается квадратное уравнение",
        ) as t:
            self.play(Indicate(char, color=TEAL_B), run_time=t.duration)

        with self.say(
            text="Его корни — единица и тройка.",
            subcaption="Корни: единица и тройка",
        ) as t:
            self.play(FadeIn(roots, shift=UP * 0.3), run_time=t.duration)

        with self.say(
            text="Значит, вдоль первого направления матрица ничего не меняет, "
            "а вдоль второго растягивает втрое.",
            subcaption="Одно направление сохраняется, второе растёт втрое",
        ) as t:
            self.play(Circumscribe(roots, color=YELLOW), run_time=t.duration)

        with self.say(
            text="А перпендикулярность этих направлений — не совпадение: "
            "так устроена любая симметричная матрица.",
            subcaption="Симметричность матрицы даёт перпендикулярность",
        ) as t:
            self.play(Indicate(formula, color=TEAL_B), run_time=t.duration)

        audit(self, "финал")


class VoiceGTTS(EigenStoryMixin, VoiceoverScene):
    """Онлайн-синтез: Google Translate TTS, русский голос."""

    def construct(self):
        self.set_speech_service(GTTSService(lang="ru"))
        self.construct_story()


class VoicePyttsx3(EigenStoryMixin, VoiceoverScene):
    """Оффлайн-синтез: espeak-ng через pyttsx3, русский голос."""

    def construct(self):
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("voice", "ru")   # без этого кириллица читается по буквам
        engine.setProperty("rate", 150)
        self.set_speech_service(PyTTSX3FixedService(engine=engine))
        self.construct_story()

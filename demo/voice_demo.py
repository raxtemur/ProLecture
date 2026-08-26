"""Voicing a scene with manim-voiceover: two TTS engines on one storyline.

    conda activate rah_manim
    manim -ql voice_demo.py VoiceGTTS       # Google Translate TTS (needs the internet)
    manim -ql voice_demo.py VoicePyttsx3    # local espeak-ng, no network

The main thing manim-voiceover is needed for: the duration of an animation is taken from
the duration of the utterance (tracker.duration), so the picture does not drift apart
from the voice. The audio is cached in media/voiceovers/, and an .srt is written next to
the video.

Two rules without which the voicing comes out dull:

  * the voice does NOT read aloud what is already written on the screen — it gives what
    is not on the screen: the meaning, the intuition, the link between the steps. The
    formulas stay formulas, the words add understanding;
  * the subtitle is set by the explicit subcaption= parameter and is kept short.
    Otherwise manim-voiceover cuts the utterance mechanically by max_subcaption_len
    (70 characters) and the line breaks mid-phrase: "is equal to lambda / squared".

The local engine works through espeak-ng from the espeakng-loader wheel:
LD_LIBRARY_PATH and ESPEAK_DATA_PATH are set automatically by
conda activate rah_manim (see $CONDA_PREFIX/etc/conda/activate.d/espeak.sh).
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
    """A workaround for a manim-voiceover 0.4.0 bug with the local engine.

    The stock PyTTSX3Service calls engine.save_to_file(text, "....mp3"), but
    pyttsx3 on top of espeak-ng always writes WAV — simply with an .mp3 extension.
    mutagen then tries to parse it as MPEG and dies with
    HeaderNotFoundError: can't sync to MPEG frame.
    So we synthesise into .wav and transcode to .mp3 ourselves.
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
        wav2mp3(wav_path, mp3_path)  # pydub → ffmpeg, the wav is deleted

        return {
            "input_text": text,
            "input_data": input_data,
            "original_audio": str(mp3_name),
        }


MATRIX = [[2, 1], [1, 2]]


class EigenStoryMixin:
    """The storyline: what an eigenvector is — on the example of the matrix [[2,1],[1,2]].

    The TTS service is plugged in by a subclass.
    """

    def say(self, text: str, subcaption: str):
        """An utterance with a short meaningful subtitle instead of a machine cut."""
        return self.voiceover(text=text, subcaption=subcaption, max_subcaption_len=90)

    def construct_story(self):
        plane = NumberPlane(
            x_range=[-4, 4, 1],
            y_range=[-2.5, 2.5, 1],
            x_length=8,
            y_length=5,
            background_line_style={"stroke_opacity": 0.3},
        ).to_edge(DOWN, buff=0.3)

        title = Text("Eigenvectors", font_size=36, weight=BOLD).to_edge(UP, buff=0.3)

        generic = Arrow(plane.c2p(0, 0), plane.c2p(2, 0.4), buff=0, color=GREY_A)
        special = Arrow(plane.c2p(0, 0), plane.c2p(0.8, 0.8), buff=0, color=RED_B)
        other = Arrow(plane.c2p(0, 0), plane.c2p(1.2, -1.2), buff=0, color=BLUE_B)
        # ApplyMatrix transforms relative to the scene's ORIGIN; the plane is shifted
        # down, so the origin has to be named explicitly, otherwise even an eigenvector
        # with λ=1 "drifts away" instead of staying put
        origin = plane.c2p(0, 0)
        expect_uniform_scale(plane, "the axes of the plane")

        with self.say(
            text="A matrix is conveniently understood not as a table of numbers "
            "but as a way of moving the plane.",
            subcaption="A matrix is a transformation of the plane",
        ) as t:
            self.play(FadeIn(title), Create(plane), run_time=t.duration)

        with self.say(
            text="Take an arbitrary vector.",
            subcaption="Taking an arbitrary vector",
        ) as t:
            self.play(GrowArrow(generic), run_time=t.duration)

        with self.say(
            text="After the multiplication by the matrix it has not only stretched but also turned.",
            subcaption="It stretched and turned",
        ) as t:
            self.play(ApplyMatrix(MATRIX, generic, about_point=origin),
                      run_time=t.duration)

        with self.say(
            text="But the transformation has distinguished directions.",
            subcaption="But there are distinguished directions",
        ) as t:
            self.play(FadeOut(generic), GrowArrow(special), GrowArrow(other),
                      run_time=t.duration)

        with self.say(
            text="Along them no rotation happens at all: "
            "the vector stays on its own line and only changes length.",
            subcaption="Along them the vector only changes length",
        ) as t:
            before_special, before_other = snapshot(special), snapshot(other)
            other_end = other.get_end().copy()
            self.play(ApplyMatrix(MATRIX, special, about_point=origin),
                      ApplyMatrix(MATRIX, other, about_point=origin),
                      run_time=t.duration)

        expect_matrix_action(before_special, special, MATRIX, "the stretched vector", coord_system=plane)
        expect_matrix_action(before_other, other, MATRIX, "the preserved vector", coord_system=plane)
        expect_point(other.get_end(), other_end, "λ=1: the vector was supposed to stay put")

        formula = MathTex(r"Av = \lambda v", font_size=48).next_to(title, DOWN, buff=0.25)
        with self.say(
            text="That is exactly what is written in the definition.",
            subcaption="This is the definition",
        ) as t:
            self.play(Write(formula), run_time=t.duration)

        audit(self, "the definition")
        self.play(FadeOut(plane, special, other), formula.animate.move_to(ORIGIN + UP * 1.2))

        char = MathTex(r"\det(A - \lambda I) = \lambda^2 - 4\lambda + 3 = 0", font_size=44)
        char.next_to(formula, DOWN, buff=0.7)
        roots = MathTex(r"\lambda_1 = 1, \qquad \lambda_2 = 3", font_size=48, color=YELLOW)
        roots.next_to(char, DOWN, buff=0.7)

        with self.say(
            text="To find such numbers, one demands "
            "that the system have a non-zero solution.",
            subcaption="We demand a non-zero solution of the system",
        ) as t:
            self.play(Write(char), run_time=t.duration)

        with self.say(
            text="The condition turns into an ordinary quadratic equation.",
            subcaption="We get a quadratic equation",
        ) as t:
            self.play(Indicate(char, color=TEAL_B), run_time=t.duration)

        with self.say(
            text="Its roots are one and three.",
            subcaption="The roots: one and three",
        ) as t:
            self.play(FadeIn(roots, shift=UP * 0.3), run_time=t.duration)

        with self.say(
            text="So along the first direction the matrix changes nothing, "
            "and along the second it stretches by a factor of three.",
            subcaption="One direction is preserved, the other grows threefold",
        ) as t:
            self.play(Circumscribe(roots, color=YELLOW), run_time=t.duration)

        with self.say(
            text="And the perpendicularity of these directions is no coincidence: "
            "that is how any symmetric matrix is built.",
            subcaption="The symmetry of the matrix gives the perpendicularity",
        ) as t:
            self.play(Indicate(formula, color=TEAL_B), run_time=t.duration)

        audit(self, "the finale")


class VoiceGTTS(EigenStoryMixin, VoiceoverScene):
    """Online synthesis: Google Translate TTS, an English voice."""

    def construct(self):
        self.set_speech_service(GTTSService(lang="en"))
        self.construct_story()


class VoicePyttsx3(EigenStoryMixin, VoiceoverScene):
    """Offline synthesis: espeak-ng through pyttsx3, an English voice."""

    def construct(self):
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("voice", "en")   # without this espeak may fall back to a locale-dependent voice
        engine.setProperty("rate", 150)
        self.set_speech_service(PyTTSX3FixedService(engine=engine))
        self.construct_story()

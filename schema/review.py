#!/usr/bin/env python3
"""Контракт ревью: что субагент обязан вернуть о проверенном сэмпле.

Почему pydantic, а не JSON-схема. Схему сэмпла (`sample.schema.json`) читают
только валидатор и люди; схему ревью читает ещё и модель — она заполняет её
через constrained decoding. Класс с полями и комментариями рядом одновременно
и документация, и валидатор, и промпт: `model_json_schema()` отдаёт то же, что
писалось бы руками, а `Field(description=...)` доезжает до модели дословно.

Два принципа, из которых выросла форма.

**Идентичность по имени, а не по номеру.** Пункты чеклиста перенумеровываются:
за одну сессию группа 4 переехала целиком (прежний 4.7 стал 4.3, прежний 4.3 —
4.6). Ревью, сохранённое ключом `"4.6"`, после такой перестановки читается как
ревью другого пункта — молча и необратимо. Поэтому в контракте живут `Group`
и `Item` — устойчивые имена, а номера остаются в тексте чеклиста и в справочной
таблице `ITEM_NUMBER` внизу файла. Таблица не авторитетна: разойдётся — правится
она, а не сохранённые ревью.

**Schema-Guided Reasoning.** Модель, которую спросили сразу про вердикт, вердикт
и выдаёт — вместе с обоснованием, придуманным задним числом. Поэтому поля в каждой
проверке идут каскадом (SGR Cascade): сначала что смотрел, потом что увидел, потом
промежуточные ответы — булевы и численные, потом и только потом `result`. Порядок
полей здесь не косметика: при constrained decoding модель физически генерирует их
в этом порядке, и `result` пишется уже после того, как основания зафиксированы.
Побочная выгода важнее прямой: расхождение двух ревьюеров становится
локализуемым — видно, на каком именно промежуточном шаге они разошлись, а не
только что вердикты разные.

    https://abdullin.com/schema-guided-reasoning/

Субагент **сохраняет заполненную модель в файл** `data/reviews/<VIDEO_ID>/<SAMPLE_ID>/
<role>.<iteration>.json`, а координатору возвращает текстовые рассуждения. Так
координатор не тащит в контекст полный json каждого субагента, но всегда может
его перечитать — и человек на приёмке тоже.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Версия самого контракта: меняется, когда меняются поля здесь.
SCHEMA_VERSION = "1.1"   # 1.1: роль full разведена на full_sample и full_window
# Версия чеклиста, по которому проверял субагент. Нужна, чтобы через полгода
# было понятно, какую редакцию пункта он применял.
CHECKLIST_VERSION = "2026-08-24"


class Strict(BaseModel):
    """Общая база: лишние поля запрещены.

    Та же дисциплина, что `additionalProperties: false` в схеме сэмпла. Модель,
    дописавшая поле от себя, обычно так маскирует то, что не влезло в контракт, —
    и это ровно тот сигнал, который нельзя терять.
    """

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Устойчивые имена: группы и пункты чеклиста
# --------------------------------------------------------------------------


class Group(StrEnum):
    """Группы чеклиста. Имя группы — часть адреса пункта."""

    FORMAL = "formal"            # 1. Формальная целостность файла
    WINDOWS = "windows"          # 2. Границы окон ответа
    TRIGGERS = "triggers"        # 3. Соответствие набора триггеров критерию вопроса
    SHORTCUTS = "shortcuts"      # 4. Разрешимость в обход видео
    RUBRIC = "rubric"            # 5. Согласованность вопроса, ответа и рубрики
    DISTRACTORS = "distractors"  # 6. Дистракторы
    LABELS = "labels"            # 7. Метки
    PROVENANCE = "provenance"    # 8. Провенанс
    DRIFT = "drift"              # 9. Дрейф документации и инструментов


class Item(StrEnum):
    """Пункты чеклиста под устойчивыми именами.

    Имя описывает **что проверяется**, а не порядок. Добавлять новые пункты можно
    в любое место — на сохранённые ревью это не влияет. Удалять нельзя: имя
    удалённого пункта остаётся здесь с пометкой, иначе старые ревью перестанут
    читаться.
    """

    # --- 1. formal (все автоматические, ревьюер их не заполняет) -----------
    WINDOW_GEOMETRY = "window-geometry"
    DISTRACTOR_GEOMETRY = "distractor-geometry"
    SAMPLE_INTEGRITY = "sample-integrity"
    DEPENDS_ON_BACKWARDS = "depends-on-backwards"
    MULTITRIGGER_HAS_DISTRACTOR = "multitrigger-has-distractor"
    DURATION_MATCHES_BUNDLE = "duration-matches-bundle"
    CLAIM_MATCHES_MODALITIES = "claim-matches-modalities"
    JSON_SCHEMA = "json-schema"
    EVIDENCE_SPAN_PRESENT = "evidence-span-present"
    SOUND_ONLY_TRIGGER = "sound-only-trigger"
    WINDOW_NOT_TOO_NARROW = "window-not-too-narrow"

    # --- 2. windows --------------------------------------------------------
    SHARED_BOUNDARY_NOT_MID_CUE = "shared-boundary-not-mid-cue"
    ANSWER_POSSIBLE_BEFORE_START = "answer-possible-before-start"      # 2.2
    ANSWER_AVAILABLE_BEFORE_QUESTION = "answer-available-before-question"  # 2.3
    WINDOW_CAN_BE_TIGHTENED = "window-can-be-tightened"                # 2.4
    AUTHOR_SAYS_ANSWER_IN_WINDOW = "author-says-answer-in-window"      # 2.5

    # --- 3. triggers -------------------------------------------------------
    NO_MISSED_TRIGGER = "no-missed-trigger"
    TRIGGER_MATCHES_CRITERION = "trigger-matches-criterion"
    EVENT_NOT_EARLIER_THAN_WINDOW = "event-not-earlier-than-window"

    # --- 4. shortcuts ------------------------------------------------------
    PROBE_PROTOCOL = "probe-protocol"
    SOLVABLE_WITHOUT_VIDEO = "solvable-without-video"        # 4.2
    VIDEO_RECOGNIZED = "video-recognized"                    # 4.3
    TRANSCRIPT_ENOUGH = "transcript-enough"                  # 4.4
    FRAMES_ENOUGH = "frames-enough"                          # 4.5
    SINGLE_FRAME_ENOUGH = "single-frame-enough"              # 4.6
    SOLVABLE_AT_ALL = "solvable-at-all"                      # 4.7
    QUESTION_ANCHORED_TO_SCREEN = "question-anchored-to-screen"  # 4.8

    # --- 5. rubric ---------------------------------------------------------
    TWINS_SHARE_RUBRIC = "twins-share-rubric"
    RUBRIC_WITHIN_QUESTION = "rubric-within-question"
    DISCRIMINATOR_IN_QUESTION = "discriminator-in-question"
    RUBRIC_NOT_PUNISHING_EXTRA = "rubric-not-punishing-extra"

    # --- 6. distractors ----------------------------------------------------
    DISTRACTOR_FULLY_COVERED = "distractor-fully-covered"
    DISTRACTOR_NOT_CORRECT_ANSWER = "distractor-not-correct-answer"
    TWINS_KEEP_LEGAL_DISTRACTOR = "twins-keep-legal-distractor"
    DISTRACTOR_WHY_HIDES_ANSWER = "distractor-why-hides-answer"

    # --- 7. labels ---------------------------------------------------------
    TEMPORAL_REL_DERIVED = "temporal-rel-derived"
    AUDIO_DEPENDENCY_EMPTY_IN_DRAFT = "audio-dependency-empty-in-draft"
    REASONING_LEVEL_NOT_INFLATED = "reasoning-level-not-inflated"
    DEPENDS_ON_IS_DEPENDENCY = "depends-on-is-dependency"
    EVIDENCE_SPAN_IS_LAST = "evidence-span-is-last"
    AUDIO_DEPENDENCY_MATCHES_PROBES = "audio-dependency-matches-probes"
    PROBE_FLAGS_CONSISTENT = "probe-flags-consistent"

    # --- 8. provenance -----------------------------------------------------
    TIMECODES_EXIST = "timecodes-exist"
    REFERENCE_MATCHES_DESCRIPTION = "reference-matches-description"
    REFERENCES_CONSISTENT_WITH_WINDOWS = "references-consistent-with-windows"
    REFERENCE_ANSWER_VERIFIED = "reference-answer-verified"   # новый, разбор ревью A3
    TWINS_AGREE_ON_SUBSTANCE = "twins-agree-on-substance"

    # --- 9. drift (автоматические) -----------------------------------------
    NUMBERS_RECOMPUTED = "numbers-recomputed"
    EXAMPLES_GENERATED = "examples-generated"
    TOOLS_IDEMPOTENT = "tools-idempotent"
    CHECKLIST_MATCHES_VALIDATOR = "checklist-matches-validator"


# --------------------------------------------------------------------------
# Мелкие типы
# --------------------------------------------------------------------------

Seconds = Annotated[float, Field(ge=0, description="момент в ролике, секунды")]


class Role(StrEnum):
    """Кто заполнял. У каждой роли свой промпт и свой набор доступного материала."""

    SEMIBLIND = "semiblind"       # знает t_end окон, не знает ответа: 2.2, 2.3
    FULL_SAMPLE = "full_sample"   # видит сэмпл целиком, один запуск на сэмпл
    FULL_WINDOW = "full_window"   # видит одно окно, по запуску на окно
    PROBE_TEXT = "probe_text"
    PROBE_VISION = "probe_vision"
    PROBE_FRAME = "probe_frame"
    PROBE_FULL = "probe_full"


# Кто какие пункты обязан закрыть. Это не справочник, а часть контракта:
# по нему валидируется полнота ревью, поэтому таблица авторитетна.
#
# Разделение не административное. Полный ревьюер знает эталон и потому смещён
# в одну сторону: на полукадре, где объект ещё дорисовывается, он «узнаёт» ответ,
# которого там ещё нет, и предлагает сдвинуть t_start влево. Координатор правку
# применяет — и за три итерации окно уезжает монотонно. Поэтому левые границы
# ему запрещены, а не просто «не поручены».
ROLE_ITEMS: dict[Role, frozenset[Item]] = {
    # 2.2 и 2.3 полу-слепой не «проверяет»: он возвращает scans, а вердикт
    # выводит координатор, сверяя t_val с t_start, которого ревьюер не видел.
    Role.SEMIBLIND: frozenset({
        Item.SOLVABLE_WITHOUT_VIDEO,
        Item.VIDEO_RECOGNIZED,
    }),
    # Полное ревью разведено на две роли, потому что прежний единый набор был
    # невыполним: контракт требовал строку по всем восемнадцати пунктам, а конвейер
    # на сэмпле с девятью окнами запускал ревьюера ПО ОКНУ и давал ему бюджет
    # кадров на это окно. Пооконный ревьюер физически не мог закрыть «не пропущено
    # ли срабатывание» (нужен весь ролик) и девять раз одинаково отвечал про текст
    # вопроса и рубрику. Итог по построению: skipped, а skipped запрещает PASS —
    # то есть на многооконных сэмплах цикл не сходился никогда.
    #
    # Граница проведена по тому, к чему пункт относится, а не по трудоёмкости:
    # окну принадлежит ровно то, что можно решить, глядя на это окно и ничего
    # больше. Приманки, ссылки provenance и эталон окну не принадлежат — они
    # общие для сэмпла, и делить их между пооконными запусками не по чему.
    Role.FULL_SAMPLE: frozenset({
        Item.NO_MISSED_TRIGGER,
        Item.TRIGGER_MATCHES_CRITERION,
        Item.QUESTION_ANCHORED_TO_SCREEN,
        Item.RUBRIC_WITHIN_QUESTION,
        Item.DISCRIMINATOR_IN_QUESTION,
        Item.RUBRIC_NOT_PUNISHING_EXTRA,
        Item.DISTRACTOR_FULLY_COVERED,
        Item.DISTRACTOR_NOT_CORRECT_ANSWER,
        Item.DISTRACTOR_WHY_HIDES_ANSWER,
        Item.REASONING_LEVEL_NOT_INFLATED,
        Item.REFERENCE_MATCHES_DESCRIPTION,
        Item.REFERENCES_CONSISTENT_WITH_WINDOWS,
        Item.REFERENCE_ANSWER_VERIFIED,
        Item.TWINS_AGREE_ON_SUBSTANCE,
    }),
    Role.FULL_WINDOW: frozenset({
        Item.WINDOW_CAN_BE_TIGHTENED,
        Item.AUTHOR_SAYS_ANSWER_IN_WINDOW,
        Item.EVENT_NOT_EARLIER_THAN_WINDOW,
        Item.DEPENDS_ON_IS_DEPENDENCY,
        Item.EVIDENCE_SPAN_IS_LAST,
    }),
}

# Пункты, которые не поручены ни одной роли субагента, потому что их выводит
# координатор из чужих ответов: 2.2 и 2.3 — из `scans` полу-слепого, 4.1 и 4.4-4.7 —
# из ответов зондов. Список нужен, чтобы сверка ниже отличала «выводится» от
# «забыли назначить»: без него пункт, выпавший из всех ролей, выглядит так же,
# как пункт, за который отвечает координатор.
COORDINATOR_ITEMS: frozenset[Item] = frozenset({
    Item.ANSWER_POSSIBLE_BEFORE_START,
    Item.ANSWER_AVAILABLE_BEFORE_QUESTION,
    Item.PROBE_PROTOCOL,
    Item.TRANSCRIPT_ENOUGH,
    Item.FRAMES_ENOUGH,
    Item.SINGLE_FRAME_ENOUGH,
    Item.SOLVABLE_AT_ALL,
})


# Пункты, у которых вывод относится к конкретному окну или приманке. Один `ok`
# на девятиоконный сэмпл — это восемь непроверенных окон под видом проверенного,
# поэтому у таких пунктов `target` обязателен.
ITEMS_NEEDING_TARGET: frozenset[Item] = frozenset({
    Item.WINDOW_CAN_BE_TIGHTENED,
    Item.AUTHOR_SAYS_ANSWER_IN_WINDOW,
    Item.EVENT_NOT_EARLIER_THAN_WINDOW,
    Item.DISTRACTOR_FULLY_COVERED,
    Item.DISTRACTOR_NOT_CORRECT_ANSWER,
    Item.DEPENDS_ON_IS_DEPENDENCY,
    Item.EVIDENCE_SPAN_IS_LAST,
})


# Какой именно индекс обязан назвать target. Пункты про приманки без
# distractor_idx бессмысленны: «приманка покрыта целиком» с одним лишь
# trigger_idx не говорит, какая из приманок проверена.
ITEMS_NEEDING_DISTRACTOR_IDX: frozenset[Item] = frozenset({
    Item.DISTRACTOR_FULLY_COVERED,
    Item.DISTRACTOR_NOT_CORRECT_ANSWER,
})


# Пункты, вывод по которым делается по тексту сэмпла и не требует ни кадров,
# ни реплик. Только у них `looked_at` может быть пустым.
ITEMS_WITHOUT_VIEWING: frozenset[Item] = frozenset({
    Item.QUESTION_ANCHORED_TO_SCREEN,
    Item.RUBRIC_WITHIN_QUESTION,
    Item.DISCRIMINATOR_IN_QUESTION,
    Item.RUBRIC_NOT_PUNISHING_EXTRA,
    Item.DISTRACTOR_WHY_HIDES_ANSWER,
    Item.REASONING_LEVEL_NOT_INFLATED,
    Item.DEPENDS_ON_IS_DEPENDENCY,
    Item.REFERENCES_CONSISTENT_WITH_WINDOWS,
})

# Пункты, применимые к любому сэмплу: `na` по ним не бывает.
# Неприменимость возможна только там, где её создаёт геометрия сэмпла — нет
# приманок, нет `depends_on`, нет близнеца. Без этого списка `na` оказывается
# дешевле честного `skipped`: он ничего не требует и не мешает вердикту PASS,
# то есть становится самым выгодным способом не проверять.
ITEMS_ALWAYS_APPLICABLE: frozenset[Item] = frozenset({
    Item.WINDOW_CAN_BE_TIGHTENED,
    Item.AUTHOR_SAYS_ANSWER_IN_WINDOW,
    Item.NO_MISSED_TRIGGER,
    Item.TRIGGER_MATCHES_CRITERION,
    Item.EVENT_NOT_EARLIER_THAN_WINDOW,
    Item.QUESTION_ANCHORED_TO_SCREEN,
    Item.RUBRIC_WITHIN_QUESTION,
    Item.DISCRIMINATOR_IN_QUESTION,
    Item.RUBRIC_NOT_PUNISHING_EXTRA,
    Item.REASONING_LEVEL_NOT_INFLATED,
    Item.EVIDENCE_SPAN_IS_LAST,
    Item.REFERENCE_MATCHES_DESCRIPTION,
    Item.REFERENCE_ANSWER_VERIFIED,
    Item.TWINS_AGREE_ON_SUBSTANCE,
})


class Verdict(StrEnum):
    """Лестница вердиктов: каждый следующий дороже в лечении."""

    PASS = "PASS"
    FIX_INTERVALS = "FIX_INTERVALS"    # лечится сдвигом границ
    FIX_QUESTION = "FIX_QUESTION"      # лечится переформулировкой
    CRITICAL_FAIL = "CRITICAL_FAIL"    # сэмпл выбрасывается


class Result(StrEnum):
    OK = "ok"            # проверил, не сработало
    FAIL = "fail"        # проверил, сработало
    SKIPPED = "skipped"  # не проверил — обязан назвать непокрытое
    NA = "na"            # пункт неприменим к этому сэмплу


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Observation(Strict):
    """Что именно субагент видел или слышал. Единица «посмотренного».

    Нужна не для отчётности: по списку наблюдений координатор видит, покрыт ли
    интервал, на котором пункт объявлен пройденным. Пункт `ok` при пустом
    `looked_at` — это `skipped`, только необъявленный.
    """

    kind: Literal["frame", "cue"]
    t: Seconds = Field(description="таймкод кадра или начала реплики")
    what: str = Field(min_length=3, description="что на кадре видно / что в реплике сказано")


class SubAnswer(Strict):
    """Промежуточный ответ внутри проверки — сердце SGR.

    Пункт чеклиста почти никогда не сводится к одному «да/нет»: 2.4 («окно можно
    ужать») распадается на «событие кончилось в момент X» и «после X ничего
    относящегося не происходит». Записанные по отдельности, эти шаги позволяют
    понять, где разошлись два ревьюера, — а не только что они разошлись.

    Формулировать вопрос надо так, чтобы ответ был проверяем: не «нормально ли
    окно», а «последний кадр, где объект ещё меняется».
    """

    question: str = Field(min_length=5, description="что именно спрашиваем у себя на этом шаге")
    answer_bool: bool | None = None
    answer_number: float | None = None
    answer_text: str | None = None
    why: str = Field(min_length=5, description="на чём основан этот промежуточный ответ")

    @model_validator(mode="after")
    def _one_answer(self) -> SubAnswer:
        filled = [x for x in (self.answer_bool, self.answer_number, self.answer_text)
                  if x is not None]
        if not filled:
            raise ValueError("промежуточный шаг без ответа: заполните одно из answer_*")
        return self


class Interval(Strict):
    t_start: Seconds
    t_end: Seconds

    @model_validator(mode="after")
    def _ordered(self) -> Interval:
        if self.t_end <= self.t_start:
            raise ValueError("интервал пуст или вывернут")
        return self


class Target(Strict):
    """К чему относится проверка: у сэмпла бывает девять окон.

    Оба поля необязательны по отдельности, но пустой `Target()` — это тот же
    «один ok на девятиоконный сэмпл», только прошедший проверку: требование
    «пункту нужен target» удовлетворяется объектом, который ни на что не
    указывает. Поэтому хотя бы одно поле обязано быть заполнено, а какое именно —
    решает пункт (см. `_target_points_somewhere` в `Check`).
    """

    trigger_idx: int | None = Field(default=None, ge=0)
    distractor_idx: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _not_empty(self) -> Target:
        if self.trigger_idx is None and self.distractor_idx is None:
            raise ValueError("пустой target: он обязан называть окно или приманку, "
                             "иначе проверка формально есть, а к чему она — неизвестно")
        return self


class Proposal(Strict):
    """Предложение правки. Ревьюер не правит файлы — правит координатор."""

    field: str = Field(description="что менять: t_start, t_end, question, rubric[2], ...")
    value: str = Field(description="на что менять; число тоже строкой, чтобы не терять формат")
    why: str = Field(min_length=10)


class Violation(Strict):
    """Признание в том, что был прочитан запретный файл.

    Провал не в том, что прочитал: путь попадает в вывод `grep`, файл открывается
    заодно с соседним. Провал — в молчании, потому что молча загрязнённое ревью
    неотличимо от чистого и портит всё, что из него выведено.
    """

    path: str
    why: str = Field(min_length=5, description="зачем открыл")
    what_seen: str = Field(min_length=5, description="что успел увидеть — честно")


class Budget(Strict):
    """При каком просмотре получен результат.

    Флаг `visiononly_solved = false` без этого числа не интерпретируется: он
    смешивает «зрения не хватило» и «зрению показали сорок картинок на полчаса».
    Сетку просмотра мы собираемся менять — и в тот день старые и новые замеры
    надо будет различать, иначе `audio_dependency` выведется из смеси режимов.
    """

    frames_viewed: int = Field(ge=0)
    sparse_step: float | None = Field(default=None, description="шаг редкой сетки, с")
    dense_intervals: list[Interval] = Field(default_factory=list,
                                            description="где смотрел часто")
    transcript_cues: int | None = Field(default=None, description="сколько реплик прочитал")


# --------------------------------------------------------------------------
# Проверка по пункту чеклиста (SGR Cascade)
# --------------------------------------------------------------------------


class Check(Strict):
    """Один пункт чеклиста.

    Порядок полей — это порядок рассуждения, и менять его нельзя: при constrained
    decoding модель генерирует поля сверху вниз, и `result`, стоящий последним,
    пишется уже после того, как основания зафиксированы. Переставь `result`
    наверх — и всё, что ниже, станет пересказом уже принятого решения.
    """

    group: Group
    item: Item

    target: Target | None = Field(default=None,
                                  description="обязателен для пунктов про конкретное окно "
                                              "или приманку; у пунктов уровня сэмпла — null")

    # --- каскад: смотрю -> вижу -> примеряю критерий -> шаги -> вывод ------
    looked_at: list[Observation] = Field(
        default_factory=list,
        description="кадры и реплики, на которых держится вывод; пусто допустимо "
                    "только для пунктов, не требующих просмотра")
    findings: str = Field(
        min_length=10,
        description="что увидел, своими словами и без оценки: сначала факты")
    criterion: str = Field(
        min_length=10,
        description="какой именно критерий пункта применяется к увиденному; "
                    "формулировать своими словами, а не цитатой чеклиста — "
                    "пересказ обнажает непонимание, цитата его прячет")
    steps: list[SubAnswer] = Field(
        default_factory=list,
        description="промежуточные ответы, из которых складывается вердикт")

    # --- и только теперь вывод --------------------------------------------
    result: Result
    confidence: Confidence = Confidence.HIGH
    proposal: Proposal | None = None
    uncovered: Interval | None = Field(
        default=None, description="что осталось непроверенным; обязателен при skipped")

    @model_validator(mode="after")
    def _group_matches_item(self) -> Check:
        """Группа выводится из пункта, но пишется всё равно.

        Дублирование намеренное: при constrained decoding модель сначала выбирает
        группу и тем сужает себе выбор пункта — это дешёвый Routing. Расхождение
        значит, что модель ошиблась ветвью, и вывод ниже относится не к тому
        пункту, который она назвала.
        """
        expected = ITEM_GROUP.get(self.item)
        if expected is not None and self.group is not expected:
            raise ValueError(f"пункт {self.item.value} принадлежит группе "
                             f"{expected.value}, а не {self.group.value}")
        if self.item in ITEMS_NEEDING_TARGET and self.target is None:
            raise ValueError(f"пункт {self.item.value} относится к конкретному окну "
                             f"или приманке: без target координатор не поймёт, что править")
        if self.target is not None:
            if self.item in ITEMS_NEEDING_DISTRACTOR_IDX and self.target.distractor_idx is None:
                raise ValueError(f"пункт {self.item.value} — про приманку, а target называет "
                                 f"только триггер: непонятно, какая приманка проверена")
            if (self.item in ITEMS_NEEDING_TARGET
                    and self.item not in ITEMS_NEEDING_DISTRACTOR_IDX
                    and self.target.trigger_idx is None):
                raise ValueError(f"пункт {self.item.value} — про окно триггера, "
                                 f"а target называет только приманку")
        return self

    @model_validator(mode="after")
    def _skipped_names_the_gap(self) -> Check:
        if self.result is Result.SKIPPED and self.uncovered is None:
            raise ValueError("skipped без uncovered: непокрытый интервал обязан быть назван, "
                             "иначе пропуск неотличим от пройденной проверки")
        if self.result is Result.FAIL and self.proposal is None:
            raise ValueError("fail без proposal: сработавший пункт обязан предлагать лечение")
        return self

    @model_validator(mode="after")
    def _conclusion_rests_on_something(self) -> Check:
        """Вывод обязан на чём-то стоять.

        `ok` при пустом `looked_at` — это `skipped`, только необъявленный: снаружи
        он неотличим от проверенного пункта, а изнутри проверки не было. Исключение
        одно — пункты, вывод по которым делается по тексту сэмпла; для них
        обязателен разбор в `steps`, потому что иначе от проверки не остаётся
        вообще ничего.
        """
        if self.result in (Result.OK, Result.FAIL):
            if self.item in ITEMS_WITHOUT_VIEWING:
                if not self.steps:
                    raise ValueError(
                        f"{self.item.value}: текстовый пункт без steps — вывод не на чём "
                        f"держится. Разложите его на проверяемые промежуточные ответы")
            elif not self.looked_at:
                raise ValueError(
                    f"{self.item.value}: result={self.result.value} при пустом looked_at. "
                    f"Пункт, по которому ничего не смотрели, — это skipped, а не ok")
        if self.result is Result.NA and self.item in ITEMS_ALWAYS_APPLICABLE:
            raise ValueError(
                f"{self.item.value} применим к любому сэмплу — na по нему не бывает. "
                f"Если проверить не удалось, это skipped с названным непокрытым интервалом")
        return self


# --------------------------------------------------------------------------
# Конверт
# --------------------------------------------------------------------------


class ReviewBase(Strict):
    """Общая часть любого ревью.

    `model` и `date` здесь, а не в сэмпле: сэмпл — это данные, ревью — это замер.
    План требует, чтобы генератор, судья и участник были разными моделями;
    проверить это постфактум можно только по сохранённым ревью, поэтому
    `data/reviews/` обязан лежать в репозитории.
    """

    schema_version: str = SCHEMA_VERSION
    checklist_version: str = CHECKLIST_VERSION
    sample_id: str
    role: Role
    iteration: int = Field(ge=1, description="номер круга правок: ревью не переписываются, "
                                             "а накапливаются — по ним видно осцилляцию")
    model: str = Field(description="какая модель заполняла")
    date: str
    workspace: str = Field(description="папка, из которой брался материал")
    budget: Budget
    violations: list[Violation] = Field(default_factory=list)
    notes: str = Field(default="", description="не более пяти строк")


# --------------------------------------------------------------------------
# Полу-слепой ревьюер: 2.2 и 2.3
# --------------------------------------------------------------------------


class IntervalScan(Strict):
    """Один отрезок просмотра у полу-слепого ревьюера.

    Почему отрезки, а не один префикс. Слепой, которому дали ролик до `t_start`
    первого окна, проверяет левую границу только этого окна: у девятиоконного
    вопроса восемь остальных не проверяет никто. Разбить на отрезки по одному
    на окно — и покрытие становится полным.

    Почему отрезок кончается на `t_end`, а не начинается с `t_start`. Ревьюер
    знает, что где-то в конце отрезка ответ уже доступен, и ищет **первый** момент,
    когда это стало так. Вопрос «мог бы ты ответить?» для многотриггерного сэмпла
    бессмыслен — ответ «да, много раз, в этом и смысл»; вопрос «с какого момента
    можно?» осмыслен всегда.

    Почему ревьюер полу-слепой, а не слепой. Он видит `t_to` — то есть знает,
    к какому моменту ответ обязан появиться. Это неустранимо: без верхней границы
    отрезка не бывает. Зато он не видит ни ответа, ни рубрики, ни `t_start`, —
    а именно `t_start` его вывод и проверяет.
    """

    idx: int = Field(ge=0, description="номер окна, к которому относится отрезок")
    t_from: Seconds = Field(description="начало отрезка: t_end предыдущего окна, "
                                        "а для первого — 0, чтобы захватить и 2.3")
    t_to: Seconds = Field(description="конец отрезка: t_end своего окна")

    watched: list[Observation] = Field(default_factory=list)
    candidates: list[SubAnswer] = Field(
        default_factory=list,
        description="моменты-кандидаты и почему они отброшены или приняты; "
                    "именно здесь видно, ошибся ревьюер или ошиблась разметка")

    t_val: Seconds | None = Field(
        default=None,
        description="самая ранняя точка отрезка, начиная с которой на вопрос "
                    "можно ответить по существу; null — если не стало возможно нигде")
    t_val_basis: str = Field(
        default="", description="что именно в этот момент появилось")
    answer_at_t_val: str = Field(
        default="", description="что конкретно можно ответить с этого момента; "
                                "сверять с эталоном будет координатор")
    confidence: Confidence = Confidence.HIGH

    @model_validator(mode="after")
    def _inside(self) -> IntervalScan:
        if self.t_to <= self.t_from:
            raise ValueError("отрезок пуст или вывернут")
        if self.t_val is not None and not (self.t_from <= self.t_val <= self.t_to):
            raise ValueError("t_val вне своего отрезка: ревьюер искал не там, где просили")
        if self.t_val is not None and len(self.t_val_basis) < 5:
            raise ValueError("t_val без основания")
        return self


class SemiBlindReview(ReviewBase):
    """Ревью полу-слепого: левые границы всех окон плюс контаминация.

    Координатор из `scans` выводит два пункта чеклиста, сам ревьюер вердиктов
    по ним не ставит:

    * `t_val[0] < question_time`  -> `answer-available-before-question` (2.3);
    * `t_val[k] < t_start[k]`     -> `answer-possible-before-start` (2.2);
    * `t_val[k] is None`          -> ревьюер не нашёл ответа там, где он обязан
      быть к концу отрезка: сигнал в сторону `author-says-answer-in-window` (2.5)
      или `solvable-at-all` (4.7), но **не** 2.2. Случая `t_val > t_end` не бывает:
      его отсекает валидатор `IntervalScan`, потому что искать за верхней границей
      отрезка ревьюеру нечем — материала там нет.

    Первый отрезок начинается с **нуля**, а не с `question_time`: иначе 2.3
    («ответ был доступен ещё до выдачи вопроса») нечем проверить — материал
    до `question_time` просто не попадёт ревьюеру в руки. Одно число `t_val[0]`
    закрывает оба пункта сразу, разделяет их сравнение с `question_time`.

    Просить самого ревьюера назвать вердикт нельзя: он не знает `t_start`,
    а знал бы — перестал бы быть полу-слепым.
    """

    role: Literal[Role.SEMIBLIND] = Role.SEMIBLIND

    prior_answer: str = Field(
        description="ответ на вопрос до всякого просмотра, по общим знаниям "
                    "(4.2). Записывается дословно, даже если сам считаешь его "
                    "догадкой: сверять будет координатор")
    recognized_video: bool = Field(
        description="узнал ли ролик до просмотра (4.3)")
    recognized_how: str = Field(
        default="", description="по каким признакам узнал")

    scans: list[IntervalScan] = Field(min_length=1)
    checks: list[Check] = Field(
        default_factory=list,
        description="пункты, которые полу-слепой закрывает напрямую: "
                    "solvable-without-video и video-recognized")

    @model_validator(mode="after")
    def _covers_its_items(self) -> SemiBlindReview:
        seen = {c.item for c in self.checks}
        required = ROLE_ITEMS[Role.SEMIBLIND]
        missing = required - seen
        if missing:
            names = ", ".join(sorted(i.value for i in missing))
            raise ValueError(f"нет строки по пунктам режима: {names}")
        alien = seen - required
        if alien:
            names = ", ".join(sorted(i.value for i in alien))
            raise ValueError(f"пункты не из этого режима: {names}. Левые границы "
                             f"полу-слепой не судит сам — их выводит координатор "
                             f"из scans, потому что t_start ему не показан")
        return self


# --------------------------------------------------------------------------
# Полный ревьюер
# --------------------------------------------------------------------------


class FullReview(ReviewBase):
    """Общая часть обоих не-слепых ревью. Сама по себе не сохраняется.

    Единственное, что здесь описано сверх общего конверта, — **покрытие**:
    строка обязана быть на каждый пункт своего режима, включая несработавшие
    (`ok`) и неприменимые (`na`). Отсутствие строки неотличимо от пройденной
    проверки, а это ровно та подмена, ради запрета которой заведён `skipped`.
    """

    verdict: Verdict
    checks: list[Check] = Field(min_length=1)

    @model_validator(mode="after")
    def _covers_its_items(self) -> FullReview:
        seen = {c.item for c in self.checks}
        required = ROLE_ITEMS[self.role]
        missing = required - seen
        if missing:
            names = ", ".join(sorted(i.value for i in missing))
            raise ValueError(f"нет строки по пунктам режима {self.role.value}: {names}. "
                             f"Отсутствие строки неотличимо от пройденной проверки — "
                             f"поставьте ok, na или skipped")
        alien = seen - required
        if alien:
            names = ", ".join(sorted(i.value for i in alien))
            raise ValueError(f"пункты не из режима {self.role.value}: {names}")
        return self

    @model_validator(mode="after")
    def _verdict_matches_checks(self) -> FullReview:
        """Вердикт не может быть лучше худшей из проверок.

        Это ловит самый частый способ сдать плохую работу как хорошую: расписать
        сработавшие пункты честно, а в вердикт поставить PASS.
        """
        bad = [c for c in self.checks if c.result in (Result.FAIL, Result.SKIPPED)]
        if bad and self.verdict is Verdict.PASS:
            names = ", ".join(sorted({c.item.value for c in bad}))
            raise ValueError(f"verdict=PASS при сработавших или пропущенных пунктах: {names}")
        return self


class FullSampleReview(FullReview):
    """Ревью сэмпла как целого: текст вопроса, рубрика, приманки, эталон, полнота
    набора триггеров. Один запуск на сэмпл, бюджет кадров — на весь ролик.

    Сюда собрано всё, что не принадлежит отдельному окну. Проверка «не пропущено
    ли срабатывание» требует редкой сетки по всей лекции; текст вопроса и рубрика
    у сэмпла одни на всех; приманки и ссылки `provenance` между окнами не делятся.
    """

    role: Literal[Role.FULL_SAMPLE] = Role.FULL_SAMPLE


class FullWindowReview(FullReview):
    """Ревью одного окна. По запуску на окно, бюджет кадров — на это окно.

    `window_idx` обязателен и дублируется в каждом `target`: без него координатор,
    получив девять файлов, не отличит девять ревью девяти окон от девяти ревью
    одного и того же — а именно ради этого различения роль и заведена.
    """

    role: Literal[Role.FULL_WINDOW] = Role.FULL_WINDOW
    window_idx: int = Field(ge=0, description="idx триггера, ревью которого это")

    @model_validator(mode="after")
    def _target_is_this_window(self) -> FullWindowReview:
        wrong = sorted({c.target.trigger_idx for c in self.checks
                        if c.target is not None and c.target.trigger_idx is not None
                        and c.target.trigger_idx != self.window_idx})
        if wrong:
            raise ValueError(f"ревью окна {self.window_idx}, а target называет окна {wrong}: "
                             f"пооконный ревьюер видит только своё окно и судить о чужих "
                             f"не может")
        return self


# --------------------------------------------------------------------------
# Зонды модальностей
# --------------------------------------------------------------------------


class ProbeAnswer(ReviewBase):
    """Ответ зонда. Вердиктов не ставит и о качестве вопроса не рассуждает.

    Зонд не знает, что участвует в проверке: он просто отвечает на вопрос по тому
    материалу, который ему дали. Решение о флаге принимает координатор, сверив
    ответ с эталоном, — иначе зонд начнёт подстраивать ответ под ожидаемый флаг.
    """

    role: Literal[Role.PROBE_TEXT, Role.PROBE_VISION,
                  Role.PROBE_FRAME, Role.PROBE_FULL]

    looked_at: list[Observation] = Field(default_factory=list)
    steps: list[SubAnswer] = Field(
        default_factory=list,
        description="как шёл к ответу; для зонда это ещё и способ отличить вывод "
                    "из материала от воспоминания о предмете")
    answer: str = Field(min_length=1, description="ответ по существу, своими словами")
    basis: str = Field(min_length=5,
                       description="откуда ответ: таймкоды и цитаты — или «общие знания». "
                                   "Если узнал ролик или вспомнил ответ до того, как "
                                   "заглянул в материал, — напиши это прямо")
    confidence: Confidence
    insufficient: bool = Field(
        default=False,
        description="материала не хватило; ставится вместе с попыткой ответа, "
                    "а не вместо неё")


Review = Annotated[SemiBlindReview | FullReview | ProbeAnswer,
                   Field(discriminator="role")]


# --------------------------------------------------------------------------
# Справочная таблица номеров. НЕ авторитетна: если разойдётся с чеклистом,
# правится она, а не сохранённые ревью.
# --------------------------------------------------------------------------

ITEM_NUMBER: dict[Item, str] = {
    Item.WINDOW_GEOMETRY: "1.1",
    Item.DISTRACTOR_GEOMETRY: "1.2",
    Item.SAMPLE_INTEGRITY: "1.3",
    Item.DEPENDS_ON_BACKWARDS: "1.4",
    Item.MULTITRIGGER_HAS_DISTRACTOR: "1.5",
    Item.DURATION_MATCHES_BUNDLE: "1.6",
    Item.CLAIM_MATCHES_MODALITIES: "1.7",
    Item.JSON_SCHEMA: "1.8",
    Item.EVIDENCE_SPAN_PRESENT: "1.9",
    Item.SOUND_ONLY_TRIGGER: "1.10",
    Item.WINDOW_NOT_TOO_NARROW: "1.11",
    Item.SHARED_BOUNDARY_NOT_MID_CUE: "2.1",
    Item.ANSWER_POSSIBLE_BEFORE_START: "2.2",
    Item.ANSWER_AVAILABLE_BEFORE_QUESTION: "2.3",
    Item.WINDOW_CAN_BE_TIGHTENED: "2.4",
    Item.AUTHOR_SAYS_ANSWER_IN_WINDOW: "2.5",
    Item.NO_MISSED_TRIGGER: "3.1",
    Item.TRIGGER_MATCHES_CRITERION: "3.2",
    Item.EVENT_NOT_EARLIER_THAN_WINDOW: "3.3",
    Item.PROBE_PROTOCOL: "4.1",
    Item.SOLVABLE_WITHOUT_VIDEO: "4.2",
    Item.VIDEO_RECOGNIZED: "4.3",
    Item.TRANSCRIPT_ENOUGH: "4.4",
    Item.FRAMES_ENOUGH: "4.5",
    Item.SINGLE_FRAME_ENOUGH: "4.6",
    Item.SOLVABLE_AT_ALL: "4.7",
    Item.QUESTION_ANCHORED_TO_SCREEN: "4.8",
    Item.TWINS_SHARE_RUBRIC: "5.1",
    Item.RUBRIC_WITHIN_QUESTION: "5.2",
    Item.DISCRIMINATOR_IN_QUESTION: "5.3",
    Item.RUBRIC_NOT_PUNISHING_EXTRA: "5.4",
    Item.DISTRACTOR_FULLY_COVERED: "6.1",
    Item.DISTRACTOR_NOT_CORRECT_ANSWER: "6.2",
    Item.TWINS_KEEP_LEGAL_DISTRACTOR: "6.3",
    Item.DISTRACTOR_WHY_HIDES_ANSWER: "6.4",
    Item.TEMPORAL_REL_DERIVED: "7.1",
    Item.AUDIO_DEPENDENCY_EMPTY_IN_DRAFT: "7.2",
    Item.REASONING_LEVEL_NOT_INFLATED: "7.3",
    Item.DEPENDS_ON_IS_DEPENDENCY: "7.4",
    Item.EVIDENCE_SPAN_IS_LAST: "7.5",
    Item.AUDIO_DEPENDENCY_MATCHES_PROBES: "7.6",
    Item.PROBE_FLAGS_CONSISTENT: "7.7",
    Item.TIMECODES_EXIST: "8.1",
    Item.REFERENCE_MATCHES_DESCRIPTION: "8.2",
    Item.REFERENCES_CONSISTENT_WITH_WINDOWS: "8.3",
    Item.REFERENCE_ANSWER_VERIFIED: "8.4",
    Item.TWINS_AGREE_ON_SUBSTANCE: "8.5",
    Item.NUMBERS_RECOMPUTED: "9.1",
    Item.EXAMPLES_GENERATED: "9.2",
    Item.TOOLS_IDEMPOTENT: "9.3",
    Item.CHECKLIST_MATCHES_VALIDATOR: "9.4",
}

# Номер группы -> группа. Явно, а не через list(Group)[n-1]: перестановка двух
# членов enum молча переназначила бы группы всем пунктам сразу, без единой ошибки.
GROUP_BY_NUMBER: dict[str, Group] = {
    "1": Group.FORMAL, "2": Group.WINDOWS, "3": Group.TRIGGERS, "4": Group.SHORTCUTS,
    "5": Group.RUBRIC, "6": Group.DISTRACTORS, "7": Group.LABELS,
    "8": Group.PROVENANCE, "9": Group.DRIFT,
}

ITEM_GROUP: dict[Item, Group] = {
    item: GROUP_BY_NUMBER[num.split(".")[0]] for item, num in ITEM_NUMBER.items()
}

ROLE_MODEL: dict[Role, type[ReviewBase]] = {
    Role.SEMIBLIND: SemiBlindReview,
    Role.FULL_SAMPLE: FullSampleReview,
    Role.FULL_WINDOW: FullWindowReview,
    Role.PROBE_TEXT: ProbeAnswer,
    Role.PROBE_VISION: ProbeAnswer,
    Role.PROBE_FRAME: ProbeAnswer,
    Role.PROBE_FULL: ProbeAnswer,
}


def check_file(path: str) -> ReviewBase:
    """Проверить сохранённое ревью. Роль берётся из самого файла.

    Субагент запускает это на себе перед тем, как отчитаться координатору:
    невалидное ревью дешевле починить на месте, чем разбирать потом, почему
    у пункта нет строки.
    """
    import json

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    role = raw.get("role")
    if role not in set(Role):
        raise SystemExit(f"неизвестная роль {role!r}; ожидается одна из "
                         f"{[r.value for r in Role]}")
    return ROLE_MODEL[Role(role)].model_validate(raw)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        if len(sys.argv) != 3:
            raise SystemExit("использование: review.py --check <файл ревью>")
        try:
            obj = check_file(sys.argv[2])
        except Exception as e:  # ValidationError, JSONDecodeError, KeyError...
            print(f"ревью НЕ валидно:\n{e}")
            raise SystemExit(1)
        print(f"ревью валидно: {obj.role.value}, сэмпл {obj.sample_id}, "
              f"круг {obj.iteration}")
        raise SystemExit(0)

    missing = [i.value for i in Item if i not in ITEM_NUMBER]
    if missing:
        raise SystemExit(f"пункты без номера: {missing}")

    # Чеклист и контракт обязаны совпадать в обе стороны (чеклист 9.4). Пункт,
    # который есть здесь и которого нет там, — это требование к ревьюеру, которого
    # он нигде не прочитает; обратное — пункт, по которому никто не отчитается.
    checklist = Path(__file__).resolve().parent.parent / "docs" / "annotation_checklist.md"
    if checklist.exists():
        import re

        pat = re.compile(r"^- `\[([AMH])\]` \*\*(\d+\.\d+)\..*\*\* · `([a-z0-9-]+)`")
        found, level, done = {}, {}, {}
        cur = None
        for line in checklist.read_text(encoding="utf-8").splitlines():
            m = pat.match(line)
            if m:
                cur = m.group(2)
                found[cur] = m.group(3)
                level[cur] = m.group(1)
            elif cur and line.strip().startswith("*Статус.*"):
                # Не сбрасываем cur: раньше второй «*Статус.*» внутри одного пункта
                # молча игнорировался, и 2.1 годами числился нереализованным при
                # живом S-33 — то есть проверка на расхождение была слепа ровно там,
                # где расхождение и было.
                if cur in done:
                    raise SystemExit(f"у пункта {cur} два «*Статус.*» — какой из них "
                                     f"настоящий, знает только автор правки; оставьте один")
                done[cur] = "Реализовано" in line
        by_num = {num: item.value for item, num in ITEM_NUMBER.items()}
        only_here = sorted(set(by_num) - set(found))
        only_there = sorted(set(found) - set(by_num))
        renamed = {n: (by_num[n], found[n]) for n in set(by_num) & set(found)
                   if by_num[n] != found[n]}
        problems = []
        if only_here:
            problems.append(f"есть в контракте, нет в чеклисте: {only_here}")
        if only_there:
            problems.append(f"есть в чеклисте, нет в контракте: {only_there}")
        if renamed:
            problems.append(f"имена разошлись: {renamed}")
        # Пункт, помеченный [A] и объявленный реализованным, обязан иметь правило
        # в валидаторе; пункт [M] — роль, которая по нему отчитывается. Иначе метка
        # уровня выводит пункт из-под чьей-либо ответственности: статус честный,
        # кода нет, роли нет, и заметить это некому.
        validator = Path(__file__).resolve().parent.parent / "tools" / "validate_samples.py"
        coded = set()
        if validator.exists():
            src = validator.read_text(encoding="utf-8")
            passports = re.findall(r"# (S-\d+) · чеклист ([\d.]+) —", src)
            coded = {num for _, num in passports}
            # Обратная сторона 9.4: правило, сославшееся на несуществующий пункт,
            # выглядит документированным, но ведёт в никуда — а заметить это
            # можно только сверкой, потому что паспорт читается как проза.
            stray = sorted({f"{rule}->{num}" for rule, num in passports
                            if num not in found})
            if stray:
                problems.append(f"правила ссылаются на пункты, которых нет: {stray}")
        assigned = {ITEM_NUMBER[i] for items in ROLE_ITEMS.values() for i in items}
        assigned |= {ITEM_NUMBER[i] for i in COORDINATOR_ITEMS}
        # Группа 9 — гигиена процесса (числа в документации, идемпотентность
        # инструментов, эта самая сверка). Её `[A]` означает «делается кодом»,
        # но кодом не валидатора: правила S-NN проверяют сэмпл, а не репозиторий.
        for num in sorted(level, key=lambda n: [int(x) for x in n.split(".")]):
            if num.startswith("9."):
                continue
            if level[num] == "A" and done.get(num) and num not in coded:
                problems.append(f"{num} помечен [A] и «Реализовано», но правила S-NN "
                                f"на него в валидаторе нет")
            if level[num] == "M" and num not in assigned:
                problems.append(f"{num} помечен [M], но не входит ни в одну роль "
                                f"и не выводится координатором")
        if problems:
            raise SystemExit("чеклист и контракт разошлись:\n  " + "\n  ".join(problems))
        n_a = sum(1 for v in level.values() if v == "A")
        print(f"чеклист сверен: {len(found)} пунктов ({n_a} автоматических), "
              f"имена совпадают, у каждого есть исполнитель")
    roles = sorted(ROLE_ITEMS)
    for i, a in enumerate(roles):
        for b in roles[i + 1:]:
            overlap = ROLE_ITEMS[a] & ROLE_ITEMS[b]
            if overlap:
                raise SystemExit(f"пункт назначен и {a.value}, и {b.value}: "
                                 f"{[i.value for i in overlap]}")
    print(f"контракт ревью {SCHEMA_VERSION}, чеклист {CHECKLIST_VERSION}")
    print(f"пунктов: {len(Item)}, групп: {len(Group)}")
    for role, items in ROLE_ITEMS.items():
        nums = sorted(ITEM_NUMBER[i] for i in items)
        print(f"  {role.value:10s} {len(items):2d} пунктов: {', '.join(nums)}")

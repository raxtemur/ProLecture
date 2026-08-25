# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это за репозиторий

Две независимые линии работы под одной крышей:

1. **ProLecture** — бенчмарк проактивных задач для стриминговых VLM на видео 3Blue1Brown.
   Это основная линия: `tools/`, `data/`, `schema/`, `docs/`, `articles/`.
2. **Песочница manim** — эксперименты с анимацией и две самописные проверки качества сцен:
   `demo/`, `scripts/`.

Проектный замысел ProLecture целиком описан в [docs/plans/general.md](docs/plans/general.md),
формат разметки — в [data/annotations/README.md](data/annotations/README.md), нарезка
кадров по смене сцен — в [docs/scene_detection.md](docs/scene_detection.md),
прогон описания видеоряда — в [docs/video_description.md](docs/video_description.md), классы ошибок
разметки и кто их ловит — в [docs/annotation_checklist.md](docs/annotation_checklist.md),
порядок работы агентов-разметчиков и ревьюеров — в
[docs/annotation_pipeline.md](docs/annotation_pipeline.md) вместе с драфтами промптов
в [docs/prompts/](docs/prompts/) и анти-примерами по шаблонам вопросов
в [docs/question_templates.md](docs/question_templates.md).
Контракт, по которому отчитываются субагенты-ревьюеры, — [schema/review.py](schema/review.py)
(pydantic, не JSON-схема: его читает и модель тоже).
Читай их перед любой правкой разметки или метрик: там зафиксированы решения, у которых
есть неочевидное «почему».

## Два окружения — главная грабля

`python3` в оболочке резолвится то в одно, то в другое. **Всегда указывай интерпретатор явно.**

| Окружение | Путь | Что есть | Чего нет |
|---|---|---|---|
| `rah_manim` | `/home/jovyan/.mlspace/envs/rah_manim/bin/python` | manim CE 0.20.1, manim-voiceover, yt-dlp, cv2, openai | matplotlib, pandas, jupyter, jsonschema |
| base conda | `/home/user/conda/bin/python3` | matplotlib, pandas, jsonschema, cv2, jupyter | yt-dlp, manim |

`tools/fetch_video.py` сам ищет интерпретатор с `yt_dlp` (список в `CANDIDATE_PYTHONS`).
Остальные инструменты и ядро ноутбука — base conda. LaTeX для manim берётся из TinyTeX
(`~/.TinyTeX/bin/x86_64-linux`, прописан в `~/.zshrc`).

## Команды

```bash
BASE=/home/user/conda/bin/python3
RAH=/home/jovyan/.mlspace/envs/rah_manim/bin/python

# конвейер данных: маппинг -> скачивание -> bundle -> проверка разметки
$BASE tools/build_3b1b_mapping.py                  # урок -> youtube_id -> manim-исходник
$BASE tools/fetch_video.py <youtube_id>            # или --slug <lesson-slug>
$BASE tools/make_bundle.py <youtube_id>            # кадры режет детектор сцен; --no-frames оставляет прежние
$BASE tools/detect_scenes.py <youtube_id>          # детектор сцен сам по себе
$BASE tools/describe_video.py <youtube_id> --settled 0.5   # описание видеоряда VLM, нужен сервер
$BASE tools/validate_samples.py data/annotations/*.jsonl

# контракт ревью: сверка чеклиста с Item и проверка сохранённого ревью
$BASE schema/review.py
$BASE schema/review.py --check data/reviews/<VIDEO_ID>/<SAMPLE_ID>/full.1.json

# ноутбук обзора (ядро — base conda, в rah_manim он не запустится)
cd data && $BASE -m nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=300 data_overview.ipynb

# manim: рендер сцены. PYTHONPATH обязателен — сцены в demo/ импортируют
# scene_asserts и layout_check, а manim кладёт в sys.path только каталог сцены
conda activate rah_manim
PYTHONPATH=scripts manim -ql demo/demo.py SquareToCircle
PYTHONPATH=scripts MANIM_LAYOUT_STRICT=1 MANIM_SCENE_STRICT=1 \
    manim -ql demo/demo2.py EigenLecture
```

Тестового фреймворка нет. Роль тестов для разметки играет `tools/validate_samples.py`:
он возвращает код 1 при любой ошибке и печатает разбивку покрытия при нуле ошибок.
Проверить одиночный файл — просто передать его вместо глоба.

## Конвейер ProLecture

```
vendor/site (3Blue1Brown.com)          vendor/videos (3b1b/videos)
   app/pages/lessons/*/index.mdx  ──┐      _YYYY/*.py
   frontmatter: video:, source:     │
                                    ▼
                         data/3b1b_mapping.json      tools/build_3b1b_mapping.py
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
          data/videos/<id>/               (путь к manim-исходнику)
          mp4 + info.json + en.vtt                 │
                     └──────────────┬──────────────┘
                                    ▼
                       data/bundles/<id>/           tools/make_bundle.py
                       transcript.md, formulas.md, frames/, bundle.json
                                    ▼
                       разметка руками по bundle
                                    ▼
                     data/annotations/<id>.jsonl    tools/validate_samples.py
```

**Ключ ко всему — frontmatter репозитория сайта.** В самом `3b1b/videos` нет ни одной ссылки
на YouTube; связь «урок ↔ ролик ↔ код сцены» существует только в
`vendor/site/app/pages/lessons/<год>/<slug>/index.mdx`, где есть поля `video:` (YouTube-id)
и `source:` (путь внутри `3b1b/videos`). Из 175 уроков 170 имеют id, 159 объявляют `source` (155 — вместе с id),
и лишь **140** указывают на реально существующий файл — остальные пути устарели, для них
скрипт предлагает `source_guess` через `difflib`.

`vendor/` не под версионным контролем; коммиты трёх сторонних репозиториев зафиксированы
в `vendor/PINNED.txt` — без них числа выше невоспроизводимы. Учти: `3b1b/videos` написан под
**manimgl** (3b1b/manim), а установлен manim **CE** — отрендерить оттуда сцену без отдельной
установки нельзя.

## Скачивание с YouTube: три граблины

Куки и логин **не нужны**, но:

- дефолтный клиент `android_vr` отдаёт URL, на которых CDN возвращает 403 — обязателен
  `--extractor-args "youtube:player_client=android"`;
- `--download-sections` не работает: он передаёт URL внешнему ffmpeg, который ходит без
  нужных заголовков. Качать целиком, резать локально;
- без PO-токена доступен только формат 18 (640×360). Для 1080p нужен плагин
  `bgutil-ytdlp-pot-provider` (логина тоже не требует).

У 3b1b субтитры **человеческие** (`subtitles`, а не `automatic_captions`), Whisper не нужен.

## Инварианты разметки

Схема — `schema/sample.schema.json`, `additionalProperties: false` на всех уровнях.
Семантику поверх схемы проверяет `tools/validate_samples.py`. Два правила, которые легко
нарушить по незнанию:

- **`temporal_rel` не ставится руками, а выводится** из `question_time` и `evidence_span`
  первого/последнего обязательного триггера. Ось определяется положением *доказательства*,
  а не окна ответа: у `post`-вопроса окно ответа тоже начинается в момент выдачи вопроса,
  и по окну он неотличим от `at`.
- **`audio_dependency` остаётся `null`, пока `status == "draft"`** — метка выводится
  из ответов зондов модальностей (`visiononly_solved` и `solvable`, чеклист 4.5),
  а не ставится мнением разметчика. Мнение живёт отдельно в `audio_dependency_claim`.

Прочее, что проверяется: непересекающиеся окна, `t_ideal` внутри своего окна, `depends_on`
только на более ранние индексы, дистрактор не лежит целиком до `question_time` и не
пересекается с триггером, у многотриггерного сэмпла есть хотя бы один дистрактор,
уникальность `id`.

## Принципы, из которых вырос дизайн

Взяты из адверсальных разборов трёх статей в `articles/` — каждый пункт закрывает провал,
на котором погорела соответствующая работа:

- метки, влияющие на выводы (`audio_dependency`), ставятся **замером**, а не декларацией;
- модель-генератор, модель-судья и оцениваемая модель — разные;
- ответы открытые с рубрикой, без MCQ (перекошенный ключ ответов ломает бенчмарк);
- обязательные бейзлайны-пустышки: blind, text-only, vision-only, frozen-frame,
  «отвечать сразу», «отвечать в конце», «молчать»;
- никаких квот вида «ровно N сэмплов на задачу» — сколько прошло валидацию, столько и есть;
- контаминация: пилот строится на видео 2026 года, контрольное видео 2017 года нужно,
  чтобы разрыв blind-бейзлайна **измерить**, а не отрицать.

## Проверки сцен manim

`scripts/layout_check.py` и `scripts/scene_asserts.py` закрывают два разных класса ошибок,
о которых manim молчит: вёрстку (выход за кадр, наложения) и семантику («картинка аккуратна,
но означает не то»). Переменные `MANIM_LAYOUT_STRICT=1` и `MANIM_SCENE_STRICT=1` превращают
предупреждения в исключения.

## Язык

Код, документация и разметка ведутся по-русски; идентификаторы, термины и цитаты из видео —
в оригинале.

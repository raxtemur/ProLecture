# Salvage-review 2: `q07` / `q07b`

## Итог

Оба близнеца можно довести до `validation.status: "validated"` минимальной
metadata-only правкой. Текст вопросов, ответы, рубрики, окна, distractors,
`act`, `temporal_rel`, `reasoning_level`, `template`, `trigger_modality` и
`audio_dependency_claim` менять не нужно.

Единственный содержательный пробел — provenance вычисляемой части ответа:
для `counterfact`, `L3` checklist 8.4 требует независимо записанное вычисление,
а текущие evidence подтверждают график, но не переход от `-log2(p)` к `-ln(p)`.
После добавления этого evidence нужно заполнить измеренные flags и производный
`audio_dependency` у обоих близнецов.

Отдельно применено разрешение пользователя: известный длинный хвост required-window
до `1000.0` и отсутствие прежнего `full_window` review сами по себе не блокируют
validation; повторная проверка интервалов после этих metadata-only правок не требуется.

## Согласованность пары

- Видео, `act: "counterfact"`, `reasoning_level: "L3"`, required rubric,
  `trigger_modality: ["visual"]` и required response совпадают по существу и по
  критериям.
- Обе required responses называют одни и те же четыре пары:
  `1/16 -> 4`, `1/8 -> 3`, `1/4 -> 2`, `1/2 -> 1`, затем один и тот же переход
  к `4 ln 2`, `3 ln 2`, `2 ln 2`, `ln 2` (наты).
- Различие формулировок корректно кодирует только цену времени: `q07` выдан в
  `930.0` до появления графика, `q07b` — в `963.0`, когда график уже на экране.
  Поэтому `pre` для `q07` и `at` для `q07b` честны.
- Optional trigger `q07` на `[946.0, 955.4)` не обязан иметь копию у `q07b` и не
  нарушает пару: это предусмотренный пунктом 2.2 ранний эквивалент в другой форме;
  его rubric явно разрешает молчание. Required criteria пары от него не меняются.
- Distractor `[918.0, 946.0)` законен только для `q07`. Для `q07b` он целиком
  предшествует `question_time = 963.0`, поэтому его отсутствие соответствует 6.3.

## Full-sample review

### Вопрос, ответ, rubric

Вопросы привязаны к конкретному экрану словами `the graph ... on screen` и
`read off which values of p the bars are drawn for`; это не textbook-only
формулировка. `L3` не завышен: позиции и исходные высоты читаются с экрана, а
новые высоты для натурального логарифма в видео не даны и должны быть выведены.

Required rubric полностью следует из вопроса:

1. четыре позиции — из `which values of p`;
2. четыре исходные высоты — из `height of each one`;
3. общий множитель `ln 2` либо явные новые значения — из контрфактической части;
4. бонус про биты/наты не обязателен;
5. запрет засчитывать ответ без позиций поддержан требованием `read off` и
   защищает визуальную привязку.

Формула ответа верна:

`p = 2^-n  =>  -ln(p) = -ln(2^-n) = n ln(2)`.

При `ln(2) ~= 0.693147` значения для `n = 4, 3, 2, 1` равны соответственно
`2.7726, 2.0794, 1.3863, 0.6931` ната. Это согласуется с обеими responses.

### Trigger completeness и distractors

Полный transcript прочитан последовательно. Единственное явное объявление именно
этого графика — `955.5`: “let me pull up some axes and show you the graph of
negative log of p”. В visual evidence график с четырьмя требуемыми столбиками
устоялся к `958.0`; более поздние сцены используют другие диаграммы и не создают
пропущенного firing по буквальному критерию вопроса.

Distractor `q07` корректен: до появления названного графика формула уже показана,
но требуемые позиции именно его столбиков ещё не прочитаны с него. `why` объясняет
преждевременность и не раскрывает четыре правильные позиции либо преобразованные
значения. У `q07b` отдельный distractor не требуется по геометрии `question_time`.

### Provenance

Текущие frame records согласуются с описаниями: у `q07` кадры `948.0`/`953.0`
показывают четыре предшествующих квадратных диаграммы, `960.0` — сам график; у
`q07b` кадр `963.0` показывает тот же график. Speech evidence `955.5–964.1`
в `q07` выровнен по границам transcript и подтверждает объявление графика.

Минимальная обязательная правка: добавить **в каждый** `provenance.evidence`
следующую запись (одинаковую по смыслу):

```json
{
  "type": "other",
  "explanation": "Independent computation: for p = 2^-n, -ln(p) = n ln(2); with ln(2) approximately 0.693147 and n = 4, 3, 2, 1, the heights are approximately 2.7726, 2.0794, 1.3863, 0.6931 nats."
}
```

Это закрывает 8.4 независимо от frame evidence и от ссылки `q07b` на control twin.

## Честные modality flags

| sample | blind_solved | textonly_solved | visiononly_solved | frozenframe_solved | solvable | audio_dependency | status |
|---|---:|---:|---:|---:|---:|---|---|
| `3b1b__l6DKRf-fAAM__q07` | `false` | `false` | `true` | `false` | `true` | `unnecessary` | `validated` |
| `3b1b__l6DKRf-fAAM__q07b` | `false` | `false` | `true` | `false` | `true` | `unnecessary` | `validated` |

Обоснование:

- **Blind — false.** Prior answer семи-слепого ревьюера численно совпал, но
  начинается с “Ожидаю” и подставляет невидимый канонический набор `2^-n`.
  Другой набор столбиков сделал бы его неверным; по coordinator rule 1 это удачная
  догадка условия, а не честное blind solving. Для `q07b` добавление `on screen
  right now` не сообщает сами четыре позиции, поэтому вывод тот же.
- **Text-only — false.** Transcript объявляет график и объясняет `-log2(p)`, но
  нигде не перечисляет четыре позиции его столбиков. Ранее произнесённый набор
  робота заканчивается повторным `1/8`, а не `1/16`; подставить канонический ряд
  можно только догадкой, запрещённой probe protocol.
- **Vision-only — true.** Реальные кадры `958.0`, `960.0`, `963.0` и `966.0`,
  зафиксированные в существующем semiblind artifact/provenance, читаемо показывают
  четыре позиции и высоты. Переход к натуральному логарифму допустимо вывести из
  общих математических знаний; speech для этого не нужен.
- **Frozen-frame — false.** Для required trigger midpoint равен `978.5` у `q07`
  и `981.5` у `q07b`. К этому времени столбики уже убраны (существующий artifact
  фиксирует на `980.0` только кривую с движущейся точкой), поэтому из ровно одного
  midpoint frame нельзя честно прочитать четыре позиции. Optional trigger `q07`
  в aggregation этого флага не участвует.
- **Solvable — true.** Уже положительный vision-only результат доказывает
  solvability; отдельный full probe не нужен.
- **Audio dependency — unnecessary.** Это производно от
  `visiononly_solved: true` и согласуется с текущим
  `audio_dependency_claim: "unnecessary"`.

## Точные минимальные изменения JSONL

Для **обеих** строк:

1. добавить одну описанную выше запись `type: "other"` в
   `provenance.evidence`;
2. заменить `audio_dependency: null` на `audio_dependency: "unnecessary"`;
3. в `validation` установить:

```json
{
  "status": "validated",
  "blind_solved": false,
  "textonly_solved": false,
  "visiononly_solved": true,
  "frozenframe_solved": false,
  "solvable": true
}
```

Существующие `validation.notes` можно сохранить без изменения. Других правок для
salvage-validation не требуется.

## Проверка

Исходный `data/annotations/l6DKRf-fAAM.jsonl` проверен без изменений:
`checked 10, with errors 0, warnings 0`.

Затем точные изменения из этого отчёта были применены только к временной копии
`/tmp/l6DKRf-fAAM.salvage2.proposed.jsonl`; команда
`python3 tools/validate_samples.py` также вернула:
`checked 10, with errors 0, warnings 0`.

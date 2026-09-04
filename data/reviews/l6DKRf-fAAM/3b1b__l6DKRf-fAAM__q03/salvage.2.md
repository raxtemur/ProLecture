# Salvage-review 2 — `3b1b__l6DKRf-fAAM__q03`

## Прочитано и принято как основание

- текущая строка `data/annotations/l6DKRf-fAAM.jsonl`;
- `coordinator.1.md`, `semiblind.1.json`, `full_sample.1.json`, `full_window0.1.json` и относящаяся к q03 запись `coordinator.log`;
- полностью `docs/prompts/coordinator.md`; релевантные prompts `reviewer_semiblind.md`, `reviewer_full_sample.md`, `reviewer_full_window.md`, `probe_text.md`, `probe_vision.md`, `probe_frame.md`, `probe_full.md`; правила modality/status из `annotation_checklist.md`, `annotation_pipeline.md` и `data/annotations/README.md`.

По разрешению пользователя интервалы заново не проверялись: `full_window0.1.json: PASS` принимается, trigger `[1621.8, 1633.6)` и его `evidence_span` остаются без изменений.

## Итог salvage

Старый `full_sample.1: FIX_QUESTION` исправим без participant-visible переписывания вопроса. После двух минимальных правок distractor metadata независимого дефекта full-sample не остаётся; итоговый full-sample verdict этой salvage-проверки — **PASS**.

Замена вопроса на вариант со словом `first`/`for the first time` не нужна. Уже написано `say straight away` и `Until the condition has been spoken — stay silent`: первая реплика в 1621.8–1629.2 прекращает режим молчания и требует немедленного ответа. Поэтому повтор в 1751.3 не является вторым добросовестным trigger; это поздний distractor. Participant-visible правка лишь создала бы новую question-version и обнулила пригодность старых blind/full-review evidence.

## Точные минимальные правки sample

1. Расширить первый distractor влево:

   - `distractor_windows[0].t_start`: `1585.0` → `1553.0`;
   - `distractor_windows[0].why` заменить на:

     > `A concrete weighted-sum expression is already being written and is shortly described as the average information per symbol, but the author has not yet named the condition; answering here is premature.`

   Это закрывает найденный `full_sample.1` участок 1553–1585 и не раскрывает содержание ответа.

2. Добавить второй distractor:

   ```json
   {
     "t_start": 1751.3,
     "t_end": 1764.7,
     "why": "The author repeats the same condition after it was already spoken at the required moment; the instruction required an immediate answer when it was named, so a first response here is late."
   }
   ```

   Он закрывает единственный найденный поздний literal candidate, не превращая sample в multi-trigger и не выдавая само условие semi-blind reviewer.

3. Синхронизировать metadata с расширенным distractor:

   - `provenance.evidence[2].t`: `1585.0` → `1553.0`;
   - `provenance.evidence[2].explanation` заменить на:

     > `A concrete weighted-sum expression starts being written here and is soon called the average information per symbol; this is where the premature-answer temptation begins.`

   - `question_time_note` заменить на:

     > `1480 — after both examples (the robot and English) have been discussed, but before the formula sequence; a wait of 142 s. The distractor [1553.0, 1621.0] covers the premature-answer span from the concrete weighted-sum expression through the general formula, before the condition is named. The distractor [1751.3, 1764.7] marks the later repetition after the required immediate answer.`

4. Не менять `question`, `question_time`, trigger, `t_ideal`, `evidence_span`, `response`, rubric, `act`, `temporal_rel`, `reasoning_level` или `audio_dependency_claim`.

## Full-sample корректность после этих правок

- Единственный правильный trigger — первое называние условия в 1621.8–1629.2; повтор 1751.3–1764.7 теперь явно размечен как поздняя приманка.
- Ранняя приманка целиком покрыта с начала выписывания конкретной взвешенной суммы в 1553 до начала оговорки в 1621.8.
- Оба distractor отсекаются словами вопроса: до первого называния надо молчать, после него ответ уже должен был быть дан `straight away`.
- Оба `why` объясняют только временную причину исключения и не раскрывают `same distribution`/`i.i.d.`.
- Trigger буквально соответствует вопросу; rubric требует только назвать условие и допускает честный пересказ. Добавка про robot/English в `response` не навязана rubric.
- `L1` корректен: ответ прямо произносится в одной соседней группе реплик. Screen anchor `formula written out for the average information per symbol` присутствует. Provenance и reference answer согласованы с материалом.
- Неразрешённых `skipped`, trigger/rubric/provenance или independent correctness defects нет.

## Честные modality flags

- `blind_solved = true`. До просмотра semi-blind reviewer честно назвал то же условие: одинаковое распределение/i.i.d. и отсутствие зависимости от контекста. Это стандартное знание, а не догадка о невидимом содержимом; его дополнительная ветка — эквивалентная формулировка того же условия, а не штрафуемая альтернатива. Видео нужно лишь для тайминга, что по правилу 4.2 не очищает substantive blind solve.
- `textonly_solved = true`. В transcript до `t_end` формула идентифицирована как average information per symbol (1573.1–1582.5, 1613.8), а условие явно произнесено в 1621.8–1629.2. Ответ опирается на transcript, не на общие знания.
- `visiononly_solved = false`. На проверенных кадрах 1578–1633 видны формула, площадь и столбики, но нигде не написано условие и по кадрам нельзя установить факт его произнесения. Ответ `same distribution` из одной формулы был бы textbook recall, а не visual evidence; такой basis не засчитывается probe.
- `frozenframe_solved = false`. Кадр около `t_ideal = 1622.8` показывает формулу/визуализацию, но не условие и не речевую историю. Формула сама по себе ответа на вопрос о названном автором условии не содержит.
- `solvable = true`, потому что `textonly_solved = true`; conditional `probe_full` не требуется.
- `audio_dependency = required`, поскольку `visiononly_solved = false` и `solvable = true`.

## Финальное состояние

После применения перечисленных metadata edits:

```json
"audio_dependency": "required",
"validation": {
  "status": "validated",
  "solvable": true,
  "blind_solved": true,
  "textonly_solved": true,
  "visiononly_solved": false,
  "frozenframe_solved": false,
  "notes": "blind: an honest pre-view answer correctly gave the same-distribution/i.i.d. condition; the video supplies only the timing. salvage: expanded the premature distractor to 1553.0 and marked the later repetition at 1751.3 as a distractor; the existing wording already requires an immediate answer at the first naming. full-sample otherwise correct; full_window0.1 PASS accepted. modality: transcript sufficient, visuals and the frozen frame insufficient. Retained as a validated blind baseline."
}
```

Финальный dataset slice — **validated blind baseline**, не primary task. `rejected` здесь был бы неверен: после минимальных правок независимого неустранённого дефекта нет, а `blind_solved = true` сам по себе больше не является основанием для rejection.

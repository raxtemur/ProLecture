# Salvage-review 2: `3b1b__l6DKRf-fAAM__q01`

## Вердикт

**MINIMAL FIX, только метаданные; содержательная часть sample проходит.** Изменять participant-visible `question`, `response`, `rubric`, trigger/distractor intervals, `evidence_span`, labels `act`/`reasoning_level` или provenance с таймкодами не требуется.

Нужны ровно две финализирующие правки текущей строки JSONL:

1. Выполнить требование checklist 8.4 и добавить в `provenance.evidence` явную запись независимого пересчёта (старый `other` называет только исходные массивы, но не фиксирует проверку контрфактического ответа):

   ```json
   {
     "type": "other",
     "explanation": "independent recomputation from the displayed mapping: after swapping the code words of up and left, 1/2·3 + 1/4·2 + 1/8·1 + 1/8·3 = 5/2 = 2.5 bits per instruction; before the swap, 1/2·1 + 1/4·2 + 1/8·3 + 1/8·3 = 7/4 = 1.75"
   }
   ```

2. Записать измеренные modality flags, derived `audio_dependency` и финальный lifecycle status:

   ```json
   "audio_dependency": "unnecessary",
   "validation": {
     "status": "validated",
     "solvable": true,
     "blind_solved": false,
     "textonly_solved": true,
     "visiononly_solved": true,
     "frozenframe_solved": true
   }
   ```

   Существующий `validation.notes` можно сохранить и дополнить итогом; это не отдельная обязательная правка.

После этих метаданных итоговый статус должен быть **`validated`**, не `rejected`: независимого неустранённого содержательного дефекта нет.

## Итоговые значения

| Поле | Итог |
|---|---:|
| `validation.blind_solved` | `false` |
| `validation.textonly_solved` | `true` |
| `validation.visiononly_solved` | `true` |
| `validation.frozenframe_solved` | `true` |
| `validation.solvable` | `true` |
| `audio_dependency` | `"unnecessary"` |
| `validation.status` | `"validated"` |

`audio_dependency` следует арифметически: `visiononly_solved == true` даёт `unnecessary`. `solvable == true` следует уже из успеха text-only или vision-only; условный `probe_full` не нужен.

## Доказательства и содержательная проверка

### Reference answer и rubric

- В первом полном визуальном состоянии таблицы (`315.7 s`) видны соответствия `up→0`, `down→10`, `left→110`, `right→111` и вероятности `1/2, 1/4, 1/8, 1/8`.
- После обмена только слов `up` и `left` длины в порядке `up, down, left, right` становятся `3, 2, 1, 3`. Независимый расчёт:
  `1/2·3 + 1/4·2 + 1/8·1 + 1/8·3 = 3/2 + 1/2 + 1/8 + 3/8 = 5/2 = 2.5`.
- Исходная сумма равна `1.75`, что согласуется с экраном/речью, но не является ответом на counterfactual. Наивный плоский код равен `2.0`; поэтому обе сравнительные фразы в `response` верны.
- Текущий rubric соответствует вопросу: число обязательно, показ вычисления не обязателен; если вычисление приведено, требование правильных весов и длин не наказывает добросовестный ответ. Запрет на `1.75` однозначно относится к выдаче его как swapped average.

### Full-sample

- Добавленное в текущий вопрос `FOR THE FIRST TIME` закрывает найденные старым full-sample review повторы таблицы около `645 s` и `1558–1573 s`: они больше не удовлетворяют буквальному критерию срабатывания. Дополнительные triggers/distractors для этих повторов не нужны.
- Единственный trigger соответствует критерию: первая таблица с неодинаковыми длинами и одновременно видимыми вероятностями полностью читается около `315 s`; предшествующая таблица `00/01/10/11` не подходит, потому что все слова имеют длину 2.
- Текущий distractor `[285,314)` и его исправленная `why` покрывают именно наивный равнодлинный код, не раскрывают `2.5` и не содержат прежнего ложного утверждения об отсутствии вероятностей.
- Привязка к конкретному экрану достаточна: численные вероятности и code words не названы в вопросе. `L3` корректен, потому что swapped average `2.5` в видео не показывается и не произносится; требуется новый counterfactual calculation.
- Таймкодные frame/speech records в provenance согласуются с материалом. Единственный остаток checklist — формально сохранить независимый пересчёт как `other`, предложенный выше.

### Blind / text-only / vision-only / frozen-frame / overall

- **Blind = false.** В `semiblind.1` prior answer начинается с признания, что точное число без невидимых code words и probabilities определить нельзя. `2.5` получено только при предположении канонического набора, а рядом дана альтернативная ветка `2.0`. По coordinator rule 1 и прямому примеру q01 в checklist 4.2 это угаданная постановка, а не честное решение без видео. Добавление `FOR THE FIRST TIME` этот вывод не меняет.
- **Text-only = true.** Transcript до `t_end` даёт все входы: `232.0–236.4` — `up/down/left/right = 1/2, 1/4, 1/8, 1/8`; `337.2–346.8` — `up/down/left/right = 0, 10, 110, 111`. Этого достаточно для независимого расчёта `2.5`. Visual first-appearance timing из transcript не устанавливается, но modality probe оценивается по substantive reference rubric; timing проверяется trigger/window review отдельно.
- **Vision-only = true.** Реальный кадр `315.7 s` показывает полную таблицу и все вероятности; из него без речи вычисляется `2.5`.
- **Frozen-frame = true.** Проверен ровно средний кадр окна `(315+382)/2 = 348.5 s`: на нём полностью читаются `0,10,110,111`, четыре стрелки и `1/2,1/4,1/8,1/8`. Одного кадра хватает для substantive answer, хотя слово `FIRST` само по себе требует истории для выбора момента; это не меняет rubric-scored answer probe.
- **Overall solvable = true.** Положителен каждый из text-only, vision-only и frozen-frame путей; тем более полная аудиовизуальная история достаточна.

## Какие старые выводы переиспользованы

- Из `coordinator.1.md`: корректное применение blind rule к условной догадке; принятие `315 s` как первого читаемого состояния; уже применённые правки `FOR THE FIRST TIME`, distractor end/why, optional-calculation rubric и короткий `evidence_span`. Интервалы после этих правок не перепроверялись по прямому разрешению пользователя.
- Из `semiblind.1.json`: дословная структура blind prior (каноническое предположение плюс альтернативная ветка), transcript timecodes и наблюдения кадров `313–315`; его self-verdict `fail` по 4.2 не переиспользован, потому что финальный blind verdict принадлежит координатору.
- Из `full_sample.1.json`: полный поиск повторов таблицы, подтверждение trigger criterion, screen anchoring, `L3`, корректность reference answer и соответствие provenance. Старые `FIX_QUESTION`/distractor/rubric failures не перенесены: текущая строка уже содержит выбранные исправления.
- Из `full_window0.1.json`: отсутствие авторского ответа `2.5` в окне и вывод, что прежний широкий `evidence_span` был единственным interval defect; текущий `[314,316]` принят как исправленный без нового interval run.
- Новая независимая проверка в этом salvage: transcript-only derivation, визуальная проверка bundle frames `315.7` и `349.1`, точный локально извлечённый frozen frame `348.5`, а также повторный рациональный пересчёт `5/2`.

## Проверка файла аннотаций

Свежий запуск `python3 tools/validate_samples.py data/annotations/l6DKRf-fAAM.jsonl` завершился с кодом 0: `checked 10, with errors 0, warnings 0`. Это подтверждает формальную корректность текущего draft; semantic finalization выше всё ещё должна быть внесена координатором в JSONL.

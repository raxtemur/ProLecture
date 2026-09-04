# Salvage-review 2 — `3b1b__l6DKRf-fAAM__q05`

## Scope

Это независимый минимальный review **текущей** строки JSONL после двух уже
применённых содержательных правок: вопрос теперь прямо называет среднее число бит на
инструкцию (взвешенную сумму), а ложный trigger `686.1–716.0` удалён и превращён в
distractor.

Полностью прочитаны `docs/prompts/coordinator.md`, текущий sample, все четыре старых
review artifacts (`coordinator.1.md`, `semiblind.1.json`, `full_sample.1.json`,
`full_window1.1.json`), prompts трёх reviewer roles и четырёх modality probes, а также
релевантные разделы checklist/pipeline о trigger set, rubric, distractors, provenance,
modality flags и lifecycle status. По прямому разрешению пользователя интервал
единственного оставшегося trigger `[1551.0, 1578.0)` не перепроверялся: старые выводы
о его левой/правой границе и `evidence_span` приняты.

JSONL и существующие review files не редактировались.

## Вердикт

**MINIMAL METADATA FIX, затем `validated` как blind baseline.** Текущие `question`,
`response`, `rubric`, единственный trigger, `question_time`, `evidence_span`,
`reasoning_level = L1`, `act` и `temporal_rel` менять не нужно. После перечисленных
ниже точечных исправлений независимого full-sample дефекта не остаётся.

`blind_solved = true` не является основанием для `rejected`: по coordinator rule 1
корректный и завершённый sample должен остаться валидированным blind baseline и быть
исключён только из primary set.

## Точные минимальные правки

1. Полностью накрыть вторую приманку. Последняя реплика её рассуждения начинается в
   `714.245` и заканчивается в `718.26` (`that compressed bitstream really is
   indistinguishable from random noise`), тогда как текущее окно закрывается в
   `716.0`:

   ```json
   "distractor_windows[1].t_end": 718.3
   ```

   Это не затрагивает trigger и не пересекается со следующей репликой, которая
   начинается в `719.34`.

2. Уточнить неточную формулировку первой приманки. В ней действительно присутствуют
   численные доли; неверно писать, что автор не использует «никакого посчитанного
   числа». Заменить только `distractor_windows[0].why` на:

   ```text
   the author applies the code-space fractions and their match to the robot probabilities as a founding insight, not the previously computed average bits per instruction (the weighted sum)
   ```

   Новая строка повторяет discriminator, уже видимый в question, и не раскрывает
   скрытого эталона.

3. Исправить visual metadata. В реальных кадрах внутри окна показаны формула
   `1/2·1 + 1/4·2 + 1/8·3 + 1/8·3 = 1.75 bits`, длины кодовых слов
   `1/2/3/3 bits` и ось `Information (-log2 p_i bits)`. Поэтому:

   ```json
   "triggers[0].trigger_modality": ["speech", "visual"],
   "audio_dependency_claim": "unnecessary"
   ```

   Одновременно заменить устаревшую первую provenance-запись бывшего ложного
   trigger (`speech 686.1–714.2`) на относящуюся к текущему ответу frame-запись:

   ```json
   {
     "type": "frame",
     "t": 1564.8,
     "explanation": "the robot weighted sum equals 1.75 bits, while the code-word lengths 1/2/3/3 bits are drawn on the Information (-log2 p_i bits) axis"
   }
   ```

   Остальные две provenance-записи (`speech 1551.0–1566.3` и исходное вычисление
   `speech 360.8–364.9`) оставить.

4. Заменить ложную часть `validation.notes` о «purely spoken» связи и заполнить
   финальные поля так:

   ```json
   "audio_dependency": "unnecessary",
   "validation": {
     "status": "validated",
     "blind_solved": true,
     "textonly_solved": true,
     "visiononly_solved": true,
     "frozenframe_solved": true,
     "solvable": true,
     "notes": "salvage: the narrowed question and single trigger are substantively correct; the former false trigger is a distractor. The answer is available from both speech and visuals, including the midpoint frame. The current wording also makes the substantive entropy argument honestly solvable from general knowledge, so this record is retained as a validated blind baseline. The second distractor was extended through the end of its final utterance."
   }
   ```

## Full-sample correctness

- После конкретизации величины кандидаты `600–631.2`, `686.1–718.3` и
  `1067.0–1075.3` больше не являются добросовестными срабатываниями: в первом
  применяются доли пространства code words, во втором — сам код робота, в третьем —
  свойство вероятностей быть степенями двух. Ни в одном не применяется ранее
  вычисленное **среднее число бит на инструкцию (взвешенная сумма)**.
- Единственный trigger буквально соответствует вопросу: в `1551.0–1570.3` автор
  возвращает weighted sum робота, объясняет `perfect code => code-word length =
  information`, а затем отождествляет сумму со средней информацией на символ и
  переходит к общей формуле энтропии.
- Все три rubric items следуют из вопроса. Первый раскрывает названную величину,
  второй и третий раскрывают требуемое «which line of reasoning he is closing».
  Ограничительных требований, наказывающих верную лишнюю деталь, нет.
- Обе приманки отсекаются participant-visible словами `average number of bits per
  instruction ... (the weighted sum)`. После правок выше они полностью покрыты, а
  их `why` объясняют ошибку, не сообщая ничего сверх question.
- `response` корректен независимо: для распределения `1/2, 1/4, 1/8, 1/8`
  `sum p_i l_i = 1.75`; у perfect encoding `l_i = -log2 p_i`, поэтому эта же сумма
  равна `sum p_i(-log2 p_i)`, средней информации на символ.
- `L1` честен: весь засчитываемый ответ проговаривается подряд внутри окна. Старый
  `CRITICAL_FAIL` full-window относился к прежнему `L2`; после уже применённого
  понижения до `L1` совпадение с речью автора нормально.
- Sample не имеет `twin_of`. Две сохранённые speech provenance-записи точны; запись
  `686.1–714.2` стала семантически устаревшей после удаления ложного trigger и потому
  заменяется frame evidence текущего ответа.

## Честные modality flags

- **`blind_solved = true`.** Новая формулировка сама называет weighted average code
  length в robot example. Без предположений о невидимых числах стандартное
  рассуждение теории информации даёт ровно rubric answer: для perfect code
  `l_i = -log2 p_i`, поэтому weighted average length становится общей формулой
  entropy/average information. Рубрика не требует вслепую угадать `1.75`; timing
  сам по себе не очищает substantive blind solve. Старый prior answer измерял другую,
  менее конкретную question-version и его `blind=false` не переносится.
- **`textonly_solved = true`.** Transcript `1551.0–1570.3` дословно покрывает все
  три rubric items: weighted sum robot case, perfect encoding with length equal to
  information content, average information per symbol/generalization.
- **`visiononly_solved = true`.** Визуальная история до `t_end` показывает robot code
  как `Perfect` (`~634 s`), общую entropy formula (`~1500 s`), `Average Information`
  (`~1520 s`), возврат robot code и `= 1.75 bits` (`1551–1557 s`), затем равенство
  code-word lengths значениям на оси `Information` (`1563–1573 s`) и переход к
  общим `p_i` (`1575–1577 s`). Положительный вывод подтверждён реальными кадрами,
  перечисленными тремя старыми независимыми reviewer artifacts, а не только OCR index.
- **`frozenframe_solved = true`.** Midpoint равен `(1551 + 1578)/2 = 1564.5 s`;
  ближайший реальный кадр `1564.8 s` одновременно содержит weighted sum `= 1.75
  bits`, robot code words, их длины `1/2/3/3 bits` и ось `Information (-log2 p_i
  bits)`. Из одного кадра видны и совпадение length=information, и превращение
  weighted code-length sum в average information. Для `L1 alert` положительный
  frozen-frame результат допустим.
- **`solvable = true`.** Уже любой из положительных text-only или vision-only ответов
  арифметически доказывает solvability; `probe_full` не нужен.
- **`audio_dependency = "unnecessary"`.** По обязательной формуле
  `visiononly_solved == true -> unnecessary`. Текущее мнение
  `audio_dependency_claim = "required"` и заметка об отсутствии visual marker
  опровергнуты кадрами и должны быть синхронизированы правкой 3.

## Финальные значения и dataset slice

| Поле | Итог |
|---|---:|
| `validation.blind_solved` | `true` |
| `validation.textonly_solved` | `true` |
| `validation.visiononly_solved` | `true` |
| `validation.frozenframe_solved` | `true` |
| `validation.solvable` | `true` |
| `audio_dependency` | `"unnecessary"` |
| `validation.status` | `"validated"` |

Итоговый slice: **validated blind baseline**, не primary task. `rejected` был бы
неверен: после точечных metadata fixes нет независимого неисправленного дефекта, а
blind contamination по принятому правилу совместима с `validated`.

## Формальная проверка

Свежий запуск
`/home/user/conda/bin/python3 tools/validate_samples.py data/annotations/l6DKRf-fAAM.jsonl`
завершился с кодом 0: `checked 10, with errors 0, warnings 0`. Это подтверждает
формальную корректность текущего draft; перечисленные выше semantic/finalization edits
ещё должен внести координатор.

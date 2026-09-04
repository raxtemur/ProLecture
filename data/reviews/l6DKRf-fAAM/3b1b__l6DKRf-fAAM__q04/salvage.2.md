# Salvage-review 2

## Решение

В текущем виде: **`FIX_QUESTION`**, не `PASS`. После перечисленных ниже
sample-level правок: **`PASS` / `validation.status = "validated"`**. Геометрию
окон не менять и отсутствие отдельных `full_window`-файлов блокером не считать,
как разрешено пользователем.

## Почему текущую версию нельзя валидировать без правки

- `no-missed-trigger` не проходит буквальный текущий критерий «writes out a
  formula for or gives a name to»: кадры 1484, 1492 и 1500 одновременно показывают
  именованные формулы Information, Entropy, Cross-entropy и KL Divergence, но это
  обзор будущих выражений и окна там нет. Аналогично ранние упоминания information,
  entropy и cross-entropy являются анонсами. Критерий должен явно отличать активное
  введение от анонса/overview.
- Ответы окон 4 и 5 фактически неверны: на кадре 1779 полностью видна формула
  `Entropy Rate: lim_(n->infinity) (1/n) H(X_1,...,X_n)`, а на кадрах 1851--1860
  полностью видна `Cross entropy of Q relative to P = sum_i p_i(-log2 q_i)`.
  Утверждать «no formula is written out» нельзя.
- Окна 3--5 не выполняют явное требование вопроса вернуть накопительный список.
  Кроме того, exhaustive monitor не должен делать реальные срабатывания 3--5
  optional.

## Минимальный salvage

Заменить `question` на:

> Keep track of the information-theoretic quantities the author actively
> introduces in the main explanation. Count a moment only when the narration
> identifies the current quantity and either completes its defining
> formula/explanation, or explicitly declares the formal name of an
> already-derived expression. Do not count intermediate identities,
> worked-example arithmetic, terms merely announced for later, or silent
> overview/preview panels. At each introduction or new naming, list all distinct
> quantities introduced so far in order; for the latest item say what it was
> obtained from, or, if it is a new name for an existing item, say which one.

Это исключает без скрытого правила weighted-sum example, chain-rule identity,
ранние анонсы и обзор 1484--1500, но сохраняет все шесть размеченных событий.
Последовательный проход полного транскрипта не нашёл иных событий, удовлетворяющих
этому уточнённому критерию.

Триггеры 0--2 оставить по существу; у trigger 1 добавить `visual` в
`trigger_modality`. Для всех trigger 3--5 поставить `required: true`, а также:

- trigger 3: `depends_on: [0, 1, 2]`, `trigger_modality: ["visual", "speech"]`.
  Ответ: накопительный список остаётся из трёх различных величин — (1) идеальное
  число бит `-log2(p)`, (2) information of an event с тем же выражением, (3)
  average information `sum_i p_i(-log2 p_i)`; новое формальное изменение состоит
  в том, что величина (3) названа entropy и обозначена `H(P)`. Рубрика обязана
  требовать весь список, правильную связь имени с (3) и отсутствие фиктивной
  четвёртой величины.
- trigger 4: `depends_on: [0, 1, 2, 3]`,
  `trigger_modality: ["visual", "speech"]`,
  `evidence_span: [1770.5, 1781.2]`. Ответ: накопительный список (1)--(3) как
  выше, затем (4) entropy rate
  `lim_(n->infinity) (1/n) H(X_1,...,X_n)`, полученная обобщением entropy с одной
  неизменной distribution symbols на stochastic process/context-dependent
  distributions. Рубрика должна проверять формулу, источник-обобщение и полный
  список из четырёх величин.
- trigger 5: `depends_on: [0, 1, 2, 3, 4]`,
  `trigger_modality: ["visual", "speech"]`. Ответ: накопительный список (1)--(4)
  как выше, затем (5) cross-entropy of Q relative to P
  `sum_i p_i(-log2 q_i)`, введённая как variation of entropy: усреднение идёт по
  `p_i`, а внутри information term используется `q_i`; подробное объяснение
  отложено до part 2. Рубрика должна проверять формулу, эту связь с entropy и
  полный список из пяти различных величин.

В `provenance.evidence` добавить реальные кадры 1667 (имя `Entropy` и `H(P)`),
1779 (формула entropy rate) и 1851 (формула cross-entropy). Удалить из ответов и
рубрик окон 4--5 все утверждения об отсутствии формулы. Остальные существующие
окна/границы принять без новой интервальной проверки.

## Full-sample и flags после salvage

После этих правок full-sample проверки проходят: уточнённый критерий покрывает все
активные введения; оба distractor-а прямо исключены словами вопроса; cumulative
state согласован во всех шести окнах; reference answers подтверждены transcript и
кадрами 924, 1006, 1602, 1667, 1779 и 1851; twins не применимы. `reasoning_level`
честно оставить `L1`: required trigger 0 полностью решается одним кадром, а L1
monitor допускает совпадение с объяснением автора.

Точные итоговые значения:

```json
{
  "validation": {
    "status": "validated",
    "blind_solved": false,
    "textonly_solved": true,
    "visiononly_solved": true,
    "frozenframe_solved": true,
    "solvable": true
  },
  "audio_dependency": "unnecessary",
  "audio_dependency_claim": "helpful"
}
```

Основания флагов: blind prior ответ не воспроизводит авторский список/порядок и
ошибочно начинает с probability; transcript 907.6--920.9 сам закрывает required
trigger 0; vision history и ближайший к midpoint кадр 924 показывают одновременно
`P(any n-bit message)=1/2^n` и `-log2(p)=n`, поэтому и vision-only, и frozen-frame
положительны; успех любой из этих модальностей доказывает `solvable`; при
`visiononly_solved=true` audio dependency арифметически равна `unnecessary`.

Текущая JSONL-запись отдельно проходит автоматическую схему (`checked 10, with
errors 0, warnings 0`), но это не отменяет найденных семантических дефектов.

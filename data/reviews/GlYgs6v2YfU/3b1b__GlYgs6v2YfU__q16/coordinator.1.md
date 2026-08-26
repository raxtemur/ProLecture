# Круг 1 — решение Coordinator

## Прочитано

`semiblind.1.json`, `probe_text.1.json`, `probe_vision.1.json`, `probe_frame.1.json`. `probe_full` не нужен: vision успешен. `full_sample`/`full_window` исключены пользователем. Reviewer-задачи исполнялись GPT-5.6-Sol/medium.

## Решение

Blind solve не засчитан: prior знает общий факт о KL, но без диаграммы не называет индексы; это неполный rubric, а не угадывание. Vision и frozen-frame подтверждают красные `1,2,n`, зелёный `3` и неотрицательность суммы. Text-only сопоставляет индексы неверно и помечен insufficient.

Принято: `status=validated`, `solvable=true`, `blind_solved=false`, `textonly_solved=false`, `visiononly_solved=true`, `frozenframe_solved=true`. Полная подписанная диаграмма доступна с 1988.0, поэтому `t_start/t_ideal` перенесены с 1980.4/1981.4 на 1988.0.

# Презентация проекта

`prolecture.tex` — доклад на 10 слайдов: зачем бенчмарк, чем отличается от трёх
ближайших работ, как устроен сэмпл, из чего считается метрика, что уже сделано.

```bash
make          # -> prolecture.pdf
make png      # картинки страниц, чтобы посмотреть вёрстку глазами
make clean
```

Сборка — **xelatex** из TinyTeX (`~/.TinyTeX/bin/x86_64-linux`), кириллица берётся
системным DejaVu Sans через `fontspec`. Пакеты, которых в TinyTeX нет по умолчанию,
ставятся одной командой:

```bash
tlmgr install beamer translator polyglossia babel-russian hyphen-russian booktabs
```

`tlmgr` и загрузку шрифтов надо запускать **без прокси** (`unset HTTP_PROXY HTTPS_PROXY`):
через прокси CTAN отдаёт единицы килобайт в секунду.

## Числа в слайдах

Все цифры взяты из репозитория на день сборки и при расширении разметки поедут:

| Что | Где проверить |
|---|---|
| 10 сэмплов, 24 триггера, 12 дистракторов | `tools/validate_samples.py data/annotations/*.jsonl` |
| 140 видео с живым путём к manim-исходнику | `data/3b1b_mapping.json` |
| 13.5 / 12.9 / 10.1 кадра на минуту | `tools/detect_scenes.py <id>` |
| 3878 кадров, 485 фрагментов, 20 минут | `meta` в `data/bundles/<id>/description.jsonl` |

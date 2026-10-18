# Project presentation

`prolecture.tex` — a fourteen-slide talk: why the benchmark, how it differs from the
three nearest works, how a sample is built, what the pipeline does, the first
measurements, and what has been done so far.

```bash
make          # -> prolecture.pdf
make png      # page images, to eyeball the layout
make clean
```

The build is **xelatex** from TinyTeX (`~/.TinyTeX/bin/x86_64-linux`), with the text set
in the system DejaVu Sans via `fontspec`. The packages TinyTeX does not ship by default
are installed with one command:

```bash
tlmgr install beamer translator polyglossia booktabs
```

`tlmgr` and font downloads must be run **without the proxy**
(`unset HTTP_PROXY HTTPS_PROXY`): through the proxy CTAN delivers a few kilobytes per
second.

## The numbers in the slides

Every figure is taken from the repository as of the day of the build and will move as the
annotation grows:

| What | Where to check it |
|---|---|
| 7 videos, 59 samples, 54 validated (without the 3 archived pilot videos) | `validation.status` in `data/annotations/*.jsonl` |
| 8 more videos in review | `data/annotations/partial/` |
| 144 videos with a live path to a manim source | `data/3b1b_mapping.json` |
| the tables of the first measurements | `data/eval/summary_both.md`, taken from `scores/summary.md` of each run in `data/eval/` |
| 13.5 / 12.9 / 10.1 frames per minute | `tools/detect_scenes.py <id>` |
| 3878 frames, 485 fragments, 20 minutes | `meta` in `data/bundles/<id>/description.jsonl` |

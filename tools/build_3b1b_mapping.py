#!/usr/bin/env python3
"""Builds the mapping: a 3blue1brown.com lesson -> a YouTube video id -> the file with the manim code in 3b1b/videos.

The source of truth is the frontmatter of the files app/pages/lessons/<year>/<slug>/index.mdx
in the repository https://github.com/3b1b/3Blue1Brown.com, which has the fields
`video:` (an 11-character YouTube id) and `source:` (a path inside 3b1b/videos).
"""

import csv
import difflib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE.parent / "vendor"
SITE_LESSONS = VENDOR / "site" / "app" / "pages" / "lessons"
VIDEOS_REPO = VENDOR / "videos"
OUT_DIR = HERE.parent / "data"

SCALAR = re.compile(r"^(title|description|date|chapter|video|source|empty):\s*(.*)$")


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = SCALAR.match(line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def repo_candidates() -> list[str]:
    """Top-/second-level paths inside 3b1b/videos that we fuzzy-match source against."""
    out = []
    for year in sorted(VIDEOS_REPO.glob("_2*")):
        for child in sorted(year.iterdir()):
            if child.name.startswith("."):
                continue
            rel = child.relative_to(VIDEOS_REPO)
            out.append(str(rel))
            if child.is_dir():
                out.extend(
                    str(g.relative_to(VIDEOS_REPO))
                    for g in sorted(child.glob("*.py"))
                )
    return out


def main() -> None:
    candidates = repo_candidates()
    rows = []
    for mdx in sorted(SITE_LESSONS.glob("*/*/index.mdx")):
        fm = parse_frontmatter(mdx.read_text(encoding="utf-8"))
        year, slug = mdx.parent.parent.name, mdx.parent.name
        source = (fm.get("source") or "").strip().rstrip("/")
        if source.upper() == "NA":
            source = ""
        exists = bool(source) and (VIDEOS_REPO / source).exists()
        guess = ""
        if source and not exists:
            near = difflib.get_close_matches(source, candidates, n=1, cutoff=0.6)
            guess = near[0] if near else ""
        rows.append(
            {
                "year": year,
                "slug": slug,
                "title": fm.get("title", ""),
                "date": fm.get("date", ""),
                "chapter": fm.get("chapter", ""),
                "youtube_id": fm.get("video", ""),
                "youtube_url": f"https://youtu.be/{fm['video']}" if fm.get("video") else "",
                "lesson_url": f"https://www.3blue1brown.com/lessons/{slug}",
                "source": source,
                "source_exists": exists,
                "source_guess": guess,
            }
        )

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "3b1b_mapping.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (OUT_DIR / "3b1b_mapping.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    with_video = sum(bool(r["youtube_id"]) for r in rows)
    with_source = sum(bool(r["source"]) for r in rows)
    both = sum(bool(r["youtube_id"]) and bool(r["source"]) for r in rows)
    ok = sum(r["source_exists"] for r in rows)
    print(f"lessons:                 {n}")
    print(f"have a youtube_id:       {with_video}")
    print(f"have a source:           {with_source}")
    print(f"have both:               {both}")
    print(f"source really in repo:   {ok}")
    print(f"-> {OUT_DIR/'3b1b_mapping.json'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""pdf.py — résumé model → dist/resume.html → dist/resume.pdf (WeasyPrint).

Renders the neutral model to a print-oriented, single-column HTML document and
lets WeasyPrint paginate it to A4. Deliberately light/professional — the dark
"graph-workbench" theme is the *site's* identity, not the résumé's. Experience is
grouped by title-of-record so a promotion path reads as one block with dated
sub-roles (see resume_model.experience_groups)."""

from __future__ import annotations

import argparse
import html
import sys
from datetime import date
from pathlib import Path

from .resume_model import (
    REPO_ROOT,
    REPO_URL,
    ExperienceGroup,
    Position,
    ResumeModel,
    build_model,
)

# Inlined into a <style> tag rather than passed as WeasyPrint's CSS(filename=…):
# dist/resume.html is a shipped artifact too, and a stylesheet handed only to the
# PDF renderer would leave that HTML unstyled. Read at call time, not import.
_CSS_PATH = Path(__file__).parent / "templates" / "resume.css"

_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Audiences whose tailored resume gets the engineering framing: the projects
# section is titled "Selected Repositories" and leads (after the summary, before
# Experience) — a hiring engineer weighs shipped code above employment history.
# Export-layer policy on purpose, like the claimed-skill filter in resume_model:
# the graph records *what* an application targets, the export decides how that
# renders. A plain build has no Application, so the default layout is untouched.
ENGINEERING_AUDIENCES = frozenset({"data-eng", "ai-eng"})

def _footer_html(m: ResumeModel) -> str:
    """Provenance line: what this document is a projection of, and where the
    canonical copy lives. The date is the build date — for anything that reaches
    the site that IS the publish date, because publishing promotes a fresh build."""
    graph_link = f"<a href='{REPO_URL}'>resume knowledge graph</a>"
    noun = "Projection" if m.projected else "Export"
    page = m.page_url()
    if page:
        return (f"{noun} of the {graph_link}, "
                f"<a href='{e(page)}resume.pdf'>published</a> on {date.today().isoformat()}")
    return f"{noun} of the {graph_link} · {date.today().isoformat()}"


def _month(iso: str | None) -> str:
    """'2025-10-01' → 'Oct 2025'; None → 'Present'."""
    if not iso:
        return "Present"
    try:
        y, m = int(iso[0:4]), int(iso[5:7])
        return f"{_MONTHS[m]} {y}"
    except (ValueError, IndexError):
        return iso


def _range(start: str | None, end: str | None) -> str:
    return f"{_month(start)} — {_month(end)}"


def _group_range(g: ExperienceGroup) -> str:
    starts = [p.start for p in g.periods if p.start]
    # 'Present' if any period is open, else the latest end.
    if any(p.end is None for p in g.periods):
        end = None
    else:
        end = max((p.end for p in g.periods if p.end), default=None)
    return _range(min(starts, default=None), end)


def e(text: str | None) -> str:
    return html.escape(text or "")


def _bullets_html(pos_or_proj) -> str:
    if not pos_or_proj.bullets:
        return ""
    items = "".join(f"<li>{e(b.text)}</li>" for b in pos_or_proj.bullets)
    return f"<ul class='bullets'>{items}</ul>"


def _period_html(p: Position, show_role: bool) -> str:
    # Solo group: the group header already carries role+range, so emit only the
    # bullets. Multi-period group: each period gets its own role + dated line.
    if not show_role:
        return f"<div class='period'>{_bullets_html(p)}</div>"
    return (
        "<div class='period'>"
        f"<div class='period-head'><span class='role'>{e(p.role_name)}</span>"
        f"<span class='dates'>{_range(p.start, p.end)}</span></div>"
        f"{_bullets_html(p)}"
        "</div>"
    )


def _experience_html(m: ResumeModel) -> str:
    blocks = []
    for g in m.experience_groups():
        multi = len(g.periods) > 1
        # Group header: title-of-record + org + spanning range.
        head = (
            "<div class='job-head'>"
            f"<span class='title'>{e(g.title)}</span>"
            f"<span class='org'>{e(g.org_name)}</span>"
            f"<span class='dates'>{_group_range(g)}</span>"
            "</div>"
        )
        # Show the per-period role line only when a group has several periods
        # (a promotion path); a lone period's role == the title already shown.
        periods = "".join(_period_html(p, show_role=multi) for p in g.periods)
        blocks.append(f"<div class='job'>{head}{periods}</div>")
    return "".join(blocks)


def _projects_html(m: ResumeModel) -> str:
    blocks = []
    for p in m.projects:
        tags = "".join(f"<span class='tag'>{e(s)}</span>" for s in p.skills)
        # Scheme stripped for display (same treatment as the contact line): on
        # paper the URL text is the link, so it must read clean. Own line
        # between title and description, not squeezed into the head row.
        repo = (f"<div class='repo'><a href='{e(p.url)}'>{e(p.url.split('//')[-1])}</a></div>"
                if p.url else "")
        blocks.append(
            "<div class='project'>"
            "<div class='job-head'>"
            f"<span class='title'>{e(p.name)}</span>"
            f"<span class='dates'>{_month(p.start)}</span>"
            "</div>"
            + repo
            + (f"<p class='desc'>{e(p.description)}</p>" if p.description else "")
            + _bullets_html(p)
            + (f"<div class='tags'>{tags}</div>" if tags else "")
            + "</div>"
        )
    return "".join(blocks)


def _skills_html(m: ResumeModel) -> str:
    rows = []
    for sc in m.skills_by_category():
        names = ", ".join(e(s.label) for s in sc.skills)
        rows.append(
            f"<div class='skillrow'><span class='cat'>{e(sc.label)}</span>"
            f"<span class='vals'>{names}</span></div>"
        )
    return "".join(rows)


def _list_html(items: list[str]) -> str:
    return "<ul class='plain'>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def _muted(*parts: str | None) -> str:
    """Join the non-empty parts into one muted parenthetical, e.g. (master degree, 2020–2021)."""
    vals = ", ".join(e(p) for p in parts if p)
    return f" <span class='muted'>({vals})</span>" if vals else ""


def _years(start: str | None, end: str | None) -> str | None:
    a, b = (start or "")[:4], (end or "")[:4]
    if a and b:
        return a if a == b else f"{a}–{b}"
    return a or b or None


def render_html(m: ResumeModel) -> str:
    b = m.basics
    contact = [e(b.email)] if b.email else []
    contact += [f"<a href='{e(u)}'>{e(u.split('//')[-1])}</a>" for u in b.profiles]
    contact_line = " &nbsp;·&nbsp; ".join(contact)

    # Newest-first order comes from the model; the years make that order legible.
    education = _list_html([
        f"<strong>{e(x.name)}</strong>"
        + (f" — {e(x.issuer)}" if x.issuer else "")
        + _muted(x.category, _years(x.start, x.end))
        for x in m.education
    ])
    # Name-is-link, unlike the printed repo URLs: badge URLs are UUID noise on
    # paper (the publicId rationale below), and the accent colour doubles as a
    # "verifiable" marker distinguishing linked certs from unlinked ones.
    certs = _list_html([
        (f"<a href='{e(c.url)}'><strong>{e(c.name)}</strong></a>" if c.url
         else f"<strong>{e(c.name)}</strong>")
        + (f" — {e(c.issuer)}" if c.issuer else "")
        + _muted(c.issued[:4] if c.issued else None)
        for c in m.certifications
    ])

    def section(title: str, body: str) -> str:
        return f"<section><h2>{title}</h2>{body}</section>" if body else ""

    engineering = bool(m.audiences & ENGINEERING_AUDIENCES)
    experience = section("Experience", _experience_html(m))
    projects = section("Selected Repositories" if engineering else "Selected Projects",
                       _projects_html(m))
    lead = projects + experience if engineering else experience + projects

    # Label text, not the URL, on purpose (unlike the contact line): a publicId
    # URL is 32 hex characters of noise on paper. Sits between the job title and
    # the contact line — the first actionable thing a reader meets.
    page = m.page_url()
    graph_line = (f"<p class='cv-link'><a href='{e(page)}'>Graph Resume</a></p>"
                  if page else "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{e(b.name)} — Resume</title>
<style>{_CSS_PATH.read_text(encoding="utf-8")}</style>
</head>
<body>
<header>
  <h1>{e(b.name)}</h1>
  {f"<p class='label'>{e(b.label)}</p>" if b.label else ""}
  {graph_line}
  <p class='contact'>{contact_line}</p>
  {f"<p class='summary'>{e(b.summary)}</p>" if b.summary else ""}
</header>
{lead}
{section("Skills", _skills_html(m))}
{section("Education", education)}
{section("Certifications", certs)}
<footer>{_footer_html(m)}</footer>
</body>
</html>"""


def write_pdf(graph: Path, out: Path, html_out: Path | None = None) -> Path:
    """graph → PDF (+ its source HTML). The importable entry point: `project.py`
    calls this per application, `main()` only adds the CLI."""
    from weasyprint import HTML  # deferred: heavy import, keeps model import light

    doc = render_html(build_model(graph))
    html_out = html_out or out.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    html_out.write_text(doc, encoding="utf-8")
    HTML(string=doc, base_url=str(out.parent)).write_pdf(str(out))
    return html_out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/resume.pdf (+ resume.html) from the graph.")
    parser.add_argument("--graph", type=Path, default=REPO_ROOT / "dist" / "graph.ttl")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist" / "resume.pdf")
    parser.add_argument("--html-out", type=Path, default=None,
                        help="also write the source HTML (default: alongside --out)")
    args = parser.parse_args()

    if not args.graph.exists():
        print(f"error: {args.graph} not found — run `make build` first", file=sys.stderr)
        return 1

    html_out = write_pdf(args.graph, args.out, args.html_out)
    print(f"pdf: {args.out} ({args.out.stat().st_size // 1024} KB)  html: {html_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

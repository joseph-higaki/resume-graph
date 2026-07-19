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
    ExperienceGroup,
    Position,
    ResumeModel,
    build_model,
)

_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


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
        blocks.append(
            "<div class='project'>"
            "<div class='job-head'>"
            f"<span class='title'>{e(p.name)}</span>"
            f"<span class='dates'>{_month(p.start)}</span>"
            "</div>"
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


def render_html(m: ResumeModel) -> str:
    b = m.basics
    contact = [e(b.email)] if b.email else []
    contact += [f"<a href='{e(u)}'>{e(u.split('//')[-1])}</a>" for u in b.profiles]
    contact_line = " &nbsp;·&nbsp; ".join(contact)

    education = _list_html([
        f"<strong>{e(x.name)}</strong>"
        + (f" — {e(x.issuer)}" if x.issuer else "")
        + (f" <span class='muted'>({e(x.category)})</span>" if x.category else "")
        for x in m.education
    ])
    certs = _list_html([
        f"<strong>{e(c.name)}</strong>" + (f" — {e(c.issuer)}" if c.issuer else "")
        for c in m.certifications
    ])

    def section(title: str, body: str) -> str:
        return f"<section><h2>{title}</h2>{body}</section>" if body else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{e(b.name)} — Résumé</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>{e(b.name)}</h1>
  {f"<p class='label'>{e(b.label)}</p>" if b.label else ""}
  <p class='contact'>{contact_line}</p>
  {f"<p class='summary'>{e(b.summary)}</p>" if b.summary else ""}
</header>
{section("Experience", _experience_html(m))}
{section("Selected Projects", _projects_html(m))}
{section("Skills", _skills_html(m))}
{section("Education", education)}
{section("Certifications", certs)}
<footer>Generated from the resume-graph knowledge graph · {date.today().isoformat()}</footer>
</body>
</html>"""


# Print CSS: A4, near-black ink, one deep-blue accent. System sans body; a mono
# face for the "data" bits (dates, skill tags) echoes the project's identity
# without turning the résumé into the site's dark theme.
_CSS = """
:root { --ink:#111418; --muted:#6b7280; --accent:#184f95; --rule:#d6dae0; --chip:#eef2f7; }
@page { size: A4; margin: 14mm 15mm; }
* { box-sizing: border-box; }
body { font-family: system-ui,-apple-system,"Segoe UI",sans-serif; color: var(--ink);
       font-size: 10.2pt; line-height: 1.4; margin: 0; }
a { color: var(--accent); text-decoration: none; }
h1 { font-size: 22pt; margin: 0; letter-spacing: -0.01em; }
.label { font-size: 11.5pt; color: var(--accent); font-weight: 600; margin: 2pt 0 0; }
.contact { font-family: "IBM Plex Mono",ui-monospace,"Cascadia Code",monospace;
           font-size: 8.6pt; color: var(--muted); margin: 5pt 0 0; }
.summary { margin: 8pt 0 0; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 9pt; margin-bottom: 4pt; }
section { margin-top: 12pt; }
h2 { font-size: 11pt; text-transform: uppercase; letter-spacing: 0.08em;
     color: var(--accent); border-bottom: 1px solid var(--rule);
     padding-bottom: 2pt; margin: 0 0 7pt; }
.job, .project { margin-bottom: 9pt; break-inside: avoid; }
.job-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8pt; }
.title { font-weight: 700; }
.org { flex: 1; color: var(--muted); font-size: 9.4pt; }
.dates { font-family: "IBM Plex Mono",ui-monospace,monospace; font-size: 8.4pt;
         color: var(--muted); white-space: nowrap; }
.period { margin: 3pt 0 0 0; }
.period-head { display: flex; justify-content: space-between; align-items: baseline; }
.role { font-weight: 600; font-size: 9.6pt; color: #2a3038; }
ul.bullets { margin: 3pt 0 0; padding-left: 15pt; }
ul.bullets li { margin: 1.5pt 0; }
.desc { margin: 3pt 0 0; }
.tags { margin-top: 4pt; }
.tag { display: inline-block; font-family: "IBM Plex Mono",ui-monospace,monospace;
       font-size: 7.6pt; background: var(--chip); color: #33506f;
       padding: 1pt 5pt; border-radius: 3px; margin: 0 3pt 3pt 0; }
.skillrow { display: flex; gap: 8pt; margin: 2.5pt 0; break-inside: avoid; }
.cat { flex: 0 0 30%; font-weight: 700; color: #2a3038; }
.vals { flex: 1; }
ul.plain { margin: 0; padding-left: 15pt; }
ul.plain li { margin: 2pt 0; }
.muted { color: var(--muted); }
footer { margin-top: 14pt; padding-top: 6pt; border-top: 1px solid var(--rule);
         font-size: 7.6pt; color: var(--muted); text-align: center; }
"""


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

    from weasyprint import HTML  # deferred: heavy import, keeps model import light

    m = build_model(args.graph)
    doc = render_html(m)

    html_out = args.html_out or args.out.with_suffix(".html")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    html_out.write_text(doc, encoding="utf-8")
    HTML(string=doc, base_url=str(args.out.parent)).write_pdf(str(args.out))
    print(f"pdf: {args.out} ({args.out.stat().st_size // 1024} KB)  html: {html_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

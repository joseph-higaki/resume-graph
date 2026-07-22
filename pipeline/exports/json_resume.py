#!/usr/bin/env python3
"""json_resume.py — résumé model → dist/resume.json (jsonresume.org v1 schema).

Maps the neutral model onto the JSON Resume contract. Positions map one-to-one
(no title-of-record folding — a reader renders repeated same-company entries as a
promotion path), skills map to keyword groups by SKOS category.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from .resume_model import REPO_ROOT, ResumeModel, build_model

SCHEMA_URL = "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json"

# sameAs host → JSON Resume network label.
_NETWORKS = {
    "github.com": "GitHub",
    "www.linkedin.com": "LinkedIn",
    "linkedin.com": "LinkedIn",
    "twitter.com": "Twitter",
    "x.com": "X",
}


def _network(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return _NETWORKS.get(host, host or url)


def to_json_resume(m: ResumeModel) -> dict:
    basics = {
        "name": m.basics.name,
        "label": m.basics.label,
        "email": m.basics.email,
        "url": m.page_url(),   # the CV's own published page; None (pruned) when unpublished
        "summary": m.basics.summary,
        "profiles": [
            {"network": _network(u), "url": u} for u in m.basics.profiles
        ],
    }

    work = [
        {
            "name": p.org_name,
            "position": p.role_name,
            "startDate": p.start,
            "endDate": p.end,           # None ⇒ current role (omitted below)
            "highlights": [b.text for b in p.bullets],
        }
        for p in m.positions
    ]

    projects = [
        {
            "name": p.name,
            "description": p.description,
            "startDate": p.start,
            "url": p.url,
            "highlights": [b.text for b in p.bullets],
            "keywords": p.skills,
        }
        for p in m.projects
    ]

    skills = [
        {
            "name": sc.label,
            "keywords": [s.label for s in sc.skills],
        }
        for sc in m.skills_by_category()
    ]

    education = [
        {"institution": e.issuer, "area": e.name, "studyType": e.category,
         "startDate": e.start, "endDate": e.end}
        for e in m.education
    ]

    certificates = [
        {"name": c.name, "issuer": c.issuer, "date": c.issued, "url": c.url}
        for c in m.certifications
    ]

    doc = {
        "$schema": SCHEMA_URL,
        "basics": basics,
        "work": work,
        "education": education,
        "skills": skills,
        "projects": projects,
        "certificates": certificates,
    }
    return _prune(doc)


def _prune(value):
    """Drop keys whose value is None or an empty list — JSON Resume readers treat
    an absent field and a null field differently, and a null endDate reads as a
    real (empty) end rather than 'current'."""
    if isinstance(value, dict):
        return {k: _prune(v) for k, v in value.items()
                if v is not None and v != []}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def write_json(graph: Path, out: Path) -> dict:
    """graph → JSON Resume document on disk; returns it for the caller's summary."""
    doc = to_json_resume(build_model(graph))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/resume.json from the graph.")
    parser.add_argument("--graph", type=Path, default=REPO_ROOT / "dist" / "graph.ttl")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist" / "resume.json")
    args = parser.parse_args()

    if not args.graph.exists():
        print(f"error: {args.graph} not found — run `make build` first", file=sys.stderr)
        return 1

    doc = write_json(args.graph, args.out)
    print(f"json-resume: {len(doc.get('work', []))} roles, "
          f"{len(doc.get('skills', []))} skill groups -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""graph_html.py — dist/graph.ttl → self-contained dist/graph.html.

A dependency-free preview of the knowledge graph: one HTML file with the nodes
and edges embedded as JSON and a vanilla-canvas force layout. NOT the M4/M5 site
(no Astro / Sigma / Comunica toolchain) — this is the "look at the data now and
start tweaking" artifact. It opens over file:// or any static server because the
data is inlined, so there is no fetch/CORS step.

Encoding (per project brief): nodes coloured by rdf:type from a CVD-validated
8-slot palette that doubles as the sidebar legend; node SIZE is the required
secondary channel so the eight hues stay separable under colour-blindness.
Skills carry a `skos:broader` edge to their category hub, so the force layout
clusters them — the AWS/GCP cloud region reads at a glance with no interaction.

Time is a filter, not a geometry. Pinning x to a date would smear the category
clusters across the x-range and defeat the point above, and derived skill dates
quantise onto their evidence's dates anyway (many skills share one position's
end date), so an axis would render as combs rather than a distribution. Instead
every node carries `last` (decimal year) and the viewer offers a "last N years"
window — see `_activity` / `_skill_activity`.

Only résumé instances + the SKOS category tree are shown. Filtered out: the
ontology/schema layer, bullet notes (they surface as prose in the side panel),
and organizations that are only credentialing bodies (see `extract`). This
module owns the data shape; `templates/graph.html` owns the viewer."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from rdflib import Graph, Namespace

from .resume_model import REPO_ROOT

# The viewer shell: CSS + JS with `/*__DATA__*/null` as the single injection
# point — a comment-guarded literal, so the template is valid HTML on its own and
# .replace avoids f-string brace escaping. Read at call time, not import.
_TEMPLATE_PATH = Path(__file__).parent / "templates" / "graph.html"

RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")
SDO = Namespace("https://schema.org/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

# Ordered: legend renders in this order; drawing order is small→large so hubs
# sit on top. Colours are exact dark-surface steps of the CVD-validated 8-slot
# palette; size is the secondary (CVD) channel — hubs large, leaves small. The
# assignment is graph-aware: Skill(aqua) is the dominant type and links to
# Category/Position/Project, so those neighbours get red/violet/yellow (all far
# from aqua). The one green↔aqua-confusable slot (green) goes to Education, which
# is peripheral and never touches a skill.
TYPE_META = {
    "Person":        {"color": "#3987e5", "size": 15, "legend": "Person"},
    "Category":      {"color": "#e66767", "size": 12, "legend": "Skill category"},
    "Position":      {"color": "#9085e9", "size": 10, "legend": "Position"},
    "Organization":  {"color": "#d55181", "size": 10, "legend": "Employer"},
    "Project":       {"color": "#c98500", "size": 8,  "legend": "Project"},
    "Certification": {"color": "#d95926", "size": 8,  "legend": "Certification"},
    "Education":     {"color": "#008300", "size": 8,  "legend": "Education"},
    "Skill":         {"color": "#199e70", "size": 5,  "legend": "Skill"},
}

# (class, type-name) pairs to harvest as nodes.
_CLASSES = [
    (RG.Person, "Person"), (RG.Position, "Position"),
    (RG.Organization, "Organization"), (RG.Project, "Project"),
    (RG.Skill, "Skill"), (RG.Certification, "Certification"),
    (RG.Education, "Education"), (SKOS.Concept, "Category"),
]

# predicate → edge kind label (only edges whose both ends are nodes are kept).
_EDGE_PREDS = {
    RG.heldBy: "heldBy",
    RG.organization: "org",
    RG.usedSkill: "usedSkill",
    RG.deliveredDuring: "deliveredDuring",
    SKOS.broader: "broader",
    RG.evidencedBy: "evidencedBy",
    RG.certifies: "certifies",
    SDO.recognizedBy: "recognizedBy",
}


# Skill radius = rg:level, the one deliberate exception to "size encodes type".
# Capped at 7 so no skill reaches Education's 8: green↔aqua is this palette's
# single CVD-confusable pair and size is what keeps it separable. Unrated skills
# draw smallest — a skill with no level is a stub by definition.
# SWAP POINT: `_skill_size` is the only place that decides this. Point it at
# evidence degree (or M7's PageRank score) without touching `extract`.
LEVEL_SIZE = {"aware": 4, "working": 5, "proficient": 6, "expert": 7}
UNRATED_SIZE = 3


def _skill_size(level: str | None) -> int:
    return LEVEL_SIZE.get((level or "").strip().lower(), UNRATED_SIZE)


# xsd:date ('2021-06-01') and xsd:gYearMonth ('2020-01') both land here; only
# the year and month are load-bearing for a multi-year window.
_YEAR_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?")


def _decimal_year(v) -> float | None:
    m = _YEAR_RE.match(str(v)) if v is not None else None
    if not m:
        return None
    return int(m.group(1)) + (int(m.group(2) or 1) - 1) / 12


def _activity(g: Graph, s, typ: str) -> tuple[float | None, bool]:
    """(most recent year, still-ongoing) for an intrinsically dated node.

    A Position with a startDate and no endDate is the *current* role, not an
    undated one — that pair is returned as ongoing and the viewer resolves it
    against its own clock, so the build stays reproducible while the window
    still slides. Projects prefer `rg:lastActivity` (the last-push snapshot):
    activity is what the window filters on, and a repo started years ago but
    pushed recently belongs in a recent window. They never report ongoing —
    absence of a date means "not recorded", not "still running"."""
    if typ == "Project":
        last = _decimal_year(g.value(s, RG.lastActivity))
        if last is not None:
            return last, False
    end = _decimal_year(g.value(s, SDO.endDate))
    if end is not None:
        return end, False
    start = _decimal_year(g.value(s, SDO.startDate))
    if typ == "Position":
        return start, start is not None
    return (start if start is not None else _decimal_year(g.value(s, RG.issued))), False


def _skill_activity(g: Graph, s, dated: dict) -> tuple[float | None, bool]:
    """A skill's "last exercised": the max over everything that evidences it.

    Three channels reach a date — `rg:evidencedBy` (via the Bullet's
    `rg:bulletOf` owner, since Bullets carry no dates of their own), an inbound
    `rg:usedSkill` from a Position, and an inbound `rg:certifies` from a
    Certification or Education. A skill reached by none of them is a stub: it is
    unevidenced by construction, so undated is the correct answer rather than a
    gap to paper over, and the viewer drops it from every bounded window.

    The Bullet hop currently changes no answer in the real vault — WS5 rolled
    each migrated project's `usedSkill` up to its owning Position, so every
    bullet-evidenced skill already has a direct dated edge. It is kept because
    that roll-up is an authoring convention with no shape enforcing it; without
    the hop, the first bullet written without the roll-up would read as
    never-exercised. Covered by a synthetic test, not the vault."""
    years: list[float] = []
    ongoing = False

    def take(n) -> None:
        nonlocal ongoing
        hit = dated.get(n)
        if hit and hit[0] is not None:
            years.append(hit[0])
            ongoing = ongoing or hit[1]

    for ev in g.objects(s, RG.evidencedBy):
        take(ev)
        owner = g.value(ev, RG.bulletOf)
        if owner is not None:
            take(owner)
    for p in g.subjects(RG.usedSkill, s):
        take(p)
    for c in g.subjects(RG.certifies, s):
        take(c)
    return (max(years) if years else None), ongoing


def _label(g: Graph, s) -> str:
    for pred in (SKOS.prefLabel, SDO.name, SDO.roleName):
        v = g.value(s, pred)
        if v:
            return str(v)
    return str(s).rsplit("/", 1)[-1]


def _attrs(g: Graph, s, typ: str) -> dict:
    """Small type-specific literal bag shown in the side panel."""
    def lit(p):
        v = g.value(s, p)
        return str(v) if v is not None else None

    if typ == "Person":
        return _drop({"summary": lit(SDO.description), "email": lit(SDO.email)})
    if typ == "Position":
        org = g.value(s, RG.organization)
        return _drop({
            "role": lit(SDO.roleName),
            "org": _label(g, org) if org else None,
            "start": lit(SDO.startDate), "end": lit(SDO.endDate),
            "titleOfRecord": lit(RG.titleOfRecord),
        })
    if typ == "Project":
        # Month resolution only: the vault's lastActivity day is a snapshot
        # artifact (always the 1st), so YYYY-MM is the honest precision.
        last = lit(RG.lastActivity)
        return _drop({"description": lit(SDO.description),
                      "lastActivity": last[:7] if last else None})
    if typ == "Skill":
        cat = g.value(s, SKOS.broader)
        return _drop({"level": lit(RG.level),
                      "category": _label(g, cat) if cat else None})
    if typ == "Category":
        return _drop({"definition": lit(SKOS.definition)})
    if typ == "Certification":
        org = g.value(s, SDO.recognizedBy)
        return _drop({"issuer": _label(g, org) if org else None})
    if typ == "Education":
        org = g.value(s, SDO.recognizedBy)
        return _drop({"credential": lit(SDO.credentialCategory),
                      "issuer": _label(g, org) if org else None})
    return {}


def _drop(d: dict) -> dict:
    return {k: v for k, v in d.items() if v}


def extract(graph_path: Path) -> dict:
    from rdflib.namespace import RDF

    g = Graph().parse(graph_path, format="turtle")

    # Two thirds of rg:Organization are credentialing bodies, never employers —
    # rendering them in the same bucket floods the Organization cluster with
    # nodes that carry one edge each. Drop them: the issuer already reaches the
    # reader as panel text on the Certification/Education node (see _attrs).
    # The role lives on the *edge*, not the node (an org can be both — IBM is),
    # so this is a "not an employer" test, not a second node type.
    employers = set(g.objects(None, RG.organization))

    nodes: dict[str, dict] = {}
    terms: dict[str, object] = {}
    for cls, typ in _CLASSES:
        for s in g.subjects(RDF.type, cls):
            if typ == "Organization" and s not in employers:
                continue
            iri = str(s)
            meta = TYPE_META[typ]
            attrs = _attrs(g, s, typ)
            nodes[iri] = {
                "id": iri, "label": _label(g, s), "type": typ,
                "color": meta["color"],
                "size": _skill_size(attrs.get("level")) if typ == "Skill" else meta["size"],
                "attrs": attrs,
            }
            terms[iri] = s

    # Activity dates, in dependency order: intrinsically dated nodes first (a
    # Bullet's owner may be one), then skills off that index, then employers as
    # the span of the roles held there. Person and Category stay undated — they
    # are structural hubs, so the viewer exempts them from the window instead.
    dated: dict[object, tuple[float | None, bool]] = {}
    for iri, node in nodes.items():
        if node["type"] in ("Position", "Project", "Certification", "Education"):
            dated[terms[iri]] = _activity(g, terms[iri], node["type"])
    for pos, org in g.subject_objects(RG.organization):
        if pos in dated and str(org) in nodes:
            prev = dated.get(terms[str(org)], (None, False))
            cur = dated[pos]
            if prev[0] is None or (cur[0] is not None and cur[0] > prev[0]):
                dated[terms[str(org)]] = cur

    for iri, node in nodes.items():
        term = terms[iri]
        if node["type"] == "Skill":
            year, ongoing = _skill_activity(g, term, dated)
        else:
            year, ongoing = dated.get(term, (None, False))
        if year is not None:
            node["last"] = round(year, 2)
        if ongoing:
            node["ongoing"] = True

    links = []
    for pred, kind in _EDGE_PREDS.items():
        for s, o in g.subject_objects(pred):
            si, oi = str(s), str(o)
            if si in nodes and oi in nodes:
                links.append({"source": si, "target": oi, "kind": kind})

    # bullets grouped by owning Position/Project — the panel's prose excerpt.
    bullets: dict[str, list[str]] = {}
    for b in g.subjects(RDF.type, RG.Bullet):
        owner = g.value(b, RG.bulletOf)
        text = g.value(b, SDO.text)
        if owner is not None and text is not None and str(owner) in nodes:
            bullets.setdefault(str(owner), []).append(str(text))

    # "unrated" earns a key cell only when the graph actually holds a level-less
    # skill — the public vault has none since the 2026-07-21 trim, so the cell
    # would be dead. It is not dead everywhere: a projection merges the stub
    # skills an Application rg:demands, which carry no level by design, and there
    # the filter must name the bucket or turning every level off leaves
    # unexplained dots on the canvas.
    unrated = any(n["type"] == "Skill" and not n["attrs"].get("level")
                  for n in nodes.values())

    return {
        "nodes": list(nodes.values()),
        "links": links,
        "bullets": bullets,
        "types": [{"type": t, **m} for t, m in TYPE_META.items()],
        "levels": ([{"level": "unrated", "size": UNRATED_SIZE}] if unrated else [])
        + [{"level": k, "size": v} for k, v in LEVEL_SIZE.items()],
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("/*__DATA__*/null", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the self-contained dist/graph.html viewer.")
    parser.add_argument("--graph", type=Path, default=REPO_ROOT / "dist" / "graph.ttl")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist" / "graph.html")
    args = parser.parse_args()

    if not args.graph.exists():
        print(f"error: {args.graph} not found — run `make build` first", file=sys.stderr)
        return 1

    data = extract(args.graph)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(data), encoding="utf-8")
    print(f"graph.html: {len(data['nodes'])} nodes, {len(data['links'])} edges "
          f"({args.out.stat().st_size // 1024} KB) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

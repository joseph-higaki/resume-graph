#!/usr/bin/env python3
"""resume_model.py — dist/graph.ttl → one neutral, in-memory résumé model.

The single graph-traversal point for every export. `json_resume.py` and `pdf.py`
map from the dataclasses below; neither touches rdflib. Isolating traversal here
is the swap point — change how the graph is read once, and both exports follow.

Design notes worth keeping:
- Positions are NOT de-duped by `rg:titleOfRecord`. Each note is one held period
  (an EPAM promotion path is several notes sharing a title-of-record). The flat
  `positions` list preserves every period; `experience_groups()` folds them into
  title-of-record buckets for the PDF's promotion narrative without losing rows.
- Skills carry their immediate SKOS category and that category's parent, so the
  cloud→aws/gcp nesting survives into the exports (skills-by-category section).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDFS

RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")
SDO = Namespace("https://schema.org/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH = REPO_ROOT / "dist" / "graph.ttl"

# Level → sort weight (expert first) and a 0–1 strength for later UI use.
LEVEL_ORDER = {"expert": 4, "proficient": 3, "working": 2, "aware": 1}


@dataclass
class Bullet:
    text: str
    audience: str | None
    order: int


@dataclass
class Position:
    iri: str
    role_name: str
    org_iri: str
    org_name: str
    start: str | None            # raw xsd:date string (YYYY-MM-DD) or None
    end: str | None              # None = current
    title_of_record: str | None
    bullets: list[Bullet] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # prefLabels


@dataclass
class Project:
    iri: str
    name: str
    description: str | None
    start: str | None
    during_iri: str | None       # owning Position IRI, if any
    bullets: list[Bullet] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    emphasized: bool = False     # rg:emphasizes on a projection's Application


@dataclass
class Skill:
    iri: str
    label: str
    level: str | None
    category_iri: str | None
    category_label: str | None
    parent_category_iri: str | None
    evidence_count: int
    emphasized: bool = False     # rg:emphasizes on a projection's Application


@dataclass
class Category:
    iri: str
    label: str
    parent_iri: str | None


@dataclass
class Certification:
    name: str
    issuer: str | None


@dataclass
class Education:
    name: str
    category: str | None
    issuer: str | None


@dataclass
class Basics:
    name: str
    label: str | None            # jobTitle
    email: str | None
    summary: str | None
    profiles: list[str] = field(default_factory=list)  # sameAs URLs


@dataclass
class ResumeModel:
    basics: Basics
    positions: list[Position]
    projects: list[Project]
    skills: list[Skill]
    categories: list[Category]
    certifications: list[Certification]
    education: list[Education]

    # --- derived views -----------------------------------------------------

    def experience_groups(self) -> list["ExperienceGroup"]:
        """Fold positions into title-of-record buckets, newest first.

        A position with no `titleOfRecord` is its own singleton bucket keyed by
        its IRI, so nothing is dropped or merged away."""
        buckets: dict[str, ExperienceGroup] = {}
        order: list[str] = []
        for p in self.positions:
            key = p.title_of_record or f"__solo__{p.iri}"
            g = buckets.get(key)
            if g is None:
                g = ExperienceGroup(
                    title=p.title_of_record or p.role_name,
                    org_name=p.org_name,
                    periods=[],
                )
                buckets[key] = g
                order.append(key)
            g.periods.append(p)
        groups = [buckets[k] for k in order]
        for g in groups:
            g.periods.sort(key=_position_sort_key, reverse=True)
        groups.sort(key=lambda g: _position_sort_key(g.periods[0]), reverse=True)
        return groups

    def skills_by_category(self) -> list["SkillCategory"]:
        """Skills grouped under their immediate category, categories ordered by
        size then label. Uncategorized skills fall into a trailing 'Other' group."""
        cats: dict[str | None, SkillCategory] = {}
        label_for = {c.iri: c.label for c in self.categories}
        for s in sorted(self.skills, key=_skill_sort_key):
            key = s.category_iri
            sc = cats.get(key)
            if sc is None:
                sc = SkillCategory(
                    iri=key,
                    label=(s.category_label or label_for.get(key) or "Other"),
                    skills=[],
                )
                cats[key] = sc
            sc.skills.append(s)
        groups = list(cats.values())
        groups.sort(key=lambda sc: (sc.iri is None, -len(sc.skills), sc.label))
        return groups


@dataclass
class ExperienceGroup:
    title: str                   # title-of-record (or lone role name)
    org_name: str
    periods: list[Position]


@dataclass
class SkillCategory:
    iri: str | None
    label: str
    skills: list[Skill]


def _position_sort_key(p: Position) -> tuple:
    # Current roles (no end) rank above ended ones with the same start.
    return (p.start or "", 1 if p.end is None else 0)


def _skill_sort_key(s: Skill) -> tuple:
    return (not s.emphasized, -LEVEL_ORDER.get(s.level or "", 0), s.label.lower())


def _emphasized_iris(g: Graph) -> set[str]:
    """IRIs an Application marks `rg:emphasizes` — empty for a non-projected graph.

    Emphasis deliberately reorders Projects and Skills only. Positions stay in
    reverse-chronological order: a reader parses an experience section by date,
    so hoisting one role out of sequence reads as a bug, not as emphasis. A
    position gets emphasized by keeping it and excluding its neighbours."""
    return {str(r.n) for r in g.query(
        "SELECT ?n WHERE { ?app a rg:Application ; rg:emphasizes ?n }",
        initNs={"rg": RG})}


# --------------------------------------------------------------------------- #
# graph → model
# --------------------------------------------------------------------------- #

def _s(v) -> str | None:
    return None if v is None else str(v)


def _bullets_for(g: Graph, subject: URIRef) -> list[Bullet]:
    q = """
    SELECT ?text ?audience ?order WHERE {
        ?b a rg:Bullet ; rg:bulletOf ?subj ; sdo:text ?text .
        OPTIONAL { ?b rg:audience ?audience }
        OPTIONAL { ?b rg:order ?order }
    } ORDER BY ?order
    """
    out = []
    for row in g.query(q, initBindings={"subj": subject},
                       initNs={"rg": RG, "sdo": SDO}):
        out.append(Bullet(
            text=str(row.text),
            audience=_s(row.audience),
            order=int(row.order) if row.order is not None else 0,
        ))
    return out


def _skills_for(g: Graph, subject: URIRef) -> list[str]:
    q = """
    SELECT DISTINCT ?label WHERE {
        ?subj rg:usedSkill ?sk . ?sk skos:prefLabel ?label .
    } ORDER BY ?label
    """
    return [str(r.label) for r in g.query(
        q, initBindings={"subj": subject}, initNs={"rg": RG, "skos": SKOS})]


def build_model(graph_path: Path = DEFAULT_GRAPH) -> ResumeModel:
    g = Graph().parse(graph_path, format="turtle")
    ns = {"rg": RG, "sdo": SDO, "skos": SKOS, "rdfs": RDFS}
    emphasized = _emphasized_iris(g)

    # basics
    brow = next(iter(g.query("""
        SELECT ?name ?title ?email ?desc WHERE {
            ?p a rg:Person ; sdo:name ?name .
            OPTIONAL { ?p sdo:jobTitle ?title }
            OPTIONAL { ?p sdo:email ?email }
            OPTIONAL { ?p sdo:description ?desc }
        }""", initNs=ns)), None)
    profiles = [str(r.url) for r in g.query(
        "SELECT ?url WHERE { ?p a rg:Person ; sdo:sameAs ?url }", initNs=ns)]
    basics = Basics(
        name=str(brow.name) if brow else "",
        label=_s(brow.title) if brow else None,
        email=_s(brow.email) if brow else None,
        summary=_s(brow.desc) if brow else None,
        profiles=sorted(profiles),
    )

    # positions
    positions: list[Position] = []
    for r in g.query("""
        SELECT ?pos ?role ?org ?orgName ?start ?end ?tor WHERE {
            ?pos a rg:Position ; sdo:roleName ?role ; rg:organization ?org .
            ?org sdo:name ?orgName .
            OPTIONAL { ?pos sdo:startDate ?start }
            OPTIONAL { ?pos sdo:endDate ?end }
            OPTIONAL { ?pos rg:titleOfRecord ?tor }
        }""", initNs=ns):
        pos = Position(
            iri=str(r.pos), role_name=str(r.role),
            org_iri=str(r.org), org_name=str(r.orgName),
            start=_s(r.start), end=_s(r.end), title_of_record=_s(r.tor),
            bullets=_bullets_for(g, r.pos), skills=_skills_for(g, r.pos),
        )
        positions.append(pos)
    positions.sort(key=_position_sort_key, reverse=True)

    # projects
    projects: list[Project] = []
    for r in g.query("""
        SELECT ?proj ?name ?desc ?start ?during WHERE {
            ?proj a rg:Project ; sdo:name ?name .
            OPTIONAL { ?proj sdo:description ?desc }
            OPTIONAL { ?proj sdo:startDate ?start }
            OPTIONAL { ?proj rg:deliveredDuring ?during }
        }""", initNs=ns):
        projects.append(Project(
            iri=str(r.proj), name=str(r.name), description=_s(r.desc),
            start=_s(r.start), during_iri=_s(r.during),
            bullets=_bullets_for(g, r.proj), skills=_skills_for(g, r.proj),
            emphasized=str(r.proj) in emphasized,
        ))
    # Emphasized projects lead; the rest stay newest-first within each block.
    projects.sort(key=lambda p: (p.emphasized, p.start or ""), reverse=True)

    # categories (SKOS concept tree)
    categories: list[Category] = []
    for r in g.query("""
        SELECT ?c ?label ?parent WHERE {
            ?c a skos:Concept ; skos:prefLabel ?label .
            OPTIONAL { ?c skos:broader ?parent }
        }""", initNs=ns):
        categories.append(Category(
            iri=str(r.c), label=str(r.label), parent_iri=_s(r.parent)))

    # skills
    skills: list[Skill] = []
    parent_of = {c.iri: c.parent_iri for c in categories}
    for r in g.query("""
        SELECT ?sk ?label ?level ?cat ?catLabel (COUNT(?ev) AS ?evc) WHERE {
            ?sk a rg:Skill ; skos:prefLabel ?label .
            OPTIONAL { ?sk rg:level ?level }
            OPTIONAL { ?sk skos:broader ?cat . ?cat skos:prefLabel ?catLabel }
            OPTIONAL { ?sk rg:evidencedBy ?ev }
        } GROUP BY ?sk ?label ?level ?cat ?catLabel""", initNs=ns):
        cat_iri = _s(r.cat)
        skills.append(Skill(
            iri=str(r.sk), label=str(r.label), level=_s(r.level),
            category_iri=cat_iri, category_label=_s(r.catLabel),
            parent_category_iri=parent_of.get(cat_iri),
            evidence_count=int(r.evc) if r.evc is not None else 0,
            emphasized=str(r.sk) in emphasized,
        ))

    # certifications
    certifications = [
        Certification(name=str(r.name), issuer=_s(r.orgName))
        for r in g.query("""
            SELECT ?c ?name ?orgName WHERE {
                ?c a rg:Certification ; sdo:name ?name .
                OPTIONAL { ?c sdo:recognizedBy ?org . ?org sdo:name ?orgName }
            } ORDER BY ?name""", initNs=ns)
    ]

    # education
    education = [
        Education(name=str(r.name), category=_s(r.cat), issuer=_s(r.orgName))
        for r in g.query("""
            SELECT ?e ?name ?cat ?orgName WHERE {
                ?e a rg:Education ; sdo:name ?name .
                OPTIONAL { ?e sdo:credentialCategory ?cat }
                OPTIONAL { ?e sdo:recognizedBy ?org . ?org sdo:name ?orgName }
            } ORDER BY ?name""", initNs=ns)
    ]

    return ResumeModel(
        basics=basics, positions=positions, projects=projects,
        skills=skills, categories=categories,
        certifications=certifications, education=education,
    )


if __name__ == "__main__":
    m = build_model()
    print(f"basics: {m.basics.name} — {m.basics.label}")
    print(f"positions: {len(m.positions)}  projects: {len(m.projects)}  "
          f"skills: {len(m.skills)}  certs: {len(m.certifications)}  "
          f"education: {len(m.education)}")
    print(f"experience groups: {len(m.experience_groups())}")
    for sc in m.skills_by_category():
        print(f"  {sc.label:24s} {len(sc.skills)} skills")

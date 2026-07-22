"""Export correctness on the real vault graph: the shared model's shape, the
JSON Resume contract, the PDF's bytes, and the self-contained graph.html payload.

All four exports read one built graph (module-scoped fixture) rather than the
vault directly — mirroring the pipeline's "everything derived from dist/graph"
rule, so a test failure means the export logic broke, not the vault."""

import json
import re
from pathlib import Path

import pytest

from pipeline import build
from pipeline.exports import graph_html, json_resume, pdf
from pipeline.exports.resume_model import REPO_URL, SITE_URL, build_model

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_VAULT = REPO_ROOT / "vault"


@pytest.fixture(scope="module")
def graph_ttl(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    g = build.export_graph(REAL_VAULT, out)
    build.write_outputs(g, out)
    return out / "graph.ttl"


@pytest.fixture(scope="module")
def model(graph_ttl):
    return build_model(graph_ttl)


# --- resume model ---------------------------------------------------------

def test_model_has_all_sections(model):
    assert model.basics.name
    assert model.positions and model.projects and model.skills
    assert model.certifications and model.education

def test_positions_not_deduped_by_title_of_record(model):
    # EPAM appears once per held period; folding must not drop rows.
    epam = [p for p in model.positions if "EPAM" in p.org_name]
    assert len(epam) > 2
    groups = model.experience_groups()
    # every position survives into exactly one group
    assert sum(len(g.periods) for g in groups) == len(model.positions)
    # at least one group folds multiple periods (a title-of-record promotion path)
    assert any(len(g.periods) > 1 for g in groups)

def test_skills_cluster_has_aws(model):
    labels = {sc.label for sc in model.skills_by_category()}
    assert "AWS" in labels
    aws = next(sc for sc in model.skills_by_category() if sc.label == "AWS")
    assert aws.skills  # non-empty cloud cluster

def test_certifications_sorted_newest_first(model):
    issued = [c.issued for c in model.certifications if c.issued]
    assert len(issued) > 3, "dates stopped flowing from rg:issued"
    assert issued == sorted(issued, reverse=True)

def test_education_sorted_newest_first(model):
    keys = [x.end or x.start for x in model.education if x.end or x.start]
    assert keys and keys == sorted(keys, reverse=True)

def test_projects_carry_repo_url(model):
    assert any(p.url and "github.com" in p.url for p in model.projects)

def test_certifications_carry_badge_url(model):
    # sdo:url is optional on certs (some badge hosts are dead — see the vault
    # notes), so "some but not necessarily all" is the correct assertion.
    assert any(c.url for c in model.certifications)


# --- JSON Resume ----------------------------------------------------------

def test_json_resume_shape(model):
    doc = json_resume.to_json_resume(model)
    assert doc["basics"]["name"] == model.basics.name
    assert len(doc["work"]) == len(model.positions)
    assert doc["skills"] and all("name" in s for s in doc["skills"])
    # round-trips as JSON
    assert json.loads(json.dumps(doc))

def test_json_resume_prunes_nulls(model):
    doc = json_resume.to_json_resume(model)
    # a current role has no endDate: pruning must omit the key, not emit null
    # (a null endDate reads as an empty end, not "present").
    assert any("endDate" not in w for w in doc["work"])          # current roles
    assert all(w["endDate"] for w in doc["work"] if "endDate" in w)  # never null

def test_json_resume_profiles_networked(model):
    doc = json_resume.to_json_resume(model)
    nets = {p["network"] for p in doc["basics"].get("profiles", [])}
    assert "GitHub" in nets or "LinkedIn" in nets

def test_json_resume_url_is_the_published_page(model):
    # Same rule as the PDF header, machine-readable channel: one page_url().
    doc = json_resume.to_json_resume(model)
    assert doc["basics"]["url"] == f"{SITE_URL}/"

def test_json_resume_projects_link_and_certs_dated(model):
    doc = json_resume.to_json_resume(model)
    assert any("url" in p for p in doc["projects"])
    assert any("date" in c for c in doc["certificates"])
    assert any("url" in c for c in doc["certificates"])


# --- PDF ------------------------------------------------------------------

def test_pdf_html_renders_sections(model):
    html = pdf.render_html(model)
    assert model.basics.name in html
    for section in ("Experience", "Skills", "Education"):
        assert section in html

def test_pdf_default_layout_experience_first(model):
    # A plain build carries no Application → no audiences → default framing.
    assert model.audiences == set()
    html = pdf.render_html(model)
    assert html.index("<h2>Experience</h2>") < html.index("<h2>Selected Projects</h2>")
    assert "Selected Repositories" not in html

def test_pdf_engineering_layout_repositories_lead(model):
    """An engineering-audience projection retitles the projects section and
    hoists it above Experience — the repo links are the evidence that matters."""
    import dataclasses
    eng = dataclasses.replace(model, audiences={"data-eng"})
    html = pdf.render_html(eng)
    assert "Selected Projects" not in html
    assert html.index("<h2>Selected Repositories</h2>") < html.index("<h2>Experience</h2>")
    assert "class='repo'" in html  # repo links render in the head line

def test_pdf_delivery_audience_keeps_default_layout(model):
    import dataclasses
    html = pdf.render_html(dataclasses.replace(model, audiences={"delivery"}))
    assert html.index("<h2>Experience</h2>") < html.index("<h2>Selected Projects</h2>")

def test_pdf_plain_build_links_site_root(model):
    """No Application in the graph → the CV points at the public site, not at an
    application page: header 'Graph Resume' → site root, footer 'published' →
    the root resume.pdf, provenance → the repo."""
    assert model.projected is False and model.public_id is None
    html = pdf.render_html(model)
    assert f"<a href='{SITE_URL}/'>Graph Resume</a>" in html
    assert f"<a href='{REPO_URL}'>resume knowledge graph</a>" in html
    assert f"<a href='{SITE_URL}/resume.pdf'>published</a>" in html
    assert "Export of the" in html and "Projection of the" not in html

def test_pdf_linked_certs_render_name_as_anchor(model):
    """A cert with sdo:url wraps its name in the link (badge URLs are UUID noise
    on paper); one without renders as plain text, not an empty anchor."""
    html = pdf.render_html(model)
    linked = next(c for c in model.certifications if c.url)
    unlinked = next(c for c in model.certifications if not c.url)
    assert (f"<a href='{pdf.e(linked.url)}'>"
            f"<strong>{pdf.e(linked.name)}</strong></a>") in html
    assert f"<strong>{pdf.e(unlinked.name)}</strong>" in html
    assert "<a href=''" not in html

def test_pdf_bytes(model, tmp_path):
    from weasyprint import HTML
    out = tmp_path / "resume.pdf"
    HTML(string=pdf.render_html(model)).write_pdf(str(out))
    data = out.read_bytes()
    assert data[:5] == b"%PDF-" and len(data) > 5000


# --- graph.html -----------------------------------------------------------

def test_graph_extract_types_and_edges(graph_ttl):
    data = graph_html.extract(graph_ttl)
    types = {n["type"] for n in data["nodes"]}
    assert {"Person", "Position", "Skill", "Category", "Project",
            "Organization", "Certification", "Education"} <= types
    ids = {n["id"] for n in data["nodes"]}
    # every edge endpoint is a real node (no dangling links in the viz)
    assert all(l["source"] in ids and l["target"] in ids for l in data["links"])
    # bullets are keyed by owning position/project nodes only
    assert all(owner in ids for owner in data["bullets"])

def test_graph_only_employer_orgs_are_nodes(graph_ttl):
    """Credentialing-only orgs stay out of the node set (they flooded the
    Organization cluster); their name still reaches the reader as panel text."""
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF

    g = Graph().parse(graph_ttl, format="turtle")
    RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")
    SDO = Namespace("https://schema.org/")
    employers = set(g.objects(None, RG.organization))
    issuer_only = {o for o in g.objects(None, SDO.recognizedBy)
                   if (o, RDF.type, RG.Organization) in g} - employers
    assert issuer_only, "fixture regression: expected some issuer-only orgs"

    data = graph_html.extract(graph_ttl)
    org_ids = {n["id"] for n in data["nodes"] if n["type"] == "Organization"}
    assert org_ids == {str(o) for o in employers}
    assert not org_ids & {str(o) for o in issuer_only}
    # the dropped names survive as an `issuer` attr on certs/education
    issuers = {n["attrs"].get("issuer") for n in data["nodes"]
               if n["type"] in ("Certification", "Education")}
    assert issuers - {None}


def test_graph_panel_urls_on_projects_and_certs(graph_ttl):
    """sdo:url reaches the side panel's attrs bag for both linkable types, and
    never as an empty string — _drop must have pruned the absent ones."""
    data = graph_html.extract(graph_ttl)
    for typ in ("Project", "Certification"):
        urls = [n["attrs"].get("url") for n in data["nodes"] if n["type"] == typ]
        assert any(urls), f"no {typ} carries a url attr"
        assert "" not in urls


def test_graph_decimal_year_handles_both_date_types():
    """Certs carry xsd:gYearMonth, positions xsd:date — one parser, both shapes."""
    assert graph_html._decimal_year("2020-01") == 2020.0
    assert graph_html._decimal_year("2021-07-01") == pytest.approx(2021.5)
    assert graph_html._decimal_year("2019") == 2019.0
    assert graph_html._decimal_year(None) is None
    assert graph_html._decimal_year("not a date") is None


def test_graph_skill_size_stays_below_education(graph_ttl):
    """Skill radius encodes rg:level, but must never reach Education's size:
    green↔aqua is the palette's confusable pair and size is what separates them."""
    education_size = graph_html.TYPE_META["Education"]["size"]
    assert max(graph_html.LEVEL_SIZE.values()) < education_size

    data = graph_html.extract(graph_ttl)
    skills = [n for n in data["nodes"] if n["type"] == "Skill"]
    assert all(n["size"] < education_size for n in skills)
    by_level = {n["attrs"].get("level"): n["size"] for n in skills}
    assert by_level["expert"] > by_level["proficient"] > by_level["working"] > by_level["aware"]
    # unrated skills are stubs — they draw smallest, not at the "aware" step
    assert by_level.get(None, graph_html.UNRATED_SIZE) < by_level["aware"]


def test_graph_skill_date_hops_bulletof_to_the_owner():
    """Bullets carry no dates, so a bullet-evidenced skill can only be dated via
    rg:bulletOf → owning Position.

    Synthetic, deliberately: in the real vault this hop is currently redundant,
    because WS5 rolled every migrated project's `usedSkill` up to its Position,
    giving each bullet-evidenced skill a direct dated edge as well. That roll-up
    is an authoring convention with no SHACL shape behind it — the day someone
    writes a bullet without it, this hop is the only thing keeping the skill from
    silently reading as never-exercised. Hence a fixture that isolates the path."""
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import RDF, XSD

    RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")
    SDO = Namespace("https://schema.org/")
    base = "https://example.org/id/"
    skill, bullet, pos = (URIRef(base + x) for x in ("s", "b", "p"))

    g = Graph()
    g.add((skill, RDF.type, RG.Skill))
    g.add((skill, RG.evidencedBy, bullet))
    g.add((bullet, RDF.type, RG.Bullet))
    g.add((bullet, RG.bulletOf, pos))
    g.add((pos, RDF.type, RG.Position))
    g.add((pos, SDO.startDate, Literal("2015-03-01", datatype=XSD.date)))
    g.add((pos, SDO.endDate, Literal("2018-09-01", datatype=XSD.date)))

    dated = {pos: graph_html._activity(g, pos, "Position")}
    year, ongoing = graph_html._skill_activity(g, skill, dated)
    assert year == pytest.approx(2018 + 8 / 12)
    assert ongoing is False


def test_graph_project_dates_are_last_activity_month(graph_ttl):
    """Projects surface rg:lastActivity, month resolution — not their start.

    Two claims: the panel attr is YYYY-MM (the vault's day is a snapshot
    artifact, so showing it would assert precision the data doesn't have), and
    the window's `last` derives from lastActivity — a repo started years ago
    but pushed recently belongs in a recent window."""
    data = graph_html.extract(graph_ttl)
    projects = [n for n in data["nodes"] if n["type"] == "Project"]
    assert projects
    for n in projects:
        assert "start" not in n["attrs"]
        la = n["attrs"].get("lastActivity")
        assert la and re.fullmatch(r"\d{4}-\d{2}", la)
        assert n["last"] == pytest.approx(graph_html._decimal_year(la), abs=0.01)


def test_graph_unevidenced_skills_stay_undated(graph_ttl):
    """A stub is unevidenced by construction, so it has no date to report —
    the gap-analysis signal, not a derivation gap to paper over."""
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF

    g = Graph().parse(graph_ttl, format="turtle")
    RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")

    data = graph_html.extract(graph_ttl)
    skills = [n for n in data["nodes"] if n["type"] == "Skill"]
    assert any("last" in n for n in skills)

    for n in (x for x in skills if "last" not in x):
        s = next(x for x in g.subjects(RDF.type, RG.Skill) if str(x) == n["id"])
        assert not list(g.objects(s, RG.evidencedBy))
        assert not list(g.subjects(RG.usedSkill, s))
        assert not list(g.subjects(RG.certifies, s))


def test_graph_ongoing_role_marks_current_not_undated(graph_ttl):
    """A Position with no endDate is the current role. It must report `ongoing`
    so the viewer resolves it against its own clock — a build-time "now" would
    make the output non-reproducible and stale the window."""
    data = graph_html.extract(graph_ttl)
    positions = [n for n in data["nodes"] if n["type"] == "Position"]
    current = [n for n in positions if n.get("ongoing")]
    assert len(current) == 1, "expected exactly one open-ended position"
    assert all(n.get("last") for n in positions), "every position resolves a year"

    # ongoing propagates: employer and the skills evidenced there are current too
    assert any(n.get("ongoing") for n in data["nodes"] if n["type"] == "Organization")
    assert any(n.get("ongoing") for n in data["nodes"] if n["type"] == "Skill")

    # The clock is never consulted at build time: every emitted year is one the
    # graph actually asserts, so two builds of one vault agree forever.
    asserted = set()
    for n in data["nodes"]:
        for key in ("start", "end", "issued", "lastActivity"):
            if (v := n["attrs"].get(key)):
                asserted.add(graph_html._decimal_year(v))
    assert max(n["last"] for n in data["nodes"] if "last" in n) <= max(asserted)


def test_graph_html_self_contained(graph_ttl):
    data = graph_html.extract(graph_ttl)
    html = graph_html.render_html(data)
    # injection happened (no leftover placeholder) and payload parses
    assert "/*__DATA__*/null" not in html
    payload = json.loads(
        re.search(r'<script id="data"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert len(payload["nodes"]) == len(data["nodes"])
    assert any(n["type"] == "Category" and n["label"] == "Cloud"
               for n in payload["nodes"])
    # self-contained: no external resource *loads* (IRIs in the data payload are
    # fine — we forbid script/style/font/image fetches, not the substring http).
    assert 'src="http' not in html
    assert 'href="http' not in html
    assert "<link" not in html.lower()
    assert "cdn" not in html.lower()

"""Projection behaviour against the real vault graph, with and without an overlay.

The `--extra-graph` contract is the whole point of these tests: the private
`resume-applications` repo merges its Application notes in this way, and this
repo must behave identically whether that overlay is present or not. Every test
here builds the public graph, optionally merges a synthetic overlay written to
tmp_path, and asserts on the projected result — no Application ever lands in the
working tree.

Cases that depend on vault content (the unevidenced-claim cascade) derive their
target by querying the graph rather than naming a note, so seed-data edits
don't break them."""

from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

from pipeline import build, project, validate

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_VAULT = REPO_ROOT / "vault"
SHAPES = REPO_ROOT / "validation" / "shapes.ttl"

RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")
SDO = Namespace("https://schema.org/")
ID = "https://joseph-higaki.github.io/resume-graph/id/"

APP = URIRef(ID + "app-test")
EPAM_STAFFING = URIRef(ID + "Delivery%20and%20Staffing%20Manager%20%E2%80%94%20EPAM")

PREFIXES = f"""
@prefix data: <{ID}> .
@prefix rg:   <{RG}> .
@prefix sdo:  <{SDO}> .
"""


@pytest.fixture(scope="module")
def graph_ttl(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    g = build.export_graph(REAL_VAULT, out)
    build.write_outputs(g, out)
    return out / "graph.ttl"


@pytest.fixture(scope="module")
def base(graph_ttl) -> Graph:
    return project.load_graph(graph_ttl)


def overlay(tmp_path: Path, body: str, name: str = "overlay.ttl") -> Path:
    path = tmp_path / name
    path.write_text(PREFIXES + body, encoding="utf-8")
    return path


def app_note(directives: str = "", audiences: str | None = '"data-eng", "general"') -> str:
    """An Application note; `audiences=None` omits rg:audience entirely."""
    line = f"rg:audience {audiences} ;" if audiences else ""
    return f"""
data:app-test a rg:Application ;
    rg:targetRole "Knowledge Graph Engineer" ;
    {line}
    {directives}
    sdo:name "test application" .
"""


def merged(graph_ttl: Path, tmp_path: Path, body: str) -> Graph:
    return project.load_graph(graph_ttl, [overlay(tmp_path, body)])


# --- the zero-application contract ---------------------------------------- #

def test_no_applications_is_a_clean_noop(base, capsys):
    """Public CI's normal path: no Application anywhere, nothing to do, exit 0."""
    assert project.applications(base) == []


def test_cli_without_overlay_succeeds(graph_ttl, tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["project.py", "--graph", str(graph_ttl),
                                     "--out-dir", str(tmp_path / "out")])
    assert project.main() == 0
    assert not (tmp_path / "out").exists()


def test_cli_with_overlay_writes_projection(graph_ttl, tmp_path, monkeypatch):
    ov = overlay(tmp_path, app_note())
    out = tmp_path / "out"
    monkeypatch.setattr("sys.argv", ["project.py", "--graph", str(graph_ttl),
                                     "--extra-graph", str(ov),
                                     "--application", "app-test",
                                     "--out-dir", str(out)])
    assert project.main() == 0
    assert (out / "app-test" / "graph.ttl").exists()


# --- application resolution ----------------------------------------------- #

def test_resolves_by_slug_and_by_iri(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path, app_note())
    assert project.resolve_application(g, "app-test") == APP
    assert project.resolve_application(g, str(APP)) == APP


def test_unknown_application_fails_loud(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path, app_note())
    with pytest.raises(project.ProjectionError, match="no rg:Application"):
        project.resolve_application(g, "nope")


# --- bullet selection ------------------------------------------------------ #

def test_bullets_filtered_to_declared_audiences(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path, app_note())
    out, stats = project.project(g, APP)
    kept = {str(o) for o in out.objects(None, RG.audience)}
    assert "delivery" not in kept
    assert stats["bullets_dropped"] > 0


def test_no_declared_audience_keeps_every_bullet(graph_ttl, tmp_path):
    """Silently emptying the experience section is worse than an untailored CV."""
    g = merged(graph_ttl, tmp_path, app_note(audiences=None))
    out, stats = project.project(g, APP)
    assert stats["bullets_dropped"] == 0
    assert list(out.subjects(RDF.type, RG.Bullet))


# --- excludes -------------------------------------------------------------- #

def test_excludes_removes_node_and_inbound_references(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path,
               app_note("rg:excludes data:Resume%20Graph ;"))
    target = URIRef(ID + "Resume%20Graph")
    assert (target, None, None) in g          # present before
    out, _ = project.project(g, APP)
    assert (target, None, None) not in out    # gone as subject
    assert (None, None, target) not in out    # and as object — no dangling refs


def test_excluding_a_position_drops_its_bullets(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path,
               app_note(f"rg:excludes <{EPAM_STAFFING}> ;"))
    out, _ = project.project(g, APP)
    assert list(out.subjects(RG.bulletOf, EPAM_STAFFING)) == []


# --- unevidenced-claim cascade --------------------------------------------- #

def sole_evidence_pair(g: Graph) -> tuple[URIRef, URIRef]:
    """A (project, skill) where that Project is the skill's only evidence.

    Derived, not hardcoded: which skill happens to rest on one project changes
    as the vault grows, and a test that names a note would rot silently."""
    for skill in sorted(set(g.subjects(RG.level, None)), key=str):
        evidence = list(g.objects(skill, RG.evidencedBy))
        if len(evidence) == 1 and (evidence[0], RDF.type, RG.Project) in g:
            return evidence[0], skill
    pytest.skip("no skill in the current vault rests on a single Project")


def test_excluding_sole_evidence_purges_the_claim(graph_ttl, tmp_path):
    base_g = project.load_graph(graph_ttl)
    evidence, skill = sole_evidence_pair(base_g)
    g = merged(graph_ttl, tmp_path, app_note(f"rg:excludes <{evidence}> ;"))
    out, stats = project.project(g, APP)
    assert stats["skills_purged"] >= 1
    assert (skill, None, None) not in out


def test_demanded_skill_is_demoted_to_a_gap_not_purged(graph_ttl, tmp_path):
    """A demanded skill without evidence IS the gap signal — it must survive."""
    base_g = project.load_graph(graph_ttl)
    evidence, skill = sole_evidence_pair(base_g)
    g = merged(graph_ttl, tmp_path,
               app_note(f"rg:excludes <{evidence}> ; rg:demands <{skill}> ;"))
    out, stats = project.project(g, APP)
    assert stats["skills_demoted"] >= 1
    assert (skill, RG.level, None) not in out       # the claim is dropped
    assert (None, RG.usedSkill, skill) not in out   # and so is every usage link
    assert (skill, None, None) in out               # but the node itself remains


# --- summary substitution --------------------------------------------------- #

def test_summary_substituted_when_present(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path,
               app_note('rg:summary "Tailored opening paragraph." ;'))
    out, stats = project.project(g, APP)
    assert stats["summary_substituted"]
    assert "Tailored opening paragraph." in {
        str(o) for o in out.objects(None, SDO.description)}


def test_default_summary_kept_when_application_has_none(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path, app_note())
    before = {str(o) for _, o in g.subject_objects(SDO.description)}
    out, stats = project.project(g, APP)
    assert not stats["summary_substituted"]
    assert {str(o) for _, o in out.subject_objects(SDO.description)} == before


# --- RoleFraming (ADR 0001 §6 checklist) ------------------------------------ #

FRAMING = """
data:framing-test a rg:RoleFraming ;
    rg:framingOf <%s> ;
    rg:audience "data-eng" ;
    sdo:roleName "Framed Engineering Title" .
""" % EPAM_STAFFING


def test_framing_applies_for_matching_audience(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path, app_note() + FRAMING)
    out, _ = project.project(g, APP)
    assert "Framed Engineering Title" in {
        str(o) for o in out.objects(EPAM_STAFFING, SDO.roleName)}


def test_other_positions_keep_their_default_role_name(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path, app_note() + FRAMING)
    out, _ = project.project(g, APP)
    others = [s for s in out.subjects(SDO.roleName, None) if s != EPAM_STAFFING]
    assert others
    for pos in others:
        assert "Framed Engineering Title" not in {
            str(o) for o in out.objects(pos, SDO.roleName)}


def test_no_matching_framing_preserves_default(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path,
               app_note(audiences='"delivery"') + FRAMING)
    before = {str(o) for o in g.objects(EPAM_STAFFING, SDO.roleName)}
    out, _ = project.project(g, APP)
    assert {str(o) for o in out.objects(EPAM_STAFFING, SDO.roleName)} == before


def test_conflicting_framings_raise(graph_ttl, tmp_path):
    conflict = FRAMING + """
data:framing-test-2 a rg:RoleFraming ;
    rg:framingOf <%s> ;
    rg:audience "data-eng" ;
    sdo:roleName "A Second Conflicting Title" .
""" % EPAM_STAFFING
    g = merged(graph_ttl, tmp_path, app_note() + conflict)
    with pytest.raises(project.ProjectionError, match="conflicting RoleFramings"):
        project.project(g, APP)


def test_framings_are_stripped_from_the_projection(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path, app_note() + FRAMING)
    out, stats = project.project(g, APP)
    assert stats["framings_stripped"] >= 1
    # rdf:type specifically — the schema layer legitimately keeps rg:RoleFraming
    # as the object of the ontology's domainIncludes declarations.
    assert list(out.subjects(RDF.type, RG.RoleFraming)) == []


# --- invariants ------------------------------------------------------------- #

def test_projection_does_not_mutate_the_input_graph(graph_ttl, tmp_path):
    g = merged(graph_ttl, tmp_path,
               app_note('rg:summary "x" ; rg:excludes data:Resume%20Graph ;') + FRAMING)
    before = len(g)
    project.project(g, APP)
    assert len(g) == before


def test_projected_graph_still_passes_the_shacl_gate(graph_ttl, tmp_path):
    """The gate holds after projection — a tailored CV is still an honest one."""
    g = merged(graph_ttl, tmp_path,
               app_note("rg:excludes data:Resume%20Graph ;") + FRAMING)
    out, _ = project.project(g, APP)
    projected = tmp_path / "projected.ttl"
    out.serialize(destination=projected, format="turtle")
    conforms, report = validate.run(projected, SHAPES)
    assert conforms, report

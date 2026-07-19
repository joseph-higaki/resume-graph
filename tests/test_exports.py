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
from pipeline.exports.resume_model import build_model

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


# --- PDF ------------------------------------------------------------------

def test_pdf_html_renders_sections(model):
    html = pdf.render_html(model)
    assert model.basics.name in html
    for section in ("Experience", "Skills", "Education"):
        assert section in html

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

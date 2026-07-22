"""The SHACL gate against the real vault: the seed data must conform (with
zero applications present — the public-CI baseline), and the evidence rule
must fire from both of its trigger directions."""

import shutil
from pathlib import Path

from rdflib import Namespace, URIRef

from pipeline import build, validate

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_VAULT = REPO_ROOT / "vault"
SHAPES = REPO_ROOT / "validation" / "shapes.ttl"

RG = "https://joseph-higaki.github.io/resume-graph/vocab/rg#"
ID = "https://joseph-higaki.github.io/resume-graph/id/"
RG_NS = Namespace(RG)


def build_and_validate(vault, out_dir):
    g = build.export_graph(vault, out_dir)
    build.write_outputs(g, out_dir)
    conforms, report = validate.run(out_dir / "graph.ttl", SHAPES)
    return g, conforms, report


def copy_vault(tmp_path):
    dst = tmp_path / "vault"
    shutil.copytree(REAL_VAULT, dst)
    return dst


def test_real_vault_conforms(tmp_path):
    g, conforms, report = build_and_validate(REAL_VAULT, tmp_path)
    assert conforms, report
    # spot-check: evidence edges made it into the graph
    assert (URIRef(ID + "AWS%20S3"), URIRef(RG + "evidencedBy"),
            URIRef(ID + "inorbis-invoice-staging")) in g


def test_bullet_evidence_reaches_a_position(tmp_path):
    """Skill -> Bullet -> Position, the path the 2026-07-20 migration bought.

    Evidence pointing at a Bullet is only honest if the Bullet resolves to a role:
    a Bullet carries no dates or employer of its own, so a dangling one would be an
    unanchored claim. Asserted over every bullet-backed skill rather than a named
    pair, which would rot the next time evidence moves."""
    g, _, _ = build_and_validate(REAL_VAULT, tmp_path)
    rows = list(g.query("""
        SELECT ?sk WHERE {
            ?sk rg:evidencedBy ?b . ?b a rg:Bullet .
            FILTER NOT EXISTS { ?b rg:bulletOf ?owner . ?owner a rg:Position }
        }""", initNs={"rg": RG_NS}))
    assert rows == [], f"bullet evidence not anchored to a Position: {rows}"


def test_esco_warning_reported_not_fatal(tmp_path):
    _, conforms, report = build_and_validate(REAL_VAULT, tmp_path)
    assert conforms
    assert "ESCO" in report  # advisory shape reports, never fails (until M6)


def test_claimed_skill_without_evidence_fails(tmp_path):
    vault = copy_vault(tmp_path)
    (vault / "_data" / "skills" / "Kubernetes.md").write_text(
        "---\n"
        'type: "[[Skill]]"\n'
        "prefLabel: Kubernetes\n"
        'broader: "[[devops]]"\n'
        "level: expert\n"
        "---\n# Kubernetes\n",
        encoding="utf-8",
    )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert not conforms
    assert "Kubernetes" in report


def test_usedskill_reference_makes_skill_claimed(tmp_path):
    vault = copy_vault(tmp_path)
    (vault / "_data" / "skills" / "Kubernetes.md").write_text(
        "---\n"
        'type: "[[Skill]]"\n'
        "prefLabel: Kubernetes\n"
        'broader: "[[devops]]"\n'
        "---\n# Kubernetes\n",
        encoding="utf-8",
    )
    (vault / "_data" / "projects" / "K8s Migration.md").write_text(
        "---\n"
        'type: "[[Project]]"\n'
        "name: K8s Migration\n"
        'description: "Fixture project that claims Kubernetes via usedSkill."\n'
        'creator: "[[profile]]"\n'
        'usedSkill: [ "[[Kubernetes]]" ]\n'
        "---\n# K8s Migration\n",
        encoding="utf-8",
    )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert not conforms
    assert "Kubernetes" in report


def test_project_without_creator_fails(tmp_path):
    # sdo:creator is what anchors a self-directed Project to the Person hub;
    # a project note without it would float off the graph unnoticed.
    vault = copy_vault(tmp_path)
    (vault / "_data" / "projects" / "Orphan Project.md").write_text(
        "---\n"
        'type: "[[Project]]"\n'
        "name: Orphan Project\n"
        'description: "Fixture project with no creator edge."\n'
        "---\n# Orphan Project\n",
        encoding="utf-8",
    )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert not conforms
    assert "creator" in report


def test_unclaimed_stub_skill_is_exempt(tmp_path):
    # A stub with no level and no usedSkill references — the shape an
    # Application-demanded skill has. Missing evidence must NOT fail it.
    # Uses Amazon Athena: a deliberate no-evidence stub nothing links via
    # usedSkill (Terraform is no longer a valid exemplar — repo projects now
    # reference it, so a bare stub would be legitimately claimed-without-evidence).
    vault = copy_vault(tmp_path)
    (vault / "_data" / "skills" / "Amazon Athena.md").write_text(
        "---\n"
        'type: "[[Skill]]"\n'
        "prefLabel: Amazon Athena\n"
        'broader: "[[cloud-aws]]"\n'
        "---\n# Amazon Athena\n",
        encoding="utf-8",
    )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert conforms, report


def test_roleframing_general_audience_rejected(tmp_path):
    # 'general' == the Position's default roleName, so a general framing is
    # meaningless — the shape's sh:in enumeration forbids it.
    vault = copy_vault(tmp_path)
    fdir = vault / "_data" / "framings"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "dm-epam-general.md").write_text(
        "---\n"
        'type: "[[RoleFraming]]"\n'
        'framingOf: "[[Program Manager and Technical Product Owner — EPAM]]"\n'
        "audience: general\n"
        'roleName: "Program Delivery Lead"\n'
        "---\n# dm-epam-general\n",
        encoding="utf-8",
    )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert not conforms
    assert "general" in report


def test_roleframing_duplicate_position_audience_rejected(tmp_path):
    # Two framings on the same (Position, audience) — projection couldn't choose
    # a roleName. The cross-node uniqueness guard (sh:sparql) must fire.
    vault = copy_vault(tmp_path)
    fdir = vault / "_data" / "framings"
    fdir.mkdir(parents=True, exist_ok=True)
    for slug, name in (("sse-acme-a", "Staff Engineer"), ("sse-acme-b", "Principal Engineer")):
        (fdir / f"{slug}.md").write_text(
            "---\n"
            'type: "[[RoleFraming]]"\n'
            'framingOf: "[[Senior Scrum Master — Verizon]]"\n'
            "audience: data-eng\n"
            f'roleName: "{name}"\n'
            f"---\n# {slug}\n",
            encoding="utf-8",
        )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert not conforms
    assert "share a Position and audience" in report

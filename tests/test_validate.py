"""The SHACL gate against the real vault: the seed data must conform (with
zero applications present — the public-CI baseline), and the evidence rule
must fire from both of its trigger directions."""

import shutil
from pathlib import Path

from rdflib import URIRef

from pipeline import build, validate

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_VAULT = REPO_ROOT / "vault"
SHAPES = REPO_ROOT / "validation" / "shapes.ttl"

RG = "https://joseph-higaki.github.io/resume-graph/vocab/rg#"
ID = "https://joseph-higaki.github.io/resume-graph/id/"


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
            URIRef(ID + "Personal%20Finances%20Lakehouse")) in g


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
        'usedSkill: [ "[[Kubernetes]]" ]\n'
        "---\n# K8s Migration\n",
        encoding="utf-8",
    )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert not conforms
    assert "Kubernetes" in report


def test_unclaimed_stub_skill_is_exempt(tmp_path):
    # A stub with no level and no usedSkill references — the shape an
    # Application-demanded skill has. Missing evidence must NOT fail it.
    vault = copy_vault(tmp_path)
    (vault / "_data" / "skills" / "Terraform.md").write_text(
        "---\n"
        'type: "[[Skill]]"\n'
        "prefLabel: Terraform\n"
        'broader: "[[devops]]"\n'
        "---\n# Terraform\n",
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
        'framingOf: "[[Delivery Manager — EPAM]]"\n'
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
            'framingOf: "[[Senior Software Engineer — Acme Consulting]]"\n'
            "audience: data-eng\n"
            f'roleName: "{name}"\n'
            f"---\n# {slug}\n",
            encoding="utf-8",
        )
    _, conforms, report = build_and_validate(vault, tmp_path / "out")
    assert not conforms
    assert "share a Position and audience" in report

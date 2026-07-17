"""Export mechanics against the fixture vault: IRI minting, wiki-link
resolution, datatype coercion, layer merge, dangling-link policy, and
Turtle ⇄ JSON-LD roundtrip sanity."""

from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF, XSD

from pipeline import build

TESTS_DIR = Path(__file__).parent
FIXTURE_VAULT = TESTS_DIR / "fixture-vault"
FIXTURE_VAULT_DANGLING = TESTS_DIR / "fixture-vault-dangling"

FX = "https://example.org/vocab/fx#"
ID = "https://example.org/id/"


def test_fixture_export_mints_and_resolves(tmp_path):
    g = build.export_graph(FIXTURE_VAULT, tmp_path)
    toaster = URIRef(ID + "toaster")

    # identity mints from file name under the root @base; folders never enter the IRI
    assert (toaster, RDF.type, URIRef(FX + "Gadget")) in g
    # wiki link resolves to the target note's minted IRI, percent-encoded
    assert (toaster, URIRef(FX + "poweredBy"), URIRef(ID + "AA%20Battery")) in g
    # context-coerced datatypes
    assert (toaster, URIRef(FX + "watts"), Literal(700, datatype=XSD.integer)) in g
    assert (toaster, URIRef("https://schema.org/datePublished"),
            Literal("2020-06-01", datatype=XSD.date)) in g
    # schema layer merged in alongside the data layer
    assert (URIRef(FX + "Gadget"), RDF.type, OWL.Class) in g


def test_dangling_link_fails_strict(tmp_path):
    with pytest.raises(build.BuildError, match="dangling wiki link"):
        build.export_graph(FIXTURE_VAULT_DANGLING, tmp_path)


def test_dangling_link_preserved_non_strict(tmp_path):
    g = build.export_graph(FIXTURE_VAULT_DANGLING, tmp_path, strict=False)
    orphan = URIRef(ID + "orphan")
    # the exporter keeps the edge, minting the missing target under the root base
    assert (orphan, RDF.type, URIRef(ID + "NoSuchClass")) in g


def test_jsonld_roundtrip_isomorphic(tmp_path):
    g = build.export_graph(FIXTURE_VAULT, tmp_path)
    build.write_outputs(g, tmp_path)
    g2 = Graph().parse(tmp_path / "graph.jsonld", format="json-ld")
    assert isomorphic(g, g2)

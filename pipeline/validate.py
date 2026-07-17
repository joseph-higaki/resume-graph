#!/usr/bin/env python3
"""validate.py — the SHACL gate: dist/graph.ttl against ontology/shapes.ttl.

allow_warnings=True is the severity contract: sh:Warning results (the advisory
ESCO shape) print in the report but don't fail; any sh:Violation exits 1.
inference stays off — subclass closure comes from the schema layer already
merged into the data graph.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import Graph

REPO_ROOT = Path(__file__).resolve().parents[1]


def run(graph_path: Path, shapes_path: Path) -> tuple[bool, str]:
    data = Graph().parse(graph_path, format="turtle")
    shapes = Graph().parse(shapes_path, format="turtle")
    conforms, _results_graph, results_text = shacl_validate(
        data_graph=data,
        shacl_graph=shapes,
        inference="none",
        allow_warnings=True,
    )
    return bool(conforms), results_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the built graph against the SHACL shapes.")
    parser.add_argument("--graph", type=Path, default=REPO_ROOT / "dist" / "graph.ttl")
    parser.add_argument("--shapes", type=Path, default=REPO_ROOT / "ontology" / "shapes.ttl")
    args = parser.parse_args()

    if not args.graph.exists():
        print(f"error: {args.graph} not found — run `make build` first", file=sys.stderr)
        return 1

    conforms, report = run(args.graph, args.shapes)
    print(report)
    if not conforms:
        print("SHACL gate: FAILED", file=sys.stderr)
        return 1
    print("SHACL gate: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

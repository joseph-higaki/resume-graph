#!/usr/bin/env python3
"""build.py — vault → dist/graph.ttl + dist/graph.jsonld.

Thin wrapper over the vendored Vault-LD exporter, run as a subprocess so the
pinned tool keeps its own CLI contract. Strict mode (the default) promotes the
exporter's *structural* warnings — dangling wiki links, fields missing from the
context, IRI collisions — to build failures: the graph must be closed over its
own links before SHACL is even worth running.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from rdflib import Graph

REPO_ROOT = Path(__file__).resolve().parents[1]
VENDORED_EXPORTER = REPO_ROOT / "pipeline" / "vendor" / "vault_to_rdf.py"

# Substrings of exporter warnings that mean the graph is structurally broken,
# not just noisy. Anything else on stderr passes through as a plain warning.
FATAL_WARNING_MARKERS = (
    "dangling wiki link",
    "not in context -> skipped",
    "mint the same IRI",
    "ambiguous note name",
)


class BuildError(RuntimeError):
    pass


def export_graph(vault: Path, out_dir: Path, strict: bool = True) -> Graph:
    """Run the vendored exporter; return schema + data layers merged into one Graph."""
    export_dir = out_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(VENDORED_EXPORTER), str(vault), "--out-dir", str(export_dir)],
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode != 0:
        raise BuildError(f"exporter exited {proc.returncode}")

    fatal = [line.strip() for line in proc.stderr.splitlines()
             if any(marker in line for marker in FATAL_WARNING_MARKERS)]
    if strict and fatal:
        raise BuildError("structural exporter warnings (strict mode):\n  "
                         + "\n  ".join(fatal))

    graph = Graph()
    graph.parse(export_dir / "schema.ttl", format="turtle")
    graph.parse(export_dir / "data.ttl", format="turtle")
    return graph


def write_outputs(graph: Graph, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=out_dir / "graph.ttl", format="turtle")
    # Compact JSON-LD keyed by the graph's own prefix map — enough for Comunica
    # and the site embed. Framing is a site concern (M4), not a build concern.
    context = {prefix: str(ns) for prefix, ns in graph.namespaces() if prefix}
    graph.serialize(destination=out_dir / "graph.jsonld", format="json-ld",
                    context=context, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/graph.{ttl,jsonld} from the vault.")
    parser.add_argument("--vault", type=Path, default=REPO_ROOT / "vault")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--no-strict", action="store_true",
                        help="report structural warnings without failing the build")
    args = parser.parse_args()

    try:
        graph = export_graph(args.vault, args.out, strict=not args.no_strict)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    write_outputs(graph, args.out)
    print(f"graph: {len(graph)} triples -> {args.out / 'graph.ttl'} (+ graph.jsonld)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

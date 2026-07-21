#!/usr/bin/env python3
"""project.py — full graph (+ optional overlay) → per-application projected graph.

Runs SPARQL over the merged graph to build a tailored CV subgraph, then writes
`<out-dir>/<slug>/graph.ttl` for the exports to consume. The exports are
unchanged and unaware: they take `--graph`, so a projection is just a different
graph pointed at the same `json_resume` / `pdf` code.

Two contracts drive the design:

- **Zero-application is the normal case here.** This public repo holds no
  Application instances (they live in the private overlay), so a bare
  `make project` must be a clean no-op, not an error. With no `--application`,
  every Application in the merged graph is projected — which in public CI is
  none.
- **`--extra-graph` is just more triples.** RDF merge means the overlay needs no
  special handling: parse both into one Graph and every query below sees the
  union. This is why the private repo can add Applications without this repo
  knowing anything about them.

The Application node deliberately **survives** into the projected graph. It
carries `rg:emphasizes`, which the exports read for ordering, and it records
which application an artifact was built for. Projected graphs are private-repo
artifacts, so the employer name in them is not a leak — but it is exactly why
projections never land in this repo's `dist/`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.parse
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef

RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")
SDO = Namespace("https://schema.org/")
NS = {"rg": RG, "sdo": SDO}

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = REPO_ROOT / "dist" / "graph.ttl"
DEFAULT_OUT = REPO_ROOT / "dist" / "applications"


class ProjectionError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# loading & resolution
# --------------------------------------------------------------------------- #

def load_graph(base: Path, extra: list[Path] | None = None) -> Graph:
    """Parse the base graph plus any overlays into one Graph (RDF merge)."""
    g = Graph()
    g.parse(base, format="turtle")
    for path in extra or []:
        if not path.exists():
            raise ProjectionError(f"extra graph not found: {path}")
        g.parse(path, format="turtle")
    return g


def applications(g: Graph) -> list[URIRef]:
    return sorted(
        (URIRef(str(r.app)) for r in g.query(
            "SELECT ?app WHERE { ?app a rg:Application }", initNs=NS)),
        key=str,
    )


def resolve_application(g: Graph, ident: str) -> URIRef:
    """Resolve an IRI or a bare slug to exactly one Application in the graph.

    Slugs are matched against the percent-encoded tail of each Application IRI,
    so `--application acme-kg-engineer` works without the caller knowing the ID
    base. Ambiguity is an error rather than a first-match — two applications
    resolving from one slug means the wrong CV could be built silently."""
    found = applications(g)
    if "://" in ident:
        target = URIRef(ident)
        if target not in found:
            raise ProjectionError(f"no rg:Application in the graph with IRI {ident}")
        return target

    wanted = urllib.parse.quote(ident)
    matches = [a for a in found if str(a).rsplit("/", 1)[-1] in (wanted, ident)]
    if not matches:
        known = ", ".join(slug_for(a) for a in found) or "(none)"
        raise ProjectionError(f"no rg:Application matching {ident!r}; known: {known}")
    if len(matches) > 1:
        raise ProjectionError(f"{ident!r} matches {len(matches)} applications: "
                              + ", ".join(str(m) for m in matches))
    return matches[0]


def slug_for(app: URIRef) -> str:
    """Filesystem-safe directory name from an Application IRI's local part."""
    tail = urllib.parse.unquote(str(app).rsplit("/", 1)[-1])
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in tail).strip("-").lower()


def dir_for(g: Graph, app: URIRef) -> str:
    """Output directory name: `rg:publicId` when set, else the readable slug.

    The two names carry different intent. A slug is for the author's disk; a
    publicId is an unguessable segment for a page served from the public Pages
    site, where the folder name is the only thing standing between a tailored CV
    and a search result. Falling back to the slug keeps this repo's zero-config
    behaviour (and the fixtures) unchanged — an application opts *in* to being
    publishable by carrying an id."""
    public = next(g.objects(app, RG.publicId), None)
    return str(public) if public else slug_for(app)


def audiences_of(g: Graph, app: URIRef) -> set[str]:
    return {str(r.a) for r in g.query(
        "SELECT ?a WHERE { ?app rg:audience ?a }",
        initBindings={"app": app}, initNs=NS)}


# --------------------------------------------------------------------------- #
# projection stages
# --------------------------------------------------------------------------- #

def _apply_role_framings(g: Graph, app: URIRef) -> None:
    """ADR 0001 §4 steps A+B: audience-specific `sdo:roleName` override.

    DELETE/INSERT rather than CONSTRUCT because this overrides one value in
    place; CONSTRUCT would force re-emitting every kept triple and then
    reconciling a position carrying both the default and framed roleName."""
    conflicts = list(g.query("""
        SELECT ?pos (COUNT(DISTINCT ?framed) AS ?n) WHERE {
            ?f a rg:RoleFraming ; rg:framingOf ?pos ; rg:audience ?a ; sdo:roleName ?framed .
            ?app rg:audience ?a .
        } GROUP BY ?pos HAVING (COUNT(DISTINCT ?framed) > 1)
    """, initBindings={"app": app}, initNs=NS))
    if conflicts:
        names = ", ".join(str(r.pos) for r in conflicts)
        raise ProjectionError(
            f"{app} matches conflicting RoleFramings for: {names}. "
            "An application declaring two specific audiences is almost always an "
            "authoring mistake — see docs/adr/0001-roleframing-projection.md §4.")

    g.update("""
        DELETE { ?pos sdo:roleName ?default }
        INSERT { ?pos sdo:roleName ?framed }
        WHERE {
            ?pos a rg:Position ; sdo:roleName ?default .
            ?f a rg:RoleFraming ; rg:framingOf ?pos ; rg:audience ?a ; sdo:roleName ?framed .
            ?app rg:audience ?a .
        }
    """, initBindings={"app": app}, initNs=NS)


def _select_bullets(g: Graph, app: URIRef) -> int:
    """Drop Bullets whose `rg:audience` is not among the Application's.

    An Application declaring no audiences keeps every bullet — silently emptying
    the experience section would be a worse failure than an untailored CV."""
    wanted = audiences_of(g, app)
    if not wanted:
        return 0
    doomed = {URIRef(str(r.b)) for r in g.query(
        "SELECT ?b ?a WHERE { ?b a rg:Bullet ; rg:audience ?a }", initNs=NS)
        if str(r.a) not in wanted}
    for b in doomed:
        _purge(g, b)
    return len(doomed)


def _apply_excludes(g: Graph, app: URIRef) -> int:
    """Remove `rg:excludes` targets and anything hanging off them.

    Deleting a node as both subject and object matters: dropping a Project must
    also drop `?skill rg:evidencedBy <project>`, or the projection leaves a
    dangling reference. If that was a skill's only evidence the projected graph
    now fails the SHACL evidence rule — which is correct and deliberate: the
    projection just made a claim it can no longer support."""
    targets = [URIRef(str(r.n)) for r in g.query(
        "SELECT ?n WHERE { ?app rg:excludes ?n }",
        initBindings={"app": app}, initNs=NS)]
    for node in targets:
        _purge(g, node)
    return len(targets)


def _purge(g: Graph, node: URIRef) -> None:
    """Delete a node's triples in both directions, cascading to its Bullets."""
    for bullet in list(g.subjects(RG.bulletOf, node)):
        g.remove((bullet, None, None))
        g.remove((None, None, bullet))
    g.remove((node, None, None))
    g.remove((None, None, node))


def _prune_unevidenced_claims(g: Graph, app: URIRef) -> tuple[int, int]:
    """Drop skill claims whose evidence was just excluded. Returns (purged, demoted).

    This is the evidence rule applied to the projection itself. `rg:excludes` on
    a Project silently orphans every skill that Project was the sole evidence
    for; leaving those skills on the CV would reintroduce exactly the
    keyword-stuffing the SHACL gate exists to prevent — the author would be
    claiming a skill whose proof they just deleted.

    Demanded skills are demoted rather than purged. A skill the Application
    `rg:demands` but that no longer has evidence is the gap-analysis signal, and
    the shape exempts unclaimed stubs — so stripping `rg:level` and inbound
    `rg:usedSkill` turns it into precisely that. Everything else is purged: an
    unevidenced, unclaimed, undemanded skill contributes nothing to a CV.

    The two FILTER NOT EXISTS clauses must stay a mirror of `rgs:EvidenceRuleShape`
    in shapes.ttl: evidence flows through two independent channels (`rg:evidencedBy`
    = used in real work, `rg:certifies` = attested by credential) and either
    satisfies the gate. Drop the certifies clause and the projection purges
    credential-only skills the gate would have passed — silently narrowing the CV
    below what the author can defend.

    One pass suffices — purging a skill removes no other skill's evidence."""
    orphans = [URIRef(str(r.sk)) for r in g.query("""
        SELECT DISTINCT ?sk WHERE {
            ?sk a rg:Skill .
            { ?sk rg:level ?level } UNION { ?work rg:usedSkill ?sk }
            FILTER NOT EXISTS { ?sk rg:evidencedBy ?evidence }
            FILTER NOT EXISTS { ?cert rg:certifies ?sk }
        }""", initNs=NS)]
    demanded = set(g.objects(app, RG.demands))

    purged = demoted = 0
    for skill in orphans:
        if skill in demanded:
            g.remove((skill, RG.level, None))
            g.remove((None, RG.usedSkill, skill))
            demoted += 1
        else:
            _purge(g, skill)
            purged += 1
    return purged, demoted


def _substitute_job_title(g: Graph, app: URIRef) -> bool:
    """Retarget the Person's `sdo:jobTitle` to the Application's `rg:targetRole`.

    The header is the first thing read and the cheapest place to be filtered out:
    a title of record that names the wrong discipline can end the review before
    the evidence is seen. Substituting the target role is the same honest
    re-emphasis RoleFraming applies to positions (ADR 0001 §1) — a CV headline
    states the role applied for, while the Experience section keeps every real
    title unchanged, so nothing here claims a title that was never held.

    `rg:targetRole` is mandatory on an Application (ApplicationShape), so this
    always fires during a projection and never during a plain build."""
    target = next(g.objects(app, RG.targetRole), None)
    if target is None:
        return False
    persons = [URIRef(str(r.p)) for r in g.query(
        "SELECT ?p WHERE { ?p a rg:Person }", initNs=NS)]
    for person in persons:
        g.remove((person, SDO.jobTitle, None))
        g.add((person, SDO.jobTitle, Literal(str(target))))
    return bool(persons)


def _substitute_summary(g: Graph, app: URIRef) -> bool:
    """Swap the Person's default `sdo:description` for the Application's summary.

    `build_model` reads the résumé summary from `sdo:description`, so rewriting
    that one triple retargets the opening paragraph with no export change."""
    summary = next(g.objects(app, RG.summary), None)
    if summary is None:
        return False
    persons = list(g.query("SELECT ?p WHERE { ?p a rg:Person }", initNs=NS))
    for row in persons:
        g.remove((URIRef(str(row.p)), SDO.description, None))
        g.add((URIRef(str(row.p)), SDO.description, Literal(str(summary))))
    return bool(persons)


def _strip_framings(g: Graph) -> int:
    """ADR 0001 §4 step C — framings are scaffolding, never CV content."""
    framings = [URIRef(str(r.f)) for r in g.query(
        "SELECT ?f WHERE { ?f a rg:RoleFraming }", initNs=NS)]
    for f in framings:
        g.remove((f, None, None))
    return len(framings)


def project(graph: Graph, app: URIRef) -> tuple[Graph, dict]:
    """Apply every projection stage to a copy of `graph`; return it plus stats.

    Stages are order-independent except that framings are stripped last (they
    must still be readable when the roleName substitution runs)."""
    g = Graph()
    for prefix, ns in graph.namespaces():
        g.bind(prefix, ns)
    g += graph

    before = len(g)
    _apply_role_framings(g, app)
    dropped_bullets = _select_bullets(g, app)
    excluded = _apply_excludes(g, app)
    purged, demoted = _prune_unevidenced_claims(g, app)   # must follow excludes
    summarized = _substitute_summary(g, app)
    retitled = _substitute_job_title(g, app)
    stripped = _strip_framings(g)

    return g, {
        "job_title_substituted": retitled,
        "triples_before": before,
        "triples_after": len(g),
        "bullets_dropped": dropped_bullets,
        "nodes_excluded": excluded,
        "skills_purged": purged,
        "skills_demoted": demoted,
        "summary_substituted": summarized,
        "framings_stripped": stripped,
        "audiences": sorted(audiences_of(graph, app)) or ["(all)"],
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

PRIVATE_META = (
    '<meta name="robots" content="noindex, nofollow, noarchive">\n'
    '<meta name="referrer" content="no-referrer">'
)


def _stamp_private(path: Path) -> None:
    """Stamp the unlisted-page metas into a generated page, in place.

    Every projected page is employer-tailored, so this is unconditional rather
    than a publish-time flag: a file that starts on disk and later gets copied to
    a public host must already carry its own refusal.

    `noindex` is the one that does work, and it is why the site's robots.txt must
    NOT disallow this path — a disallowed URL is never fetched, so the meta is
    never read, and a URL that leaks from elsewhere gets indexed anyway. Allow
    the crawl, refuse the index.

    `no-referrer` closes the likelier leak: the URL segment is the only thing
    keeping the page unlisted, and every outbound click from an unhardened page
    hands that segment to a third party in the Referer header.

    Neither is access control. Pages serves no custom headers, so the
    non-HTML siblings (resume.pdf, graph.ttl, resume.json) carry nothing at
    all — they rely purely on the URL being unguessable."""
    html = path.read_text(encoding="utf-8")
    if PRIVATE_META not in html:
        path.write_text(html.replace("<head>", f"<head>\n{PRIVATE_META}", 1), encoding="utf-8")


def _run_exports(dest: Path) -> None:
    """Render resume.pdf + resume.json + graph.html from a projected graph.

    Imported lazily: WeasyPrint pulls in native libraries, and a bare
    `make project` (the zero-application no-op) has no business paying for them.

    graph.html inlines its data, so the projected viewer opens from file:// with
    no server — and it shows the *tailored* subgraph, which is the artifact worth
    looking at: what the exclusions and audience filter actually removed. It is
    duplicated to index.html so the directory is directly servable as a URL path;
    a redirect stub would cost a round trip on the one page a reader lands on."""
    from .exports import graph_html, json_resume, pdf

    graph = dest / "graph.ttl"
    pdf.write_pdf(graph, dest / "resume.pdf", dest / "resume.html")
    json_resume.write_json(graph, dest / "resume.json")
    (dest / "graph.html").write_text(
        graph_html.render_html(graph_html.extract(graph)), encoding="utf-8")
    for page in ("graph.html", "resume.html"):
        _stamp_private(dest / page)
    shutil.copyfile(dest / "graph.html", dest / "index.html")

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project the graph into per-application CV subgraphs.")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--extra-graph", type=Path, action="append", default=[],
                        help="overlay graph to merge (repeatable); the private "
                             "repo's Application notes arrive this way")
    parser.add_argument("--application", default=None,
                        help="Application IRI or slug; omit to project all "
                             "(none in this repo — a clean no-op)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--clean", action="store_true",
                        help="remove each target directory before writing")
    parser.add_argument("--export", action="store_true",
                        help="also write resume.pdf + resume.json + graph.html beside each "
                             "projected graph")
    args = parser.parse_args()

    if not args.graph.exists():
        print(f"error: {args.graph} not found — run `make build` first", file=sys.stderr)
        return 1

    try:
        merged = load_graph(args.graph, args.extra_graph)
        targets = ([resolve_application(merged, args.application)]
                   if args.application else applications(merged))
    except ProjectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not targets:
        print("no rg:Application in the graph — nothing to project "
              "(expected in this repo; applications live in the private overlay)")
        return 0

    for app in targets:
        try:
            projected, stats = project(merged, app)
        except ProjectionError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        dest = args.out_dir / dir_for(merged, app)
        if args.clean and dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        projected.serialize(destination=dest / "graph.ttl", format="turtle")
        if args.export:
            _run_exports(dest)
        print(f"projected {slug_for(app)}: {stats['triples_before']} -> "
              f"{stats['triples_after']} triples "
              f"(audiences {'+'.join(stats['audiences'])}; "
              f"-{stats['bullets_dropped']} bullets, "
              f"-{stats['nodes_excluded']} excluded, "
              f"-{stats['skills_purged']} skills unevidenced, "
              f"{stats['skills_demoted']} demoted to gaps, "
              f"summary={'yes' if stats['summary_substituted'] else 'default'}) "
              f"-> {dest / 'graph.ttl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

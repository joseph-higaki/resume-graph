#!/usr/bin/env python3
"""graph_html.py — dist/graph.ttl → self-contained dist/graph.html.

A dependency-free preview of the knowledge graph: one HTML file with the nodes
and edges embedded as JSON and a vanilla-canvas force layout. NOT the M4/M5 site
(no Astro / Sigma / Comunica toolchain) — this is the "look at the data now and
start tweaking" artifact. It opens over file:// or any static server because the
data is inlined, so there is no fetch/CORS step.

Encoding (per project brief): nodes coloured by rdf:type from a CVD-validated
8-slot palette that doubles as the legend; node SIZE is the required secondary
channel so the eight hues stay separable under colour-blindness. Skills carry a
`skos:broader` edge to their category hub, so the force layout clusters them —
the AWS/GCP cloud region reads at a glance with no interaction. Only résumé
instances + the SKOS category tree are shown; the ontology/schema layer and
bullet notes are filtered out (bullets surface as prose in the side panel)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rdflib import Graph, Namespace

from .resume_model import REPO_ROOT

RG = Namespace("https://joseph-higaki.github.io/resume-graph/vocab/rg#")
SDO = Namespace("https://schema.org/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

# Ordered: legend renders in this order; drawing order is small→large so hubs
# sit on top. Colours are exact dark-surface steps of the CVD-validated 8-slot
# palette; size is the secondary (CVD) channel — hubs large, leaves small. The
# assignment is graph-aware: Skill(aqua) is the dominant type and links to
# Category/Position/Project, so those neighbours get red/violet/yellow (all far
# from aqua). The one green↔aqua-confusable slot (green) goes to Education, which
# is peripheral and never touches a skill.
TYPE_META = {
    "Person":        {"color": "#3987e5", "size": 15, "legend": "Person"},
    "Category":      {"color": "#e66767", "size": 12, "legend": "Skill category"},
    "Position":      {"color": "#9085e9", "size": 10, "legend": "Position"},
    "Organization":  {"color": "#d55181", "size": 10, "legend": "Organization"},
    "Project":       {"color": "#c98500", "size": 8,  "legend": "Project"},
    "Certification": {"color": "#d95926", "size": 8,  "legend": "Certification"},
    "Education":     {"color": "#008300", "size": 8,  "legend": "Education"},
    "Skill":         {"color": "#199e70", "size": 5,  "legend": "Skill"},
}

# (class, type-name) pairs to harvest as nodes.
_CLASSES = [
    (RG.Person, "Person"), (RG.Position, "Position"),
    (RG.Organization, "Organization"), (RG.Project, "Project"),
    (RG.Skill, "Skill"), (RG.Certification, "Certification"),
    (RG.Education, "Education"), (SKOS.Concept, "Category"),
]

# predicate → edge kind label (only edges whose both ends are nodes are kept).
_EDGE_PREDS = {
    RG.heldBy: "heldBy",
    RG.organization: "org",
    RG.usedSkill: "usedSkill",
    RG.deliveredDuring: "deliveredDuring",
    SKOS.broader: "broader",
    RG.evidencedBy: "evidencedBy",
    RG.certifies: "certifies",
    SDO.recognizedBy: "recognizedBy",
}


def _label(g: Graph, s) -> str:
    for pred in (SKOS.prefLabel, SDO.name, SDO.roleName):
        v = g.value(s, pred)
        if v:
            return str(v)
    return str(s).rsplit("/", 1)[-1]


def _attrs(g: Graph, s, typ: str) -> dict:
    """Small type-specific literal bag shown in the side panel."""
    def lit(p):
        v = g.value(s, p)
        return str(v) if v is not None else None

    if typ == "Person":
        return _drop({"summary": lit(SDO.description), "email": lit(SDO.email)})
    if typ == "Position":
        org = g.value(s, RG.organization)
        return _drop({
            "role": lit(SDO.roleName),
            "org": _label(g, org) if org else None,
            "start": lit(SDO.startDate), "end": lit(SDO.endDate),
            "titleOfRecord": lit(RG.titleOfRecord),
        })
    if typ == "Project":
        return _drop({"description": lit(SDO.description), "start": lit(SDO.startDate)})
    if typ == "Skill":
        cat = g.value(s, SKOS.broader)
        return _drop({"level": lit(RG.level),
                      "category": _label(g, cat) if cat else None})
    if typ == "Category":
        return _drop({"definition": lit(SKOS.definition)})
    if typ == "Certification":
        org = g.value(s, SDO.recognizedBy)
        return _drop({"issuer": _label(g, org) if org else None})
    if typ == "Education":
        org = g.value(s, SDO.recognizedBy)
        return _drop({"credential": lit(SDO.credentialCategory),
                      "issuer": _label(g, org) if org else None})
    return {}


def _drop(d: dict) -> dict:
    return {k: v for k, v in d.items() if v}


def extract(graph_path: Path) -> dict:
    from rdflib.namespace import RDF

    g = Graph().parse(graph_path, format="turtle")

    nodes: dict[str, dict] = {}
    for cls, typ in _CLASSES:
        for s in g.subjects(RDF.type, cls):
            iri = str(s)
            meta = TYPE_META[typ]
            nodes[iri] = {
                "id": iri, "label": _label(g, s), "type": typ,
                "color": meta["color"], "size": meta["size"],
                "attrs": _attrs(g, s, typ),
            }

    links = []
    for pred, kind in _EDGE_PREDS.items():
        for s, o in g.subject_objects(pred):
            si, oi = str(s), str(o)
            if si in nodes and oi in nodes:
                links.append({"source": si, "target": oi, "kind": kind})

    # bullets grouped by owning Position/Project — the panel's prose excerpt.
    bullets: dict[str, list[str]] = {}
    for b in g.subjects(RDF.type, RG.Bullet):
        owner = g.value(b, RG.bulletOf)
        text = g.value(b, SDO.text)
        if owner is not None and text is not None and str(owner) in nodes:
            bullets.setdefault(str(owner), []).append(str(text))

    return {
        "nodes": list(nodes.values()),
        "links": links,
        "bullets": bullets,
        "types": [{"type": t, **m} for t, m in TYPE_META.items()],
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return _TEMPLATE.replace("/*__DATA__*/null", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the self-contained dist/graph.html viewer.")
    parser.add_argument("--graph", type=Path, default=REPO_ROOT / "dist" / "graph.ttl")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist" / "graph.html")
    args = parser.parse_args()

    if not args.graph.exists():
        print(f"error: {args.graph} not found — run `make build` first", file=sys.stderr)
        return 1

    data = extract(args.graph)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(data), encoding="utf-8")
    print(f"graph.html: {len(data['nodes'])} nodes, {len(data['links'])} edges "
          f"({args.out.stat().st_size // 1024} KB) -> {args.out}")
    return 0


# --------------------------------------------------------------------------- #
# The viewer. Self-contained: CSS + JS + data inlined. `/*__DATA__*/null` is the
# single injection point (a comment-guarded literal so the file is valid HTML
# even before injection, and .replace avoids f-string brace escaping).
# --------------------------------------------------------------------------- #
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>resume-graph — knowledge graph</title>
<style>
  :root {
    --bg:#0b111b; --surface:#0f1620; --panel:#131c28; --line:#1e2a3a;
    --ink:#e6edf6; --muted:#8b9bb2; --faint:#5b6b82; --accent:#3987e5;
    --mono:"IBM Plex Mono",ui-monospace,"Cascadia Code","SF Mono",Menlo,monospace;
    --sans:"Space Grotesk",system-ui,-apple-system,"Segoe UI",sans-serif;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--ink);
    font-family:var(--sans); overflow:hidden; }
  #stage { position:fixed; inset:0; }
  canvas { display:block; width:100%; height:100%; touch-action:none; cursor:grab; }
  canvas.grabbing { cursor:grabbing; }

  /* top bar */
  #bar { position:fixed; top:0; left:0; right:0; display:flex; gap:12px;
    align-items:center; padding:10px 14px; z-index:5;
    background:linear-gradient(180deg,rgba(11,17,27,.92),rgba(11,17,27,0)); }
  #bar h1 { font-size:13px; letter-spacing:.14em; text-transform:uppercase;
    margin:0; color:var(--muted); font-weight:600; }
  #bar h1 b { color:var(--ink); font-weight:700; }
  #search { margin-left:auto; background:var(--surface); border:1px solid var(--line);
    color:var(--ink); font-family:var(--mono); font-size:12px; padding:6px 10px;
    border-radius:7px; width:200px; }
  #search::placeholder { color:var(--faint); }
  .btn { background:var(--surface); border:1px solid var(--line); color:var(--muted);
    font-family:var(--mono); font-size:11px; padding:6px 10px; border-radius:7px;
    cursor:pointer; }
  .btn:hover { color:var(--ink); border-color:var(--accent); }
  .btn.on { color:var(--bg); background:var(--accent); border-color:var(--accent); }

  /* legend */
  #legend { position:fixed; left:14px; bottom:14px; z-index:5; background:rgba(15,22,32,.86);
    border:1px solid var(--line); border-radius:10px; padding:10px 12px; backdrop-filter:blur(6px); }
  #legend .lg-title { font-size:10px; letter-spacing:.12em; text-transform:uppercase;
    color:var(--faint); margin-bottom:7px; }
  .lg-row { display:flex; align-items:center; gap:8px; font-size:12px; padding:2px 0;
    cursor:pointer; color:var(--muted); font-family:var(--mono); user-select:none; }
  .lg-row:hover { color:var(--ink); }
  .lg-row.off { opacity:.35; text-decoration:line-through; }
  .lg-dot { width:11px; height:11px; border-radius:50%; flex:0 0 auto; }
  .lg-n { margin-left:auto; color:var(--faint); font-size:10px; }

  /* detail panel */
  #panel { position:fixed; top:0; right:0; bottom:0; width:340px; z-index:6;
    background:var(--panel); border-left:1px solid var(--line); padding:0;
    transform:translateX(100%); transition:transform .22s ease; overflow-y:auto; }
  #panel.open { transform:translateX(0); }
  @media (prefers-reduced-motion:reduce){ #panel{ transition:none; } }
  #panel .p-head { padding:18px 18px 12px; border-bottom:1px solid var(--line);
    position:sticky; top:0; background:var(--panel); }
  #panel .p-type { font-family:var(--mono); font-size:11px; letter-spacing:.1em;
    text-transform:uppercase; display:inline-flex; align-items:center; gap:7px; }
  #panel .p-type .lg-dot { width:9px; height:9px; }
  #panel h2 { margin:9px 0 0; font-size:19px; line-height:1.25; }
  #panel .p-close { position:absolute; top:14px; right:14px; background:none; border:none;
    color:var(--muted); font-size:20px; cursor:pointer; line-height:1; }
  #panel .p-close:hover { color:var(--ink); }
  #panel .p-body { padding:14px 18px 40px; }
  .kv { margin:0 0 12px; }
  .kv .k { font-family:var(--mono); font-size:10px; letter-spacing:.08em;
    text-transform:uppercase; color:var(--faint); margin-bottom:3px; }
  .kv .v { font-size:13.5px; line-height:1.5; color:var(--ink); }
  .rel-group { margin-top:14px; }
  .rel-group .rg-t { font-family:var(--mono); font-size:10px; letter-spacing:.08em;
    text-transform:uppercase; color:var(--faint); margin-bottom:6px;
    display:flex; justify-content:space-between; }
  .chip { display:inline-flex; align-items:center; gap:6px; font-size:12px;
    background:var(--surface); border:1px solid var(--line); color:var(--ink);
    padding:3px 9px; border-radius:20px; margin:0 5px 5px 0; cursor:pointer;
    font-family:var(--mono); }
  .chip:hover { border-color:var(--accent); }
  .chip .lg-dot { width:8px; height:8px; }
  ul.prose { margin:6px 0 0; padding-left:16px; }
  ul.prose li { font-size:12.5px; line-height:1.45; color:var(--muted); margin:4px 0; }
  #hint { position:fixed; right:14px; bottom:14px; z-index:4; color:var(--faint);
    font-family:var(--mono); font-size:11px; text-align:right; pointer-events:none; }
</style>
</head>
<body>
<div id="stage"><canvas id="c"></canvas></div>
<div id="bar">
  <h1><b>resume</b>-graph</h1>
  <button class="btn" id="reset-btn" title="Re-run layout & recenter">reset</button>
  <input id="search" placeholder="search nodes…" autocomplete="off">
</div>
<div id="legend"><div class="lg-title">node type · click to filter</div><div id="lg-rows"></div></div>
<aside id="panel"><div class="p-head"><button class="p-close" id="p-close">×</button>
  <span class="p-type" id="p-type"></span><h2 id="p-title"></h2></div>
  <div class="p-body" id="p-body"></div></aside>
<div id="hint">scroll = zoom · drag = pan / move node · click = inspect</div>

<script id="data" type="application/json">/*__DATA__*/null</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- model ---------------------------------------------------------------
const byId = new Map();
DATA.nodes.forEach(n => {
  n.x = (Math.random()-.5)*600; n.y = (Math.random()-.5)*600;
  n.vx = 0; n.vy = 0; n.deg = 0; byId.set(n.id, n);
});
const links = DATA.links.filter(l => byId.has(l.source) && byId.has(l.target))
  .map(l => ({ s: byId.get(l.source), t: byId.get(l.target), kind: l.kind }));
links.forEach(l => { l.s.deg++; l.t.deg++; });
// adjacency for highlight + panel
const adj = new Map();
DATA.nodes.forEach(n => adj.set(n.id, []));
links.forEach(l => { adj.get(l.s.id).push({ o:l.t, kind:l.kind, dir:"out" });
                     adj.get(l.t.id).push({ o:l.s, kind:l.kind, dir:"in" }); });
const typeColor = Object.fromEntries(DATA.types.map(t => [t.type, t.color]));
const hidden = new Set();

// ---- force layout --------------------------------------------------------
// Plain O(n²) Verlet-ish sim: repulsion + link springs + gravity to origin.
// n≈170 so the quadratic loop is trivial; no quadtree needed.
const REST = { broader:55, usedSkill:80, evidencedBy:95, default:70 };
let alpha = 1;
function tick() {
  const nodes = DATA.nodes;
  // repulsion (charge scales with node size so hubs clear space)
  for (let i=0;i<nodes.length;i++){ const a=nodes[i];
    for (let j=i+1;j<nodes.length;j++){ const b=nodes[j];
      let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy||.01;
      if (d2>90000) continue;                 // ignore far pairs (perf + looseness)
      const d=Math.sqrt(d2);
      const f=(220*(a.size+b.size)/6)/d2;
      const fx=dx/d*f, fy=dy/d*f;
      a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
    }
  }
  // springs
  for (const l of links){ const a=l.s, b=l.t;
    let dx=b.x-a.x, dy=b.y-a.y, d=Math.hypot(dx,dy)||.01;
    const rest=REST[l.kind]||REST.default;
    const f=(d-rest)*0.02;
    const fx=dx/d*f, fy=dy/d*f;
    a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
  }
  // gravity + integrate
  for (const n of nodes){
    if (n===dragged) continue;
    n.vx-=n.x*0.0016; n.vy-=n.y*0.0016;
    n.vx*=0.86; n.vy*=0.86;
    n.x+=n.vx*alpha; n.y+=n.vy*alpha;
  }
  alpha=Math.max(alpha*0.995, 0.02);
}

// ---- canvas / camera -----------------------------------------------------
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
let W=0, H=0, DPR=Math.min(window.devicePixelRatio||1, 2);
const cam = { x:0, y:0, k:1 };  // world = (screen - center)/k - cam? see toWorld
function resize(){ W=canvas.clientWidth; H=canvas.clientHeight;
  canvas.width=W*DPR; canvas.height=H*DPR; }
window.addEventListener("resize", resize); resize();
// center camera initially
cam.x = 0; cam.y = 0; cam.k = 0.9;
function toScreen(p){ return { x:(p.x-cam.x)*cam.k+W/2, y:(p.y-cam.y)*cam.k+H/2 }; }
function toWorld(sx,sy){ return { x:(sx-W/2)/cam.k+cam.x, y:(sy-H/2)/cam.k+cam.y }; }

let selected=null, hover=null;
function neighborsOf(n){ return n ? new Set(adj.get(n.id).map(e=>e.o.id)) : null; }

function draw(){
  ctx.setTransform(DPR,0,0,DPR,0,0);
  ctx.clearRect(0,0,W,H);
  const focus = selected || hover;
  const near = neighborsOf(focus);

  // edges
  ctx.lineWidth = 1;
  for (const l of links){
    if (hidden.has(l.s.type)||hidden.has(l.t.type)) continue;
    const a=toScreen(l.s), b=toScreen(l.t);
    const lit = focus && (l.s===focus||l.t===focus);
    const broad = l.kind==="broader";
    let stroke;
    if (lit) stroke = "rgba(160,190,230,.6)";
    else if (broad) stroke = `rgba(230,103,103,${focus?0.10:0.22})`;
    else stroke = `rgba(120,140,170,${focus?0.05:0.10})`;
    ctx.strokeStyle = stroke;
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  }
  // nodes (small→large so hubs draw on top)
  const order=[...DATA.nodes].sort((p,q)=>p.size-q.size);
  ctx.font = "12px "+getComputedStyle(document.body).getPropertyValue("--mono");
  ctx.textAlign="center"; ctx.textBaseline="middle";
  for (const n of order){
    if (hidden.has(n.type)) continue;
    const s=toScreen(n); const r=(n.size+ (n.deg>8?2:0))*Math.max(cam.k,.55);
    const isNear = !focus || n===focus || (near&&near.has(n.id));
    ctx.globalAlpha = isNear ? 1 : 0.14;
    ctx.beginPath(); ctx.arc(s.x,s.y,r,0,6.2832);
    ctx.fillStyle=n.color; ctx.fill();
    if (n===selected){ ctx.lineWidth=2.5; ctx.strokeStyle="#e6edf6"; ctx.stroke(); }
    // labels: hubs always; others when zoomed-in or focused/near
    const showLabel = n.type==="Category"||n.type==="Person"||
      (cam.k>1.15 && n.size>=8) || (focus && isNear);
    if (showLabel && isNear){
      ctx.globalAlpha = 1;
      ctx.fillStyle = "rgba(230,237,246,.92)";
      ctx.fillText(n.label, s.x, s.y - r - 8);
    }
  }
  ctx.globalAlpha=1;
}

// ---- main loop -----------------------------------------------------------
function frame(){ if(alpha>0.021||dragged) tick(); draw(); raf=requestAnimationFrame(frame); }
let raf;
function run(){
  if (REDUCED){ for(let i=0;i<400;i++) tick(); draw();
    (function loop(){ draw(); raf=requestAnimationFrame(loop); })(); }
  else frame();
}

// ---- interaction ---------------------------------------------------------
let dragged=null, panning=false, moved=false, last={x:0,y:0}, downNode=null;
function pick(sx,sy){
  let best=null, bestD=Infinity;
  for (const n of DATA.nodes){ if(hidden.has(n.type)) continue;
    const s=toScreen(n); const r=(n.size+2)*Math.max(cam.k,.55)+4;
    const d=(s.x-sx)**2+(s.y-sy)**2;
    if (d<r*r && d<bestD){ best=n; bestD=d; } }
  return best;
}
canvas.addEventListener("pointerdown", e=>{
  canvas.setPointerCapture(e.pointerId); moved=false; last={x:e.clientX,y:e.clientY};
  const n=pick(e.offsetX,e.offsetY); downNode=n;
  if(n){ dragged=n; alpha=Math.max(alpha,.5); } else { panning=true; canvas.classList.add("grabbing"); }
});
canvas.addEventListener("pointermove", e=>{
  if(Math.abs(e.clientX-last.x)+Math.abs(e.clientY-last.y)>3) moved=true;
  if(dragged){ const w=toWorld(e.offsetX,e.offsetY); dragged.x=w.x; dragged.y=w.y; dragged.vx=0; dragged.vy=0; }
  else if(panning){ cam.x-=(e.clientX-last.x)/cam.k; cam.y-=(e.clientY-last.y)/cam.k; last={x:e.clientX,y:e.clientY}; }
  else { const n=pick(e.offsetX,e.offsetY); if(n!==hover){ hover=n; canvas.style.cursor=n?"pointer":"grab"; } }
});
canvas.addEventListener("pointerup", e=>{
  if(!moved && downNode) select(downNode);
  else if(!moved && !downNode) select(null);
  dragged=null; panning=false; canvas.classList.remove("grabbing");
});
canvas.addEventListener("wheel", e=>{
  e.preventDefault();
  const w=toWorld(e.offsetX,e.offsetY);
  cam.k=Math.min(4, Math.max(.25, cam.k*(e.deltaY<0?1.12:0.89)));
  const w2=toWorld(e.offsetX,e.offsetY); cam.x+=w.x-w2.x; cam.y+=w.y-w2.y;
}, {passive:false});

// ---- side panel ----------------------------------------------------------
const panel=document.getElementById("panel");
const AT = { Position:["role","org","start","end","titleOfRecord"],
  Project:["description","start"], Skill:["level","category"],
  Person:["summary","email"], Category:["definition"],
  Certification:["issuer"], Education:["credential","issuer"] };
const KLABEL = { role:"Role", org:"Organization", start:"Start", end:"End",
  titleOfRecord:"Title of record", description:"Description", level:"Level",
  category:"Category", summary:"Summary", email:"Email", definition:"Definition",
  issuer:"Issuer", credential:"Credential" };
const REL = { usedSkill:"Skills used", broader:"Category", evidencedBy:"Evidence",
  certifies:"Certifies", org:"Organization", heldBy:"Held by",
  deliveredDuring:"Delivered during", recognizedBy:"Recognized by" };
function esc(s){ return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function dot(t){ return `<span class="lg-dot" style="background:${typeColor[t]}"></span>`; }

function select(n){
  selected=n;
  if(!n){ panel.classList.remove("open"); return; }
  document.getElementById("p-type").innerHTML = dot(n.type)+n.type;
  document.getElementById("p-title").textContent = n.label;
  let h="";
  for(const k of (AT[n.type]||[])){ if(n.attrs[k]) h+=`<div class="kv"><div class="k">${KLABEL[k]||k}</div><div class="v">${esc(n.attrs[k])}</div></div>`; }
  // prose excerpt (bullets on positions/projects)
  const bl=DATA.bullets[n.id];
  if(bl&&bl.length){ h+=`<div class="rel-group"><div class="rg-t"><span>Highlights</span></div><ul class="prose">${bl.map(b=>`<li>${esc(b)}</li>`).join("")}</ul></div>`; }
  // relationships grouped by kind
  const groups={};
  for(const e of adj.get(n.id)){ const key=e.kind; (groups[key]=groups[key]||[]).push(e.o); }
  const orderKinds=["usedSkill","broader","evidencedBy","certifies","org","heldBy","deliveredDuring","recognizedBy"];
  for(const k of orderKinds){ if(!groups[k]) continue;
    const chips=groups[k].map(o=>`<span class="chip" data-id="${esc(o.id)}">${dot(o.type)}${esc(o.label)}</span>`).join("");
    h+=`<div class="rel-group"><div class="rg-t"><span>${REL[k]||k}</span><span>${groups[k].length}</span></div>${chips}</div>`;
  }
  const body=document.getElementById("p-body"); body.innerHTML=h;
  body.querySelectorAll(".chip").forEach(c=>c.addEventListener("click",()=>{
    const o=byId.get(c.dataset.id); if(o){ centerOn(o); select(o); }
  }));
  panel.classList.add("open");
}
document.getElementById("p-close").addEventListener("click",()=>select(null));
function centerOn(n){ cam.x=n.x; cam.y=n.y; cam.k=Math.max(cam.k,1.3); }

// ---- legend / filters ----------------------------------------------------
const counts={}; DATA.nodes.forEach(n=>counts[n.type]=(counts[n.type]||0)+1);
const rows=document.getElementById("lg-rows");
DATA.types.forEach(t=>{ if(!counts[t.type]) return;
  const el=document.createElement("div"); el.className="lg-row"; el.dataset.type=t.type;
  el.innerHTML=`<span class="lg-dot" style="background:${t.color}"></span>${t.legend}<span class="lg-n">${counts[t.type]}</span>`;
  el.addEventListener("click",()=>{ if(hidden.has(t.type)){hidden.delete(t.type);el.classList.remove("off");}
    else{hidden.add(t.type);el.classList.add("off");} });
  rows.appendChild(el);
});

// ---- search --------------------------------------------------------------
document.getElementById("search").addEventListener("keydown",e=>{
  if(e.key!=="Enter") return; const q=e.target.value.trim().toLowerCase(); if(!q) return;
  const hit=DATA.nodes.find(n=>n.label.toLowerCase().includes(q));
  if(hit){ centerOn(hit); select(hit); }
});

resize(); run();
</script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())

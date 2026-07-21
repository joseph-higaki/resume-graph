# resume-graph — every target runs through uv so the venv always matches uv.lock.
UV := uv run

# Private overlay repo: DATA ONLY (Application notes, framings, private skills).
# Overridable so the two repos need not be siblings.
APPS_REPO ?= ../resume-applications

.PHONY: all build validate test export serve project applications site hooks clean

all: test build validate export

# Activate the tracked git hooks (core.hooksPath is local config, not tracked).
# Run once per clone. Enforces the data/schema/mechanism commit-purity rule.
hooks:
	git config core.hooksPath .githooks

build:
	$(UV) python pipeline/build.py

validate:
	$(UV) python pipeline/validate.py

test:
	$(UV) pytest

# M2: everything derived from the graph. Depends on build so dist/graph.ttl is
# fresh. `export` is a standalone rule (not grouped) — a "export project:" line
# would be parsed as GNU make's `export` DIRECTIVE, not a target.
export: build
	$(UV) python -m pipeline.exports.json_resume
	$(UV) python -m pipeline.exports.pdf
	$(UV) python -m pipeline.exports.graph_html

# Preview locally: static-serve dist/ (graph.html · resume.pdf · resume.json).
# Data is inlined in graph.html, so `open dist/graph.html` works too — this is
# just the convenient one-command server. Run `make export` first (or `make all`).
serve:
	@echo "serving dist/ → http://localhost:8000/graph.html  (Ctrl-C to stop)"
	@cd dist && $(UV) python -m http.server 8000

# M3: application projection. Bare `make project` is a clean no-op here — this
# repo holds no Applications. The private overlay repo drives it with:
#   make project EXTRA=../resume-applications/dist/overlay.ttl APP=some-slug
# APP is optional; without it every Application in the merged graph is projected.
project: build
	$(UV) python -m pipeline.project --export \
	  $(if $(EXTRA),--extra-graph $(EXTRA)) $(if $(APP),--application $(APP))

# One-command drive of the private overlay: mechanism here, data and artifacts
# there. Reads $(APPS_REPO)/vault, writes $(APPS_REPO)/{build,dist} — nothing
# employer-shaped ever enters this working tree, so the two repos stay
# separately committable. Optional slug:
#   make applications APP=some-slug
#
# The overlay is a throwaway vault: this repo's context + _schema (so
# `type: "[[Application]]"` resolves — a CURIE `rg:Application` would resolve
# too, but the exporter reads a CURIE @type as *schema layer* and would mint the
# note under the ontology base) plus the private notes on top.
#
# --no-strict is correct HERE AND NOWHERE ELSE. Links to public data notes
# ([[Python]], [[Resume Graph]]) are intentionally dangling: the exporter mints
# them under the vault base which — same context, same @base — is byte-identical
# to the public IRI, and the RDF merge in project.py unifies them. Those
# warnings are the mechanism working.
applications: build
	@test -d "$(APPS_REPO)/vault" || { \
	  echo "APPS_REPO=$(APPS_REPO) has no vault/ — set APPS_REPO=<path to the private overlay repo>"; \
	  exit 1; }
	rm -rf "$(APPS_REPO)/build"
	mkdir -p "$(APPS_REPO)/build/vault"
	cp vault/context.jsonld "$(APPS_REPO)/build/vault/"
	cp -r vault/_schema "$(APPS_REPO)/build/vault/_schema"
	cp -r "$(APPS_REPO)"/vault/* "$(APPS_REPO)/build/vault/"
	$(UV) python pipeline/build.py \
	  --vault "$(abspath $(APPS_REPO))/build/vault" \
	  --out "$(abspath $(APPS_REPO))/build" \
	  --build-dir "$(abspath $(APPS_REPO))/build/layers" --no-strict
	$(UV) python -m pipeline.project --export --clean \
	  --extra-graph "$(abspath $(APPS_REPO))/build/graph.ttl" \
	  --out-dir "$(abspath $(APPS_REPO))/dist/applications" \
	  $(if $(APP),--application $(APP))

# M4/M5 = the full Astro + Sigma + Comunica site. The lightweight preview lives
# in `export` (dist/graph.html); this remains the placeholder for the real site.
site:
	@echo "target 'site' is not implemented yet (M4/M5)"

clean:
	rm -rf dist build

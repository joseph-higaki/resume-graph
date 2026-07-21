# resume-graph — every target runs through uv so the venv always matches uv.lock.
UV := uv run

# Private overlay repo: DATA ONLY (Application notes, framings, private skills).
# Overridable so the two repos need not be siblings.
APPS_REPO ?= ../resume-applications

# This repo on GitHub — the target of `make deploy`'s dispatch. Not derived from
# `git remote` because the deploy must name the repo whose Pages site is being
# rebuilt, which stays the same when someone works from a fork.
GRAPH_REPO ?= joseph-higaki/resume-graph

.PHONY: all build validate test export serve project applications publish deploy pages site hooks clean

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

# Assemble the exact tree GitHub Pages serves. CI runs this same target rather
# than its own copy of the cp lines, so what `make serve` shows locally is what
# deploys — including the unlisted /application/<publicId>/ pages, which are
# folded in only when the private repo is reachable (never on a fork or a PR).
# Idempotent: rebuilt from scratch every time, because Pages replaces the whole
# site on each deploy and a stale pages/ would publish yesterday's graph.
pages: export
	rm -rf pages && mkdir -p pages
	cp dist/graph.html dist/graph.jsonld dist/graph.ttl \
	   dist/resume.html dist/resume.json dist/resume.pdf pages/
	cp dist/graph.html pages/index.html
	cp site/public/robots.txt pages/
	@if [ -d "$(APPS_REPO)/published" ]; then \
	  mkdir -p pages/application; \
	  cp -r "$(APPS_REPO)"/published/. pages/application/; \
	  echo "folded in $$(find pages/application -mindepth 1 -maxdepth 1 -type d | wc -l) unlisted application(s)"; \
	else \
	  echo "no $(APPS_REPO)/published — public-only site (the normal CI case)"; \
	fi

# Preview locally: static-serve the assembled site, applications included, so a
# published URL can be opened at its real path before it goes live.
serve: pages
	@echo "serving pages/ → http://localhost:8000/  (Ctrl-C to stop)"
	@cd pages && $(UV) python -m http.server 8000

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

# Promote built application CVs into the private repo's `published/` tree, which
# is what this repo's Pages job checks out and serves under /application/<id>/.
# Publishing is a deliberate, reviewable git commit over there — not a build side
# effect — so `make applications` can be re-run freely without changing the site,
# and un-publishing is `git rm` on one directory.
#
# The 32-hex filter IS the safety gate: project.py names a directory after
# `rg:publicId` when the note carries one and after the readable slug when it
# does not, so an application without an id is structurally unpublishable and a
# folder named for an employer can never reach a public host.
#
#   make publish              # every application carrying an rg:publicId
publish:
	@test -d "$(APPS_REPO)/dist/applications" || { \
	  echo "no $(APPS_REPO)/dist/applications — run \`make applications\` first"; exit 1; }
	@n=0; for d in "$(APPS_REPO)"/dist/applications/*/; do \
	  id=$$(basename "$$d"); \
	  if ! echo "$$id" | grep -qE '^[0-9a-f]{32}$$'; then \
	    echo "skip  $$id — no rg:publicId, stays local"; continue; fi; \
	  rm -rf "$(APPS_REPO)/published/$$id"; \
	  mkdir -p "$(APPS_REPO)/published"; \
	  cp -r "$$d" "$(APPS_REPO)/published/$$id"; \
	  echo "stage $$id"; n=$$((n+1)); \
	done; \
	echo "$$n application(s) staged in $(APPS_REPO)/published — commit there to deploy"

# Redeploy the Pages site now, from your own gh credentials. Same signal the
# private repo's publish.yml sends, so this is the manual twin of the automated
# path — and it makes GRAPH_REPO_TOKEN optional: if you are content to type one
# command after each publish, that PAT (and publish.yml itself) can be skipped.
# APPS_REPO_TOKEN in the public repo is NOT optional; a CI runner cannot read a
# private repo without it.
#
# The guards exist because CI checks out the REMOTE published/ tree. A local
# `make publish` that was never committed and pushed deploys nothing at all,
# silently and successfully — the one failure this whole mechanism invites.
deploy:
	@command -v gh >/dev/null 2>&1 || { \
	  echo "gh CLI not found — install it, or trigger the run from the Actions tab"; exit 1; }
	@test -d "$(APPS_REPO)/published" || { \
	  echo "no $(APPS_REPO)/published — run \`make publish\` first"; exit 1; }
	@dirty="$$(git -C "$(APPS_REPO)" status --porcelain -- published/)"; \
	 test -z "$$dirty" || { \
	   echo "✗ uncommitted changes under $(APPS_REPO)/published:"; \
	   printf '%s\n' "$$dirty" | sed 's/^/    /'; \
	   echo "  CI serves the pushed tree, not this one — commit and push first."; exit 1; }
	@git -C "$(APPS_REPO)" fetch --quiet origin
	@br="$$(git -C "$(APPS_REPO)" rev-parse --abbrev-ref HEAD)"; \
	 ahead="$$(git -C "$(APPS_REPO)" rev-list --count origin/$$br..HEAD 2>/dev/null || echo 0)"; \
	 test "$$ahead" = 0 || { \
	   echo "✗ $(APPS_REPO) is $$ahead commit(s) ahead of origin/$$br — push first."; exit 1; }
	@before="$$(gh run list -R $(GRAPH_REPO) --limit 1 --json databaseId --jq '.[0].databaseId')"; \
	 gh api repos/$(GRAPH_REPO)/dispatches -f event_type=applications-updated; \
	 sleep 8; \
	 after="$$(gh run list -R $(GRAPH_REPO) --limit 1 --json databaseId --jq '.[0].databaseId')"; \
	 if [ "$$before" = "$$after" ]; then \
	   echo "✗ dispatch accepted but no run started."; \
	   echo "  /dispatches answers 204 either way — it cannot report doing nothing."; \
	   echo "  GitHub only honours repository_dispatch for workflows already on the"; \
	   echo "  DEFAULT branch: check that ci.yml on $(GRAPH_REPO)'s default branch"; \
	   echo "  carries \`repository_dispatch: types: [applications-updated]\`."; \
	   exit 1; fi; \
	 echo "run $$after started → https://github.com/$(GRAPH_REPO)/actions/runs/$$after"
	@for d in "$(APPS_REPO)"/published/*/; do \
	  echo "  live in ~2 min: https://joseph-higaki.github.io/resume-graph/application/$$(basename $$d)/"; \
	done

# M4/M5 = the full Astro + Sigma + Comunica site. The lightweight preview lives
# in `export` (dist/graph.html); this remains the placeholder for the real site.
site:
	@echo "target 'site' is not implemented yet (M4/M5)"

clean:
	rm -rf dist build

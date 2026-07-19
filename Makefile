# resume-graph — every target runs through uv so the venv always matches uv.lock.
UV := uv run

.PHONY: all build validate test export serve project site hooks clean

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

project:
	@echo "target 'project' is not implemented yet (M3)"

# M4/M5 = the full Astro + Sigma + Comunica site. The lightweight preview lives
# in `export` (dist/graph.html); this remains the placeholder for the real site.
site:
	@echo "target 'site' is not implemented yet (M4/M5)"

clean:
	rm -rf dist build

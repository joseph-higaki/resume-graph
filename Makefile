# resume-graph — every target runs through uv so the venv always matches uv.lock.
UV := uv run

.PHONY: all build validate test export project site clean

all: test build validate

build:
	$(UV) python pipeline/build.py

validate:
	$(UV) python pipeline/validate.py

test:
	$(UV) pytest

# Placeholders — arrive in later milestones. Kept as separate rules: a grouped
# "export project site:" line is parsed as GNU make's `export` DIRECTIVE, not a rule.
export:
	@echo "target 'export' is not implemented yet (M2)"

project:
	@echo "target 'project' is not implemented yet (M3)"

site:
	@echo "target 'site' is not implemented yet (M4/M5)"

clean:
	rm -rf dist

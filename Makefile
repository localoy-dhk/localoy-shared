.DEFAULT_GOAL := help
PY ?= python3

.PHONY: help generate check test build build-python build-js clean release-check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

generate: ## Regenerate both packages from enums.json + VERSION
	$(PY) generate.py

check: ## Fail if any generated file is out of date (what CI runs)
	$(PY) generate.py --check

test: ## Run the generator test suite
	$(PY) -m pytest tests -q

build: build-python build-js ## Build both packages

build-python: generate ## Build the Python sdist + wheel
	$(PY) -m build python/

build-js: generate ## Build the JS package
	cd js && npm ci && npm run build

release-check: check test build ## Everything CI does before a tag is cut
	@echo "VERSION = $$(cat VERSION)"
	@echo "Tag this release with: git tag v$$(cat VERSION) && git push origin v$$(cat VERSION)"

clean: ## Remove build output
	rm -rf python/dist python/build js/dist js/node_modules .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

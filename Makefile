.PHONY: clean clean_tox compile_translations coverage docs dummy_translations \
        extract_translations fake_translations help pull_translations push_translations \
        quality requirements selfcheck test test-all upgrade install_transifex_client

SRC_FILES_PROD = forum tests test_utils manage.py
SRC_FILES = ${SRC_FILES_PROD} setup.py

.DEFAULT_GOAL := help

# For opening files in a browser. Use like: $(BROWSER)relative/path/to/file.html
BROWSER := python -m webbrowser file://$(CURDIR)/

help: ## display this help message
	@echo "Please use \`make <target>' where <target> is one of"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

clean: ## remove generated byte code, coverage reports, and build artifacts
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	coverage erase
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info

clean_tox: ## clear tox requirements cache
	rm -fr .tox

coverage: clean ## generate and view HTML coverage report
	pytest --cov-report html
	$(BROWSER)htmlcov/index.html

docs: ## generate Sphinx HTML documentation, including API docs
	tox -e docs
	$(BROWSER)docs/_build/html/index.html

# Define PIP_COMPILE_OPTS="-v" to get more information during make compile-requirements.
compile-requirements: export CUSTOM_COMPILE_COMMAND=make upgrade
compile-requirements: ## Re-compile *.in requirements to *.txt
	pip install --quiet -r requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	pip-compile $(COMPILE_OPTS) --allow-unsafe requirements/pip.in
	pip-compile $(COMPILE_OPTS) requirements/pip-tools.in
	pip install --quiet -r requirements/pip.txt
	pip install --quiet -r requirements/pip-tools.txt
	pip-compile $(COMPILE_OPTS) requirements/base.in
	pip-compile $(COMPILE_OPTS) requirements/test.in
	pip-compile $(COMPILE_OPTS) requirements/doc.in
	pip-compile $(COMPILE_OPTS) requirements/quality.in
	pip-compile $(COMPILE_OPTS) requirements/ci.in
	pip-compile $(COMPILE_OPTS) requirements/dev.in
	# Let tox control the Django version for tests
	sed '/^[dD]jango==/d' requirements/test.txt > requirements/test.tmp
	mv requirements/test.tmp requirements/test.txt

format:
	black ${SRC_FILES}

upgrade: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	$(MAKE) compile-requirements COMPILE_OPTS="--upgrade"

piptools: ## install pinned version of pip-compile and pip-sync
	pip install -r requirements/pip.txt
	pip install -r requirements/pip-tools.txt

requirements: clean_tox piptools ## install development environment requirements
	pip-sync -q requirements/dev.txt requirements/private.*

test-all: selfcheck clean test test-quality test-pii test-e2e ## run all tests

test: ## run unit tests
	pytest

test-quality: test-lint test-codestyle test-mypy test-format ## run static coverage tests

test-lint: ## run pylint
	pylint ${SRC_FILES}

test-codestyle: ## run pycodestyle, pydocstyle
	pycodestyle ${SRC_FILES}
	pydocstyle ${SRC_FILES}

test-isort: ## run isort checks
	isort --check-only --diff ${SRC_FILES}

test-mypy: ## run type tests
	mypy ${SRC_FILES_PROD}

test-format: ## Run code formatting tests
	black --check ${SRC_FILES}

test-pii: export DJANGO_SETTINGS_MODULE=forum.settings.test
test-pii: ## # check for PII annotations on all Django models
	 code_annotations django_find_annotations --config_file .pii_annotations.yml --lint --report --coverage

test-e2e: e2e-stop-services e2e-start-services # run end-to-end tests
	pytest tests/e2e

e2e-start-services: # Start dependency containers necessary for e2e tests
	docker compose -f tests/e2e/docker-compose.yml --project-name forum_e2e up -d

e2e-stop-services: # Stop dependency containers necessary for e2e tests
	docker compose -f tests/e2e/docker-compose.yml --project-name forum_e2e down

selfcheck: ## check that the Makefile is well-formed
	@echo "The Makefile is well-formed."

## Localization targets

extract_translations: ## extract strings to be translated, outputting .mo files
	rm -rf docs/_build
	cd forum && i18n_tool extract --no-segment

compile_translations: ## compile translation files, outputting .po files for each supported language
	cd forum && i18n_tool generate

detect_changed_source_translations:
	cd forum && i18n_tool changed

ifeq ($(OPENEDX_ATLAS_PULL),)
pull_translations: ## Pull translations from Transifex
	tx pull -t -a -f --mode reviewed --minimum-perc=1
else
# Experimental: OEP-58 Pulls translations using atlas
pull_translations:
	find forum/conf/locale -mindepth 1 -maxdepth 1 -type d -exec rm -r {} \;
	atlas pull $(OPENEDX_ATLAS_ARGS) translations/forum/forum/conf/locale:forum/conf/locale
	python manage.py compilemessages

	@echo "Translations have been pulled via Atlas and compiled."
endif

push_translations: ## push source translation files (.po) from Transifex
	tx push -s

dummy_translations: ## generate dummy translation (.po) files
	cd forum && i18n_tool dummy

build_dummy_translations: extract_translations dummy_translations compile_translations ## generate and compile dummy translation files

validate_translations: build_dummy_translations detect_changed_source_translations ## validate translations

install_transifex_client: ## Install the Transifex client
	# Instaling client will skip CHANGELOG and LICENSE files from git changes
	# so remind the user to commit the change first before installing client.
	git diff -s --exit-code HEAD || { echo "Please commit changes first."; exit 1; }
	curl -o- https://raw.githubusercontent.com/transifex/cli/master/install.sh | bash
	git checkout -- LICENSE README.md ## overwritten by Transifex installer

# One command to set up, one to run.
PY ?= python

setup:
	$(PY) -m pip install -e ".[dev]"

demo:
	hub seed && hub serve

check:
	ruff check .
	ruff format --check .
	mypy
	HUB_OFFLINE=1 pytest -q
	HUB_OFFLINE=1 $(PY) eval/run_eval.py --check

.PHONY: setup demo check

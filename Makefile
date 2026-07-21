# jellyc developer targets. The bootstrap fixpoint (M5) is not wired yet;
# `test` runs everything that exists today.

PY = python3

.PHONY: all vendor blob probes check test runtime diff clean

all: test

vendor:
	sh tools/vendor.sh

blob:
	$(PY) tools/regen_blob.py

probes: vendor
	$(PY) tools/probes.py

check: vendor
	$(PY) tests/test_checker.py

runtime: blob
	$(PY) tests/test_runtime.py

diff: vendor blob
	$(PY) tests/run.py

# full gate for the milestones landed so far
test: probes check runtime diff

clean:
	rm -rf build/runtime.o build/runtime.elf build/t __pycache__ */__pycache__

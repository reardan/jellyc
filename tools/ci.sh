#!/bin/sh
# Full jellyc gate for the milestones landed so far. Mirror this into a CI
# workflow when the repo has `workflow` push scope. Needs: python3, binutils.
set -eu
cd "$(dirname "$0")/.."

sh tools/vendor.sh

# runtime blob must regenerate reproducibly
python3 tools/regen_blob.py
git diff --exit-code -- build/blob.bin build/blob.syms

python3 tools/probes.py            # interpreter semantics jellyc relies on
python3 tests/test_checker.py      # subset checker unit tests
python3 tests/test_runtime.py      # M2 gate: clean ELF, syscall hygiene
python3 tests/run.py               # differential suite: interpreter vs compiled
echo "jellyc: all checks passed"

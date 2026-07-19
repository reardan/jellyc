#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
cd "$ROOT"
chmod +x jellyc tests/run.sh

fail=0
check() {
  local name="$1" expect="$2"
  shift 2
  local got
  got="$("$@" | tr -d '\r')"
  if [[ "$got" == "$expect" ]]; then
    echo "ok $name"
  else
    echo "FAIL $name: expected $(printf %q "$expect") got $(printf %q "$got")" >&2
    fail=1
  fi
}

check 'expr-mul' 'a*b' ./jellyc -e '×'
check 'expr-add' 'a+b' ./jellyc -e '+'
check 'expr-halve' 'a/2' ./jellyc -e 'H'
check 'expr-neg' '-a' ./jellyc -e 'N'
check 'expr-pow' 'a**b' ./jellyc -e '*'

check 'run-mul' '42' ./jellyc -r '×' 14 3
check 'run-add' '42' ./jellyc -r '+' 40 2
check 'run-sub' '7' ./jellyc -r '-' 10 3
check 'run-div' '5' ./jellyc -r '÷' 20 4
check 'run-mod' '1' ./jellyc -r '%' 10 3
check 'run-halve' '5.0' ./jellyc -r 'H' 10
check 'run-neg' '-3' ./jellyc -r 'N' 3
check 'run-abs' '3' ./jellyc -r 'A' -3
check 'run-pow' '8' ./jellyc -r '*' 2 3

check 'file-mul' '42' ./jellyc -fr examples/mul.jelly 6 7

# Match official Jelly for the subset
check 'vs-jelly-mul' '42' jelly eun '×' 14 3
check 'vs-jellyc-mul' '42' ./jellyc -r '×' 14 3

if [[ "$fail" -ne 0 ]]; then
  echo "Some tests failed" >&2
  exit 1
fi
echo "All tests passed."

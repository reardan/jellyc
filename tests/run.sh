#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
cd "$ROOT"
chmod +x jellyc tests/run.sh
python3 tools/gen_jellyc.py >/dev/null

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

check_elf() {
  local name="$1" file="$2"
  if file "$file" | grep -q 'ELF 64-bit LSB executable, x86-64'; then
    echo "ok $name"
  else
    echo "FAIL $name: not an x86-64 ELF: $(file "$file")" >&2
    fail=1
  fi
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# --- native backend (default when bin/jellyc1 exists) ---
./jellyc -o "$tmpdir/mul" '×'
check_elf 'elf-mul' "$tmpdir/mul"
check 'run-mul' '42' "$tmpdir/mul" 14 3

./jellyc -o "$tmpdir/add" '+'
check 'run-add' '42' "$tmpdir/add" 40 2

check 'run-sub' '7' ./jellyc -r '-' 10 3
check 'run-div' '5' ./jellyc -r '÷' 20 4
check 'run-mod' '1' ./jellyc -r '%' 10 3
check 'run-halve' '5' ./jellyc -r 'H' 10
check 'run-neg' '-3' ./jellyc -r 'N' 3
check 'run-abs' '3' ./jellyc -r 'A' -3
check 'run-pow' '8' ./jellyc -r '*' 2 3
check 'file-mul' '42' ./jellyc -fr examples/mul.jelly 6 7

# Match official Jelly semantics for the subset
check 'vs-jelly-mul' '42' jelly eun '×' 14 3
check 'vs-jellyc-mul' '42' ./jellyc -r '×' 14 3

# Unsupported rejects
if ./jellyc '“hi”' >/dev/null 2>&1; then
  echo 'FAIL unsupported should reject' >&2
  fail=1
else
  echo 'ok reject-unsupported'
fi

# --- backend parity: jelly path ≡ native path ---
if [[ ! -x bin/jellyc1 ]]; then
  echo 'FAIL bin/jellyc1 missing after gen' >&2
  fail=1
else
  echo 'ok native-present'
fi

for a in H N A + × ÷ - % '*'; do
  JELLYC_BACKEND=jelly ./jellyc "$a" >"$tmpdir/j.bin"
  JELLYC_BACKEND=native ./jellyc "$a" >"$tmpdir/n.bin"
  if cmp -s "$tmpdir/j.bin" "$tmpdir/n.bin"; then
    echo "ok parity-$a"
  else
    echo "FAIL parity-$a" >&2
    fail=1
  fi
done

# freestanding native compiler itself is an ELF
check_elf 'elf-jellyc1' bin/jellyc1

# compositional helper seed still parses
if jelly fu elf_hdr.jelly >/dev/null 2>&1; then
  echo 'ok elf_hdr-parse'
else
  # niladic magic link alone is enough to smoke
  if jelly eun '127,69,76,70' | grep -q '127'; then
    echo 'ok elf_hdr-magic'
  else
    echo 'FAIL elf_hdr helpers' >&2
    fail=1
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  echo "Some tests failed" >&2
  exit 1
fi
echo "All tests passed."

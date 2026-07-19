# jellyc — Jelly → x86-64 ELF compiler written in Jelly
# Bootstrap: https://github.com/DennisMitchell/jellylanguage

.PHONY: install gen bootstrap test demo clean

export PATH := $(HOME)/.local/bin:$(PATH)

install:
	pip3 install --upgrade --user jellylanguage

# Regenerate elf.jelly, jellyc.jelly, bin/jellyc1, elf_hdr.jelly
gen:
	python3 tools/gen_jellyc.py

# Build native stage-1 and prove it matches the Jelly backend byte-for-byte
bootstrap: gen
	@set -f; for a in H N A + × ÷ - % *; do \
	  JELLYC_BACKEND=jelly ./jellyc "$$a" > /tmp/jellyc_boot_j.bin; \
	  JELLYC_BACKEND=native ./jellyc "$$a" > /tmp/jellyc_boot_n.bin; \
	  cmp /tmp/jellyc_boot_j.bin /tmp/jellyc_boot_n.bin || { echo "bootstrap mismatch: $$a" >&2; exit 1; }; \
	  echo "ok bootstrap $$a"; \
	done; \
	echo "bootstrap: jelly ≡ jellyc1 for all supported atoms"

test: install gen
	./tests/run.sh

demo: install gen
	@echo '== × 14 3 =='
	./jellyc -r '×' 14 3
	@echo '== H 10 =='
	./jellyc -r 'H' 10
	@echo '== file(1) =='
	./jellyc -o /tmp/jellyc_demo_mul '×'
	file /tmp/jellyc_demo_mul

clean:
	rm -rf bin __pycache__ tools/__pycache__ *.pyc /tmp/jellyc_demo_mul /tmp/jellyc_boot_*.bin

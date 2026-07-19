# jellyc — Jelly → x86-64 ELF compiler written in Jelly
# Bootstrap: https://github.com/DennisMitchell/jellylanguage

.PHONY: install test demo gen clean

export PATH := $(HOME)/.local/bin:$(PATH)

install:
	pip3 install --upgrade --user jellylanguage

test: install
	./tests/run.sh

demo: install
	@echo '== × 14 3 =='
	./jellyc -r '×' 14 3
	@echo '== H 10 =='
	./jellyc -r 'H' 10
	@echo '== file(1) =='
	./jellyc -o /tmp/jellyc_demo_mul '×'
	file /tmp/jellyc_demo_mul

# Regenerate elf.jelly (blobs) + jellyc.jelly (lookup)
gen:
	python3 tools/gen_jellyc.py

clean:
	rm -rf bin __pycache__ *.pyc /tmp/jellyc_demo_mul

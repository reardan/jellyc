# jellyc — Jelly compiler written in Jelly
# Bootstrap runtime: https://github.com/DennisMitchell/jellylanguage

.PHONY: install test demo clean

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
	@echo '== compile + =='
	./jellyc '+'

clean:
	rm -rf bin __pycache__ *.pyc

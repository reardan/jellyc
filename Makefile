# jellyc — Jelly compiler (self-hosting)
#
#   make          build host bootstrap (gcc) -> bin/jellyc
#   make verify   self-host fixpoint: jellycN == jellycN+1
#   make test     compile and run examples
#   make clean

CC       = gcc
CFLAGS   = -Wall -Wextra -O2 -std=c11 -Wno-builtin-declaration-mismatch
OUT      = bin
JELLYC   = $(OUT)/jellyc
HOST     = $(OUT)/jellyc0

.PHONY: all verify test clean bootstrap

all: $(JELLYC)

$(OUT):
	mkdir -p $(OUT)

# Stage 0: compile the Jelly compiler with a C compiler.
# Jelly's surface syntax is a C subset, so gcc can bootstrap it.
$(HOST): jellyc.jelly | $(OUT)
	$(CC) $(CFLAGS) -x c -o $@ jellyc.jelly

# Stage 1+: promote the self-hosted compiler to bin/jellyc
$(JELLYC): $(HOST) jellyc.jelly
	$(HOST) < jellyc.jelly > $(JELLYC)
	chmod +x $(JELLYC)

# Four-stage self-host and binary fixpoint check.
verify: $(HOST)
	@echo "Stage 1: host -> jellyc1"
	$(HOST) < jellyc.jelly > $(OUT)/jellyc1
	chmod +x $(OUT)/jellyc1
	@echo "Stage 2: jellyc1 -> jellyc2"
	$(OUT)/jellyc1 < jellyc.jelly > $(OUT)/jellyc2
	chmod +x $(OUT)/jellyc2
	@echo "Stage 3: jellyc2 -> jellyc3"
	$(OUT)/jellyc2 < jellyc.jelly > $(OUT)/jellyc3
	chmod +x $(OUT)/jellyc3
	@echo "Comparing stage 2 and stage 3 (fixpoint)..."
	@cmp -s $(OUT)/jellyc2 $(OUT)/jellyc3
	@cp $(OUT)/jellyc2 $(JELLYC)
	@chmod +x $(JELLYC)
	@echo "SUCCESS: jellyc self-hosts (jellyc2 == jellyc3)"

bootstrap: verify

test: $(JELLYC)
	@echo "== hello =="
	$(JELLYC) < examples/hello.jelly > $(OUT)/hello
	chmod +x $(OUT)/hello
	$(OUT)/hello > $(OUT)/hello.out
	cmp -s $(OUT)/hello.out tests/expected/hello.txt
	@echo "ok hello"
	@echo "== fib =="
	$(JELLYC) < examples/fib.jelly > $(OUT)/fib
	chmod +x $(OUT)/fib
	$(OUT)/fib > $(OUT)/fib.out
	cmp -s $(OUT)/fib.out tests/expected/fib.txt
	@echo "ok fib"
	@echo "== fizzbuzz =="
	$(JELLYC) < examples/fizzbuzz.jelly > $(OUT)/fizzbuzz
	chmod +x $(OUT)/fizzbuzz
	$(OUT)/fizzbuzz > $(OUT)/fizzbuzz.out
	cmp -s $(OUT)/fizzbuzz.out tests/expected/fizzbuzz.txt
	@echo "ok fizzbuzz"
	@echo "All tests passed."

clean:
	rm -rf $(OUT)

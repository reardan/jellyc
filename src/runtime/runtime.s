# jellyc runtime blob (x86-64 Linux, syscalls only, no libc).
#
# Assembled once at development time by tools/regen_blob.py into a flat,
# position-*dependent-but-relocatable* code blob: all internal control flow is
# RIP-relative or relative CALL/JMP, so the blob runs correctly at whatever
# base address the compiler places it (the ELF layout puts it at 0x400100).
#
# The compiler links to this blob in exactly two ways:
#   * e_entry points at _start (the first byte of the blob), and
#   * compiled code CALLs runtime routines at (blob_base + symbol_offset),
#     and reads/writes the `main_ptr` cell at (blob_base + its offset).
# tools/regen_blob.py records those offsets from the linked symbol table.
#
# Value representation (tagged 64-bit words):
#   int  v : (v << 1) | 1        low bit 1  -> signed 63-bit integer
#   list p : pointer p           low bit 0  -> 8-byte-aligned heap object
#   list object at p: [ int64 length ][ word elem_0 ] ... [ word elem_{n-1} ]
#
# Register conventions (SysV-ish): args in rdi/rsi, result in rax, r11 scratch.
# Runtime routines preserve rbx, rbp, r12-r15 (callee-saved), which compiled
# links use to hold their own arguments (r12 = left, r13 = right).

	.intel_syntax noprefix
	.text
	.globl _start

# --- syscall numbers --------------------------------------------------------
	.equ SYS_read,  0
	.equ SYS_write, 1
	.equ SYS_mmap,  9
	.equ SYS_exit,  60

	.equ PROT_RW,      0x3
	.equ MAP_ANON_PRIV, 0x4022   # PRIVATE | ANONYMOUS | NORESERVE
	.equ ARENA_SIZE,   0x40000000  # 1 GiB heap
	.equ INBUF_SIZE,   0x10000000  # 256 MiB stdin buffer
	.equ OUTBUF_SIZE,  0x10000000  # 256 MiB stdout buffer

# ===========================================================================
# _start: program entry.
#   1. map heap arena, stdin buffer, stdout buffer
#   2. read all of stdin into the input buffer
#   3. build a tagged list of the input bytes  -> rdi (main's left arg)
#   4. rsi = tagged 256 (main's right arg default)
#   5. call the main link through main_ptr
#   6. deep-flatten the result into the output buffer, write it, exit 0
# ===========================================================================
_start:
	# heap arena
	mov rax, SYS_mmap
	xor rdi, rdi
	mov rsi, ARENA_SIZE
	mov rdx, PROT_RW
	mov r10, MAP_ANON_PRIV
	mov r8, -1
	xor r9, r9
	syscall
	lea r11, [rip + bump_ptr]
	mov [r11], rax

	# stdin buffer
	mov rax, SYS_mmap
	xor rdi, rdi
	mov rsi, INBUF_SIZE
	mov rdx, PROT_RW
	mov r10, MAP_ANON_PRIV
	mov r8, -1
	xor r9, r9
	syscall
	lea r11, [rip + inbuf_ptr]
	mov [r11], rax

	# stdout buffer
	mov rax, SYS_mmap
	xor rdi, rdi
	mov rsi, OUTBUF_SIZE
	mov rdx, PROT_RW
	mov r10, MAP_ANON_PRIV
	mov r8, -1
	xor r9, r9
	syscall
	lea r11, [rip + outbuf_ptr]
	mov [r11], rax

	# read all of stdin into inbuf; r12 = total bytes read
	xor r12, r12
.read_loop:
	mov rax, SYS_read
	xor rdi, rdi
	lea r11, [rip + inbuf_ptr]
	mov rsi, [r11]
	add rsi, r12
	mov rdx, INBUF_SIZE
	sub rdx, r12
	syscall
	test rax, rax
	jle .read_done
	add r12, rax
	jmp .read_loop
.read_done:
	# build tagged list of r12 bytes
	mov rdi, r12
	call rt_alloc              # rax = list object of length r12
	mov r13, rax              # r13 = list ptr
	lea r11, [rip + inbuf_ptr]
	mov r14, [r11]            # r14 = raw input bytes
	xor rcx, rcx              # index
.build_loop:
	cmp rcx, r12
	jge .build_done
	movzx rax, byte ptr [r14 + rcx]
	lea rax, [rax + rax + 1]   # tag int: (b<<1)|1
	mov [r13 + 8 + rcx*8], rax
	inc rcx
	jmp .build_loop
.build_done:
	# call main link: rdi = input list, rsi = tagged 256
	mov rdi, r13
	mov rsi, (256 << 1) | 1
	lea r11, [rip + main_ptr]
	call [r11]

	# deep-flatten result (rax) into outbuf
	mov rdi, rax
	call rt_emit_value

	# write outbuf
	mov rax, SYS_write
	mov rdi, 1
	lea r11, [rip + outbuf_ptr]
	mov rsi, [r11]
	lea r11, [rip + out_len]
	mov rdx, [r11]
	syscall

	mov rax, SYS_exit
	xor rdi, rdi
	syscall

# ===========================================================================
# rt_abort: write "jellyc: trap\n" to stderr and exit 1. Target of every
# JellyCore domain trap (rule R6) and of unknown-token call sites.
# ===========================================================================
	.globl rt_abort
rt_abort:
	mov rax, SYS_write
	mov rdi, 2
	lea rsi, [rip + trap_msg]
	mov rdx, 13
	syscall
	mov rax, SYS_exit
	mov rdi, 1
	syscall

# ===========================================================================
# rt_alloc(rdi = element count) -> rax = list object pointer.
# Allocates 1 + count words from the bump arena, stores the length, leaves
# elements uninitialized. Never frees.
# ===========================================================================
	.globl rt_alloc
rt_alloc:
	lea r11, [rip + bump_ptr]
	mov rax, [r11]            # rax = object base (aligned)
	mov [rax], rdi           # store length
	lea rdx, [rax + 8 + rdi*8]
	mov [r11], rdx           # advance bump pointer
	ret

# ===========================================================================
# rt_emit_value(rdi = value): append the value's bytes to outbuf, deeply.
# int  -> one byte (low 8 bits of the untagged value)
# list -> recurse over elements
# ===========================================================================
	.globl rt_emit_value
rt_emit_value:
	test rdi, 1
	jnz .emit_int
	# list: rdi = ptr, length at [rdi]
	push rbx
	push r12
	push r13
	mov r12, rdi             # object
	mov r13, [rdi]           # length
	xor rbx, rbx             # index
.emit_loop:
	cmp rbx, r13
	jge .emit_ret
	mov rdi, [r12 + 8 + rbx*8]
	call rt_emit_value
	inc rbx
	jmp .emit_loop
.emit_ret:
	pop r13
	pop r12
	pop rbx
	ret
.emit_int:
	sar rdi, 1               # untag
	lea r11, [rip + outbuf_ptr]
	mov r10, [r11]
	lea r11, [rip + out_len]
	mov rax, [r11]
	mov [r10 + rax], dil     # store low byte
	inc rax
	mov [r11], rax
	ret

# ===========================================================================
# rt_iterable(rdi = value, rsi = make_range flag) -> rax = list.
#   list  -> returned unchanged
#   int x, make_range=0 -> [x]
#   int x, make_range!=0 -> [1, 2, ..., x]   (x<=0 -> [])
# Mirrors the interpreter's iterable(); used by € and other iterators.
# ===========================================================================
	.globl rt_iterable
rt_iterable:
	test rdi, 1
	jz .iter_islist          # low bit 0 -> already a list
	sar rdi, 1               # untag int -> rdx below
	mov rdx, rdi
	test rsi, rsi
	jnz .iter_range
	# wrap: [x]
	push rdx
	mov rdi, 1
	call rt_alloc
	pop rdx
	lea rdx, [rdx + rdx + 1]  # re-tag
	mov [rax + 8], rdx
	ret
.iter_range:
	# [1..x]; if x<=0 -> empty
	test rdx, rdx
	jg .iter_range_go
	xor rdi, rdi
	call rt_alloc
	ret
.iter_range_go:
	push rdx
	mov rdi, rdx
	call rt_alloc            # rax = list of length x
	pop rdx
	xor rcx, rcx
.iter_range_loop:
	cmp rcx, rdx
	jge .iter_range_done
	lea r11, [rcx + 1]        # value i+1
	lea r11, [r11 + r11 + 1]  # tag
	mov [rax + 8 + rcx*8], r11
	inc rcx
	jmp .iter_range_loop
.iter_range_done:
	ret
.iter_islist:
	mov rax, rdi
	ret

# ===========================================================================
# rt_len(rdi = value) -> rax = tagged int length.
#   list -> its length; int -> 1 (iterable wrap), matching interpreter L.
# ===========================================================================
	.globl rt_len
rt_len:
	test rdi, 1
	jnz .len_int
	mov rax, [rdi]           # length
	lea rax, [rax + rax + 1]  # tag
	ret
.len_int:
	mov rax, (1 << 1) | 1
	ret

# ===========================================================================
# rt_reverse(rdi = list) -> rax = new reversed list. Traps on an int.
# ===========================================================================
	.globl rt_reverse
rt_reverse:
	test rdi, 1
	jnz rt_abort
	push rbx
	push r12
	push r13
	mov r12, rdi
	mov r13, [rdi]           # length
	push rdi
	mov rdi, r13
	call rt_alloc            # rax = dest
	pop rdi
	xor rbx, rbx
.rev_loop:
	cmp rbx, r13
	jge .rev_done
	mov rdx, [r12 + 8 + rbx*8]
	mov rcx, r13
	dec rcx
	sub rcx, rbx             # dest index = len-1-i
	mov [rax + 8 + rcx*8], rdx
	inc rbx
	jmp .rev_loop
.rev_done:
	pop r13
	pop r12
	pop rbx
	ret

# ===========================================================================
# rt_concat(rdi = x, rsi = y) -> rax = iterable(x) ++ iterable(y).
# Scalars auto-wrap ([x]); lists used as-is. Implements the ; atom.
# ===========================================================================
	.globl rt_concat
rt_concat:
	push rbx
	push r12
	push r13
	push r14
	# left -> r12 (ptr), r13 (len)
	test rdi, 1
	jz .cat_llist
	push rsi
	mov rsi, 0
	call rt_iterable         # rdi int -> [x]
	pop rsi
	mov r12, rax
	jmp .cat_left_done
.cat_llist:
	mov r12, rdi
.cat_left_done:
	mov r13, [r12]
	# right -> r14 (ptr)
	test rsi, 1
	jz .cat_rlist
	mov rdi, rsi
	mov rsi, 0
	call rt_iterable
	mov r14, rax
	jmp .cat_right_done
.cat_rlist:
	mov r14, rsi
.cat_right_done:
	mov rdi, r13
	add rdi, [r14]           # total length
	call rt_alloc            # rax = dest
	# copy left
	xor rcx, rcx
.cat_cl:
	cmp rcx, r13
	jge .cat_cl_done
	mov rdx, [r12 + 8 + rcx*8]
	mov [rax + 8 + rcx*8], rdx
	inc rcx
	jmp .cat_cl
.cat_cl_done:
	# copy right after left
	mov r9, [r14]            # right length
	xor rcx, rcx
.cat_cr:
	cmp rcx, r9
	jge .cat_cr_done
	mov rdx, [r14 + 8 + rcx*8]
	mov r8, r13
	add r8, rcx
	mov [rax + 8 + r8*8], rdx
	inc rcx
	jmp .cat_cr
.cat_cr_done:
	pop r14
	pop r13
	pop r12
	pop rbx
	ret

# ===========================================================================
# data cells (RIP-relative; the compiler patches main_ptr in the output file)
# ===========================================================================
	.align 8
	.globl main_ptr
main_ptr:  .quad 0          # absolute address of the main link (patched)
bump_ptr:  .quad 0          # next free arena address
inbuf_ptr: .quad 0
outbuf_ptr:.quad 0
out_len:   .quad 0
trap_msg:  .ascii "jellyc: trap\n"

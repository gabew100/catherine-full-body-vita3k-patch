"""Builds the PCSG01179 shader cache fog fallback patch for one eboot.
Usage: python fog_fallback.py <text segment .bin>

The engine has two caches filled from the precompiled shaders in Shader.cpk, both keyed by the
material key: shaders (v1.00 0x81320e98) and vertex+fragment program pairs (v1.00 0x81321144).
Their create functions are stubs returning 0, so a miss stores a NULL program. For each cache this
rewrites the miss path: first retry the walk with the fog bits cleared, then run the original miss
code. Three redundant stores of 0 (the node was just memset) and a repeated base address load are
dropped to make room. The functions are found by their list walk bytes and the call targets are read
from the original code, so the same script works for every eboot that has these functions.
"""
import sys

import capstone
import keystone

TEXT_BASE = 0x81000000
text = open(sys.argv[1], "rb").read()
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
ks = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_THUMB)


def disasm(addr, size):
    return [(i.address, i.bytes, i.mnemonic, i.op_str) for i in cs.disasm(text[addr - TEXT_BASE:addr - TEXT_BASE + size], addr)]


def find(pattern_hex, back):
    """Address of the only match of a byte pattern, minus back."""
    pattern = bytes.fromhex(pattern_hex)
    i = text.find(pattern)
    if i < 0 or text.find(pattern, i + 1) >= 0:
        sys.exit(f"pattern {pattern_hex[:16]}... not found exactly once")
    return TEXT_BASE + i - back


def calls(code):
    return [int(op.lstrip("#"), 16) for _, _, m, op in code if m in ("bl", "blx")]


def check_stub(addr):
    if [x[2:] for x in disasm(addr, 4)] != [("movs", "r0, #0"), ("bx", "lr")]:
        sys.exit(f"{addr:08x} is not a stub returning 0")


def build(name, miss, tail, asm, expected, want_calls):
    orig = disasm(miss, tail - miss)
    got = " ".join(m for _, _, m, _ in orig)
    if got != " ".join(expected.split()):
        sys.exit(f"unexpected code at {miss:08x}: {got}")
    code = bytes(ks.asm(asm, miss)[0])
    room = tail - miss
    if len(code) > room:
        sys.exit(f"new code is {len(code)} bytes, only {room} fit")
    code += b"\x00\xbf" * ((room - len(code)) // 2)  # nop
    new = [(i.address, i.bytes, i.mnemonic, i.op_str) for i in cs.disasm(code, miss)]
    assert sum(len(b) for _, b, _, _ in new) == room
    assert calls(new) == want_calls, (calls(new), want_calls)
    print(f"# {name}, original:")
    for a, b, m, op in orig:
        print(f"#   {a:08x}: {b.hex():<10} {m:<8} {op}")
    print(f"# {name}, patched:")
    for a, b, m, op in new:
        print(f"#   {a:08x}: {b.hex():<10} {m:<8} {op}")
    return f"0:0x{miss - TEXT_BASE:X} " + " ".join(f"0x{x:02X}" for x in code)


# Shader cache, v1.00 0x81320e98. r6 = key, lr/r8/sl = key words 0-2, r4 = lock (base + 0x7c),
# list head at base + 0x78
shaders = find("a988814218d1a96891ea0e01394013d1e96891ea080111ea09010dd1", 0x3C)
miss, tail = shaders + 0x7A, shaders + 0xF4
unlock, alloc, memset, memcpy, create, lock, _, clone = calls(disasm(miss, tail - miss))
check_stub(create)
line1 = build("shader cache lookup", miss, tail, f"""
    tst.w   r8, #1
    beq     create
    bic.w   r8, r8, #1
    bic.w   sl, sl, #0x33000000
    ldr     r5, [r4, #-4]
    b       #{shaders + 0x38:#x}
create:
    adds    r0, r4, #0
    bl      #{unlock:#x}
    movs    r0, #0x28
    bl      #{alloc:#x}
    adds    r5, r0, #0
    movs    r1, #0
    movs    r2, #0x28
    blx     #{memset:#x}
    adds    r0, r5, #4
    adds    r1, r6, #0
    movs    r2, #0x18
    blx     #{memcpy:#x}
    adds    r0, r6, #0
    bl      #{create:#x}
    str     r0, [r5, #0x1c]
    cmp     r4, #0
    beq     locked
    adds    r0, r4, #0
    bl      #{lock:#x}
locked:
    sub.w   r0, r4, #0x7c
    ldr     r1, [r0, #0x78]
    cbz     r1, empty
    str     r1, [r5, #0x24]
    str     r5, [r1, #0x20]
empty:
    str     r5, [r0, #0x78]
    cbz     r4, unlocked
    adds    r0, r4, #0
    bl      #{unlock:#x}
unlocked:
    movw    r0, #0x7f30
    movt    r0, #0x8180
    ldr     r1, [r0, #0x10]
    ands    r0, r1, #0x2000000
    beq     #{tail:#x}
    ands    r0, r1, #0x1000000
    beq     #{tail:#x}
    adds    r0, r5, #0
    bl      #{clone:#x}
""", """adds bl movs bl adds movs movs blx adds adds movs blx adds bl str cmp beq adds bl movs str
        movw movt ldr cbz str str b movs str movw movt str cbz adds bl movw movt ldr ands beq ands beq adds bl""",
    [unlock, alloc, memset, memcpy, create, lock, unlock, clone])

# Program pair cache, v1.00 0x81321144. sb = key, r4/r5/r6 = masked key words 0-2, r7 = lock
# (base + 0x74), list head at base + 0x70
pairs = find("b8f8041081421dd1d8f8081011ea0e01a14217d1d8f80c1011ea0a01a94211d1", 0x5A)
miss, tail = pairs + 0xA8, pairs + 0x12A
unlock, alloc, memset, addref, memcpy, create, lock, _, clone = calls(disasm(miss, tail - miss))
check_stub(create)
line2 = build("program pair cache lookup", miss, tail, f"""
    tst.w   r5, #1
    beq     create
    bic.w   r5, r5, #1
    bic.w   r6, r6, #0x33000000
    ldr     r8, [r7, #-4]
    b       #{pairs + 0x3C:#x}
create:
    adds    r0, r7, #0
    bl      #{unlock:#x}
    movs    r0, #0x2c
    bl      #{alloc:#x}
    adds    r4, r0, #0
    movs    r1, #0
    movs    r2, #0x2c
    blx     #{memset:#x}
    adds.w  r0, r4, #0x20
    bl      #{addref:#x}
    adds    r0, r4, #4
    mov     r1, sb
    movs    r2, #0x18
    blx     #{memcpy:#x}
    mov     r0, sb
    bl      #{create:#x}
    str     r0, [r4, #0x1c]
    cmp     r7, #0
    beq     locked
    adds    r0, r7, #0
    bl      #{lock:#x}
locked:
    sub.w   r0, r7, #0x74
    ldr     r1, [r0, #0x70]
    cbz     r1, empty
    str     r1, [r4, #0x28]
    str     r4, [r1, #0x24]
empty:
    str     r4, [r0, #0x70]
    cbz     r7, unlocked
    adds    r0, r7, #0
    bl      #{unlock:#x}
unlocked:
    movw    r0, #0x7f30
    movt    r0, #0x8180
    ldr     r1, [r0, #0x10]
    ands    r0, r1, #0x2000000
    beq     #{tail:#x}
    ands    r0, r1, #0x1000000
    beq     #{tail:#x}
    adds    r0, r4, #0
    bl      #{clone:#x}
""", """adds bl movs bl adds movs movs blx adds.w bl adds mov movs blx mov bl str cmp beq adds bl movs str
        movw movt ldr cbz str str b movs str movw movt str cbz adds bl movw movt ldr ands beq ands beq adds bl""",
    [unlock, alloc, memset, addref, memcpy, create, lock, unlock, clone])

print("[eboot.bin]")
print(line1)
print(line2)

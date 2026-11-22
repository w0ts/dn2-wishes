"""Section 7 as LZMA (docs/lzma7.md): dnfw.codec.lzma7 and the ColdFire decoder csrc/waverider/lzma7.c,
compiled for the host, agree on every stream: what decodes, and what is refused into the uploader's error
path; a stream without our magic goes to stock's aPLib routine untouched."""

from __future__ import annotations

import os
import pathlib
import random
import shutil
import struct
import subprocess
import zlib

import pytest

from dnfw.codec import aplibpack, lzma7
from dnfw.container import section as S

ROOT = pathlib.Path(__file__).resolve().parent.parent
REFUSE = 0x100000
HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
extern long dn_depack7(const uint8_t *src, uint8_t *dst);
extern volatile uint32_t dn7_status;
long host_stock_calls;
long host_stock(const uint8_t *src, uint8_t *dst) { host_stock_calls++; dst[0] = 0xA5; return 7; }
unsigned long host_malloc(unsigned int n) { return (unsigned long)malloc(n); }   /* as stock: an integer */
/* no +Drive copy here (test_lzma7cache.py has it) */
int dn7c_load(const uint8_t *id, uint8_t *dst, uint32_t len, uint32_t crc) { return 0; }
void dn7c_store(const uint8_t *id, uint8_t *dst, uint32_t len, uint32_t crc) { }
int main(int argc, char **argv)
{
    FILE *f = fopen(argv[1], "rb");
    static uint8_t src[0x110000], dst[0x100000];
    size_t n = fread(src, 1, sizeof src, f);
    fclose(f);
    (void)n;
    long got = dn_depack7(src, dst);
    printf("%ld %u %ld\n", got, (unsigned)dn7_status, host_stock_calls);
    if (got > 0 && got < 0x100000) {
        FILE *o = fopen(argv[2], "wb");
        fwrite(dst, 1, (size_t)got, o);
        fclose(o);
    }
    return 0;
}
"""


def _content(n: int, seed: int) -> bytes:
    rnd = random.Random(seed)
    words = [rnd.randrange(64) for _ in range(256)]
    out = bytearray()
    while len(out) < n:                                   # repetitive, like code, with noise
        out += bytes(words[rnd.randrange(256)] for _ in range(rnd.randrange(1, 40)))
        if rnd.random() < 0.3:
            out += rnd.randbytes(rnd.randrange(1, 9))
    return bytes(out[:n])


def _stored(stream: bytes) -> bytes:
    return len(stream).to_bytes(4, "big") + (sum(stream) & 0xFFFFFFFF).to_bytes(4, "big") + stream


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("lzma7")
    (d / "h.c").write_text(HARNESS)
    (d / "stub.h").write_text("long host_stock(const unsigned char *src, unsigned char *dst);\n"
                              "unsigned long host_malloc(unsigned int n);\n")
    exe = d / "h"
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", "-DDN7_STOCK_DEPACK=host_stock", "-DDN7_MALLOC=host_malloc", "-DDN7_FREE=free", "-include", "stdlib.h", "-include", str(d / "stub.h"),
                        "-o", str(exe), str(d / "h.c"), str(ROOT / "csrc" / "waverider" / "lzma7.c")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    def run(stored: bytes):
        (d / "in.bin").write_bytes(stored)
        out = d / "out.bin"
        if out.exists():
            os.remove(out)
        got, status, stock = map(int, subprocess.run([str(exe), str(d / "in.bin"), str(out)], capture_output=True,
                                                     text=True, check=True).stdout.split())
        return got, status, stock, (out.read_bytes() if out.exists() else None)
    return run


def test_pack_round_trip_and_header():
    data = _content(200_000, 1)
    s = lzma7.pack(data)
    assert s[:4] == b"DN7Z" and struct.unpack(">I", s[4:8])[0] == len(data)
    assert struct.unpack(">I", s[12:16])[0] == zlib.crc32(data)
    assert lzma7.unpack(s) == data
    assert len(s) < len(aplibpack.pack(data))


@pytest.mark.parametrize("corrupt", ["crc", "length", "props", "body", "pad"])
def test_unpack_refuses_what_the_decoder_refuses(corrupt):
    data = _content(50_000, 2)
    s = bytearray(lzma7.pack(data))
    if corrupt == "crc":
        s[12] ^= 1
    elif corrupt == "length":
        s[4:8] = struct.pack(">I", lzma7.MAX + 1)
    elif corrupt == "props":
        s[8] = (1 * 5 + 2) * 9 + 2                      # lc + lp = 4
    elif corrupt == "body":
        s[len(s) // 2] ^= 0x55
    else:
        s[9] = 1
    with pytest.raises(lzma7.Lzma7Error):
        lzma7.unpack(bytes(s))


def test_section_stores_and_unpacks_lzma7():
    data = _content(120_000, 3)
    sec = S.compress_lzma7(7, 0, data)
    assert len(sec.stored) % S.STORED_ALIGN == 0 and sec.sum_ok
    assert sec.unpack() == data
    assert S.compress(7, 0, data).unpack() == data      # aPLib still reads as before


def test_the_decoder_agrees_with_the_codec(harness):
    for seed, n in ((4, 1), (5, 70_000), (6, 400_000)):
        data = _content(n, seed)
        got, status, stock, out = harness(_stored(lzma7.pack(data)))
        assert (got, status, stock, out) == (n, 2, 0, data)


def test_the_decoder_hands_aplib_to_stock(harness):
    got, status, stock, out = harness(_stored(aplibpack.pack(_content(5_000, 7))))
    assert (got, status, stock) == (7, 1, 1) and out[:1] == b"\xa5"


@pytest.mark.parametrize("corrupt,why", [("crc", 6), ("length", 3), ("props", 4), ("pad", 4), ("short", 5)])
def test_the_decoder_refuses_into_the_error_path(harness, corrupt, why):
    data = _content(60_000, 8)
    s = bytearray(lzma7.pack(data))
    if corrupt == "crc":
        s[12] ^= 1
    elif corrupt == "length":
        s[4:8] = struct.pack(">I", lzma7.MAX + 1)
    elif corrupt == "props":
        s[8] = (1 * 5 + 2) * 9 + 2
    elif corrupt == "pad":
        s[10] = 1
    else:
        s = s[: len(s) // 2]                            # a cut stream: decodes zeros, fails the CRC or length
    got, status, stock, _ = harness(_stored(bytes(s)))
    assert got == REFUSE and stock == 0
    assert status == why or (corrupt == "short" and status in (5, 6))


def test_the_decoder_refuses_a_corrupt_body(harness):
    data = _content(80_000, 9)
    s = bytearray(lzma7.pack(data))
    for at in (40, len(s) // 3, len(s) - 20):
        bad = bytearray(s)
        bad[at] ^= 0x5A
        got, status, stock, _ = harness(_stored(bytes(bad)))
        assert got == REFUSE and status in (5, 6) and stock == 0

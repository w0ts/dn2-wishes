"""The DSP program decoded once and kept on the +Drive (csrc/waverider/lzma7cache.c, docs/lzma7.md "The cache"):
lzma7.c and lzma7cache.c compiled for the host, the stock block driver played by a fake +Drive (the cache's
sectors only). Each run is one boot's dn_depack7: the first writes the copy, the next reads it byte for byte
without decoding, and a damaged, foreign or half-written copy, a read or a write that fails, or a +Drive that is
not up all end in the decode, never in a wrong program."""

from __future__ import annotations

import os
import pathlib
import random
import shutil
import struct
import subprocess
import zlib

import pytest

from dnfw.codec import lzma7

ROOT = pathlib.Path(__file__).resolve().parent.parent
C_HDR, C_SECTORS = 0x6E8000, 1 + 2048


def _content(n: int, seed: int) -> bytes:
    rnd = random.Random(seed)
    words = [rnd.randrange(64) for _ in range(256)]
    out = bytearray()
    while len(out) < n:                                   # repetitive, like code, with noise (test_lzma7's)
        out += bytes(words[rnd.randrange(256)] for _ in range(rnd.randrange(1, 40)))
        if rnd.random() < 0.3:
            out += rnd.randbytes(rnd.randrange(1, 9))
    return bytes(out[:n])


def _stored(stream: bytes) -> bytes:
    return len(stream).to_bytes(4, "big") + (sum(stream) & 0xFFFFFFFF).to_bytes(4, "big") + stream
HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern long dn_depack7(const uint8_t *src, uint8_t *dst);
extern volatile uint32_t dn7_status, dn7c_state, dn7c_why;
static uint8_t disk[(1 + 2048) * 512];
uint32_t host_ready = 1, host_sectors = 48340992;
static long reads, writes, write_fail_at = -1, read_fail = 0, bad = 0;
long host_stock(const uint8_t *src, uint8_t *dst) { return 0x100000; }
unsigned long host_malloc(unsigned int n) { return (unsigned long)malloc(n); }
static int span_ok(uint32_t s, uint32_t n)
{
    if (s < 0x6E8000u || n == 0 || n > 0x10000u || (s - 0x6E8000u) * 512u + n > sizeof disk) { bad++; return 0; }
    return 1;
}
int host_read(uint32_t s, uint32_t n, void *buf)
{
    reads++;
    if (read_fail || !span_ok(s, n))
        return -1;
    memcpy(buf, disk + (s - 0x6E8000u) * 512u, n);
    return 0;
}
int host_write(uint32_t s, uint32_t n, const void *buf)
{
    if (writes++ == write_fail_at || !span_ok(s, n))
        return -1;                                  /* a failed write (or a power cut): nothing after it */
    memcpy(disk + (s - 0x6E8000u) * 512u, buf, n);
    return 0;
}
int main(int argc, char **argv)
{
    static uint8_t src[0x110000], buf[0x100000];
    FILE *f = fopen(argv[1], "rb");
    fread(src, 1, sizeof src, f);
    fclose(f);
    f = fopen(argv[2], "rb");
    if (f) { fread(disk, 1, sizeof disk, f); fclose(f); }
    host_ready = atoi(argv[4]);
    write_fail_at = atol(argv[5]);
    read_fail = atoi(argv[6]);
    memset(buf, 0xEE, sizeof buf);
    buf[0] = 3;                                     /* the uploader's 0x03; dst after it, as stock */
    long got = dn_depack7(src, buf + 1);
    f = fopen(argv[2], "wb");                      /* the +Drive as this boot left it */
    fwrite(disk, 1, sizeof disk, f);
    fclose(f);
    printf("%ld %u %u %u %ld %ld %ld\n", got, (unsigned)dn7_status, (unsigned)dn7c_state, (unsigned)dn7c_why,
           reads, writes, bad);
    if (got > 0 && got < 0x100000) {
        f = fopen(argv[3], "wb");
        fwrite(buf + 1, 1, (size_t)got, f);
        fclose(f);
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def boot(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("lzma7cache")
    (d / "h.c").write_text(HARNESS)
    (d / "stub.h").write_text("#include <stdint.h>\n"
                              "long host_stock(const unsigned char *src, unsigned char *dst);\n"
                              "unsigned long host_malloc(unsigned int n);\n"
                              "int host_read(uint32_t s, uint32_t n, void *buf);\n"
                              "int host_write(uint32_t s, uint32_t n, const void *buf);\n"
                              "extern uint32_t host_ready, host_sectors;\n")
    exe = d / "h"
    defines = ["-DDN7_STOCK_DEPACK=host_stock", "-DDN7_MALLOC=host_malloc", "-DDN7_FREE=free",
               "-DDN7C_READ=host_read", "-DDN7C_WRITE=host_write", "-DDN7C_READY=host_ready",
               "-DDN7C_SECTORS=host_sectors"]
    r = subprocess.run([cc, "-O1", "-w", *defines, "-include", "stdlib.h", "-include", str(d / "stub.h"),
                        "-o", str(exe), str(d / "h.c"), str(ROOT / "csrc" / "waverider" / "lzma7.c"),
                        str(ROOT / "csrc" / "waverider" / "lzma7cache.c")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    def run(stored: bytes, disk, *, ready=1, write_fail_at=-1, read_fail=0):
        (d / "in.bin").write_bytes(stored)
        out = d / "out.bin"
        if out.exists():
            os.remove(out)
        res = subprocess.run([str(exe), str(d / "in.bin"), str(disk), str(out), str(ready), str(write_fail_at),
                              str(read_fail)], capture_output=True, text=True, check=True).stdout.split()
        got, status, state, why, reads, writes, bad = map(int, res)
        assert bad == 0, "a driver call outside the cache's sectors or over 64 KB"
        return {"got": got, "status": status, "state": state, "why": why, "reads": reads, "writes": writes,
                "out": out.read_bytes() if out.exists() else None}
    return run


def _build(n=300_000, seed=11):
    data = _content(n, seed)
    return data, _stored(lzma7.pack(data))


def test_first_boot_writes_the_copy_header_last(boot, tmp_path):
    data, stored = _build()
    disk = tmp_path / "disk.bin"
    r = boot(stored, disk)
    assert (r["got"], r["status"], r["state"], r["out"]) == (len(data), 2, 3, data)
    img = disk.read_bytes()
    hdr = img[:512]
    assert hdr[:4] == b"DN7C" and struct.unpack(">III", hdr[4:16]) == (1, len(data), zlib.crc32(data))
    assert hdr[16:40] == stored[:24] and struct.unpack(">I", hdr[40:44])[0] == zlib.crc32(hdr[:40])
    assert img[512:512 + len(data)] == data
    # writes: the header cleared, the program in 64 KB calls, the header
    assert r["writes"] == 1 + -(-len(data) // 0x10000) + 1


def test_second_boot_reads_it_byte_for_byte(boot, tmp_path):
    data, stored = _build()
    disk = tmp_path / "disk.bin"
    boot(stored, disk)
    r = boot(stored, disk)
    assert (r["got"], r["status"], r["state"], r["writes"], r["out"]) == (len(data), 8, 1, 0, data)


@pytest.mark.parametrize("where,why", [("magic", 1), ("id", 2), ("length", 3), ("check", 4), ("body", 5),
                                       ("last", 5)])
def test_a_damaged_copy_falls_back_to_decoding_and_is_rewritten(boot, tmp_path, where, why):
    data, stored = _build()
    disk = tmp_path / "disk.bin"
    boot(stored, disk)
    img = bytearray(disk.read_bytes())
    at = {"magic": 0, "id": 20, "length": 9, "check": 41, "body": 512 + len(data) // 2,
          "last": 512 + len(data) - 1}[where]
    img[at] ^= 0x10
    disk.write_bytes(bytes(img))
    r = boot(stored, disk)
    assert (r["got"], r["status"], r["state"], r["why"], r["out"]) == (len(data), 2, 3, why, data)
    r = boot(stored, disk)
    assert (r["status"], r["state"], r["out"]) == (8, 1, data)


def test_a_new_build_id_refreshes_the_copy(boot, tmp_path):
    old, old_stored = _build(seed=12)
    new, new_stored = _build(seed=13)
    disk = tmp_path / "disk.bin"
    boot(old_stored, disk)
    r = boot(new_stored, disk)
    assert (r["status"], r["state"], r["why"], r["out"]) == (2, 3, 2, new)
    r = boot(new_stored, disk)
    assert (r["status"], r["state"], r["out"]) == (8, 1, new)


def test_same_program_other_stream_is_another_id(boot, tmp_path):
    data, stored = _build(seed=14)
    disk = tmp_path / "disk.bin"
    boot(stored, disk)
    other = bytearray(stored)
    other[4:8] = struct.pack(">I", (struct.unpack(">I", stored[4:8])[0] + 1) & 0xFFFFFFFF)   # another byte sum
    r = boot(bytes(other), disk)
    assert (r["status"], r["why"]) == (2, 2)


@pytest.mark.parametrize("fail_at", [0, 1, 3, 6])
def test_a_failed_write_still_boots_and_never_leaves_a_wrong_program(boot, tmp_path, fail_at):
    data, stored = _build()
    disk = tmp_path / "disk.bin"
    old, old_stored = _build(seed=15)
    boot(old_stored, disk)                          # an older build's valid copy on the +Drive
    r = boot(stored, disk, write_fail_at=fail_at)
    assert (r["got"], r["status"], r["state"], r["out"]) == (len(data), 2, 4, data)
    r = boot(stored, disk)                          # the next boot: decodes and writes it again
    assert (r["status"], r["state"], r["out"]) == (2, 3, data)
    r = boot(old_stored, disk)                      # nor does the old build read a half-written copy
    assert r["out"] == old and r["status"] == 2


def test_a_failed_read_decodes(boot, tmp_path):
    data, stored = _build()
    disk = tmp_path / "disk.bin"
    boot(stored, disk)
    r = boot(stored, disk, read_fail=1)
    assert (r["status"], r["state"], r["out"]) == (2, 3, data)    # decoded, then written again


def test_no_drive_no_io(boot, tmp_path):
    data, stored = _build()
    disk = tmp_path / "disk.bin"
    r = boot(stored, disk, ready=0)
    assert (r["status"], r["state"], r["reads"], r["writes"], r["out"]) == (2, 0, 0, 0, data)


def test_an_erased_copy_decodes(boot, tmp_path):
    data, stored = _build()
    disk = tmp_path / "disk.bin"
    boot(stored, disk)
    for erased in (0x00, 0xFF):                     # the card's ERASED_MEM_CONT either way
        disk.write_bytes(bytes([erased]) * (C_SECTORS * 512))
        r = boot(stored, disk)
        assert (r["status"], r["state"], r["why"], r["out"]) == (2, 3, 1, data)


def test_the_largest_program_fits_its_sectors(boot, tmp_path):
    rnd = random.Random(16)
    data = bytes(rnd.randrange(4) for _ in range(0xFFE00))   # the largest whose whole sectors fit the buffer
    stored = _stored(lzma7.pack(data))
    disk = tmp_path / "disk.bin"
    assert boot(stored, disk)["state"] == 3
    r = boot(stored, disk)
    assert (r["status"], r["out"]) == (8, data)

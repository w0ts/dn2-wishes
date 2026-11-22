"""const-pool proof: the pool builds PERC text vs the bases: the same instructions in the same order but
(a) Rn = 0xV -> Rn = DM(k, I6) with pool[k + len(pool) // 2] == V, (b) the I6 save, set and restore."""
import json, re, sys
base, new = sys.argv[1], sys.argv[2]
pool = json.load(open(f"{new}/csrc/waverider/sharc/perc_pool.json"))["words"]
def ins(path):
    out = []
    for l in open(path):
        s = l.strip()
        if l.startswith("      ") and s and not s.startswith(("//", ".")) and ";" in s:
            code, _, note = s.partition("//")
            out.append((re.sub(r"0x[0-9a-f]{5,}", "A", code.strip()), code.strip(), note.strip()))
    return out
tot = {"pooled": 0, "added": 0}
for name in ("perc", "perc2a", "perc2b"):
    a = ins(f"{base}/csrc/waverider/sharc/{name}.asm"); b = ins(f"{new}/csrc/waverider/sharc/{name}.asm")
    i = j = 0; pooled = added = 0
    while i < len(a) or j < len(b):
        if j < len(b) and re.match(r"^(DM\(0x2dde70\) = I6|I6 = 0x2e1a60|I6 = DM\(0x2dde70\));$", b[j][1]):
            added += 1; j += 1; continue
        assert i < len(a) and j < len(b), (name, i, j)
        m = re.match(r"^R(\d+) = DM\((-?\d+), I6\);$", b[j][1])
        if m:
            k = int(m.group(2)); v = int(b[j][2].split()[0], 16) & 0xFFFFFFFF
            ma = re.match(r"^R(\d+) = (-?0x[0-9a-f]+);$", a[i][1])
            assert ma and ma.group(1) == m.group(1) and (int(ma.group(2), 16) & 0xFFFFFFFF) == v == pool[k + len(pool) // 2], (name, a[i], b[j])
            pooled += 1
        else:
            assert a[i][0] == b[j][0], (name, i, a[i], b[j])
        i += 1; j += 1
    print(f"{name}: {len(a)} -> {len(b)} instructions, {pooled} loads from the pool, {added} added (I6)")
    tot["pooled"] += pooled; tot["added"] += added
print("ALL SAME but those:", tot, "pool distinct values used:", len(set(pool)))

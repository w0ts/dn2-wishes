#!/usr/bin/env bash
# Our patches to selache (github.com/js216/selache, GPL-3.0; the bench's SHARC+ assembler), applied to a
# checkout of it and selas rebuilt (docs/selas-encoding.md). Idempotent: a patch already in the checkout is
# skipped. On gpufarm: tools/selache/apply.sh ~/dn2mk2-bench/Z/selache ~/dn2mk2-bench/tools/selache-target
#   SELACHE  the selache checkout (base 2b26d3b, "cosmetic change")
#   TARGET   cargo's target directory (the bench's selas is TARGET/release/selas)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
selache="$(cd "$1" && pwd)"
target="$2"
export PATH="$HOME/.cargo/bin:$PATH"
for p in "$here"/0*.patch; do
  if git -C "$selache" apply --reverse --check "$p" 2>/dev/null; then
    echo "already in: $(basename "$p")"
  else
    git -C "$selache" apply --check "$p"
    git -C "$selache" apply "$p"
    echo "applied: $(basename "$p")"
  fi
done
(cd "$selache" && cargo test -q -p selas modify_nw && nice -n 10 cargo build -q --release -p selas --target-dir "$target")
echo "built: $target/release/selas"

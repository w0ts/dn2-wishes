#!/usr/bin/env bash
# Our patches to selache (github.com/js216/selache, GPL-3.0; the bench's SHARC+ assembler), applied to a
# checkout of it and selas rebuilt (docs/selas-encoding.md). Idempotent: a patch already in the checkout is
# skipped. On the farm: tools/selache/apply.sh $BENCH/Z/selache $BENCH/tools/selache-target \
#   $BENCH/tools/selmap-target
#   SELACHE  the selache checkout (base 2b26d3b, "cosmetic change")
#   TARGET   cargo's target directory (the bench's selas is TARGET/release/selas)
#   SELMAP_TARGET (optional) selmap's target directory, rebuilt from the patched decoder
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
(cd "$selache" && cargo test -q -p selas modify_nw && cargo test -q -p selas multifunction \
  && cargo test -q -p selinstr multi && nice -n 10 cargo build -q --release -p selas --target-dir "$target")
echo "built: $target/release/selas"
# 0002 changes selinstr's decoder too: selmap (tools/selmap, the gate's second decoder) is rebuilt from it when
# its target directory is given (on the farm: $BENCH/tools/selmap-target)
if [ -n "${3:-}" ]; then
  (cd "$here/../selmap" && nice -n 10 cargo build -q --release --target-dir "$3")
  echo "built: $3/release/selmap"
fi

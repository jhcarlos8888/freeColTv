#!/usr/bin/env bash
# Inventario de verdad DEX: todos los descriptores de clase de classes*.dex.
# Uso: tools/inventario_dex.sh [salida]   (por defecto mediciones/dex_clases.txt)
set -euo pipefail
BASE="$(cd "$(dirname "$0")/.." && pwd)"
DEXDUMP="${DEXDUMP:-$HOME/Android/Sdk/build-tools/34.0.0/dexdump}"
DEC="$BASE/XuperDorado_project/apktool_decoded"
OUT="${1:-$BASE/mediciones/dex_clases.txt}"
[ -x "$DEXDUMP" ] || { echo "no existe dexdump: $DEXDUMP" >&2; exit 1; }
: > "$OUT"
n=0
for d in "$DEC"/classes*.dex; do
  # Class descriptor  : 'Lfoo/Bar$baz;'
  "$DEXDUMP" -f "$d" | sed -n "s/^  Class descriptor  : '\(.*\)'$/\1/p" >> "$OUT"
  n=$((n+1))
done
echo "dex procesados: $n | clases: $(wc -l < "$OUT") | salida: $OUT"

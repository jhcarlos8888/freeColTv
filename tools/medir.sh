#!/usr/bin/env bash
# Compila TODO app/src/main/java replicando EXACTAMENTE la invocacion de javac de
# Gradle/AGP (verificado: 19.028 errores = N0 de Gradle, mismas familias), pero
# sin Gradle => iteracion de ~10 s y sin el transporte que provoco el OOM.
#
# Replicacion exacta (descubierta por medicion):
#   * MISMO orden de ficheros (app/build/sources_gradle_order.txt): el orden
#     cambia el numero de errores que javac recupera/reports.
#   * MISMA plataforma: --system <jdkImage de AGP> (si no, difieren sun.misc,
#     javax.swing, java.lang.Object...).
#   * Mismos flags: -g -encoding UTF-8 -source/-target 17 -Xmaxerrs 300000
#     -XDstringConcat=inline.
#
# Uso:  tools/medir.sh [log_salida]
#   OUT=/tmp/opencode/xx tools/medir.sh mediciones/mi_log.log
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRJ="$BASE/XuperDorado_project"
SRC="$PRJ/app/src/main/java"
CPFILE="$PRJ/app/build/compile_classpath.txt"
ORDFILE="$PRJ/app/build/sources_gradle_order.txt"
IMGFILE="$PRJ/app/build/system_image.txt"
LOG="${1:-$BASE/mediciones/actual.log}"
OUT="${OUT:-/tmp/opencode/javac_out}"

if [ ! -f "$CPFILE" ]; then
  echo "FALTA el classpath de Gradle. Ejecuta:" >&2
  echo "  gradle -I tools/dump_classpath.gradle -q :app:dumpCp" >&2
  exit 2
fi

mkdir -p "$OUT/classes" "$(dirname "$LOG")"

# Orden de fuentes: el de Gradle si existe (paridad exacta); si no, orden alfabético
if [ -f "$ORDFILE" ]; then
  LISTA="$ORDFILE"
  # la lista se genera con los ficheros actuales: si el arbol ha cambiado
  # (renombres/borrados) hay que volver a volcarla con Gradle
  faltan=0
  while IFS= read -r l; do
    p="${l%\"}"; p="${p#\"}"
    [ -f "$p" ] || faltan=$((faltan+1))
  done < "$ORDFILE"
  if [ "$faltan" -gt 0 ]; then
    echo "AVISO: la lista de fuentes de Gradle tiene $faltan ficheros inexistentes." >&2
    echo "       Regenerala: gradle -I tools/dump_classpath.gradle -q :app:dumpCp" >&2
  fi
  echo "fuentes: en ORDEN de Gradle ($(wc -l < "$LISTA"))"
else
  LISTA="$OUT/sources.txt"
  # IMPORTANTE: las rutas llevan espacios y javac separa los argumentos del @file
  # por espacios => hay que entrecomillarlas (si no, los fragmentos que empiezan
  # por '/' se toman por error como flags).
  find "$SRC" -name '*.java' | LC_ALL=C sort | sed 's/^/"/; s/$/"/' > "$LISTA"
  echo "fuentes: ORDEN ALFABETICO ($(wc -l < "$LISTA")) [sin paridad con Gradle]"
fi

SYSARGS=()
if [ -f "$IMGFILE" ] && [ -n "$(cat "$IMGFILE")" ]; then
  SYSARGS=(--system "$(cat "$IMGFILE")")
  echo "plataforma: --system $(basename "$(cat "$IMGFILE")")"
else
  echo "plataforma: JDK por defecto [sin paridad con Gradle]"
fi

set +e
/usr/bin/time -f "tiempo=%Es maxrss=%MKB" javac \
  -J-Xmx8g \
  -g \
  -encoding UTF-8 \
  -source 17 -target 17 \
  -Xmaxerrs 300000 \
  -XDstringConcat=inline \
  ${SYSARGS[@]+"${SYSARGS[@]}"} \
  -cp "$(cat "$CPFILE")" \
  -d "$OUT/classes" \
  "@$LISTA" > "$LOG" 2>&1
rc=$?
set -e

echo "javac exit=$rc"
echo "log: $LOG ($(wc -l < "$LOG") lineas)"
echo "resumen javac: $(grep -E '^[0-9]+ errors?$' "$LOG" | tail -1 || echo '(sin resumen: compilacion abortada)')"
tail -1 "$LOG" | grep -q "tiempo=" && tail -1 "$LOG" || true
echo "N0 de referencia (Gradle): 19,028 errors | SOMBRA=2193"

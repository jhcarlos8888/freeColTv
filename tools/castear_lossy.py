#!/usr/bin/env python3
"""Cast estrecho guiado por caret para 'possible lossy conversion'.

Sintoma javac: `incompatible types: possible lossy conversion from int
to short|byte`. En el DEX no hay registros small-type: el decompilador
declara campos/params short|byte pero las expresiones se calculan como
int. El bytecode original TRUNCABA (semantica DEX), asi que anadir el
cast explicito la preserva exactamente.

Regla segura: solo se envuelve un token SIMPLE (literal o identificador)
que es la EXPRESION COMPLETA hasta un delimitador `,`, `)` o `;` (pos.
del caret = inicio de la expresion ofensiva). Expresiones complejas se
omiten y se reportan (nunca se reescribe a ciegas).

Uso:
  python3 tools/castear_lossy.py <log> [--aplicar]
"""
import argparse
import os
import re
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAT = re.compile(
    r"^(.*\.java):(\d+): error: incompatible types: possible lossy "
    r"conversion from (\w+) to (\w+)$")
PAT_TOKEN = re.compile(r"^([\w.$]+)\b")
# delimitadores que cierran una expresion de argumento
DELIMS = ",);"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    lineas_log = open(args.log, encoding="utf-8", errors="replace"
                      ).read().split("\n")

    cambios = defaultdict(list)   # fich -> [(linea_idx, col, tipo)]
    stats = Counter()
    omitidos = []

    for i, ln in enumerate(lineas_log):
        m = PAT.match(ln.rstrip("\n"))
        if not m:
            continue
        fich, l_err = m.group(1), int(m.group(2))
        tipo = m.group(4)   # tipo destino (short/byte/int/...)
        # bloque javac: [i+1] codigo, [i+2] caret
        if i + 2 >= len(lineas_log):
            stats["bloque_incompleto"] += 1
            continue
        cod_log = lineas_log[i + 1]
        caret = lineas_log[i + 2]
        ccol = caret.find("^")
        if ccol < 0:
            stats["sin_caret"] += 1
            continue
        lineas = open(fich, encoding="utf-8", errors="replace").read(
        ).split("\n")
        if l_err - 1 >= len(lineas):
            stats["linea_fuera"] += 1
            continue
        cod = lineas[l_err - 1]
        # el log conserva la sangria original: col = columna del caret
        frag = cod_log.strip()
        if (frag if len(frag) < 40 else frag[:40]) not in cod:
            stats["linea_no_coincide"] += 1
            omitidos.append((fich, l_err))
            continue
        # javac apunta a veces al '.' de un acceso (countObject.value):
        # se retrocede hasta el inicio de la cadena calificada
        col = ccol
        while col > 0 and (cod[col - 1].isalnum()
                           or cod[col - 1] in "_$."):
            col -= 1
        if col > 0 and (cod[col - 1].isalnum()
                        or cod[col - 1] in "_$."):
            stats["expresion_compleja"] += 1
            omitidos.append((fich, l_err, cod.strip()[:80]))
            continue
        resto = cod[col:]
        mt = PAT_TOKEN.match(resto)
        token = mt.group(1) if mt else None
        tras = resto[mt.end():].lstrip() if mt else ""
        if token and tras and tras[0] in ",);":
            # regla 1: token simple que es la expresion completa
            cambios[fich].append((l_err - 1, col, tipo, "token", token))
            stats["casts"] += 1
            continue
        # regla 2: asignacion -> envolver TODO el RHS
        if " = " in cod and cod.index(" = ") < col \
                and cod.count(" = ") == 1 and cod.rstrip().endswith(";"):
            ini = cod.index(" = ") + 3
            fin = cod.rstrip().rindex(";")
            cambios[fich].append((l_err - 1, ini, tipo, "rhs",
                                 (ini, fin)))
            stats["casts_rhs"] += 1
            continue
        stats["expresion_compleja"] += 1
        omitidos.append((fich, l_err, cod.strip()[:80]))

    print("resumen:")
    for k, v in stats.most_common():
        print(f"  {v:5d}  {k}")
    if omitidos[:8]:
        print("omitidos (muestra):")
        for o in omitidos[:8]:
            rel = o[0].split(os.sep + "java" + os.sep)[-1]
            print(f"    {rel}:{o[1]}  {o[2] if len(o) > 2 else ''}")

    if args.aplicar:
        for fich, items in cambios.items():
            lineas = open(fich, encoding="utf-8", errors="replace").read(
            ).split("\n")
            tocadas = set()
            # orden descendente por linea y columna (coords originales)
            for l0, col, tipo, op, payload in sorted(
                    items, key=lambda x: (-x[0], -x[1])):
                cod = lineas[l0]
                if op == "token":
                    if cod[col:col + len(payload)] != payload:
                        stats["desfase_no_aplicado"] += 1
                        continue
                    lineas[l0] = cod[:col] + f"({tipo}) " + cod[col:]
                    tocadas.add(l0)
                else:   # rhs: se recalcula en el momento de aplicar
                    if l0 in tocadas or cod.count(" = ") != 1 \
                            or not cod.rstrip().endswith(";"):
                        stats["rhs_omitido"] += 1
                        continue
                    ini = cod.index(" = ") + 3
                    fin = cod.rstrip().rindex(";")
                    lineas[l0] = (cod[:ini] + f"({tipo}) ("
                                  + cod[ini:fin] + ")" + cod[fin:])
                    tocadas.add(l0)
            open(fich, "w", encoding="utf-8").write("\n".join(lineas))
        total = stats["casts"] + stats["casts_rhs"]
        print(f"[APlicado] {total} casts.")
    else:
        total = stats["casts"] + stats["casts_rhs"]
        print(f"\n[DRY-RUN] {total} casts previstos. Repite con --aplicar.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Repara referencias a paquetes raiz SOMBREADOS por tipos homonimos.

Sintoma javac (variante a, cadena se rompe en el 2o segmento):

    t.k.a(TAG);
      ^
    symbol:   variable k
    location: interface t          <- 't' anidado sombrea al paquete t

    symbol:   method d(...)        <- variante b: e/b sombrea e.anidada.b
    location: class b0.e.b

Causa: en EXPRESIONES JLS resuelve el izquierdo como TIPO si hay tipo en
scope; no existe forma de escribir el paquete sombreado. Verificado con
javac (sondas A/B/C en /tmp/opencode/probe2):

  * `import t.k;` + `k.a(...)` funciona aunque haya tipo 't' anidado
    (los imports se resuelven contra paquetes, fuera del scope de
    expresiones) -> estrategia 'a'. Requiere que el simple 'k' no este
    sombreado en el sitio (si el fichero declara tipo anidado 'k', no).
  * `import static e.b.d;` + `d(...)` funciona con 'e' Y 'b' anidados
    -> estrategia 'b'. Requiere que el simple 'd' no este sombreado.

Eleccion por sitio: si el fichero declara un TIPO anidado con el nombre
del 2o segmento -> estrategia b; si no -> a. Cada linea se reescribe
eliminando solo el prefijo `<paquete>.` y se anade el import oportuno
(sin duplicarlo).

Estricto: exige que `symbol` coincida con el segmento que rompe la
cadena y que el `location` contenga el nombre del paquete (evita falsos
positivos como argumentos perdidos en lineas que ademas citan paquetes).

Uso:
  python3 tools/importar_paquetes_sombreados.py <log> [--aplicar]
"""
import argparse
import os
import re
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main",
                   "java")

PAT_ERR = re.compile(r"^(.*\.java):(\d+): error: cannot find symbol$")
PAT_SYM = re.compile(r"^\s+symbol:\s+(variable|method|class)\s+(\S+)")
# location: '<kind> <nombre>' con kind de TIPO (class/interface/...);
# el nombre puede llevar puntos (p.ej. 'class b0.e.b')
PAT_LOC = re.compile(
    r"^\s+location:\s+(class|interface|enum|type)\s+([A-Za-z_$][\w$.]*)"
    r"\s*$")
PAT_COD = re.compile(r"(?<![\w.$])(\w+)\.(\w+)\.(\w+)\s*\(")
PAT_TIPO_ANID = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|private|protected|"
    r"static|final|abstract|strictfp|sealed)\s+)*"
    r"(?:class|interface|enum|record)\s+(\w+)\b")


def raices():
    return {d for d in os.listdir(SRC)
            if os.path.isdir(os.path.join(SRC, d))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    raiz = raices()
    lineas_log = open(args.log, encoding="utf-8", errors="replace"
                      ).read().split("\n")

    cambios = defaultdict(list)   # fich -> [(linea_idx, pkg, cls, mem, estrat)]
    imports = defaultdict(set)    # fich -> set(lineas import)
    stats = Counter()
    omitidos = []

    for i, ln in enumerate(lineas_log):
        m = PAT_ERR.match(ln.rstrip("\n"))
        if not m:
            continue
        fich, l_err = m.group(1), int(m.group(2))
        if i + 4 >= len(lineas_log):
            stats["bloque_incompleto"] += 1
            continue
        cod = lineas_log[i + 1]
        msym = PAT_SYM.match(lineas_log[i + 3])
        mloc = PAT_LOC.match(lineas_log[i + 4])
        if not msym or not mloc:
            # orden invertido u otro formato
            msym2 = PAT_SYM.match(lineas_log[i + 4])
            msloc2 = PAT_LOC.match(lineas_log[i + 3])
            if not (msym2 and msloc2):
                stats["bloque_sin_sym_loc"] += 1
                continue
            msym, mloc = msym2, msloc2
        tipo_sym, nom_sym = msym.group(1), msym.group(2)
        loc = mloc.group(2)   # nombre del tipo (sin el kind)

        cands = []
        for mc in PAT_COD.finditer(cod):
            pkg, cls, mem = mc.group(1), mc.group(2), mc.group(3)
            if pkg not in raiz:
                continue
            if not os.path.isfile(os.path.join(SRC, pkg, cls + ".java")):
                continue
            # el location debe contener el nombre del paquete sombreado
            segs_loc = loc.split(".")
            if pkg not in segs_loc:
                continue
            # coherencia symbol <-> segmento que rompio la cadena
            if tipo_sym == "variable" and nom_sym == cls:
                varante = "a"
            elif tipo_sym == "method" and nom_sym.split("(")[0] == mem:
                varante = "b"
            elif tipo_sym == "variable" and nom_sym == mem:
                varante = "b"   # cadena se rompio en variable del miembro
            else:
                continue
            cands.append((mc, pkg, cls, mem, varante))
        if not cands:
            stats["sin_firma"] += 1
            continue
        if len(cands) > 1:
            stats["ambiguo"] += 1
            omitidos.append((fich.split(os.sep + "java" + os.sep)[-1],
                             l_err, cod.strip()[:70]))
            continue
        mc, pkg, cls, mem, varante = cands[0]

        # eleccion: tipo anidado con nombre del 2o segmento -> static
        tipos_fich = set()
        if os.path.isfile(fich):
            for l in open(fich, encoding="utf-8", errors="replace"):
                mt = PAT_TIPO_ANID.match(l)
                if mt:
                    tipos_fich.add(mt.group(1))
        estrat = "b" if cls in tipos_fich else "a"
        if varante == "a" and estrat == "a":
            stats["estrat_a"] += 1
        elif estrat == "b":
            stats["estrat_b"] += 1
        cambios[fich].append((l_err - 1, pkg, cls, mem, estrat))
        if estrat == "a":
            imports[fich].add(f"import {pkg}.{cls};")
        else:
            imports[fich].add(f"import static {pkg}.{cls}.{mem};")

    print("resumen:")
    for k, v in stats.most_common():
        print(f"  {v:5d}  {k}")
    if omitidos[:6]:
        print("omitidos (muestra):")
        for o in omitidos[:6]:
            print(f"    {o[0]}:{o[1]}  {o[2]}")

    total = sum(len(v) for v in cambios.values())
    print(f"previstos: {total} sitios en {len(cambios)} ficheros")
    print("muestra:")
    n = 0
    for fich, items in cambios.items():
        for l0, pkg, cls, mem, estrat in items:
            try:
                cod = open(fich, encoding="utf-8",
                           errors="replace").read().split("\n")[l0]
            except Exception:
                continue
            nuevo = (f"{cls}.{mem}(" if estrat == "a" else f"{mem}(")
            rel = fich.split(os.sep + "java" + os.sep)[-1]
            print(f"  {rel}:{l0+1} [{estrat}]")
            print(f"    - {cod.strip()[:95]}")
            print(f"    + {cod.replace(pkg + '.' + cls + '.' + mem + '(', nuevo, 1).strip()[:95]}")
            n += 1
            if n >= 8:
                break
        if n >= 8:
            break

    if args.aplicar:
        for fich, items in cambios.items():
            lineas = open(fich, encoding="utf-8", errors="replace"
                          ).read().split("\n")
            for l0, pkg, cls, mem, estrat in sorted(items,
                                                    key=lambda x: -x[0]):
                cod = lineas[l0]
                viejo = f"{pkg}.{cls}.{mem}("
                nuevo = (f"{cls}.{mem}(" if estrat == "a"
                         else f"{mem}(")
                if viejo not in cod:
                    stats["desfase_no_aplicado"] += 1
                    continue
                lineas[l0] = cod.replace(viejo, nuevo, 1)
            # insercion de imports (sin duplicar)
            texto = "\n".join(lineas)
            existentes = set(re.findall(r"^import .*$", texto, re.M))
            nuevos = [im for im in sorted(imports[fich])
                      if im not in existentes]
            if nuevos:
                idx_ult = -1
                for j, l in enumerate(lineas):
                    if l.startswith("import "):
                        idx_ult = j
                    elif l.startswith("package ") and idx_ult < 0:
                        idx_pkg = j
                if idx_ult >= 0:
                    lineas[idx_ult + 1:idx_ult + 1] = nuevos
                else:
                    # tras la ultima linea 'package' (o al inicio)
                    pos = 0
                    for j, l in enumerate(lineas):
                        if l.startswith("package "):
                            pos = j + 1
                    lineas[pos:pos] = [""] + nuevos
            open(fich, "w", encoding="utf-8").write("\n".join(lineas))
        print(f"[APlicado] {total} sitios.")
    else:
        print("\n[DRY-RUN] nada modificado. Repite con --aplicar.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Repara errores de javac causados por el renombrado de clases tapadoras.

Filosofia: **javac indica la posicion exacta (caret) y el contexto**; aqui solo se
reescribe el identificador que javac senala, y solo si el contexto demuestra que
se refiere a la clase que renombramos. Nada de adivinar.

Reglas implementadas (todas seguras: en el baseline el nombre viejo resolvia,
por lo que un error con esta forma no puede ser pre-existente):

  R1  caret sobre un nombre renombrado C:
        - calificador != ""  -> el calificador debe ser exactamente pkg
        - calificador == ""   -> el fichero esta en pkg, o lo importa
                                 (import pkg.C / import pkg.*)
  R2  caret sobre N de 'C.N' y el calificador termina en .C renombrado
  R3  mensaje 'package <pkg>.C does not exist' (imports) -> renombrar C en la
      cadena del propio mensaje/linea

Repetir hasta punto fijo (cada iteracion ~10 s con tools/medir.sh):

    tools/medir.sh mediciones/loop_N.log
    python3 tools/reparar_por_errores.py mediciones/loop_N.log
"""
import argparse
import collections
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")
MED = os.path.join(BASE, "mediciones")

PAT_ARCH = re.compile(r"^(.*\.java):(\d+): error: (.*)$")
PAT_SYM = re.compile(r"symbol:\s+(?:class|variable|method)\s+([\w]+)")
PAT_LOC = re.compile(r"location:\s+(?:class|interface|enum)\s+([\w.$]+)")
PAT_CARET = re.compile(r"^[ \t]*\^")
PAT_PKG = re.compile(r"^package\s+([\w.]+)\s*;")
PAT_IMP = re.compile(r"^import\s+([\w.$]+)\s*;", re.M)
PAT_IMPW = re.compile(r"^import\s+([\w.]+)\.\*\s*;", re.M)


def leer(ruta):
    return open(ruta, encoding="utf-8", errors="replace").read()


def escribir(ruta, txt):
    open(ruta, "w", encoding="utf-8").write(txt)


def paquete_de(ruta):
    rel = ruta.replace(SRC + "/", "").replace(SRC + os.sep, "")
    return os.path.dirname(rel).replace("/", ".")


def parsear_bloques(log):
    """[(ruta, linea, msg, cod, caret_col, sym, loc)] — una entrada por error.

    Cada linea de error se procesa por separado y NUNCA se consume la
    siguiente (antes, un bloque sin linea 'location:' se tragaba los
    errores venideros y se perdian ~4.800 bloques del log).
    """
    lineas = open(log, encoding="utf-8", errors="replace").read().split("\n")
    out = []
    for i, ln0 in enumerate(lineas):
        m = PAT_ARCH.match(ln0)
        if not m:
            continue
        cod = car = sym = loc = None
        for j in range(i + 1, min(i + 6, len(lineas))):
            ln = lineas[j]
            if PAT_ARCH.match(ln):
                break  # siguiente error: no consumir
            if ln.startswith("  symbol:"):
                ms = PAT_SYM.search(ln)
                if ms:
                    sym = ms.group(1)
                continue
            if ln.startswith("  location:"):
                ml = PAT_LOC.search(ln)
                if ml:
                    loc = ml.group(1)
                break
            if ln.startswith("package ") and "does not exist" in ln:
                mp = PAT_PKG.search(ln)
                if mp:
                    loc = mp.group(1)
                break
            if cod is None and ln and not PAT_CARET.match(ln):
                cod = ln
            elif car is None and PAT_CARET.match(ln):
                car = len(ln) - len(ln.lstrip(" \t")) + 1
        out.append(
            dict(f=m.group(1), l=int(m.group(2)), msg=m.group(3), cod=cod,
                 car=car, sym=sym, loc=loc)
        )
    return out


def cargar_mapa(ruta_mapa):
    """-> (mapa "pkg::C"->nuevo, por_nombre C -> [(pkg, nuevo)], por_pkg pkg -> {C:nuevo})"""
    mapa = json.load(open(ruta_mapa, encoding="utf-8"))
    por_nombre = collections.defaultdict(list)
    por_pkg = collections.defaultdict(dict)
    for k, nuevo in mapa.items():
        pkg, C = k.split("::")
        por_nombre[C].append((pkg, nuevo))
        por_pkg[pkg][C] = nuevo
    return mapa, por_nombre, por_pkg


def import_del_fichero(txt):
    """(importes sencillos {fqn}, paquetes con wildcard {pkg})"""
    return set(PAT_IMP.findall(txt)), set(PAT_IMPW.findall(txt))


def planificar(bloques, por_nombre, por_pkg):
    """Devuelve {(ruta, linea, col): (inicio, fin, nuevo, regla)} por fichero."""
    cache_imp = {}
    cache_txt = {}
    cambios = collections.defaultdict(dict)
    descartes = collections.Counter()
    motivos = collections.Counter()

    def texto(ruta):
        if ruta not in cache_txt:
            cache_txt[ruta] = leer(ruta)
        return cache_txt[ruta]

    def intenta_r2(b, cod, c):
        """'C.N' con el calificador C renombrado -> reescribe C. True si registra."""
        ruta = b["f"]
        mq = re.search(r"([\w.]+)\.\s*$", cod[:c])
        if not mq:
            return False
        partes = mq.group(1).split(".")
        L = partes[-1]
        if L not in por_nombre:
            return False
        pref = ".".join(partes[:-1])
        ini = c - 1 - len(L)
        if ini < 0 or cod[ini:ini + len(L)] != L:
            return False
        nuevo = None
        if pref:
            for pkg_c, n_c in por_nombre[L]:
                if pkg_c == pref:
                    nuevo = n_c
                    break
        else:
            # calificador simple: precedencia JLS 6.3/6.4.1
            #   tipo anidado del fichero > import sencillo > paquete > wildcard
            if re.search(
                r"(?<![\w.])(?:class|interface|enum)\s+" + re.escape(L) + r"\b",
                texto(ruta),
            ):
                return False  # sombreado por tipo anidado: no tocar
            pkg_fich = paquete_de(ruta)
            if ruta not in cache_imp:
                cache_imp[ruta] = import_del_fichero(leer(ruta))
            imp_s, imp_w = cache_imp[ruta]
            imp_L = {f for f in imp_s if f.rsplit(".", 1)[-1] == L}
            for pkg_c, n_c in por_nombre[L]:
                if pkg_c + "." + n_c in imp_s:
                    imp_L.add(pkg_c + "." + n_c)
            if imp_L:
                for pkg_c, n_c in por_nombre[L]:
                    if pkg_c + "." + L in imp_L or pkg_c + "." + n_c in imp_L:
                        nuevo = n_c
                        break
                if nuevo is None:
                    return False  # importado de otro pkg sin renombrar: no tocar
            else:
                nuevo = por_pkg.get(pkg_fich, {}).get(L)
                if nuevo is None:
                    cands = [n_c for pkg_c, n_c in por_nombre[L] if pkg_c in imp_w]
                    if len(cands) == 1:
                        nuevo = cands[0]
        if nuevo is None:
            return False
        pos = (ruta, b["l"], ini + 1)
        cambios[ruta][pos] = (ini, ini + len(L), nuevo, "R2")
        motivos["R2 calificador C.N"] += 1
        return True

    for b in bloques:
        ruta, cod, car = b["f"], b["cod"], b["car"]
        if not cod or not car:
            descartes["sin posicion caret"] += 1
            continue
        c = car - 1
        if c >= len(cod):
            descartes["caret fuera de rango"] += 1
            continue

        # javac suele situar el caret sobre el '.' de 'pkg.C.n' / 'C.n':
        # desplazamos al identificador que hay justo despues del punto.
        if cod[c] == "." and c + 1 < len(cod) and re.match(r"[A-Za-z_$]", cod[c + 1]):
            c += 1

        # --- R3: 'package <pkg>.C does not exist' -------------------------
        if b["msg"].startswith("package ") and b["msg"].endswith("does not exist"):
            cadena = b["msg"][len("package "):-len(" does not exist")].strip()
            partes = cadena.split(".")
            if len(partes) >= 2:
                pref, L = ".".join(partes[:-1]), partes[-1]
                nuevo = por_pkg.get(pref, {}).get(L)
                if nuevo:
                    mm = re.search(
                        r"(?<![\w.])" + re.escape(pref) + r"\." + re.escape(L) + r"(?![\w])",
                        cod,
                    )
                    if mm:
                        ini = mm.end() - len(L)
                        cambios[ruta][(ruta, b["l"], ini + 1)] = (ini, mm.end(), nuevo, "R3")
                        motivos["R3 import/paquete"] += 1
                        continue
            descartes["package does not exist no renombrable"] += 1
            continue

        m = re.match(r"\w+", cod[c:])
        if not m:
            descartes["caret no es identificador"] += 1
            continue
        tok = m.group(0)

        # Seguridad: si javac dice que falta OTRO simbolo, no reescribimos nada.
        if (b["msg"].startswith("cannot find symbol") and b["sym"]
                and b["sym"] != tok):
            descartes["caret no apunta al simbolo (tok!=sym)"] += 1
            continue

        if tok not in por_nombre:
            # --- R2: el calificador termina en .C renombrado ---------------
            if intenta_r2(b, cod, c):
                continue
            mq = re.search(r"([\w.]+)\.\s*$", cod[:c])
            if not mq or mq.group(1).split(".")[-1] not in por_nombre:
                descartes["token y calificador no renombrables"] += 1
            else:
                descartes["R2 contexto no valido"] += 1
            continue

        # --- R1: caret sobre un nombre renombrado C ------------------------
        mq = re.search(r"([\w.]+)\.\s*$", cod[:c])
        cal = mq.group(1) if mq else ""
        nuevo = None
        if cal:
            nuevo = por_pkg.get(cal, {}).get(tok)
            if nuevo is None:
                # el calificador puede ser el la clase renombrada ('C.N' con
                # N homonimo a otro nombre): probar R2 antes de descartar
                if intenta_r2(b, cod, c):
                    continue
                descartes["R1 calificador no coincide con pkg"] += 1
                continue
        else:
            pkg_fich = paquete_de(ruta)
            if ruta not in cache_imp:
                cache_imp[ruta] = import_del_fichero(leer(ruta))
            imp_s, imp_w = cache_imp[ruta]
            nuevo = None
            # precedencia JLS 6.4.1: import sencillo > paquete > wildcard.
            # el import puede estar ya renombrado (pkg.nuevo): tambien vale.
            imp_directo = False
            for pkg_c, n_c in por_nombre[tok]:
                if pkg_c + "." + tok in imp_s or pkg_c + "." + n_c in imp_s:
                    imp_directo = True
                    nuevo = n_c
                    break
            if not imp_directo:
                if any(f.rsplit(".", 1)[-1] == tok for f in imp_s):
                    # importa tok de OTRO paquete y ese tok no esta renombrado:
                    # el import gana al paquete, no hay nada que reescribir
                    descartes["R1 importado no renombrado"] += 1
                    continue
                nuevo = por_pkg.get(pkg_fich, {}).get(tok)
                if nuevo is None:
                    cands = [n_c for pkg_c, n_c in por_nombre[tok] if pkg_c in imp_w]
                    if len(cands) > 1:
                        descartes["R1 wildcard ambiguo"] += 1
                        continue
                    nuevo = cands[0] if cands else None
            if nuevo is None:
                descartes["R1 sin contexto (ni pkg ni import)"] += 1
                continue
        pos = (ruta, b["l"], c + 1)
        cambios[ruta][pos] = (c, c + len(tok), nuevo, "R1")
        motivos["R1 nombre simple"] += 1

    return cambios, motivos, descartes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--mapa", default=os.path.join(MED, "mapa_renames.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.log):
        sys.exit(f"no existe el log: {args.log}")
    if not os.path.isfile(args.mapa):
        sys.exit(f"no existe el mapa: {args.mapa}")

    mapa, por_nombre, por_pkg = cargar_mapa(args.mapa)
    bloques = parsear_bloques(args.log)
    print(f"errores leidos: {len(bloques)}")

    cambios, motivos, descartes = planificar(bloques, por_nombre, por_pkg)
    n_sites = sum(len(v) for v in cambios.values())
    print(f"\nreparaciones propuestas: {n_sites} en {len(cambios)} ficheros")
    for k, v in motivos.most_common():
        print(f"    {v:5d}  {k}")
    if descartes:
        print("descartadas (no renombrables / sin contexto):")
        for k, v in descartes.most_common(8):
            print(f"    {v:5d}  {k}")

    if args.dry_run:
        print("\n[DRY-RUN] nada escrito.")
        return

    aplicados = 0
    for ruta, sitios in cambios.items():
        txt = leer(ruta)
        lineas = txt.split("\n")
        # los cambios estan por (fichero, linea, col): se aplican linea a linea
        por_linea = collections.defaultdict(list)
        for (_f, l, col), (a, bnd, nuevo, regla) in sitios.items():
            por_linea[l].append((a, bnd, nuevo))
        for l, lst in por_linea.items():
            base = 0
            for k in range(l - 1):
                base += len(lineas[k]) + 1
            # offsets globales de la linea
            lst_sorted = sorted(lst, reverse=True)
            linea = lineas[l - 1]
            for a, bnd, nuevo in lst_sorted:
                linea = linea[:a] + nuevo + linea[bnd:]
            lineas[l - 1] = linea
            aplicados += len(lst)
        escribir(ruta, "\n".join(lineas))

    print(f"\naplicados: {aplicados}")
    print("SIGUIENTE: tools/medir.sh <siguiente log>  y repetir hasta punto fijo.")


if __name__ == "__main__":
    main()

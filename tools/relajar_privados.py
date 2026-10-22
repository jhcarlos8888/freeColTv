#!/usr/bin/env python3
"""Relaja miembros `private` accedidos entre clases.

Sintoma javac: `error: X has private access in C` (X simple o calificado).
Motivacion verificada contra el DEX original (dexdump): el decompilador
emitio acceso directo a campos `private` que en el DEX se usaban via metodos
accesores sinteticos (ej. Lmc/j;: campo `a` = PRIVATE STATIC + metodo
`a()Z` = PUBLIC STATIC FINAL SYNTHETIC). Quitar `private` preserva la
semantica: mismo almacen y valor, solo se amplia el alcance de compilacion
(el acceso entre clases es legal en el bytecode DEX/Java).

Localizacion de la declaracion: indice global de declaraciones con `private`
por nombre de miembro (los nombres jadx-renombrados como f6477a son casi
unicos). Con varias coincidencias se desambigua con el calificador escrito
en la linea del caret (p.ej. `f.a.f6477a` -> fichero f.java) y, en ultimo
lugar, con la cercania de paquete; si sigue habiendo empate se omite y se
reporta.

Uso:
  python3 tools/relajar_privados.py <log> [--aplicar]

Por defecto dry-run (solo informa). Con --aplicar quita el modificador
`private` de las declaraciones (se conserva el resto byte a byte). Los
simbolos calificados (`Owner.N has private access`, tipos anidados) se
resuelven desde P4-8 consultando el indice por el N interior y usando el
mensaje/calificador para localizar el fichero de Owner; SOLO se relaja
si todos los accesos son del mismo paquete que la declaracion (quitar
`private` -> package-private no cruza paquetes); si hay varios paquetes
se omite y se reporta.
"""
import argparse
import os
import re
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")

PAT_ERR = re.compile(
    r"^(.*\.java):(\d+): error: ([\w.$]+) has private access in ([\w.$]+)$")
PAT_ERR_CTOR = re.compile(
    r"^(.*\.java):(\d+): error: ([\w.$]+)\([^)]*\) has private access in ([\w.$]+)$")

# declaracion de miembro con 'private' (campo o metodo)
PAT_MIEMBRO = re.compile(
    r"^(\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|protected\s+)?)"
    r"(private\s+)"
    r"((?:(?:static|final|transient|volatile|synchronized|native|abstract|strictfp|default)\s+)*)"
    r"([\w.$<>\[\], ?]+\s+)"
    r"([\w$]+)\s*([;=(])")
# declaracion de tipo anidado con 'private'
PAT_TIPO = re.compile(
    r"^(\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|protected\s+)?)"
    r"(private\s+)"
    r"((?:(?:static|final|abstract|strictfp|sealed)\s+)*)"
    r"((?:class|interface|enum|record)\s+)"
    r"([\w$]+)\b")
# constructor con 'private'
PAT_CTOR = re.compile(
    r"^(\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|protected\s+)?)"
    r"(private\s+)"
    r"([\w$]+)\s*\(")


def java_files():
    for raiz, _dirs, fichs in os.walk(SRC):
        for f in fichs:
            if f.endswith(".java"):
                yield os.path.join(raiz, f)


def construir_indice():
    """nombre_de_miembro -> lista de (fichero, linea, kind, match)."""
    idx = defaultdict(list)
    for fich in java_files():
        for i, ln in enumerate(
                open(fich, encoding="utf-8", errors="replace")):
            if "private" not in ln:
                continue
            ln = ln.rstrip("\n")   # el apply reconstruye lineas sin \n
            m = PAT_MIEMBRO.match(ln)
            if m:
                idx[m.group(5)].append((fich, i, "miembro", ln))
                continue
            m = PAT_TIPO.match(ln)
            if m:
                idx[m.group(5)].append((fich, i, "tipo", ln))
                continue
            m = PAT_CTOR.match(ln)
            if m:
                idx[m.group(3)].append((fich, i, "ctor", ln))
    return idx


def reljava(ruta_abs):
    marca = os.sep + "java" + os.sep
    i = ruta_abs.find(marca)
    return ruta_abs[i + len(marca):] if i >= 0 else ""


def desambiguar(cands, qual, pkg_err, cls):
    """Entre candidatos (fich, ...): prefiere cuyo nombre base == qual,
    despues el fichero de la clase declarante (`in bd` -> bd.java; para
    clases anidadas el fichero es el tipo exterior), despues el mismo
    paquete que el error. Devuelve lista filtrada."""
    if qual:
        base = [c for c in cands
                if os.path.basename(c[0])[:-5] == qual]
        if base:
            cands = base
    cls_top = cls.split(".")[0]
    fich_cls = [c for c in cands
                if os.path.basename(c[0])[:-5] == cls_top]
    if fich_cls:
        cands = fich_cls
    if pkg_err:
        mismo = [c for c in cands
                 if os.path.dirname(reljava(c[0])).replace(os.sep, ".")
                 == pkg_err]
        if mismo:
            cands = mismo
    return cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    # 1) objetivos: miembro -> (fich_err, pkg_err, qual, nerr)
    objetivos = {}
    sin_cuantificar = Counter()
    for ln in open(args.log, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\n")
        m = PAT_ERR.match(ln)
        es_ctor = False
        if m:
            fich_err, sym, cls = m.group(1), m.group(3), m.group(4)
        else:
            m = PAT_ERR_CTOR.match(ln)
            if not m:
                continue
            es_ctor = True
            fich_err, sym, cls = m.group(1), m.group(3), m.group(4)
        if "." in sym:
            # P4-8: tipo anidado calificado (Owner.N): se consulta el
            # indice por el N interior; el propio mensaje (`in Owner`) y
            # el calificador del caret apuntan al tipo exterior
            # (p.ej. e____.b -> e____.java). Solo se relaja si todos los
            # accesos son del mismo paquete que la decl (suficiente).
            sim_idx = sym.rsplit(".", 1)[1]
        else:
            sim_idx = sym
        pkg_err = os.path.dirname(reljava(fich_err)).replace(os.sep, ".")
        clave = (sym, cls, es_ctor)
        objetivos.setdefault(clave, {"nerr": 0, "fich_err": fich_err,
                                     "pkg_err": pkg_err,
                                     "sim_idx": sim_idx,
                                     "pkgs": set()})
        objetivos[clave]["pkgs"].add(pkg_err)
        objetivos[clave]["nerr"] += 1

    # 2) calificador escrito en la linea del caret de cada error
    lineas_log = open(args.log, encoding="utf-8", errors="replace",
                      ).read().split("\n")
    qual_por_err = {}
    for i, ln in enumerate(lineas_log):
        m = PAT_ERR.match(ln) or PAT_ERR_CTOR.match(ln)
        if not m:
            continue
        cod = lineas_log[i + 1] if i + 1 < len(lineas_log) else ""
        mq = re.search(r"(?<![\w$])([A-Za-z_$][\w$]*)\s*\.\s*[\w$]+", cod)
        qual_por_err[(m.group(1), m.group(3))] = mq.group(1) if mq else None

    # 3) indice de declaraciones
    idx = construir_indice()

    # 4) resolver cada objetivo
    cambios = []      # (fich, linea, sym, kind, nerr, ln)
    omitidos = Counter()
    detalles_omit = []
    for (sym, cls, es_ctor), info in objetivos.items():
        cands = idx.get(info["sim_idx"], [])
        if es_ctor:
            cands = [c for c in cands if c[2] == "ctor"]
        if not cands:
            omitidos["sin_declaracion_private"] += 1
            detalles_omit.append(("sin decl", sym, cls, info["fich_err"]))
            continue
        qual = qual_por_err.get((info["fich_err"], sym))
        cands = desambiguar(cands, qual, info["pkg_err"], cls)
        # mismo nombre puede ser campo y metodo: si tras filtrar queda mas
        # de un fichero distinto -> empate; un mismo fichero con varias
        # lineas (sobrecargas) se relaja entero.
        fichs = {c[0] for c in cands}
        if len(fichs) > 1:
            omitidos["empate_ficheros"] += 1
            detalles_omit.append(("empate", sym, cls,
                                  ",".join(sorted(os.path.basename(f)
                                                  for f in fichs)[:4])))
            continue
        if info["sim_idx"] != sym:
            # tipo anidado calificado: quitar 'private' solo vale si
            # TODOS los accesos son del mismo paquete que la declaracion
            pkg_decl = os.path.dirname(reljava(cands[0][0])
                                       ).replace(os.sep, ".")
            if info["pkgs"] != {pkg_decl}:
                omitidos["calificado_multi_paquete"] += 1
                detalles_omit.append(("multi-pkg", sym, pkg_decl,
                                      ",".join(sorted(info["pkgs"])[:3])))
                continue
        for fich, i, kind, ln in cands:
            cambios.append((fich, i, sym, kind, info["nerr"], ln))

    # 5) aplicar
    por_fich = defaultdict(list)
    for fich, i, sym, kind, nerr, ln in cambios:
        por_fich[fich].append((i, ln))
    if args.aplicar:
        for fich, items in por_fich.items():
            lineas = open(fich, encoding="utf-8", errors="replace",
                          ).read().split("\n")
            for i, ln in items:
                m = (PAT_MIEMBRO.match(ln) or PAT_TIPO.match(ln)
                     or PAT_CTOR.match(ln))
                lineas[i] = ln[:m.start(2)] + ln[m.end(2):]
            open(fich, "w", encoding="utf-8").write("\n".join(lineas))

    erros_relajados = sum(c[4] for c in cambios)
    print(f"objetivos (miembros con errores): {len(objetivos)}")
    print(f"declaraciones a relajar         : {len(cambios)}")
    print(f"errores cubiertos por ellas     : {erros_relajados}")
    print(f"ficheros tocados                : {len(por_fich)}")
    if sin_cuantificar:
        print("fuera de ambito:")
        for k, v in sin_cuantificar.most_common(8):
            print(f"    {v:4d}  {k}")
    if omitidos:
        print("omitidos:")
        for k, v in omitidos.most_common(8):
            print(f"    {v:4d}  {k}")
        for d in detalles_omit[:10]:
            print(f"      {d}")
    print("\nmuestra de cambios:")
    for fich, i, sym, kind, nerr, ln in cambios[:8]:
        m = (PAT_MIEMBRO.match(ln) or PAT_TIPO.match(ln) or PAT_CTOR.match(ln))
        print(f"  {os.path.relpath(fich, SRC)}:{i+1} [{kind}] "
              f"(errores: {nerr})")
        print(f"    - {ln.strip()[:95]}")
        print(f"    + {(ln[:m.start(2)] + ln[m.end(2):]).strip()[:95]}")
    if args.aplicar:
        print(f"\n[APlicado] {len(cambios)} declaraciones en "
              f"{len(por_fich)} ficheros.")
    else:
        print("\n[DRY-RUN] nada modificado. Repite con --aplicar.")


if __name__ == "__main__":
    main()

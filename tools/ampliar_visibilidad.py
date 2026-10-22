#!/usr/bin/env python3
"""Amplia visibilidad o simplifica accesos protegidos.

Dos sintomas javac mecanicos, ambos ampliacion de alcance (semantica
preservada; verificado contra el patron del decompilador):

1. `X is not public in Y; cannot be accessed from outside package`
   -> se anyade `public` a la declaracion de la clase o miembro X en Y.
   (Muchos son el segundo paso de la relajacion private->package de
   P4-3: el miembro se accede ahora desde OTRO paquete.)

2. `X has protected access in Y`
   -> si el acceso esta escrito `((Y) this).X` (cast al super tipo JDK/
   app que el decompilador emitio), se quita el cast: `this.X` es legal
   porque el miembro heredado se accede via el tipo propio de la clase.
   En caso contrario se promueve la declaracion a `public`.

Uso:
  python3 tools/ampliar_visibilidad.py <log> [--aplicar]
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relajar_privados as rp  # noqa: E402  (reutiliza indice/parseos)

SRC = rp.SRC

PAT_NPUB = re.compile(
    r"^(.*\.java):(\d+): error: ([\w.$]+) is not public in ([\w.$]+);"
    r" cannot be accessed from outside package$")
PAT_PROT = re.compile(
    r"^(.*\.java):(\d+): error: ([\w.$]+) has protected access in "
    r"([\w.$]+)$")
# constructor: 'b() is not public in b'
PAT_NPUB_CTOR = re.compile(
    r"^(.*\.java):(\d+): error: ([\w$]+)\(\) is not public in "
    r"([\w.$]+); cannot be accessed from outside package$")
# decl de constructor: nombre igual al de la clase, sin tipo
PAT_CTOR_LN = re.compile(
    r"^(\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|protected\s+|"
    r"private\s+)?)"
    r"([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?:throws [\w.,\s]+)?\{")

# mods de tipo que preceden a class/interface/enum
PAT_DECL_TIPO = re.compile(
    r"^(\s*)(?:(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|protected\s+|"
    r"private\s+|static\s+|final\s+|abstract\s+|strictfp\s+|sealed\s+)*)"
    r"((?:class|interface|enum|record)\s+)([\w$]+)\b")

# indice local de TODOS los miembros (no solo private: los relajados en
# P4-3 ya no son private y el indice de relajar_privados no los ve)
PAT_MIEMBRO_TODO = re.compile(
    r"^(\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:public\s+|protected\s+|"
    r"private\s+)?)"
    r"((?:(?:static|final|transient|volatile|synchronized|native|abstract|"
    r"strictfp|default)\s+)*)"
    r"([\w.$<>\[\], ?]+\s+)"
    r"([\w$]+)\s*([;=(])")

# palabras que jamas son tipo de una declaracion de miembro (evita
# indexar sentencias como 'return obj;')
PALABRAS_SENTENCIA = {
    "return", "throw", "new", "if", "while", "for", "switch", "case",
    "else", "do", "break", "continue", "try", "catch", "finally",
    "synchronized", "assert", "package", "import", "this", "super",
    "instanceof", "default", "yield",
}


def construir_indice_todo():
    """nombre -> [(fich, linea, linea_txt, cadena_clases)] de
    declaraciones reales. La cadena de clases encadenadas se sigue por
    indentacion (salida del decompilador siempre indentada)."""
    idx = defaultdict(list)
    for fich in rp.java_files():
        pila = []   # [(indent, nombre)]
        for i, ln in enumerate(
                open(fich, encoding="utf-8", errors="replace")):
            mt = PAT_DECL_TIPO.match(ln)
            if mt:
                ind = len(ln) - len(ln.lstrip())
                while pila and pila[-1][0] >= ind:
                    pila.pop()
                pila.append((ind, mt.group(3)))
                continue
            m = PAT_MIEMBRO_TODO.match(ln)
            if not m:
                continue
            if m.group(3).strip() in PALABRAS_SENTENCIA:
                continue
            cadena = ".".join(n for _i, n in pila) or "?"
            idx[m.group(4)].append((fich, i, ln.rstrip("\n"), cadena))
    return idx


def resolver_miembro(idx, simbolo, quals, cls, fich_err):
    """Localiza la declaracion del miembro: por la cadena de calificadores
    del propio codigo de acceso, luego por import del fichero con error,
    luego por su paquete, luego globalmente si es inequívoco."""
    cands = idx.get(simbolo, [])
    if not cands:
        return [], False
    todos = cands
    cls_top = quals[-1] if quals else cls.split(".")[-1]
    cands = [c for c in todos if c[3].split(".")[-1] == cls_top]
    if not cands and quals:
        # el calificador puede ser una VARIABLE ('pVar.f14181a'), no una
        # clase: se reintenta con el nombre de clase del propio mensaje
        cls_top = cls.split(".")[-1]
        cands = [c for c in todos if c[3].split(".")[-1] == cls_top]
    if not cands:
        return [], False
    # 0) la cadena completa del codigo coincide con la cadena del contexto
    if len(quals) > 1:
        sel = [c for c in cands if c[3].endswith(".".join(quals))]
        if sel:
            return sel, False
    pkg_err = os.path.dirname(rp.reljava(fich_err)).replace(os.sep, ".")
    # 1) import en el fichero con error del calificador raiz
    if os.path.isfile(fich_err):
        txt = open(fich_err, encoding="utf-8", errors="replace").read()
        raiz = quals[0] if quals else cls_top
        for mm in re.finditer(
                r"^import ([\w.]*\.)?" + re.escape(raiz) + r"\s*;",
                txt, re.M):
            fqn = (mm.group(1) or "") + raiz
            destino = os.path.join(SRC, fqn.replace(".", "/") + ".java")
            sel = [c for c in cands if c[0] == destino]
            if sel:
                return sel, False
    # 2) mismo paquete que el fichero con error
    sel = [c for c in cands
           if os.path.dirname(rp.reljava(c[0])).replace(os.sep, ".")
           == pkg_err]
    if sel:
        return sel, False
    # 3) inequivoco en todo el arbol
    fichs = {c[0] for c in cands}
    return cands, len(fichs) > 1


def cualificadores(cod, simbolo):
    """'f.a.f6477a' -> ['f', 'a'] (calificadores previos al simbolo)."""
    m = re.search(r"([\w.$]+)\s*\.\s*" + re.escape(simbolo) + r"\b", cod)
    return m.group(1).split(".") if m else []


def lineas_log(path):
    return open(path, encoding="utf-8", errors="replace").read().split("\n")


def promover_publico(linea):
    """Quita private/protected y deja public en la declaracion."""
    m = re.match(
        r"^(\s*(?:@\w+(?:\([^)]*\))?\s+)*)(?:public\s+)?"
        r"(?:protected\s+|private\s+)?((?:(?:static|final|transient|"
        r"volatile|synchronized|native|abstract|strictfp|default)\s+)*)"
        r"(.+)$", linea)
    if not m:
        return None
    return f"{m.group(1)}public {m.group(2)}{m.group(3)}"


def anyadir_publico_tipo(linea):
    """Anyade 'public' a una declaracion de tipo que no lo lleva."""
    m = PAT_DECL_TIPO.match(linea)
    if not m or linea[m.start(2):].lstrip().startswith("public"):
        return None
    return f"{m.group(1)}public {m.group(2)}{m.group(3)}" + \
        linea[m.end(3):]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    lineas = lineas_log(args.log)
    idx = construir_indice_todo()

    cambios = defaultdict(list)   # fich -> [(linea_idx, nueva_linea, nota)]
    stats = Counter()
    omitidos = []

    for i, ln in enumerate(lineas):
        ln = ln.rstrip("\n")
        m = PAT_NPUB.match(ln)
        es_npub = bool(m)
        es_ctor = False
        if not m:
            m = PAT_NPUB_CTOR.match(ln)
            es_ctor = bool(m)
            es_npub = es_ctor
        if not m:
            m = PAT_PROT.match(ln)
        if not m:
            continue
        fich, l_err = m.group(1), int(m.group(2))
        simbolo, cls = m.group(3), m.group(4)
        l0 = l_err - 1
        fich_src = open(fich, encoding="utf-8", errors="replace").read(
        ).split("\n")
        cod = fich_src[l0] if l0 < len(fich_src) else ""

        if es_ctor:
            # el ctor pertenece a una clase cuyo nombre simple puede ser
            # SOMBRREADO: segun JLS 6.4.1 los miembros heredados de los
            # supertipos ganan al import simple (AppWrapper extends y9.d
            # hereda la anidada y9.d.b, que sombrea a r7.b importada).
            # Se buscan candidatos: supertipos, luego imports, luego el
            # mismo paquete; en cada uno, el ctor sin argumentos.
            cls_top = cls.split(".")[-1]
            cands_fich = []
            if os.path.isfile(fich):
                txt = open(fich, encoding="utf-8", errors="replace").read()
                # mapa de imports: nombre simple -> FQN (para resolver
                # supertipos simples como 'extends d' -> y9.d)
                mapa_imp = {}
                for mm in re.finditer(r"^import ([\w.]+)\s*;", txt, re.M):
                    fqn = mm.group(1)
                    mapa_imp[fqn.split(".")[-1]] = fqn
                # 0) supertipos citados en extends/implements
                for mext in re.finditer(
                        r"(?:extends|implements)\s+([\w.$,<>\[\]\s]+?)"
                        r"\s*(?:\{|implements|,|$)", txt):
                    for tok in re.split(r"[,\s]+", mext.group(1)):
                        tok = re.sub(r"<.*", "", tok).strip()
                        if not tok:
                            continue
                        if "." not in tok and tok in mapa_imp:
                            tok = mapa_imp[tok]
                        cand = os.path.join(SRC, tok.replace(".", "/")
                                            + ".java")
                        if os.path.isfile(cand) and cand not in cands_fich:
                            cands_fich.append(cand)
                # 1) import del nombre simple
                for mm in re.finditer(
                        r"^import ([\w.]*\.)?" + re.escape(cls_top)
                        + r"\s*;", txt, re.M):
                    fqn = (mm.group(1) or "") + cls_top
                    destino = os.path.join(SRC, fqn.replace(".", "/")
                                           + ".java")
                    if os.path.isfile(destino) and destino not in cands_fich:
                        cands_fich.append(destino)
            mismo = os.path.join(os.path.dirname(fich), cls_top + ".java")
            if os.path.isfile(mismo) and mismo not in cands_fich:
                cands_fich.append(mismo)
            found = False
            for buscado in cands_fich:
                bl = open(buscado, encoding="utf-8", errors="replace"
                          ).read().split("\n")
                for li, l in enumerate(bl):
                    mm = PAT_CTOR_LN.match(l)
                    if (mm and mm.group(2) == simbolo
                            and not mm.group(3).strip()):
                        nueva = promover_publico(l)
                        if nueva:
                            cambios[buscado].append((li, nueva,
                                                     f"ctor {simbolo}"))
                            stats["ctor_publico"] += 1
                            found = True
                        break
                if found:
                    break
            if not found:
                stats["ctor_no_encontrado"] += 1
                omitidos.append(("ctor", fich, l_err))
            continue

        if es_npub and "." in simbolo:
            # tipo anidado cualificado: d_.c -> la clase anidada 'inner'
            # vive en el fichero de la clase 'outer', que puede venir
            # calificado en extends/implements del propio fichero, en un
            # import, o ser el propio fichero (busqueda previa)
            outer, inner = simbolo.rsplit(".", 1)
            buscado = None
            if os.path.isfile(fich):
                txt = open(fich, encoding="utf-8", errors="replace").read()
                # 0) FQN en clausulas extends/implements del fichero
                for mext in re.finditer(
                        r"(?:extends|implements)\s+([\w.$,<>\[\]\s]+?)"
                        r"\s*(?:\{|implements|,|$)", txt):
                    for tok in re.split(r"[,\s]+", mext.group(1)):
                        tok = re.sub(r"<.*", "", tok).strip()
                        if tok and tok.split(".")[-1] == outer:
                            cand = os.path.join(
                                SRC, tok.replace(".", "/") + ".java")
                            if os.path.isfile(cand):
                                buscado = cand
                                break
                    if buscado:
                        break
                # 1) import del outer
                if not buscado:
                    for mm in re.finditer(
                            r"^import ([\w.]*\.)?" + re.escape(outer)
                            + r"\s*;", txt, re.M):
                        fqn = (mm.group(1) or "") + outer
                        cand = os.path.join(SRC, fqn.replace(".", "/")
                                            + ".java")
                        if os.path.isfile(cand):
                            buscado = cand
                            break
            if not buscado and "." in outer:
                cand = os.path.join(SRC, outer.replace(".", "/") + ".java")
                if os.path.isfile(cand):
                    buscado = cand
            if not buscado:
                buscado = fich   # fallback: el propio fichero
            found = False
            bl = open(buscado, encoding="utf-8", errors="replace").read(
            ).split("\n")
            for li, l in enumerate(bl):
                mm = PAT_DECL_TIPO.match(l)
                if mm and mm.group(3) == inner and "public" not in \
                        mm.group(2):
                    nueva = anyadir_publico_tipo(l)
                    if nueva:
                        cambios[buscado].append((li, nueva,
                                                 f"tipo anidado {simbolo}"))
                        stats["npub_tipo_anidado"] += 1
                        found = True
                        break
            if not found:
                stats["npub_anidado_no_encontrado"] += 1
                omitidos.append(("npub anidado", fich, l_err))
            continue

        if es_npub:
            # 'X is not public in Y': Y puede ser una CLASE importada por
            # el fichero con error (X anidada dentro), un PAQUETE
            # (directorio con X.java), o una CLASE del mismo paquete, o
            # bien X es un miembro de la clase Y.
            es_clase = False
            buscado, origen = None, None
            cls_top = cls.split(".")[-1]
            # 0) import del fichero con error: si importa un tipo Y, la
            #    referencia 'X' es anidada de ese tipo (regla JLS)
            if os.path.isfile(fich):
                txt = open(fich, encoding="utf-8", errors="replace").read()
                for mm in re.finditer(
                        r"^import ([\w.]*\.)?" + re.escape(cls_top)
                        + r"\s*;", txt, re.M):
                    fqn = (mm.group(1) or "") + cls_top
                    destino = os.path.join(SRC, fqn.replace(".", "/")
                                           + ".java")
                    if os.path.isfile(destino):
                        buscado, origen = destino, "tipo anidado (import)"
                        break
            if not buscado:
                dir_pkg = os.path.join(SRC, cls.replace(".", "/"))
                f_paquete = os.path.join(dir_pkg, simbolo + ".java")
                f_clase = os.path.join(SRC, cls.replace(".", "/")
                                       + ".java")
                if os.path.isdir(dir_pkg) and os.path.isfile(f_paquete):
                    buscado, origen = f_paquete, "clase en paquete"
                elif os.path.isfile(f_clase):
                    buscado, origen = f_clase, "tipo anidado"
            if buscado:
                bl = open(buscado, encoding="utf-8", errors="replace"
                          ).read().split("\n")
                for lj, l in enumerate(bl):
                    mm = PAT_DECL_TIPO.match(l)
                    if mm and mm.group(3) == simbolo:
                        nueva = anyadir_publico_tipo(l)
                        if nueva:
                            cambios[buscado].append((lj, nueva, origen))
                            stats["npub_clase"] += 1
                        es_clase = True
                        break
            if es_clase:
                continue
            # miembro: indice global completo
            quals = cualificadores(cod, simbolo)
            cands, empate = resolver_miembro(idx, simbolo, quals, cls, fich)
            if not cands or empate:
                stats["npub_miembro_" + ("empate" if empate
                                         else "no_encontrado")] += 1
                omitidos.append(("npub miembro", fich, l_err))
                continue
            for df, li, l, _cand in cands:
                nueva = promover_publico(l)
                if nueva:
                    cambios[df].append((li, nueva, f"miembro {simbolo}"))
                    stats["npub_miembro"] += 1
            continue

        # ---- protected ----
        pat_cast = re.compile(
            r"\(\(\s*[\w.$]+\s*\)\s*this\s*\)(\s*\.\s*" +
            re.escape(simbolo) + r"\b)")
        if pat_cast.search(cod):
            nueva = pat_cast.sub(r"this\1", cod, count=1)
            cambios[fich].append((l0, nueva, f"cast this->{simbolo}"))
            stats["prot_cast"] += 1
            continue
        quals = cualificadores(cod, simbolo)
        cands, empate = resolver_miembro(idx, simbolo, quals, cls, fich)
        if not cands or empate:
            stats["prot_miembro_" + ("empate" if empate
                                     else "no_encontrado")] += 1
            omitidos.append(("prot miembro", fich, l_err))
            continue
        for df, li, l, _cand in cands:
            nueva = promover_publico(l)
            if nueva:
                cambios[df].append((li, nueva, f"miembro {simbolo}"))
                stats["prot_miembro"] += 1

    print("resumen:")
    for k, v in stats.most_common():
        print(f"  {v:5d}  {k}")
    total = sum(len(set((f, l) for l, _n, _x in v)) for f, v in cambios.items())
    print(f"cambios en {len(cambios)} ficheros (~{total} lineas)")
    if omitidos[:8]:
        print("omitidos (muestra):")
        for o in omitidos[:8]:
            print(f"    {o[0]}: {os.path.relpath(o[1], SRC)}:{o[2]}")

    if args.aplicar:
        for fich, items in cambios.items():
            fl = open(fich, encoding="utf-8", errors="replace").read(
            ).split("\n")
            vistos = set()
            for li, nueva, _nota in items:
                if li in vistos:
                    continue
                vistos.add(li)
                fl[li] = nueva
            open(fich, "w", encoding="utf-8").write("\n".join(fl))
        print("[APlicado]")
    else:
        print("\n[DRY-RUN] nada modificado. Repite con --aplicar.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Elimina la colision "clase del paquete vs paquete raiz" renombrando los paquetes
raiz implicados:  X  ->  obf_X

Por que esta estrategia y no renombrar las clases tapadoras:
  * solo cambia la resolucion de PAQUETES; la resolucion de tipos (clases) queda
    identica, asi que no puede haber "roturas silenciosas" de significado.
  * el compilador decide por nosotros que referencias son de paquete: tras el
    renombrado, toda referencia real a ese paquete deja de compilar y aparece en
    el log con su posicion exacta (para el pase de reparacion por errores).

Seguridad:
  * tokenizador propio: NO escribe dentro de literales de cadena/carácter ni
    comentarios (ahi viven nombres de clase usados por reflexion).
  * dry-run por defecto; --aplicar hace los cambios.
  * verifica que la declaracion package de cada archivo movido queda coherente.

Uso:
  python3 renombrar_paquetes_raiz.py --paquetes l,p1,w --aplicar
  python3 renombrar_paquetes_raiz.py --desde-log /tmp/gradle_baseline.log --aplicar
"""
import argparse
import os
import re
import shutil
import sys
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RAIZ, "XuperDorado_project", "app", "src", "main", "java")
PREFIX = "obf_"

# ---------------------------------------------------------------- tokenizador
def tramos_codigo(src: str):
    """Devuelve SOLO los tramos de texto que son codigo fuente, excluyendo
    literales de cadena/carácter y comentarios (ahi no se debe escribir)."""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n:
            if src[i + 1] == "/":                     # comentario de linea
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if src[i + 1] == "*":                     # comentario de bloque
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
        if c in "\"'":                                # literal cadena/caracter
            fin = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == fin:
                    j += 1
                    break
                if src[j] == "\n":                    # mal cerrado: no invadimos
                    break
                j += 1
            i = j
            continue
        # comienza un tramo de codigo
        j = i
        while j < n:
            cj = src[j]
            if cj in "\"'":
                break
            if cj == "/" and j + 1 < n and src[j + 1] in "/*":
                break
            j += 1
        out.append((i, j))
        i = j
    return out


def map_code(src: str):
    """Devuelve un bytearray donde 1 = posicion dentro de codigo (fuera de
    literales y comentarios)."""
    marca = bytearray(len(src))
    for a, b in tramos_codigo(src):
        marca[a:b] = b"\x01" * (b - a)
    return marca


# ---------------------------------------------------------------- utilidades
def paquetes_en_src():
    return {d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d))}


def paquetes_desde_log(log_path, raiz_paqs):
    """Paquetes raiz que aparecen como 'location' en errores de 'cannot find symbol'
    donde ademas existe <raiz>/<simbolo>.java  -> esa es la referencia a paquete."""
    pat_arch = re.compile(r"^(.*\.java):(\d+): error: (.*)$")
    pat_sym = re.compile(r"symbol:\s+(?:class|variable|method)\s+([\w]+)")
    pat_loc = re.compile(r"location:\s+(?:class|interface|enum)\s+([\w.$]+)")
    objetivos = Counter()
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        lineas = fh.read().split("\n")
    i = 0
    while i < len(lineas):
        m = pat_arch.match(lineas[i])
        if m and m.group(3).startswith("cannot find symbol") and i + 4 < len(lineas):
            ms = pat_sym.search(lineas[i + 3])
            ml = pat_loc.search(lineas[i + 4])
            if ms and ml:
                loc = ml.group(1).split(".")[-1]
                sym = ms.group(1)
                if loc in raiz_paqs and os.path.isfile(os.path.join(SRC, loc, sym + ".java")):
                    objetivos[loc] += 1
        i += 1
    return objetivos


def archivos_java(base):
    for dp, _, fs in os.walk(base):
        for f in fs:
            if f.endswith(".java"):
                yield os.path.join(dp, f)


def tipos_de_paquete(nombre):
    """archivos de primer nivel (clases top-level) de un paquete raiz."""
    d = os.path.join(SRC, nombre)
    if not os.path.isdir(d):
        return set()
    return {f[:-5] for f in os.listdir(d) if f.endswith(".java")}


def clase_en_alcance(src, paquete_puntos, nombre_clase):
    """Intenta localizar el archivo .java de la clase 'nombre_clase' en alcance del
    archivo (mismo paquete o via import de tipo simple)."""
    if paquete_puntos:
        p = os.path.join(SRC, paquete_puntos.replace(".", "/"), nombre_clase + ".java")
        if os.path.isfile(p):
            return p
    else:
        p = os.path.join(SRC, nombre_clase + ".java")
        if os.path.isfile(p):
            return p
    m = re.search(r"^import\s+([\w.]+)\." + re.escape(nombre_clase) + r"\s*;", src, re.M)
    if m:
        p = os.path.join(SRC, m.group(1).replace(".", "/"), nombre_clase + ".java")
        if os.path.isfile(p):
            return p
    # clase declarada en este mismo archivo (clase anidada o la propia)
    if re.search(r"\b(?:class|interface|enum)\s+" + re.escape(nombre_clase) + r"\b", src):
        return "<anidada>"
    return None


REC_ANIDADOS = re.compile(
    r"^[ \t]+(?:public |private |protected |static |final |abstract |strictfp |strict |volatile |transient |native )*"
    r"(?:class|interface|enum)[ \t]+([\w]+)", re.M)


def declara_anidado(path, nombre):
    if path == "<anidada>":
        return True  # no podemos resolverlo: asumimos miembro para no romper nada
    try:
        txt = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return nombre in REC_ANIDADOS.findall(txt)


# ---------------------------------------------------------------- transformacion
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paquetes", help="lista separada por comas")
    ap.add_argument("--desde-log", help="deriva la lista de un log de errores")
    ap.add_argument("--aplicar", action="store_true", help="si no se pasa, es dry-run")
    args = ap.parse_args()

    raiz_paqs = paquetes_en_src()
    if args.paquetes:
        objetivos = Counter({p: 0 for p in args.paquetes.split(",") if p})
    elif args.desde_log:
        objetivos = paquetes_desde_log(args.desde_log, raiz_paqs)
    else:
        sys.exit("indica --paquetes o --desde-log")

    objetivos = [p for p in objetivos if p in raiz_paqs]
    print(f"paquetes raiz a renombrar ({len(objetivos)}): {', '.join(sorted(objetivos))}\n")

    # 1) calcular el impacto (referencias candidatas) ANTES de tocar nada
    def existe_tipo(X, Y, movido):
        """¿Existe el tipo Y dentro del paquete X? En dry-run los directorios
        siguen con su nombre original; tras --aplicar ya estan con prefijo."""
        base = os.path.join(SRC, (PREFIX if movido else "") + X)
        if Y == "*":
            return os.path.isdir(base)
        p = os.path.join(base, Y)
        return os.path.isfile(p + ".java") or os.path.isdir(p)

    impacto = Counter()
    refs_a_rewrite = Counter()
    archivos_afectados = set()
    pat_ref = re.compile(r"(?<![\w$.])(" + "|".join(map(re.escape, sorted(objetivos))) + r")\s*\.\s*(\w+|\*)")

    for ruta in archivos_java(SRC):
        txt = open(ruta, encoding="utf-8", errors="replace").read()
        marca = map_code(txt)
        rel = os.path.relpath(ruta, SRC)
        pkg = os.path.dirname(rel).replace("/", ".")
        for m in pat_ref.finditer(txt):
            if not marca[m.start(1)]:
                continue
            X, Y = m.group(1), m.group(2)
            # ¿esta referencia es de paquete?  => el paquete contiene a Y
            if not existe_tipo(X, Y, movido=False):
                continue
            # si en alcance hay una CLASE X que declara anidado Y, es referencia
            # de tipo (clase) -> NO tocar
            archivo_clase = clase_en_alcance(txt, pkg, X)
            if archivo_clase and declara_anidado(archivo_clase, Y):
                continue
            refs_a_rewrite[X] += 1
            archivos_afectados.add(ruta)

    print(f"referencias de paquete a reescribir: {sum(refs_a_rewrite.values())} "
          f"en {len(archivos_afectados)} archivos")
    for k, v in refs_a_rewrite.most_common(20):
        print(f"    {k:8s} -> {PREFIX + k:10s} {v:6d} referencias")

    if not args.aplicar:
        print("\n[DRY-RUN] no se ha modificado nada. Repite con --aplicar.")
        return

    # 2) mover directorios
    movidos = 0
    for X in objetivos:
        origen = os.path.join(SRC, X)
        destino = os.path.join(SRC, PREFIX + X)
        if os.path.exists(destino):
            sys.exit(f"destino ya existe: {destino}")
        shutil.move(origen, destino)
        movidos += 1
    print(f"\ndirectorios movidos: {movidos}")

    # 3) reescribir declaraciones package dentro de los movidos
    pkg_decl = 0
    for ruta in archivos_java(SRC):
        rel = os.path.relpath(ruta, SRC)
        partes = rel.split(os.sep)
        # reconstruct: el prefijo va en la raiz del paquete movido
        for X in objetivos:
            if partes[0] == PREFIX + X:
                txt = open(ruta, encoding="utf-8", errors="replace").read()
                viejo = "package " + X + ";"
                nuevo = "package " + PREFIX + X + ";"
                if viejo in txt:
                    txt = txt.replace(viejo, nuevo, 1)
                    pkg_decl += 1
                viejo2 = re.compile(r"^package\s+" + re.escape(X) + r"\.", re.M)
                txt, n = viejo2.subn("package " + PREFIX + X + ".", txt)
                pkg_decl += n
                open(ruta, "w", encoding="utf-8").write(txt)
                break
    print(f"declaraciones package actualizadas: {pkg_decl}")

    # 4) reescribir referencias (mismo criterio que en el dry-run)
    reescritas = Counter()
    for ruta in list(archivos_java(SRC)):
        txt = open(ruta, encoding="utf-8", errors="replace").read()
        marca = map_code(txt)
        rel = os.path.relpath(ruta, SRC)
        pkg = os.path.dirname(rel).replace("/", ".")
        cambios = []
        for m in pat_ref.finditer(txt):
            if not marca[m.start(1)]:
                continue
            X, Y = m.group(1), m.group(2)
            if not existe_tipo(X, Y, movido=True):
                continue
            archivo_clase = clase_en_alcance(txt, pkg, X)
            if archivo_clase and declara_anidado(archivo_clase, Y):
                continue
            cambios.append((m.start(1), m.end(1), PREFIX + X))
            reescritas[X] += 1
        if cambios:
            for a, b, nuevo in sorted(cambios, reverse=True):
                txt = txt[:a] + nuevo + txt[b:]
            open(ruta, "w", encoding="utf-8").write(txt)

    print(f"referencias reescritas: {sum(reescritas.values())} en "
          f"{len(set(archivos_afectados))} archivos")
    print("\nOK. Siguiente paso: compilar y reparar los restos con "
          "tools/repara_por_errores.py <log>")


if __name__ == "__main__":
    main()

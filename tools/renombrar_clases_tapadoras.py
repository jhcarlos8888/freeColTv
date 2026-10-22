#!/usr/bin/env python3
"""Estrategia B: elimina la colision 'clase vs paquete raiz' renombrando la CLASE
TAPADORA (la que sombrea) en su paquete:   pkg.C  ->  pkg.C_

Por que renombrar la clase y no el paquete (medido, ver mediciones/):
  * los 2.193 errores de sombra desaparecen SOLOS: al quitar la clase tapadora,
    la referencia C.N vuelve a enlazar con el paquete raiz C.
  * javac reporta unicamente los usos de TIPO que rompen (casi 0 falsos
    positivos), mientras que renombrar paquetes rompia 10.662 referencias con
    riesgo de chocar con variables ofuscadas de una letra.
  * riesgos residuales acotados y comprobados: 2 strings de reflexion (umeng),
    0 en AndroidManifest, 0 en res/*.xml.

Riesgo de rotura SILENCIOSA y su neutralizacion:
  si la clase C declara anidado N y el paquete raiz C TAMBIEN tiene tipo N,
  entonces 'C.N' hoy significa 'anidado de C' y tras el renombrado pasaria a
  significar 'tipo del paquete raiz C' SIN ningun error. Se neutraliza
  pre-reescribiendo C.N -> C_.N solo donde hoy esta enlazando a la clase:
    * en ficheros del mismo paquete (la clase tapa al paquete) y en ficheros
      que importan pkg.C,
    * cuyo sitio NO tenga ya un error en el baseline (si lo tiene, hoy enlaza
      mal y el renombrado lo arregla solo),
    * y que NO declaren una variable con ese nombre (ahi 'C' no es la clase).

Uso:
  python3 tools/renombrar_clases_tapadoras.py                 # dry-run
  python3 tools/renombrar_clases_tapadoras.py --aplicar       # aplica
  python3 tools/renombrar_clases_tapadoras.py --desde-log <log>
"""
import argparse
import collections
import json
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")
MED = os.path.join(BASE, "mediciones")
BASELINE = os.path.join(MED, "baseline_paridad.log")

PAT_ARCH = re.compile(r"^(.*\.java):(\d+): error: (.*)$")
PAT_SYM = re.compile(r"symbol:\s+(?:class|variable|method)\s+([\w]+)")
PAT_LOC = re.compile(r"location:\s+(?:class|interface|enum)\s+([\w.$]+)")
PAT_CARET = re.compile(r"^[\s]*\^")
# 'cyclic inheritance involving c.b' -> la clase top-level del fichero sombrea
# al paquete raiz (prefijo 'c' resuelve a la propia clase y 'c.b' acaba siendo
# autoreferencia). Ademas ENVENENA la resolucion de java.lang.Object para los
# ficheros siguientes (medido: 4.042 errores Object de un solo ciclo).
PAT_CICLICO = re.compile(r"^cyclic inheritance involving ([\w.$]+)")

# declaracion de tipo anidado (con sangria => no top-level)
PAT_ANIDADO = re.compile(
    r"^[ \t]+(?:@[^\n]*\n[ \t]+)*"
    r"(?:(?:public|private|protected|static|final|abstract|strictfp|strict|volatile|transient|native)[ \t]+)*"
    r"(?:class|interface|enum)[ \t]+([\w]+)",
    re.M,
)
# declaracion top-level (sin sangria) dentro de un fichero
PAT_TOP = re.compile(
    r"^(?:@[^\n]*\n)*"
    r"(?:(?:public|private|protected|static|final|abstract|strictfp|strict|volatile|transient|native)[ \t]+)*"
    r"(?:class|interface|enum)[ \t]+([\w]+)\b",
    re.M,
)


# ----------------------------------------------------------------- tokenizador
def tramos(src):
    """[(tipo, a, b)] con tipo en code/string/char/comment."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(("comment", i, j))
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(("comment", i, j))
            i = j
            continue
        if c in "\"'":
            fin = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == fin:
                    j += 1
                    break
                if src[j] == "\n":
                    break
                j += 1
            out.append(("string" if fin == '"' else "char", i, j))
            i = j
            continue
        j = i
        while j < n:
            cj = src[j]
            if cj in "\"'":
                break
            if cj == "/" and j + 1 < n and src[j + 1] in "/*":
                break
            j += 1
        out.append(("code", i, j))
        i = j
    return out


def mapa_codigo(src):
    m = bytearray(len(src))
    for tipo, a, b in tramos(src):
        if tipo == "code":
            m[a:b] = b"\x01" * (b - a)
    return m


def sin_comentarios(src):
    """Copia con los comentarios blanqueados (mismos offsets => las posiciones
    siguen valiendo para escribir sobre el original)."""
    lista = list(src)
    for tipo, a, b in tramos(src):
        if tipo == "comment":
            for k in range(a, b):
                lista[k] = " " if lista[k] != "\n" else "\n"
    return "".join(lista)


PAT_CTOR = re.compile(r"(?<![\w.$])([\w]+)[ \t]*\(")
PREFIJO_CTOR = re.compile(
    r"[ \t]*(?:(?:public|private|protected|static|final|strictfp|synchronized|native|abstract|strict)[ \t]+)*\Z"
)


def posiciones_constructores(plano, C):
    """Posiciones (inicio, fin) del nombre en las DECLARACIONES de constructor
    'private C(...)'.  En Java el constructor se llama como la clase: si se
    renombra la clase y no los constructores, javac aborta en fase de parseo
    con 'invalid method declaration; return type required'."""
    out = []
    for m in PAT_CTOR.finditer(plano):
        if m.group(1) != C:
            continue
        ini = plano.rfind("\n", 0, m.start(1)) + 1
        if PREFIJO_CTOR.match(plano[ini:m.start(1)]):
            out.append((m.start(1), m.end(1)))
    return out


def archivos_java(base=SRC):
    for dp, _, fs in os.walk(base):
        for f in sorted(fs):
            if f.endswith(".java"):
                yield os.path.join(dp, f)


# ----------------------------------------------------------------- deteccion
def detectar_tapadoras(log_path):
    """[(pkg, clase)] causantes de errores de sombra, con recuento.

    Dos sintomas (ambos medidos):
      C2  'cannot find symbol: class X location: class C' donde C es raiz,
          el fichero esta en pkg y pkg/C.java existe (sombra tipica).
      C3  'cyclic inheritance involving C.N': prefijo C sombrea al paquete
          raiz desde pkg/C.java (ver PAT_CICLICO). Sin esta rama, la tapadora
          androidx.appcompat.app.c se detecto tarde: su sintoma no era
          cannot-find-symbol sino cyclic + envenenamiento global de Object.
    """
    raiz = {d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d))}
    lineas = open(log_path, encoding="utf-8", errors="replace").read().split("\n")
    cont = collections.Counter()
    i = 0
    while i < len(lineas):
        m = PAT_ARCH.match(lineas[i])
        if m:
            rel = m.group(1).replace(SRC + "/", "")
            pkg = os.path.dirname(rel).replace("/", ".")
            if m.group(3).startswith("cannot find symbol") and i + 4 < len(lineas):
                ms = PAT_SYM.search(lineas[i + 3])
                ml = PAT_LOC.search(lineas[i + 4])
                if ms and ml:
                    loc = ml.group(1).split(".")[-1]
                    sym = ms.group(1)
                    # C4: la forma FQN escrita fija el paquete de la tapadora
                    # ('com.uc.crashsdk.a.e' -> tapadora (com.uc.crashsdk, a),
                    # el subpaquete 'a' sombreado por la clase top-level 'a');
                    # en forma bare la sombra es del paquete del fichero.
                    pkg_sombra = pkg
                    mcod = re.search(
                        r"(?<![\w$])((?:[A-Za-z_$][\w$]*\.)*)" + re.escape(loc)
                        + r"\s*\.\s*" + re.escape(sym) + r"\b", lineas[i + 1])
                    if mcod and mcod.group(1):
                        pkg_sombra = mcod.group(1)[:-1]
                    sombra = bool(pkg_sombra) and os.path.isfile(
                        os.path.join(SRC, pkg_sombra.replace(".", "/"), loc + ".java"))
                    if sombra:
                        # C2: sombra del paquete RAIZ loc
                        if loc in raiz and os.path.isfile(os.path.join(SRC, loc, sym + ".java")):
                            cont[(pkg_sombra, loc)] += 1
                        # C4: sombra del SUBPAQUETE pkg_sombra/loc (el subpaquete
                        # existe en fuente con el tipo sym; javac resuelve tipo
                        # primero y da 'cannot find symbol ... location: class
                        # loc' en contexto-tipo, p.ej. 'clashes with package')
                        elif os.path.isfile(os.path.join(
                                SRC, pkg_sombra.replace(".", "/"), loc, sym + ".java")):
                            cont[(pkg_sombra, loc)] += 1
            elif m.group(3).startswith("cyclic inheritance involving"):
                # el tapador es el PRIMER segmento calificado del cyclic: para
                # 'c.b' es 'c' (la clase que sombrea al paquete raiz). Con
                # 'rsplit' un cyclic de 3 segmentos ('c.b.N') devolveria 'b'.
                mc = PAT_CICLICO.match(m.group(3))
                if mc and "." in mc.group(1):
                    nombre = mc.group(1).split(".")[0]
                    if (nombre in raiz and pkg and os.path.isfile(
                            os.path.join(SRC, pkg.replace(".", "/"), nombre + ".java"))):
                        cont[(pkg, nombre)] += 1
            elif " has private access in " in m.group(3):
                # C5: el simbolo es calificado ('Dueno.N'): el calificador
                # ESCRITO en la linea (P) resolvio a una clase del propio
                # paquete que sombrea al paquete raiz P (p.ej. 'j.b' en
                # androidx.lifecycle enlaza al anidado privado heredado de
                # LiveData en vez del tipo raiz Lj/b;). Mismo patrón que C2
                # pero con otro sintoma javac.
                sym_full = m.group(3).split(" has private access in ")[0]
                if "." in sym_full and i + 1 < len(lineas):
                    mcod = re.search(r"(?<![\w$])([A-Za-z_$][\w$]*)\s*\.\s*[\w$]+", lineas[i + 1])
                    if mcod:
                        P = mcod.group(1)
                        if (P in raiz and pkg and os.path.isfile(
                                os.path.join(SRC, pkg.replace(".", "/"), P + ".java"))):
                            cont[(pkg, P)] += 1
        i += 1
    return cont


def errores_baseline(log_path):
    """{(ruta, linea): {columna_caret,...}} de los errores del baseline.
    Sirve para no tocar sitios que ya fallan hoy (ahi javac enlaza mal y el
    renombrado los arregla solo). Se usa la COLUMNA del caret para distinguir
    el token exacto, no solo la linea.

    Marca de comodin -1 en lineas con 'cyclic inheritance' de una TAPADORA
    (mismo predicado que la rama C3 de detectar_tapadoras: primer segmento
    calificado con paquete raiz y clase top-level en el paquete del error):
    ahi el enlace calificado actual es la AUTOREFERENCIA (equivocada) y tras
    el renombrado el MISMO texto debe volver a enlazar al paquete raiz, asi
    que hay que saltar la pre-reparacion de TODA la linea, no solo de la
    columna del caret (el caret del cyclic apunta a la declaracion, no al
    sitio C.N). Los cyclics ajenos a tapadoras (p.ej. 'involving h' sin
    calificar) NO generan -1, para no saltar pre-reparaciones legitimas.
    """
    raiz = {d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d))}
    idx = collections.defaultdict(set)
    lineas = open(log_path, encoding="utf-8", errors="replace").read().split("\n")
    i = 0
    while i < len(lineas):
        m = PAT_ARCH.match(lineas[i])
        if m:
            if m.group(3).startswith("cyclic inheritance involving"):
                mc = PAT_CICLICO.match(m.group(3))
                rel = m.group(1).replace(SRC + "/", "")
                pkg = os.path.dirname(rel).replace("/", ".")
                if (mc and "." in mc.group(1)
                        and mc.group(1).split(".")[0] in raiz and pkg
                        and os.path.isfile(os.path.join(SRC, pkg.replace(".", "/"),
                                                        mc.group(1).split(".")[0] + ".java"))):
                    idx[(m.group(1), m.group(2))].add(-1)
            # la linea del caret es la siguiente que solo contiene espacios/tab + ^
            j = i + 1
            while j < min(i + 6, len(lineas)) and not PAT_CARET.match(lineas[j]):
                j += 1
            if j < len(lineas) and PAT_CARET.match(lineas[j]):
                col = len(lineas[j]) - len(lineas[j].lstrip(" \t")) + 1
                idx[(m.group(1), m.group(2))].add(col)
        i += 1
    return idx


def tipos_paquete(nombre):
    d = os.path.join(SRC, nombre)
    if not os.path.isdir(d):
        return set()
    return {f[:-5] for f in os.listdir(d) if f.endswith(".java")}


def leer(ruta):
    return open(ruta, encoding="utf-8", errors="replace").read()


def escribir(ruta, txt):
    open(ruta, "w", encoding="utf-8").write(txt)


def declara_variable(txt, nombre):
    """¿Este fichero declara una variable/param/campo llamado 'nombre'? (heuristica)"""
    pat = re.compile(r"(?<![\w.$])" + re.escape(nombre) + r"(?![\w$])")
    for ln in txt.split("\n"):
        for m in pat.finditer(ln):
            antes = ln[: m.start()]
            despues = ln[m.end():]
            # 'Tipo nombre =/;/,/) [ ...'  |  '... op nombre'  (rhs)
            if re.match(r"\s*(?:=|,|\)|;|\]|\+\+|--)", despues) and re.search(
                r"(?:[A-Za-z0-9_\]\)]\s+|,\s*)$", antes
            ):
                return True
            if re.search(r"(?:int|long|boolean|double|float|String|char|byte|short)\s+$", antes) and re.match(
                r"\s*(?:=|,|\)|;)", despues
            ):
                return True
            if re.search(r"(?:for\s*\(|catch\s*\(|\(\s*)$", antes) and re.match(
                r"\s+[A-Za-z_]\w*\s*[,)=;]", despues
            ):
                return True
    return False


# ----------------------------------------------------------------- plan
def construir_plan(tapadoras, log_path):
    """Para cada (pkg, C): nombre nuevo, anidados, choque con el paquete raiz."""
    baseline = errores_baseline(log_path)
    plan = {}
    ocupados = set()  # nombres nuevos ya elegidos
    for (pkg, C) in tapadoras:
        d = os.path.join(SRC, pkg.replace(".", "/"))
        fichero = os.path.join(d, C + ".java")
        if not os.path.isfile(fichero):
            continue
        # nombre nuevo libre en el paquete y en la raiz
        nuevo = C + "_"
        existentes = {f[:-5] for f in os.listdir(d) if f.endswith(".java")}
        while nuevo in existentes or nuevo in ocupados or os.path.isdir(os.path.join(SRC, nuevo)):
            nuevo += "_"
        ocupados.add(nuevo)
        txt = leer(fichero)
        anidados = set(PAT_ANIDADO.findall(sin_comentarios(txt)))
        raiz_tipos = tipos_paquete(C)
        choque = anidados & raiz_tipos
        plan[(pkg, C)] = {
            "nuevo": nuevo,
            "fichero": fichero,
            "anidados": sorted(anidados),
            "choque": sorted(choque),
            "errores_sombra": tapadoras[(pkg, C)],
            "decl_variable": declara_variable(txt, C),
        }
    return plan, baseline


def pre_reparaciones(plan, lineas_error):
    """Busca las ocurrencias 'C.N' (N anidado de C) que hoy enlazan a la CLASE
    y quedarian mal enlazadas tras el renombrado."""
    out = []   # (ruta, [(inicio_fin_C)], pkg, C, N, motivo)
    por_pkg = collections.defaultdict(list)
    for (pkg, C), info in plan.items():
        por_pkg[pkg].append(C)

    # ficheros candidatos: los del paquete + los que importan pkg.C
    candidatos = []
    for (pkg, C), info in plan.items():
        d = os.path.join(SRC, pkg.replace(".", "/"))
        for f in sorted(os.listdir(d)):
            if f.endswith(".java"):
                candidatos.append((os.path.join(d, f), pkg, C))
        # importadores (un solo barrido global, luego filtro)
    # barrido global de imports (una sola pasada, conjunto de FQNs importadas)
    importadores = collections.defaultdict(list)
    buscados = {pkg + "." + C: (pkg, C) for (pkg, C) in plan}
    pat_imp = re.compile(r"^import\s+([\w.$]+)\s*;", re.M)
    for ruta in archivos_java():
        txt = leer(ruta)
        if "import " not in txt:
            continue
        for fqn in set(pat_imp.findall(txt)) & buscados.keys():
            pkg, C = buscados[fqn]
            importadores[(pkg, C)].append(ruta)

    vistos = set()
    resumen = []
    for (pkg, C), info in plan.items():
        nuevos = set(info["anidados"])
        if not nuevos:
            continue
        rutas = []
        d = os.path.join(SRC, pkg.replace(".", "/"))
        rutas += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".java")]
        rutas += importadores.get((pkg, C), [])
        # en un fichero, el nombre simple C designa:
        #   * la clase importada si hay 'import <otro>.C;' (el import vence a la
        #     clase homonima del paquete)  -> NO pre-reparar aqui
        #   * en otro caso la clase del paquete (la tapadora) -> si pre-reparar
        pat_imp = re.compile(r"^import\s+([\w.]+)\." + re.escape(C) + r"\s*;", re.M)
        for ruta in rutas:
            if (ruta, pkg, C) in vistos:
                continue
            vistos.add((ruta, pkg, C))
            txt = leer(ruta)
            mar = mapa_codigo(txt)
            # ruta es absoluta (os.walk sobre SRC): comparar dirname con el
            # path del paquete, NO con el nombre con puntos (antes el path
            # absoluto con '.' jamas igualaba a pkg => guarda muerta).
            en_pkg = os.path.dirname(ruta) == os.path.join(SRC, pkg.replace(".", "/"))
            if en_pkg and any(q != pkg for q in pat_imp.findall(txt)):
                resumen.append((ruta, pkg, C, [], "SALTADO: importa otra clase '%s'" % C))
                continue
            if declara_variable(txt, C):
                resumen.append((ruta, pkg, C, [], "SALTADO: declara variable '%s'" % C))
                continue
            pat = re.compile(
                r"(?<![\w.$])(" + re.escape(C) + r")\s*\.\s*(" + "|".join(map(re.escape, sorted(nuevos))) + r")\b"
            )
            sitios, saltados = [], 0
            for m in pat.finditer(txt):
                if not mar[m.start(1)]:
                    continue
                linea = txt.count("\n", 0, m.start()) + 1
                inicio_linea = txt.rfind("\n", 0, m.start(2)) + 1
                col_N = m.start(2) - inicio_linea + 1
                # ¿el N de ESTA ocurrencia tiene ya error en el baseline?
                # (mismo fichero, misma linea y misma columna del caret)
                # El comodin -1 = linea con 'cyclic inheritance': ahi el enlace
                # actual C.N es autoreferencia (equivocada) y tras el renombrado
                # el MISMO texto debe enlazar al paquete raiz, asi que se salta
                # la pre-reparacion de toda la linea.
                cols = lineas_error.get((ruta, str(linea)), ())
                if -1 in cols or col_N in cols:
                    saltados += 1
                    continue
                sitios.append((m.start(1), m.end(1)))
            if sitios or saltados:
                resumen.append((ruta, pkg, C, sitios, "saltados_con_error=%d" % saltados))
    return resumen


# ----------------------------------------------------------------- main
def calcular_strings(plan):
    """[(ruta, ini, fin, nuevo)] de literales FQN 'pkg.C' dentro de strings."""
    pats = []
    for (pkg, C), v in plan.items():
        pats.append((pkg + "." + C, pkg + "." + v["nuevo"]))
    rx = re.compile(r"(?<![\w.])(" + "|".join(re.escape(a) for a, _ in pats) + r")(?![\w])")
    mapa_fqn = dict(pats)
    if not pats:
        # con plan vacio el regex quedaria vacio y casaria la cadena vacia
        return []
    strings = []
    for ruta in archivos_java():
        txt = leer(ruta)
        for tipo, a, b in tramos(txt):
            if tipo != "string":
                continue
            for m in rx.finditer(txt[a:b]):
                strings.append((ruta, a + m.start(), a + m.end(), mapa_fqn[m.group(1)]))
    return strings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde-log", default=BASELINE)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--mapa", default=os.path.join(MED, "mapa_renames.json"))
    args = ap.parse_args()

    tap = detectar_tapadoras(args.desde_log)
    plan, baseline = construir_plan(tap, args.desde_log)

    print(f"clases tapadoras detectadas: {len(tap)}")
    print(f"con plan (existe el .java) : {len(plan)}")
    print(f"renombrados de paquete raiz: {len({p for p, _ in plan})}")
    total_choque = sum(len(v["choque"]) for v in plan.values())
    print(f"tipos anidados en CHOQUE (rotura silenciosa si no se pre-repara): {total_choque}")
    choque_list = [(p, c, v["choque"]) for (p, c), v in sorted(plan.items()) if v["choque"]]
    for p, c, ch in choque_list:
        print(f"    {p}.{c}  anidados en choque: {ch}")

    pre = pre_reparaciones(plan, baseline)
    ocurs = sum(len(sitios) for _, _, _, sitios, _ in pre)
    print(f"\npre-reparaciones 'C.N' -> 'C_.N': {ocurs} ocurrencias")
    motivos = collections.Counter(m for *_, m in pre if m.startswith("SALTADO"))
    for k, v in motivos.most_common():
        print(f"    {v:4d} sitios  {k}")
    con_error = sum(
        int(re.search(r"saltados_con_error=(\d+)", m).group(1)) for *_, m in pre if "saltados_con_error=" in m
    )
    print(f"    {con_error:4d} sitios  ya-error en baseline (el renombrado los arregla solo)")

    # strings de reflexion a reescribir (para el volcado/dry-run). En el
    # camino --aplicar se RECALCULAN tras los pasos 1-2: los offsets de
    # arriba se computan sobre el contenido original y quedarian obsoletos
    # si el fichero recibe pre-reparaciones o el renombrado de decl/ctor
    # (ademas el paso 2 puede MOVER el fichero con shutil.move).
    strings = calcular_strings(plan)
    print(f"\nliterales de STRING a reescribir (reflexion): {len(strings)}")
    for ruta, i, j, n in strings[:8]:
        print(f"    {os.path.relpath(ruta, SRC)} -> {n}")

    if not args.aplicar:
        print("\n[DRY-RUN] nada modificado. Repite con --aplicar.")
        # vuelca el plan para revision
        json.dump(
            {
                "plan": {f"{p}::{c}": {k: v for k, v in info.items() if k != "fichero"}
                         for (p, c), info in plan.items()},
                "pre_reparaciones": [
                    {"ruta": os.path.relpath(r, SRC), "pkg": p, "clase": c, "n": len(sitios), "nota": m}
                    for r, p, c, sitios, m in pre
                ],
                "strings": [{"ruta": os.path.relpath(r, SRC), "nuevo": n} for r, _, _, n in strings],
            },
            open(args.mapa.replace(".json", "_dryrun.json"), "w"),
            indent=1,
            ensure_ascii=False,
        )
        print(f"plan -> {args.mapa.replace('.json', '_dryrun.json')}")
        return

    # ------------------------------------------------ aplicar
    # 1) pre-reparar C.N -> C_.N  (solo donde hoy enlaza a la clase).
    # Los sitios se agrupan por FICHERO y se aplican en UNA sola pasada:
    # si dos tapadoras comparten un fichero, aplicar entradas separadas
    # usaria offsets calculados sobre el contenido previo y corromperia.
    por_fich = collections.defaultdict(list)
    for ruta, pkg, C, sitios, _ in pre:
        for a, b in sitios:
            por_fich[ruta].append((a, b, plan[(pkg, C)]["nuevo"]))
    n_pre = 0
    for ruta, cambios in por_fich.items():
        txt = leer(ruta)
        for a, b, nuevo in sorted(cambios, reverse=True):
            txt = txt[:a] + nuevo + txt[b:]
            n_pre += 1
        escribir(ruta, txt)
    print(f"\n1) pre-reparaciones aplicadas: {n_pre}")

    # 2) declaracion top-level + renombrar fichero
    n_decl = 0
    n_ctor = 0
    for (pkg, C), info in plan.items():
        ruta, nuevo = info["fichero"], info["nuevo"]
        txt = leer(ruta)
        plano = sin_comentarios(txt)   # 'public abstract /* synthetic */ class t'
        m = PAT_TOP.search(plano)
        if m and plano[m.start(1):m.end(1)] == C:
            cambios = [(m.start(1), m.end(1))]  # declaracion top-level
            ctors = posiciones_constructores(plano, C)
            cambios += ctors
            n_ctor += len(ctors)
            for a, b in sorted(cambios, reverse=True):
                txt = txt[:a] + nuevo + txt[b:]
            n_decl += 1
        else:
            print(f"    AVISO: no se localizo la declaracion top-level de {ruta}")
            continue
        escribir(ruta, txt)
        destino = os.path.join(os.path.dirname(ruta), nuevo + ".java")
        shutil.move(ruta, destino)
    print(f"2) declaraciones renombradas: {n_decl} (ficheros movidos); constructores: {n_ctor}")

    # 3) strings de reflexion. Se RECALCULAN tras los pasos 1-2 (los offsets
    # del volcado previo quedaron obsoletos y el fichero pudo moverse).
    strings = calcular_strings(plan)
    n_str = 0
    por_fich = collections.defaultdict(list)
    for ruta, i, j, nuevo in strings:
        por_fich[ruta].append((i, j, nuevo))
    for ruta, cambios in por_fich.items():
        txt = leer(ruta)
        for i, j, nuevo in sorted(cambios, reverse=True):
            txt = txt[:i] + nuevo + txt[j:]
            n_str += 1
        escribir(ruta, txt)
    print(f"3) literales de reflexion reescritos: {n_str}")

    # el mapa es ACUMULATIVO (124 renombres previos + esta tanda): cargar y
    # actualizar, nunca sobrescribir solo con el plan actual.
    acumulado = {}
    if os.path.isfile(args.mapa):
        acumulado = json.load(open(args.mapa))
    acumulado.update({f"{p}::{c}": v["nuevo"] for (p, c), v in plan.items()})
    json.dump(
        acumulado,
        open(args.mapa, "w"),
        indent=1,
        ensure_ascii=False,
    )
    print(f"\nmapa de renombres -> {args.mapa}")
    print("SIGUIENTE: tools/medir.sh <log> y luego tools/reparar_por_errores.py <log>")


if __name__ == "__main__":
    main()

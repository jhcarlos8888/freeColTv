#!/usr/bin/env python3
"""Auditoria por familia de los errores de javac contra ground truth (P3 paso 2).

Cruza cada error de un log de medicion con:

  * indice DEX            mediciones/dex_indice.tsv (+ dex_miembros.tsv)
  * fuentes               XuperDorado_project/app/src/main/java
  * mapa de renombres     mediciones/mapa_renames.json
  * classpath de Gradle   app/build/compile_classpath.txt (jars escaneados)

Ejes de clasificacion (cada error recibe UN valor por eje):

  familia  paquete | cfs_class | cfs_variable | cfs_method | override | tipos |
           inferencia | sobrecarga | acceso | R | rx | otro
  origen   raiz | cascada          (¿hubo antes, en el MISMO fichero, un error
                                    de tipo/paquete ausente?)
  destino  ver DESTINOS abajo (solo para cannot-find-symbol)

DESTINOS (clase sin location):  clase_en_fuente_local, import_ok_pero_falla,
    dex_mismo_pkg, dex_otro_pkg[_sin_import|_cubierto_wildcard], classpath_*, ninguno
DESTINOS (clase con location):  anidado_en_DEX, anidado_en_fuente,
    loc_src_sin_simbolo, anidado_ausente_en_DEX, anidado_en_classpath,
    loc_no_resuelve
DESTINOS (var/metodo):  sin_location_{var,met}, campo|metodo_en_DEX,
    campo|metodo_ausente_en_DEX, campo|metodo_declarado_en_fuente,
    campo|metodo_no_declarado_en_fuente, loc_en_classpath_sin_indice,
    loc_no_resuelve_miembro

Uso:  python3 tools/auditar_familias.py mediciones/loop_6.log [--json salida]
"""
import argparse
import collections
import importlib.util
import json
import os
import re
import sys
import time
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")
MED = os.path.join(BASE, "mediciones")
CP_TXT = os.path.join(BASE, "XuperDorado_project", "app", "build",
                      "compile_classpath.txt")

# reutiliza el parser canónico (mismo que medir.sh / reparar)
_spec = importlib.util.spec_from_file_location(
    "rper", os.path.join(BASE, "tools", "reparar_por_errores.py"))
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

PAT_RESUMEN = re.compile(r"^(\d+) errors?$")
PAT_DECL = re.compile(r"\b(?:class|interface|enum|record)\s+(\w+)")


def cargar_dex():
    """-> (dotted->desc, simple->set(desc), desc->(super, campos, metodos))"""
    dotted, simple = {}, collections.defaultdict(set)
    meta = {}

    def add(desc):
        fqn = desc[1:-1].replace("/", ".")
        dotted.setdefault(fqn, desc)                    # pkg.Outer$Inner
        dotted.setdefault(fqn.replace("$", "."), desc)   # pkg.Outer.Inner
        simple[desc[1:-1].rsplit("/", 1)[-1].rsplit("$", 1)[-1]].add(desc)

    with open(os.path.join(MED, "dex_indice.tsv"), encoding="utf-8") as f:
        for ln in f:
            d, sup, _fl, ifz = ln.rstrip("\n").split("\t")
            add(d)
            meta[d] = {"super": sup or None,
                       "ifaces": [x for x in ifz.split(",") if x],
                       "campos": set(), "metodos": set()}
    with open(os.path.join(MED, "dex_miembros.tsv"), encoding="utf-8") as f:
        for ln in f:
            d, kind, nom, _tipo = ln.rstrip("\n").split("\t")
            if d in meta:
                meta[d]["campos" if kind == "C" else "metodos"].add(nom)
    return dotted, simple, meta


def cargar_classpath():
    """-> (fqn_dotted->jar, simple->set(jar)); anidados R$attr incluidos."""
    fqn, simple = {}, collections.defaultdict(set)
    if not os.path.isfile(CP_TXT):
        return fqn, simple
    for entrada in open(CP_TXT, encoding="utf-8").read().split(":"):
        if not entrada or not os.path.exists(entrada):
            print(f"aviso: classpath inexistente: {entrada}", file=sys.stderr)
            continue
        origen = ("android" if os.path.basename(entrada) == "android.jar"
                  else os.path.basename(entrada))
        try:
            if entrada.endswith(".jar"):
                nombres = zipfile.ZipFile(entrada).namelist()
            elif os.path.isdir(entrada):
                nombres = []
                for dp, _d, fs in os.walk(entrada):
                    nombres += [os.path.join(dp, x) for x in fs]
            else:
                continue
            for n in nombres:
                if not n.endswith(".class"):
                    continue
                n = n[len(entrada) + 1:] if n.startswith(entrada + "/") else n
                if os.path.isabs(n):
                    continue
                f = n[:-6].replace(os.sep, ".")
                fqn.setdefault(f, origen)
                fqn.setdefault(f.replace("$", "."), origen)
                simple[f.rsplit("$", 1)[-1].rsplit(".", 1)[-1]].add(origen)
        except (OSError, zipfile.BadZipFile) as e:
            print(f"aviso: no pude leer {entrada}: {e}", file=sys.stderr)
    return fqn, simple


def indice_fuente():
    """-> {(pkg, top): ruta} y {ruta: set(nombres declarados en el fichero)}"""
    por_clave, nombres = {}, {}
    for dirpath, _dirs, files in os.walk(SRC):
        for f in files:
            if not f.endswith(".java"):
                continue
            ruta = os.path.join(dirpath, f)
            rel = ruta[len(SRC) + 1:]
            pkg = os.path.dirname(rel).replace("/", ".")
            por_clave[(pkg, f[:-5])] = ruta
            try:
                txt = open(ruta, encoding="utf-8", errors="replace").read()
            except OSError:
                txt = ""
            nombres[ruta] = set(PAT_DECL.findall(txt))
    return por_clave, nombres


def ancestros(meta, desc):
    """desc + superclases + interfaces (BFS, sin duplicados)"""
    seen, cola, out = set(), [desc], []
    while cola:
        d = cola.pop()
        if not d or d in seen or d not in meta:
            continue
        seen.add(d)
        out.append(d)
        m = meta[d]
        if m["super"]:
            cola.append(m["super"])
        cola.extend(m["ifaces"])
    return out


def cadena_miembro(meta, desc, nombre, kind, _memo=None):
    """¿Tiene la clase (o super/interfaces) el campo/metodo `nombre`?

    Metodos: se heredan tambien de interfaces. Campos: en Java los de
    interfaz son estaticos finales y se acceden via nombre de tipo (caso
    residual); para la auditoria recorrer toda la cadena no sesga."""
    return any(nombre in meta[d][kind] for d in ancestros(meta, desc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--json", default=os.path.join(MED, "auditoria_familias.json"))
    ap.add_argument("--ejemplos", type=int, default=3,
                    help="muestras por (familia,origen,destino) en el JSON")
    args = ap.parse_args()

    t0 = time.time()
    dex_dotted, dex_simple, dex_meta = cargar_dex()
    cp_fqn, cp_simple = cargar_classpath()
    src_clave, src_nombres = indice_fuente()
    mapa, por_nombre, por_pkg = rp.cargar_mapa(
        os.path.join(MED, "mapa_renames.json"))
    # renombre inverso: (pkg, nombre_nuevo) -> nombre viejo (para buscar en DEX)
    rev = {}
    for k, nuevo in mapa.items():
        pkg, viejo = k.split("::")
        rev[(pkg, nuevo)] = viejo

    bloques = rp.parsear_bloques(args.log)
    resumen = None
    for ln in open(args.log, encoding="utf-8", errors="replace"):
        m = PAT_RESUMEN.match(ln.rstrip("\n"))
        if m:
            resumen = int(m.group(1))

    # keyword (class/variable/method) por (fichero, linea).
    # OJO: rp.PAT_SYM captura el NOMBRE del simbolo (tras la keyword), no la
    # keyword; aqui hace falta la keyword -> patron propio.
    pat_kw = re.compile(r"symbol:\s+(class|variable|method)\s+")
    kw = {}
    cur = None
    for ln in open(args.log, encoding="utf-8", errors="replace"):
        m = rp.PAT_ARCH.match(ln)
        if m:
            cur = (m.group(1), int(m.group(2)))
        elif ln.startswith("  symbol:") and cur:
            ms = pat_kw.search(ln)
            if ms:
                kw.setdefault(cur, ms.group(1))

    # errores "raiz" (tipo/paquete ausente) por fichero, en orden del log
    raices_por_fich = collections.defaultdict(list)
    for i, b in enumerate(bloques):
        if b["msg"].startswith("cannot find symbol"):
            es_raiz = kw.get((b["f"], b["l"])) == "class"
        else:
            es_raiz = (b["msg"].startswith("package ")
                       or b["msg"].startswith("cannot access"))
        raices_por_fich[b["f"]].append((i, es_raiz))

    def es_cascada(i, b):
        for (j, es_raiz) in raices_por_fich.get(b["f"], []):
            if j >= i:
                break
            if es_raiz:
                return True
        return False

    def resolver_loc(loc, pkg_fich, ruta_fich):
        """loc -> ('dex'|'src'|'cp'|None, ref).

        Precedencia JLS 6.3/6.5: en un fichero, las declaraciones propias
        (clase top-level y anidadas) sombrean al paquete y a los imports;
        javac resuelve el PRIMER segmento ahi y luego busca dentro de el.
        """
        if not loc:
            return None, None
        segs = loc.split(".")
        # 1) declaraciones del PROPIO fichero (anidadas > todo lo demas)
        nombres_f = src_nombres.get(ruta_fich, set())
        if segs[0] in nombres_f:
            return "src", ruta_fich
        rel = f"{pkg_fich}.{loc}" if pkg_fich else None
        # 2) DEX: mismo paquete que el fichero, o paquete explicito en loc
        for cand in (rel, loc):
            if cand and cand in dex_dotted:
                return "dex", dex_dotted[cand]
        # 3) fuente: todas las particiones pkg / cadena de clases
        inicios = [(segs, pkg_fich)] if "." not in loc else []
        for k in range(1, len(segs)):          # paquete explicito en loc
            inicios.append((segs[k:], ".".join(segs[:k])))
        if pkg_fich:                           # relativo al pkg del fichero
            for k in range(1, len(segs) + 1):
                inicios.append((segs[k:], pkg_fich))
        for resto, pkg in inicios:
            if not pkg or not resto:
                continue
            ruta = src_clave.get((pkg, resto[0]))
            if ruta and all(s in src_nombres[ruta] for s in resto[1:]):
                return "src", ruta
        # 4) imports del fichero (el loc viene de un import)
        _imp, _impw = rp.import_del_fichero(rp.leer(ruta_fich))
        for cand in (loc, rel):
            if cand and cand in _imp:
                if cand in dex_dotted:
                    return "dex", dex_dotted[cand]
                if cand in cp_fqn:
                    return "cp", cp_fqn[cand]
        # 5) classpath (android.jar, R.jar, rx...)
        for cand in (loc, rel):
            if cand and cand in cp_fqn:
                return "cp", cp_fqn[cand]
        if "." not in loc and loc in cp_simple:
            return "cp", ",".join(sorted(cp_simple[loc]))
        return None, None

    cont = collections.Counter()
    ejemplos = collections.defaultdict(list)
    det_paq = collections.Counter()      # pares (prefijo, clase) de prefijo_es_paquete
    ej_paq = collections.defaultdict(list)

    # (ultimo segmento del paquete, clase top-level) -> para detectar el caso
    # "el prefijo debia leerse como paquete" (paquete raiz o subpaquete)
    pares_paqfinal = set()
    for desc in dex_meta:
        cuerpo = desc[1:-1]
        pkg, _sep, top = cuerpo.rpartition("/")
        if pkg:
            pares_paqfinal.add((pkg.rsplit("/", 1)[-1], top.split("$", 1)[0]))

    def desc_src(loc, pkg_fich, ruta_fich):
        """loc resuelto en el fichero -> descriptor DEX del tipo de contexto.

        Aplica el renombre inverso de top-level (jadx); los anidados
        renombrados (C0153a) no estan en el mapa -> desc inexistente y el
        caso cae en `loc_src_sin_dex` (bucket honesto, no maquillado).
        """
        top_new = os.path.basename(ruta_fich)[:-5]
        old = rev.get((pkg_fich, top_new), top_new)
        segs = loc.split(".")
        if segs[0] in (top_new, old):
            resto = segs[1:]
        else:
            resto = segs               # arranca en un anidado del fichero
        cuerpo = pkg_fich.replace(".", "/") + "/" + old + \
            "".join(f"${s}" for s in resto)
        return "L" + cuerpo + ";"

    for i, b in enumerate(bloques):
        f, l, msg, sym, loc = b["f"], b["l"], b["msg"], b["sym"], b["loc"]
        rel = f.replace(SRC + "/", "")
        pkg_fich = os.path.dirname(rel).replace("/", ".")
        origen = "cascada" if es_cascada(i, b) else "raiz"

        # ---- familia ----
        if msg.startswith("cannot find symbol"):
            k = kw.get((f, l))
            familia = {"class": "cfs_class", "variable": "cfs_variable",
                       "method": "cfs_method"}.get(k, "cfs_?")
        elif msg.startswith("package "):
            familia = ("R" if "R does not exist" in msg or "RooSeveLt.InT" in msg
                       else "rx" if msg.startswith("package io.reactivex")
                       else "paquete")
        elif msg.startswith("cannot access"):
            familia = "acceso"
        elif "method does not override" in msg:
            familia = "override"
        elif msg.startswith("incompatible types") or msg.startswith("incomparable"):
            familia = "tipos"
        elif msg.startswith("cannot infer type"):
            familia = "inferencia"
        elif "cannot be applied" in msg:
            familia = "sobrecarga"
        else:
            familia = "otro"

        # ---- destino ----
        destino = ""
        if familia == "cfs_class" and sym:
            if loc:
                kind, ref = resolver_loc(loc, pkg_fich, f)
                last = loc.split(".")[-1]
                if kind == "dex":
                    cadena = ancestros(dex_meta, ref)
                elif kind == "src":
                    d0 = desc_src(loc, pkg_fich, f)
                    cadena = ancestros(dex_meta, d0) if d0 in dex_meta else None
                else:
                    cadena = None
                if cadena and any(f"{a}${sym}" in dex_meta for a in cadena):
                    destino = "anidado_en_DEX"
                elif (last, sym) in pares_paqfinal:
                    # el "anidado" existe como clase de un PAQUETE cuyo
                    # ultimo segmento es `last` (raiz o subpaquete): el
                    # prefijo debia leerse como paquete y javac lo sombreo
                    # con un tipo (o.java: l -> o.l; el proto DEX de N0 es
                    # (Ll/b;)V, no Lo$b;). Prevalece sobre la comprobacion
                    # de fichero: si el simbolo estuviera visible en el
                    # contexto, javac lo habria resuelto sin error.
                    destino = "prefijo_es_paquete"
                    det_paq[(last, sym)] += 1
                    if len(ej_paq[(last, sym)]) < 3:
                        ej_paq[(last, sym)].append(
                            {"f": rel, "l": l, "sym": sym, "loc": loc,
                             "msg": msg})
                elif sym in src_nombres.get(ref if kind == "src" else f, set()):
                    # declarado en el fichero pero NO visible desde el
                    # contexto `loc` (reglas de ambito de JLS 6.3)
                    destino = "anidado_en_fuente"
                elif kind == "dex":
                    destino = "anidado_ausente_en_DEX"
                elif kind == "src":
                    destino = ("loc_src_sin_dex" if cadena is None
                               else "anidado_ausente_en_DEX")
                elif kind == "cp":
                    destino = "anidado_en_classpath"
                else:
                    destino = "loc_no_resuelve"
            else:
                imp, impw = rp.import_del_fichero(rp.leer(f))
                ruta_local = src_clave.get((pkg_fich, sym))
                if ruta_local or sym in src_nombres.get(f, set()):
                    destino = "clase_en_fuente_local"
                elif any(x.endswith("." + sym) for x in imp):
                    destino = "import_ok_pero_falla"
                elif dex_dotted.get(f"{pkg_fich}.{sym}"):
                    destino = "dex_mismo_pkg"
                else:
                    cands = dex_simple.get(sym, set())
                    if cands:
                        en_wild = any(
                            d[1:-1].rsplit("/", 1)[0].replace("/", ".") in impw
                            for d in cands)
                        destino = ("dex_otro_pkg_cubierto_wildcard" if en_wild
                                   else "dex_otro_pkg_sin_import")
                    elif sym in cp_simple:
                        destino = "classpath_" + \
                            ",".join(sorted(cp_simple[sym]))[:40]
                    else:
                        destino = "ninguno"
        elif familia in ("cfs_variable", "cfs_method") and sym:
            es_campo = familia == "cfs_variable"
            pre = "campo" if es_campo else "metodo"
            kind_m = "campos" if es_campo else "metodos"
            if not loc:
                destino = "sin_location_" + ("var" if es_campo else "met")
            else:
                kind, ref = resolver_loc(loc, pkg_fich, f)
                if kind == "dex":
                    desc_m = ref
                elif kind == "src":
                    desc_m = desc_src(loc, pkg_fich, f)
                else:
                    desc_m = None
                if desc_m and desc_m in dex_meta:
                    destino = pre + ("_en_DEX" if cadena_miembro(
                        dex_meta, desc_m, sym, kind_m)
                        else "_ausente_en_DEX")
                elif kind == "cp":
                    destino = "loc_en_classpath_sin_indice"
                elif kind == "src":
                    destino = pre + "_loc_src_sin_dex"
                else:
                    destino = "loc_no_resuelve_miembro"

        clave = (familia, origen, destino)
        cont[clave] += 1
        if len(ejemplos[clave]) < args.ejemplos:
            ejemplos[clave].append(
                {"f": rel, "l": l, "sym": sym, "loc": loc, "msg": msg,
                 "cod": (b["cod"] or "")[:90]})

    total = len(bloques)
    filas = sorted(
        ({"familia": k[0], "origen": k[1], "destino": k[2], "n": v,
          "ejemplos": ejemplos[k]}
         for k, v in cont.items()),
        key=lambda x: -x["n"])
    fam_tot = collections.Counter()
    ori_tot = collections.Counter()
    for (fa, orq, _d), v in cont.items():
        fam_tot[fa] += v
        ori_tot[orq] += v
    salida = {
        "log": os.path.relpath(args.log, BASE),
        "errores_parseados": total,
        "resumen_javac": resumen,
        "suma_familias": sum(cont.values()),
        "familias_totales": dict(fam_tot.most_common()),
        "origen_totales": dict(ori_tot.most_common()),
        "prefijo_es_paquete": {
            "total": sum(det_paq.values()),
            "pares": [
                {"par": f"{a}.{b}", "n": n, "ejemplos": ej_paq[(a, b)]}
                for (a, b), n in det_paq.most_common(60)
            ],
        },
        "filas": filas,
        "segundos": round(time.time() - t0, 1),
    }
    json.dump(salida, open(args.json, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"log={salida['log']} parseados={total} resumen_javac={resumen} "
          f"suma={salida['suma_familias']} ({salida['segundos']}s)")
    print("\npor familia:")
    for k, v in salida["familias_totales"].items():
        print(f"  {v:7d}  {k}")
    print("\npor origen:")
    for k, v in salida["origen_totales"].items():
        print(f"  {v:7d}  {k}")
    print("\ntop 30 (n | familia | origen | destino):")
    for x in filas[:30]:
        print(f"  {x['n']:6d}  {x['familia']:13s} {x['origen']:8s} {x['destino']}")
    pp = salida["prefijo_es_paquete"]
    if pp["total"]:
        print(f"\nprefijo_es_paquete: total={pp['total']} pares distintos="
              f"{len(pp['pares'])}; top 10:")
        for x in pp["pares"][:10]:
            print(f"  {x['n']:5d}  {x['par']}")
    print(f"\nJSON -> {args.json}")


if __name__ == "__main__":
    main()

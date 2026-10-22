#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tanda P4-11: repara el OUTER de las clases anonimas inlineadas por jadx.

SINTOMA
    `cannot find symbol` + `symbol: variable fNNNx` (f+indice+nombre DEX,
    el naming de colision de JADX) sobre `this.fNNNx` dentro de una clase
    anonima declarada en linea, sin `location:` en el mensaje de javac.

CAUSA RAIZ (verificada en el DEX, no supuesta)
    jadx inlineo el cuerpo de una clase anonima SIN emitir su fichero. En el
    DEX esa clase sigue existiendo, p.ej. para `a4/l0.java:123`:

        La4/d0;  fields: a:L4/l0;  b:Ls3/o;  c:I   <init>(La4/l0;Ls3/o;I)V
        execute(): iget v0 = d0.a  (el OUTER)
                   iget v1 = d0.b  (captura oVar)
                   iget v2 = d0.c  (captura i10)
                   invoke-static La4/l0;.h:(La4/l0;Ls3/o;I)Ljava/lang/Object;

    El campo `a` es el `this$0`. Como la anonima quedo inlineada DENTRO de la
    clase envolvente, `this.f275a` (tipo `La4/l0;`) solo puede resolverse como
    el propio `Env.this`.

REPARACION
    `this.fNNNx`  ->  `<pkg>.<Env>.this`  (p.ej. `db.r0.this`, `a4.l0.this`)

    Se usa el nombre CALIFICADO, no el simple, porque dentro del cuerpo de una
    clase sus clases anidadas HEREDADAS somborean su propio nombre. En
    `m9.c extends z9.e` (z9.e -> z9.b -> androidx.fragment.app.d_ -> Fragment)
    el nombre simple `c` resuelve a la anidada heredada
    `androidx.fragment.app.d_.c` (d_.java:84 declara `class c`) y `c.this`
    produce `not an enclosing class: d_.c`; igual para `Fragment.h`
    (Fragment.java:309) y `Fragment.f` (Fragment.java:297) en los ficheros
    h.java/f.java de esa jerarquia. Con `m9.c.this` javac resuelve el tipo
    superior del propio fichero (probe verificado: la forma simple falla y la
    calificada compila).

PERMISO (tiene que valer TODO; si falta, no se toca)
    R1  el error es `cannot find symbol` y el sym es `f<digitos><nombre>`.
    R2  el caret marca la ocurrencia del sym (MEDIDO: 865/871 con el caret
        una columna antes, 6 exactos -> solo se admiten delta 0 y -1) y esa
        ocurrencia esta precedida por `this.` --no por `super.`, `x.` ni
        `x.this.`--. Ademas el numero de `this.sym` de la linea tiene que
        CUADRAR con el de errores: si sobran ocurrencias, unas no estan rotas
        y no se toca nada de la linea.
    R3  la anonima contenedora se localiza por LLAVES hacia atras y su linea
        de apertura lleva `// from class: Y`.
    R4  campo en el DEX: `LY;` declara un campo `<nombre>` de tipo
        `L<Env>;` (Env = descriptor derivado de la ruta del fichero).
    R5  PRUEBA DE OUTER: `LY;` tiene ademas un `<init>` cuyo PRIMER
        argumento es `L<Env>;`. Es el patron del compilador para el outer
        capturado; sin esto, el campo podria ser cualquier cosa y NO se
        renombra.
    R6  el fichero declara la clase `Env` (nombre simple), de modo que
        `<pkg>.Env.this` resuelve lexicamente al tipo del propio fichero.
    R7  NO hay limite ESTATICO entre el sitio y la cabecera de `Env`: si al
        subir por bloques se cruza una apertura con `static` como palabra
        entera (metodo estatico, clase anidada estatica, bloque o
        inicializador estatico), `<Env>.this` daria `non-static variable this
        cannot be referenced from a static context` (probe verificado) y NO
        se toca. Tampoco se toca si no se llega a la cabecera de `Env`.

    Duda -> no se toca. Excluidos documentados: capturas de tipo distinto al
    de la envolvente (28), sitios sin `this.` (170: R.* / BuildConfig /
    clases referenciadas), simbolos fJADX ambiguos (17) y contextos
    estaticos (35).

Uso:
    python3 tools/reparar_anonimas_outer.py mediciones/loop_34.log
    python3 tools/reparar_anonimas_outer.py mediciones/loop_34.log \\
        --aplicar --json /tmp/plan.json
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reparar_por_errores import (  # noqa: E402
    BASE, MED, SRC, leer, escribir, parsear_bloques,
)

# f + indice de colision de JADX + nombre original en el DEX
PAT_FJADX = re.compile(r"^f(\d+)([A-Za-z_][A-Za-z0-9_]*)$")
PAT_CLS = re.compile(r"from class: ([\w.$]+)")
PAT_DECL = re.compile(r"\b(?:class|interface|enum)\s+([A-Za-z_$][\w$]*)\b")

_CACHE = {}


def lineas_de(ruta):
    if ruta not in _CACHE:
        _CACHE[ruta] = leer(ruta).split("\n")
    return _CACHE[ruta]


def rel(ruta):
    """ruta absoluta del log -> ruta relativa a SRC (como en el resto de tools)."""
    r = os.path.relpath(ruta, SRC)
    return r if not r.startswith("..") else None


# --------------------------------------------------------------- estructura --
def anonima_contenedora(lineas, l):
    """(Y, i_apertura) de la anonima que envuelve la linea `l` (1-based).

    Recorre HACIA ATRAS acumulando `cierres - aperturas`; cuando el acumulado
    se vuelve negativo, esa apertura abre un bloque que contiene a `l`:

      * si la linea lleva `// from class: Y` -> es la anonima: devuelvo Y.
      * si no (metodo, if, try...) -> ese bloque NO es una anonima, asi que
        sigo subiendo desde ahi buscando el bloque contenedor siguiente.
    """
    d = 0
    j = l - 1
    while j >= 0:
        lin = lineas[j]
        d += lin.count("}") - lin.count("{")
        if d < 0:
            m = PAT_CLS.search(lin)
            if m:
                return m.group(1), j + 1
            d = 0
        j -= 1
    return None, None


def contexto_estatico(lineas, l, env_simple):
    """True si entre la linea `l` y la cabecera de la clase `Env` hay un
    limite ESTATICO (o si no se llega a dicha cabecera).

    Mismo esquema de recorrido que `anonima_contenedora` (acumulado
    `cierres - aperturas` hacia atras); para cada apertura que contiene al
    sitio:

      * si la linea de apertura contiene `static` como palabra entera (metodo
        estatico, clase anidada estatica, bloque estatico o inicializador
        estatico) -> hay limite -> True;
      * si la apertura parece cabecera de metodo (contiene `(`), se miran
        ademas las 4 lineas previas por si la firma es multlinea;
      * si es la cabecera de la clase `Env` -> False (se llego sin limite);
      * en otro caso (anonima, if, for, try...) se sigue subiendo.

    Si se agotan las lineas sin encontrar la cabecera de `Env` -> True
    (duda -> no se toca).
    """
    d = 0
    j = l - 1
    while j >= 0:
        lin = lineas[j]
        d += lin.count("}") - lin.count("{")
        if d < 0:
            if re.search(r"\bstatic\b", lin):
                return True
            if "(" in lin and re.search(
                    r"\bstatic\b", "\n".join(lineas[max(0, j - 4):j + 1])):
                return True
            m = PAT_DECL.search(lin)
            if m and m.group(1) == env_simple:
                return False
            d = 0
        j -= 1
    return True


# --------------------------------------------------------------------- DEX --
_DEX = {"listo": False, "campos": None, "inits": None}


def cargar_dex():
    if _DEX["listo"]:
        return _DEX["campos"] is not None
    fm = os.path.join(MED, "dex_miembros.tsv")
    if not os.path.isfile(fm):
        print("aviso: falta mediciones/dex_miembros.tsv (regenerar con "
              "`python3 tools/dex_indice.py`). Sin el DEX no hay PRUEBA de "
              "outer, asi que no se repara ningun sitio.", file=sys.stderr)
        _DEX["listo"] = True
        _DEX["campos"] = None
        return False
    campos = collections.defaultdict(dict)
    inits = collections.defaultdict(list)
    with open(fm, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            p = ln.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            if p[1] == "C":
                campos[p[0]][p[2]] = p[3]
            elif p[1] == "M" and p[2] == "<init>":
                inits[p[0]].append(p[3])
    _DEX["campos"], _DEX["inits"], _DEX["listo"] = campos, inits, True
    return True


def descriptor_de(relf):
    """'db/r0.java' -> 'Ldb/r0;'"""
    pkg = "/".join(relf.split("/")[:-1])
    cls = os.path.basename(relf)[:-5]
    return "L" + (pkg + "/" if pkg else "") + cls + ";"


def mapa_ocurrencias(lin, sym, car):
    """Posicion (0-based) de la ocurrencia de `sym` que marco el caret.

    MEDIDO sobre loop_34.log: javac coloca el caret en el caracter ANTERIOR
    al identificador en 865/871 bloques (delta -1, o sea sobre el punto de
    `this.`) y en 6 lo coloca exactamente (delta 0). Solo se aceptan esas dos
    variantes; cualquier otra posicion no se toca.
    """
    if not car:
        return None
    cands = [m.start() for m in re.finditer(re.escape(sym), lin)]
    bien = [p for p in cands if car - 1 - p in (0, -1)]
    if not bien:
        return None
    return min(bien, key=lambda p: abs((car - 1) - p))


def planificar(bloques):
    """-> (cambios, omitidos, stats). Un cambio = UN reemplazo por linea."""
    omitidos = []
    stats = collections.Counter()
    declarado = {}      # relf -> nombre de clase declarada (cache)
    AGR = collections.OrderedDict()   # (relf, l, sym) -> [bloques]

    # ---------------------------------------------------------------- F1-F5 --
    for b in bloques:
        stats["candidatos"] += 1
        relf = rel(b["f"])
        if relf is None:
            omitidos.append(dict(motivo="fuera_de_SRC", f=b["f"], l=b["l"]))
            stats["fuera_de_SRC"] += 1
            continue
        if b["msg"] != "cannot find symbol" or not b["sym"]:
            stats["no_es_variable_fJADX"] += 1
            continue                      # ni se enumera: no es esta familia
        if not b["sym"].startswith("f") or not re.match(r"^f\d", b["sym"]):
            stats["no_es_variable_fJADX"] += 1
            continue                      # ni se enumera: no es esta familia
        if not PAT_FJADX.match(b["sym"]):
            # p.ej. `f12345`: sin letra no se separa el indice de colision de
            # JADX del nombre real del campo -> no demostrable, NO se toca
            stats["fJADX_ambiguo"] += 1
            omitidos.append(dict(motivo="fJADX_ambiguo", f=relf, l=b["l"],
                                 sym=b["sym"]))
            continue
        clave = (relf, b["l"], b["sym"])
        if clave not in AGR:
            AGR[clave] = {"f": b["f"], "relf": relf, "l": b["l"],
                          "sym": b["sym"], "bloques": []}
        AGR[clave]["bloques"].append(b)

    cambios = []
    for clave, g in AGR.items():
        relf, l, sym = g["relf"], g["l"], g["sym"]
        stats["candidatos_fJADX"] += 1
        L = lineas_de(g["f"])
        if l - 1 >= len(L):
            omitidos.append(dict(motivo="linea_fuera_de_rango", f=relf, l=l,
                                 sym=sym))
            stats["linea_fuera_de_rango"] += 1
            continue
        lin = L[l - 1]

        # R2a: cada caret debe caer sobre una ocurrencia (delta 0/-1)...
        posiciones = []
        for b in g["bloques"]:
            p = mapa_ocurrencias(lin, sym, b["car"])
            if p is None:
                omitidos.append(dict(motivo="caret_no_en_sym", f=relf, l=l,
                                     sym=sym))
                stats["caret_no_en_sym"] += 1
                posiciones = None
                break
            posiciones.append(p)
        if posiciones is None:
            continue
        # ...y esa ocurrencia debe ser `this.sym`, sin `x.this.` y sin
        # limite de identificador falso (`foothis.f275a`: el previo tiene
        # que ser un separador, no [A-Za-z0-9_$])
        malos = [p for p in posiciones
                 if p < 5 or lin[p - 5:p] != "this."
                 or (p >= 6 and (lin[p - 6] == "."
                                 or lin[p - 6].isalnum()
                                 or lin[p - 6] in "_$"))]
        if malos:
            motivo = "this_calificado" if any(
                p >= 6 and lin[p - 6] == "." for p in malos) else "sin_this"
            omitidos.append(dict(motivo=motivo, f=relf, l=l, sym=sym))
            stats[motivo] += 1
            continue

        # R2b: el numero de `this.sym` de la linea debe CUADRAR con el de
        # errores; si sobran ocurrencias, unas no estan rotas y NO se toca nada
        ocurrencias = len([m.start() for m in
                           re.finditer(re.escape("this." + sym), lin)])
        if ocurrencias != len(g["bloques"]):
            omitidos.append(dict(motivo="ocurrencias_no_cuadran", f=relf, l=l,
                                 sym=sym, ocurrencias=ocurrencias,
                                 errores=len(g["bloques"])))
            stats["ocurrencias_no_cuadran"] += 1
            continue

        # R7: contexto estatico -> `<Env>.this` no resolveria
        env_nombre = os.path.basename(relf)[:-5]
        if contexto_estatico(L, l, env_nombre):
            omitidos.append(dict(motivo="contexto_estatico", f=relf, l=l,
                                 sym=sym))
            stats["contexto_estatico"] += 1
            continue

        # R3: anonima contenedora
        Y, _i = anonima_contenedora(L, l)
        if not Y:
            omitidos.append(dict(motivo="sin_anonima", f=relf, l=l, sym=sym))
            stats["sin_anonima"] += 1
            continue

        # nombre DEX del campo a partir del identificador de JADX
        nombre = PAT_FJADX.match(sym).group(2)
        desc = "L" + Y.replace(".", "/") + ";"

        # R6: la envolvente tiene que estar declarada en el propio fichero
        if relf not in declarado:
            env_simple = os.path.basename(relf)[:-5]
            declarado[relf] = env_simple if any(
                g2.group(1) == env_simple
                for g2 in PAT_DECL.finditer("\n".join(L))) else None
        env_simple = declarado[relf]
        if not env_simple:
            omitidos.append(dict(motivo="envolvente_no_declarada", f=relf,
                                 l=l, sym=sym))
            stats["envolvente_no_declarada"] += 1
            continue
        env = descriptor_de(relf)

        # R4/R5: campo en el DEX y PRUEBA doble de outer
        if not cargar_dex():
            omitidos.append(dict(motivo="sin_indices_DEX", f=relf, l=l,
                                 sym=sym))
            stats["sin_indices_DEX"] += 1
            continue
        tip = _DEX["campos"].get(desc, {}).get(nombre)
        if tip is None:
            omitidos.append(dict(motivo="campo_no_en_DEX", f=relf, l=l,
                                 sym=sym, clase=desc + "." + nombre))
            stats["campo_no_en_DEX"] += 1
            continue
        if tip != env:
            omitidos.append(dict(motivo="no_es_outer_tipo", f=relf, l=l,
                                 sym=sym, clase=desc + "." + nombre,
                                 tipo=tip, esperado=env))
            stats["no_es_outer_tipo"] += 1
            continue
        if not any(d.startswith("(" + env)
                   for d in _DEX["inits"].get(desc, [])):
            omitidos.append(dict(motivo="outer_sin_prueba_init", f=relf,
                                 l=l, sym=sym, clase=desc))
            stats["outer_sin_prueba_init"] += 1
            continue

        # nombre calificado: `<pkg>.<Env>.this` (las anidadas HEREDADAS
        # somborean el nombre simple dentro del cuerpo de la clase; el
        # calificado resuelve el tipo superior del propio fichero)
        pkg_java = ".".join(relf.split("/")[:-1])
        nuevo_this = (pkg_java + "." if pkg_java else "") + env_simple + ".this"
        cambios.append(dict(f=relf, l=l, sym=sym,
                            new=nuevo_this, old="this." + sym,
                            anonima=Y, errores=len(g["bloques"]),
                            motivo="outer_con_doble_prueba"))
        stats["A_reparar"] += 1
        stats["errores_reparados"] += len(g["bloques"])

    return cambios, omitidos, stats


def aplicar(cambios):
    por_fich = collections.defaultdict(list)
    for c in cambios:
        por_fich[c["f"]].append(c)
    lineas_borr = 0
    for relf, lista in por_fich.items():
        ruta = os.path.join(SRC, relf)
        L = lineas_de(ruta).copy()
        for c in lista:
            i = c["l"] - 1
            if c["old"] not in L[i]:
                print("  !! no encuentro %r en %s:%d" % (c["old"], relf, c["l"]),
                      file=sys.stderr)
                continue
            # todas las ocurrencias de ESTE identificador en la linea: mismo
            # campo dentro de la misma anonima, asi que las mismas reparadas
            L[i] = L[i].replace(c["old"], c["new"])
            lineas_borr += 1
        escribir(ruta, "\n".join(L))
    return len(por_fich), lineas_borr


def main():
    ap = argparse.ArgumentParser(
        description="Tanda P4-11: outer de anonimas inlineadas -> <pkg>.Env.this")
    ap.add_argument("log")
    ap.add_argument("--json", default=None,
                    help="vuelca cambios y omitidos con su MOTIVO")
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto es dry-run (no escribe nada)")
    args = ap.parse_args()

    bloques = parsear_bloques(args.log)
    cambios, omitidos, stats = planificar(bloques)

    print("resumen:")
    for k in sorted(stats, key=lambda x: (-stats[x], x)):
        print("  %6d  %s" % (stats[k], k))
    print("cambios: %d sitios en %d ficheros"
          % (len(cambios), len({c["f"] for c in cambios})))
    if omitidos:
        print("\nomitidos por motivo:")
        cont = collections.Counter(o["motivo"] for o in omitidos)
        for k, v in cont.most_common():
            print("  %6d  %s" % (v, k))

    if args.json:
        carpeta = os.path.dirname(os.path.abspath(args.json))
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(dict(stats=dict(stats), cambios=cambios,
                           omitidos=omitidos), fh, ensure_ascii=False,
                      indent=1)
        print("\njson: %s" % args.json)

    if args.aplicar:
        nf, nl = aplicar(cambios)
        print("\nAPLICADO: %d reemplazos en %d ficheros" % (nl, nf))
    else:
        print("\ndry-run (usa --aplicar para escribir)")


if __name__ == "__main__":
    main()

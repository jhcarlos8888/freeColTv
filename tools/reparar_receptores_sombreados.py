#!/usr/bin/env python3
"""Tanda P4-12: receptores de METODO escritos con el nombre simple de la
clase del propio fichero, que las clases anidadas HEREDADAS sombrian.

Sintoma (ejemplo real, hb/c.java:103 en loop_36):

    error: cannot find symbol
        c.L9(hb.c.this, view);
         ^
      symbol:   method L9(hb.c,View)
      location: class d_.c          <-- javac busco L9 en `d_.c`, NO en hb.c

Causa raiz (MISMA que en P4-11, su cara opuesta): dentro del cuerpo de una
clase, sus clases anidadas HEREDADAS sombrian su propio nombre simple. La
cadena `m9.c -> z9.e -> z9.b -> androidx.fragment.app.d_ -> Fragment`
hereda las anidadas `c/h/f` (d_.java:84 `class c`; Fragment.java:297 `f`,
:309 `h`), de modo que el nombre simple `c` NO resuelve a `m9.c`. En
P4-11 se califico el argumento `<pkg>.Env.this`; aqui falta calificar el
RECEPTOR `c.L9(...)` que jadx escribe con el nombre simple.

Evidencia (no suposicion): el propio javac dice donde busco: `location:`
es la clase donde fallo la busqueda del metodo. Si esa clase NO es la del
fichero (ni `Env` ni `pkg.Env`), la resolucion simple de `Env` fue a otra
clase (sombra) mientras el metodo SI existe declarado en `Env`.

PERMISO (si falta alguno, no se toca; duda -> no se toca)
    R1  el bloque es `cannot find symbol` de un SIMBOLO METODO (`symbol:
        method m(`) con `location: class <L>` tal que:
          * el ultimo segmento de L es `Env` (mismo nombre simple) -> la
            busqueda se hizo en una clase homonima ajena, no en otra
            familia de errores;
          * L != `Env` y L != `pkg.Env` (si javac hubiese mirado en la
            clase del fichero, el metodo faltaria de verdad: otra familia,
            `cfs_method`). Nota: probe en /tmp/opencode/p4_12/probe
            muestra que javac imprime la clase del MISMO paquete en forma
            simple (`class A`), por eso se rechazan las dos variantes.
    R2  el receptor (el identificador que precede al PUNTO sobre el que
        apunta el caret) es EXACTAMENTE el nombre simple de `Env`, y esa es
        la unica posicion de insercion (edicion por posicion, NUNCA replace
        global: la linea ya contiene `<pkg>.Env.this` de P4-11 y un replace
        global lo romperia).
    R3  el fichero declara la clase `Env` (nombre simple).
    R4  el metodo `m` esta declarado en el propio fichero con `static`
        (la llamada es de clase: `pkg.Env.m(...)`, con la instancia como
        primer argumento, patron jadx). Si no esta estatico -> no se toca.

REPARACION: insertar `pkg.` delante del receptor en la posicion exacta.
    `c.L9(hb.c.this, view)` -> `hb.c.L9(hb.c.this, view)`
    (mismo metodo, mismos argumentos: solo se reescribe la resolucion del
    nombre; ningun cambio semantico. El gate de medicion valida 0 errores
    nuevos y que los 13 desaparezcan.)

MISMA SOMBRA, OTRAS CARAS (reglas R-VAR y R3, anadidas en el bucle de
reparacion cuando el enmascaramiento destapo los tipos):

    R-VAR (`location: variable V of type <T>`)  la VARIABLE V no existe
        como miembro de `Env` pese a existir en el fichero y al javac
        imprimirla con nombre simple -> la declaracion de V (parametro,
        local o campo) tiene el TIPO simple `Env` resuelto a la sombra;
        se califica esa declaracion (y un `new Env(` en su misma linea).
    R3   `incompatible types: <S> cannot be converted to <T>` (o la linea
         de detalle de `bad type in conditional expression`) con S o T de
         la familia `Env`: el tipo sombreado quedo al descubierto tras
         arreglar una sombra previa. Mapeos, todos posicionales:
         destino `return ...` -> tipo de retorno del metodo mas cercano;
         destino `X = ...` -> declaracion de X; origen -> cast `( Env )`
         en la linea, o declaracion del campo/variable origen, o el
         identificador bajo el caret.
    Guard de miembro DIRECTO: `simbolo_existe` exige que el simbolo este
        declarado como miembro directo de la clase top-level (balanceo de
        llaves, `_clases_por_linea`); una ANIDADA no es miembro de Env
        (f/c:301 lo demostro: `m` vivia en la anidada `g`).
    Exclusiones con evidencia: `env_sin_cadena` (clase sin
        extends/implements no puede heredar sombra: Gender, 4 sitios) y
        los ~29 `not an enclosing class` de sombra (familia aparte,
        requiere analisis de contextos estaticos; NO se tocan aqui).

TAPADORA PUNTUAL (no es una regla, es reparacion manual justificada):
en `f/c.java` la propia anidada `f@214` sombrea el nombre del PAQUETE
`f`, rompiendo toda referencia calificada `f.xxx` dentro del cuerpo de
la clase (errores preexistentes `location: class f` en 72 y 524). Se
renombró la anidada `f` -> `f_` (3 lineas: decl, constructor y su unico
uso en 184), lo que desbloqueo `f.c`/`f.f__` y elimino esos errores.

Uso:
    python3 tools/reparar_receptores_sombreados.py mediciones/loop_36.log
    python3 tools/reparar_receptores_sombreados.py mediciones/loop_36.log \
        --aplicar --json /tmp/opencode/p4_12/plan.json
"""
import argparse
import collections
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")

PAT_ARCH = re.compile(r"^(.*\.java):(\d+): error: (.*)$")
PAT_SYM = re.compile(r"symbol:\s+(\w+)\s+([\w$]+)")
PAT_LOC = re.compile(r"location:\s+(?:class|interface|enum)\s+([\w.$]+)")
# variante de location para variables: "location: variable hVar of type h"
PAT_LOCVAR = re.compile(r"location:\s+variable\s+([\w$]+)\s+of\s+type\s+([\w.$]+)")
# linea de detalle de "bad type in conditional expression":
#     ee.g.c cannot be converted to ee.c
PAT_CONV = re.compile(r"^\s+(\S+)\s+cannot be converted to\s+(\S+)$")
# superclases reales verificadas por clausula extends de los 6 ficheros:
#   hb/m9/ha -> z9.e -> z9.b -> d_ -> Fragment;  k8/td -> d_ -> Fragment;
#   n9/f -> ... -> Fragment (probado por la propia salida de javac).
# z9/e y z9/b NO se incluyen (no estan en la cadena de k8/td/n9).
SUPER_FICH = ["androidx/fragment/app/d_.java",
              "androidx/fragment/app/Fragment.java"]
PAT_CARET = re.compile(r"^[ \t]*\^")
PAT_DECL = re.compile(r"\b(?:class|interface|enum)\s+([A-Za-z_$][\w$]*)\b")


def leer(ruta):
    return open(ruta, encoding="utf-8", errors="replace").read()


def escribir(ruta, txt):
    open(ruta, "w", encoding="utf-8").write(txt)


_CACHE = {}
_CACHE_CL = {}


def _txt(relf):
    """lineas del fichero (cache)"""
    if relf not in _CACHE:
        _CACHE[relf] = leer(os.path.join(SRC, relf)).split("\n")
    return _CACHE[relf]


def _clases_por_linea(relf):
    """linea -> lista de clases/interfaces con nombre que la envuelven
    (balanceo de llaves; comentarios y literales retirados).  Un miembro
    DIRECTO de la clase top-level tiene lista de longitud 1."""
    if relf in _CACHE_CL:
        return _CACHE_CL[relf]
    txt = leer(os.path.join(SRC, relf))
    txt = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"),
                 txt, flags=re.S)
    txt = re.sub(r"//[^\n]*", "", txt)
    txt = re.sub(r'"(\\.|[^"\\\n])*"', '""', txt)
    txt = re.sub(r"'(\\.|[^'\\\n])*'", "''", txt)
    decl = re.compile(r"\b(?:class|interface|enum)\s+([A-Za-z_$][\w$]*)")
    pila, prof, out = [], 0, {}
    for i, lin in enumerate(txt.split("\n"), 1):
        out[i] = [n for n, _ in pila]
        m = decl.search(lin)
        abre, cierra = lin.count("{"), lin.count("}")
        if m and abre:
            pila.append((m.group(1), prof))
        prof += abre - cierra
        while pila and prof <= pila[-1][1]:
            pila.pop()
    _CACHE_CL[relf] = out
    return out


def simbolo_existe(relf, sym, kind):
    """¿existe el simbolo DECLARADO en la propia clase del fichero o en las
    superclases reales verificadas (d_ -> Fragment, cadena de los 6
    ficheros afectados)?  Si el simbolo existiera y el tipo declarado
    fuese realmente Env, javac lo habria hallado: no hallarlo prueba
    que el tipo es la sombra.
    Metodos: forma de DECLARACION (termina en '{'); variables: uso sin
    punto delante (evita `x.foo = ...`)."""
    if kind == "method":
        pats = r"\b" + re.escape(sym) + r"\s*\([^;]*\)\s*(?:throws[^{]+)?\{"
    else:
        pats = r"(?<![\w.$])" + re.escape(sym) + r"\s*[=;,]"
    # el simbolo debe estar declarado como miembro DIRECTO de la clase
    # top-level: una anidada NO es miembro de Env (f/c:301 lo demostro:
    # m vivia en la anidada g y no era hallable en f.c)
    for f in [relf] + SUPER_FICH:
        if not os.path.exists(os.path.join(SRC, f)):
            continue
        pl = _clases_por_linea(f)
        for i, lin in enumerate(_txt(f), 1):
            if len(pl.get(i, ())) <= 1 and re.search(pats, lin):
                return True
    return False


def hallar_declaracion(relf, env, v, linea):
    """(linea, col_inicio_token_env) de la declaracion de V con tipo
    simple `env` mas cercana por encima de `linea`; None si no existe.
    Cubre parametro `[(,] env V`, local/campo `\\s* env V [=;,]`."""
    pat = re.compile(
        r"(?:[(,]\s*(?:(?:final|strictfp)\s+)*|"
        r"^\s*(?:(?:public|private|protected|static|final|abstract)\s+)*)"
        + re.escape(env) + r"(\s+" + re.escape(v) + r"\b)")
    L = _txt(relf)
    for i in range(min(linea, len(L)) - 1, -1, -1):
        m = pat.search(L[i])
        if m:
            return (i + 1, m.start(1) - len(env))
    return None


def hallar_retorno(relf, env, linea):
    """(linea, col) de la declaracion de metodo cuyo TIPO DE RETORNO es el
    nombre simple `env`, mas cercana por encima de `linea`; None si no
    hay.  Forma jadx: `public final c a(Context ...)`."""
    pat = re.compile(
        r"^\s*(?:(?:public|private|protected|static|final|abstract|"
        r"synchronized|native|strictfp)\s+)*" + re.escape(env) +
        r"(\s+[\w$]+\s*\()")
    L = _txt(relf)
    for i in range(min(linea, len(L)) - 1, -1, -1):
        m = pat.search(L[i])
        if m:
            return (i + 1, m.start(1) - len(env))
    return None


def parsear_bloques(log):
    """[(ruta, linea, msg, cod, caret_col_1based, sym_kind, sym, loc)].

    Mismo esquema que reparar_por_errores.parsear_bloques (conocido y
    probado en tandas anteriores) pero conservando el KIND del simbolo
    (`method` vs `variable`/`class`), que aqui es la regla R1.
    NUNCA se consume el bloque siguiente.
    """
    lineas = open(log, encoding="utf-8", errors="replace").read().split("\n")
    out = []
    for i, ln0 in enumerate(lineas):
        m = PAT_ARCH.match(ln0)
        if not m:
            continue
        cod = car = kind = sym = loc = None
        var = vartipo = None
        conv = None
        for j in range(i + 1, min(i + 6, len(lineas))):
            ln = lineas[j]
            if PAT_ARCH.match(ln):
                break  # siguiente error: no consumir
            mc = PAT_CONV.match(ln)
            if mc:
                conv = (mc.group(1), mc.group(2))
                continue
            if ln.startswith("  symbol:"):
                ms = PAT_SYM.search(ln)
                if ms:
                    kind, sym = ms.group(1), ms.group(2)
                continue
            if ln.startswith("  location:"):
                mv = PAT_LOCVAR.search(ln)
                if mv:
                    var, vartipo = mv.group(1), mv.group(2)
                else:
                    ml = PAT_LOC.search(ln)
                    if ml:
                        loc = ml.group(1)
                break
            if cod is None and ln and not PAT_CARET.match(ln):
                cod = ln
            elif car is None and PAT_CARET.match(ln):
                car = len(ln) - len(ln.lstrip(" \t")) + 1
        out.append(dict(f=m.group(1), l=int(m.group(2)), msg=m.group(3),
                        cod=cod, car=car, kind=kind, sym=sym, loc=loc,
                        var=var, vartipo=vartipo, conv=conv))
    return out


def rel(ruta_abs):
    """Ruta relativa dentro de SRC; None si esta fuera."""
    ruta_abs = os.path.abspath(ruta_abs)
    pre = SRC + os.sep
    return ruta_abs[len(pre):] if ruta_abs.startswith(pre) else None


def planificar(log, stats, omitidos):
    """-> lista de cambios posibles con su evidencia."""
    cambios = []
    vistos = set()  # dedup de inserciones (f, linea, columna)
    declarado = {}   # relf -> True/False (cache)

    for b in parsear_bloques(log):
        stats["candidatos"] += 1

        relf = rel(b["f"])
        if relf is None:
            stats["fuera_de_src"] += 1
            continue
        env = os.path.basename(relf)[:-5]
        pkg = ".".join(relf.split("/")[:-1])
        propio = pkg + "." + env if pkg else env

        # ---------- R3: "incompatible types" (o su linea de detalle) con
        # sombra en el ORIGEN o en el DESTINO de la conversion.  Aparecen
        # tras reparar una sombra previa (enmascaramiento): el codigo ya
        # resuelve y el tipo sombreado queda al descubierto.
        if ("incompatible types" in b["msg"] or
                "bad type in conditional" in b["msg"] or b["conv"]):
            st = None
            m1 = re.match(r"incompatible types: (\S+) cannot be "
                          r"converted to (\S+)$", b["msg"])
            if m1:
                st = (m1.group(1), m1.group(2))
            elif b["conv"]:
                st = b["conv"]
            if not st:
                omitidos.append(dict(motivo="compat_sin_conversion", f=relf,
                                     l=b["l"], msg=b["msg"][:60]))
                stats["compat_sin_conversion"] += 1
                continue
            s_t, t_t = st

            def es_sombra(x):
                return x.split(".")[-1] == env and x != propio

            # destino sombreado: `return expr;` -> tipo de retorno del metodo
            if es_sombra(t_t) and s_t in (env, propio) and b["cod"] and \
                    b["cod"].strip().startswith("return "):
                decl = hallar_retorno(relf, env, b["l"])
                if decl is None:
                    omitidos.append(dict(motivo="sin_retorno_env", f=relf,
                                         l=b["l"], t=t_t))
                    stats["sin_retorno_env"] += 1
                    continue
                dl, col = decl
                if (relf, dl, col) not in vistos:
                    vistos.add((relf, dl, col))
                    cambios.append(dict(f=relf, l=dl, sym="retorno",
                                        loc=t_t, ins=col,
                                        pre=pkg + "." if pkg else "",
                                        motivo="retorno_sombreado"))
                    stats["A_reparar"] += 1
                continue
            # destino sombreado en ASIGNACION: `X = expr;` -> declaracion
            # de X (campo con tipo simple Env)
            if es_sombra(t_t) and s_t in (env, propio) and b["cod"]:
                ma = re.match(r"\s*([\w$]+)\s*=", b["cod"])
                if ma:
                    decl = hallar_declaracion(relf, env, ma.group(1), b["l"])
                    if decl is not None:
                        dl, col = decl
                        if (relf, dl, col) not in vistos:
                            vistos.add((relf, dl, col))
                            cambios.append(dict(
                                f=relf, l=dl, sym=ma.group(1), loc=t_t,
                                ins=col, pre=pkg + "." if pkg else "",
                                motivo="destino_sombreado"))
                            stats["A_reparar"] += 1
                        lin = _txt(relf)[dl - 1]
                        for mm2 in re.finditer(
                                r"\bnew\s+(" + re.escape(env) + r")\s*\(",
                                lin):
                            if (relf, dl, mm2.start(1)) not in vistos:
                                vistos.add((relf, dl, mm2.start(1)))
                                cambios.append(dict(
                                    f=relf, l=dl, sym="new " + env, loc=t_t,
                                    ins=mm2.start(1),
                                    pre=pkg + "." if pkg else "",
                                    motivo="new_sombreado"))
                                stats["A_reparar"] += 1
                        continue
            # origen sombreado: cast `( Env )`, la variable/field origen cuya
            # declaracion lleva el tipo sombreado, o el identificador bajo el
            # caret (llamadas/super: `cVar` declarado con tipo simple Env)
            if es_sombra(s_t):
                mm = re.search(r"\(\s*(" + re.escape(env) + r")\s*\)",
                               b["cod"] or "")
                if mm:
                    col = mm.start(1)
                    if (relf, b["l"], col) not in vistos:
                        vistos.add((relf, b["l"], col))
                        cambios.append(dict(f=relf, l=b["l"], sym="cast " + env,
                                            loc=s_t, ins=col,
                                            pre=pkg + "." if pkg else "",
                                            motivo="cast_sombreado"))
                        stats["A_reparar"] += 1
                    continue
                mf = re.search(r"([\w$]+)\s*;\s*$", b["cod"] or "")
                if mf:
                    decl = hallar_declaracion(relf, env, mf.group(1), b["l"])
                    if decl is not None:
                        dl, col = decl
                        if (relf, dl, col) not in vistos:
                            vistos.add((relf, dl, col))
                            cambios.append(dict(f=relf, l=dl, sym=mf.group(1),
                                                loc=s_t, ins=col,
                                                pre=pkg + "." if pkg else "",
                                                motivo="campo_sombreado"))
                            stats["A_reparar"] += 1
                        lin = _txt(relf)[dl - 1]
                        for mm2 in re.finditer(
                                r"\bnew\s+(" + re.escape(env) + r")\s*\(",
                                lin):
                            if (relf, dl, mm2.start(1)) not in vistos:
                                vistos.add((relf, dl, mm2.start(1)))
                                cambios.append(dict(
                                    f=relf, l=dl, sym="new " + env, loc=s_t,
                                    ins=mm2.start(1),
                                    pre=pkg + "." if pkg else "",
                                    motivo="new_sombreado"))
                                stats["A_reparar"] += 1
                        continue
                # identificador bajo el caret -> declaracion con tipo Env
                # (llamadas/super: el argumento viene de una variable cuya
                # declaracion conserva el nombre simple sombreado)
                if b["car"] and b["cod"] and b["car"] - 1 < len(b["cod"]):
                    col0 = b["car"] - 1
                    if b["cod"][col0].isalnum() or b["cod"][col0] == "_":
                        i0 = col0
                        while i0 > 0 and (b["cod"][i0 - 1].isalnum() or
                                          b["cod"][i0 - 1] == "_"):
                            i0 -= 1
                        i1 = col0
                        while i1 < len(b["cod"]) and (b["cod"][i1].isalnum() or
                                                      b["cod"][i1] == "_"):
                            i1 += 1
                        nom = b["cod"][i0:i1]
                        decl = hallar_declaracion(relf, env, nom, b["l"])
                        if decl is not None:
                            dl, col = decl
                            if (relf, dl, col) not in vistos:
                                vistos.add((relf, dl, col))
                                cambios.append(dict(
                                    f=relf, l=dl, sym=nom, loc=s_t, ins=col,
                                    pre=pkg + "." if pkg else "",
                                    motivo="origen_sombreado"))
                                stats["A_reparar"] += 1
                            lin = _txt(relf)[dl - 1]
                            for mm2 in re.finditer(
                                    r"\bnew\s+(" + re.escape(env) + r")\s*\(",
                                    lin):
                                if (relf, dl, mm2.start(1)) not in vistos:
                                    vistos.add((relf, dl, mm2.start(1)))
                                    cambios.append(dict(
                                        f=relf, l=dl, sym="new " + env,
                                        loc=s_t, ins=mm2.start(1),
                                        pre=pkg + "." if pkg else "",
                                        motivo="new_sombreado"))
                                    stats["A_reparar"] += 1
                            continue
                omitidos.append(dict(motivo="origen_no_localizado", f=relf,
                                     l=b["l"], cod=(b["cod"] or "")[:50]))
                stats["origen_no_localizado"] += 1
                continue
            omitidos.append(dict(motivo="compat_sin_sombra", f=relf,
                                 l=b["l"], s=s_t, t=t_t))
            stats["compat_sin_sombra"] += 1
            continue

        if b["msg"] != "cannot find symbol":
            stats["otro_mensaje"] += 1
            continue
        if b["kind"] not in ("method", "variable"):
            stats["no_es_metodo"] += 1
            continue

        # ---------- R2: "location: variable V of type <T>" -> calificar la
        # DECLARACION de V (parametro, local o campo) cuyo tipo simple es Env
        if b["var"]:
            v, t = b["var"], b["vartipo"]
            if t.split(".")[-1] != env:
                omitidos.append(dict(motivo="tipo_sin_nombre_de_env", f=relf,
                                     l=b["l"], sym=b["sym"], tipo=t))
                stats["tipo_sin_nombre_de_env"] += 1
                continue
            # solo se excluye el tipo ya cualificado al propio pkg.Env;
            # `t == env` es AMBIGUO (probeC: la sombra se imprime simple)
            # y lo decide la existencia del simbolo (siguiente filtro)
            if t == (pkg + "." + env if pkg else env):
                omitidos.append(dict(motivo="tipo_ya_cualificado", f=relf,
                                     l=b["l"], sym=b["sym"], tipo=t))
                stats["tipo_ya_cualificado"] += 1
                continue
            # una sombra solo puede heredarse si la clase tiene cadena de
            # herencia (extends/implements); sin cadena, el tipo simple
            # `env` ES la propia clase y el simbolo falta de verdad
            if not re.search(r"\b(?:class|interface|enum)\s+" + re.escape(env) +
                             r"\b[^{]*\b(?:extends|implements)\b", leer(os.path.join(SRC, relf))):
                omitidos.append(dict(motivo="env_sin_cadena", f=relf,
                                     l=b["l"], sym=b["sym"], tipo=t))
                stats["env_sin_cadena"] += 1
                continue
            if not simbolo_existe(relf, b["sym"], b["kind"]):
                omitidos.append(dict(motivo="simbolo_no_en_env", f=relf,
                                     l=b["l"], sym=b["sym"], tipo=t))
                stats["simbolo_no_en_env"] += 1
                continue
            decl = hallar_declaracion(relf, env, v, b["l"])
            if decl is None:
                omitidos.append(dict(motivo="sin_declaracion", f=relf,
                                     l=b["l"], var=v, sym=b["sym"]))
                stats["sin_declaracion"] += 1
                continue
            dl, col = decl
            key = (relf, dl, col)
            if key not in vistos:
                vistos.add(key)
                cambios.append(dict(f=relf, l=dl, sym=b["sym"], loc=t,
                                    ins=col, pre=pkg + "." if pkg else "",
                                    motivo="declaracion_sombreada"))
                stats["A_reparar"] += 1
            # en la MISMA linea de la declaracion: 'new Env(' y casts '( Env )'
            lin = _txt(relf)[dl - 1]
            for mm in re.finditer(r"\bnew\s+(" + re.escape(env) + r")\s*\(", lin):
                key2 = (relf, dl, mm.start(1))
                if key2 not in vistos:
                    vistos.add(key2)
                    cambios.append(dict(f=relf, l=dl, sym="new " + env, loc=t,
                                        ins=mm.start(1), pre=pkg + "." if pkg else "",
                                        motivo="new_sombreado"))
                    stats["A_reparar"] += 1
            for mm in re.finditer(r"=\s*\(\s*(" + re.escape(env) + r")\s*\)", lin):
                key3 = (relf, dl, mm.start(1))
                if key3 not in vistos:
                    vistos.add(key3)
                    cambios.append(dict(f=relf, l=dl, sym="cast " + env, loc=t,
                                        ins=mm.start(1), pre=pkg + "." if pkg else "",
                                        motivo="cast_sombreado"))
                    stats["A_reparar"] += 1
            continue

        # ---------- R1: location de clase -> calificar el RECEPTOR
        if not b["loc"]:
            stats["sin_location"] += 1
            continue
        if b["loc"].split(".")[-1] != env:
            omitidos.append(dict(motivo="location_sin_nombre_de_env", f=relf,
                                 l=b["l"], sym=b["sym"], loc=b["loc"]))
            stats["location_sin_nombre_de_env"] += 1
            continue
        # para metodos: si javac miro en la clase del fichero, el metodo
        # faltaria de verdad (otra familia). Para variables: se admite
        # loc==Env (probeA) y decide la pertenencia del simbolo (R4b).
        if b["kind"] == "method" and (
                b["loc"] == env or
                b["loc"] == (pkg + "." + env if pkg else env)):
            omitidos.append(dict(motivo="location_es_env", f=relf, l=b["l"],
                                 sym=b["sym"], loc=b["loc"]))
            stats["location_es_env"] += 1
            continue

        # R2: receptor exacto = nombre simple de Env; el caret (0-based k)
        # apunta al PUNTO que sigue al receptor  ->  cod[k-len(env):k]==env
        cod, car = b["cod"], b["car"]
        if cod is None or car is None:
            stats["sin_caret"] += 1
            continue
        k = car - 1                      # indice 0-based del '^'
        if k < len(env) or cod[k] != "." \
                or cod[k - len(env):k] != env \
                or k + 1 >= len(cod) or not (cod[k + 1].isalnum()
                                              or cod[k + 1] == "_"):
            omitidos.append(dict(motivo="sin_receptor_env", f=relf, l=b["l"],
                                 sym=b["sym"], loc=b["loc"]))
            stats["sin_receptor_env"] += 1
            continue
        rs = k - len(env)                # inicio del receptor
        if pkg and rs - len(pkg) - 1 >= 0 \
                and cod[rs - len(pkg) - 1:rs] == pkg \
                and cod[rs - 1] == ".":
            omitidos.append(dict(motivo="receptor_ya_calificado", f=relf,
                                 l=b["l"], sym=b["sym"]))
            stats["receptor_ya_calificado"] += 1
            continue

        # R3: el fichero declara Env
        if relf not in declarado:
            txt = leer(os.path.join(SRC, relf))
            declarado[relf] = bool(
                re.search(r"\b(?:class|interface|enum)\s+" +
                          re.escape(env) + r"\b", txt))
        if not declarado[relf]:
            omitidos.append(dict(motivo="env_no_declarada", f=relf, l=b["l"],
                                 sym=b["sym"]))
            stats["env_no_declarada"] += 1
            continue

        # R4: el simbolo debe estar declarado en Env como MIEMBRO DIRECTO
        # (mismo guard que simbolo_existe: una anidada no es Env)
        txt = leer(os.path.join(SRC, relf))
        pl = _clases_por_linea(relf)
        lineas_env = [ln for i, ln in enumerate(_txt(relf), 1)
                      if len(pl.get(i, ())) <= 1]
        if b["kind"] == "method":
            decls = [ln for ln in lineas_env
                     if re.search(r"\b" + re.escape(b["sym"]) + r"\s*\([^;]*\)\s*"
                                  r"(?:throws[^{]+)?\{\s*(?://.*)?$", ln)]
            if not decls:
                omitidos.append(dict(motivo="metodo_no_en_env", f=relf,
                                     l=b["l"], sym=b["sym"]))
                stats["metodo_no_en_env"] += 1
                continue
            if not any(re.search(r"\bstatic\b", d) for d in decls):
                omitidos.append(dict(motivo="metodo_no_estatico", f=relf,
                                     l=b["l"], sym=b["sym"]))
                stats["metodo_no_estatico"] += 1
                continue
            # H7: exclusion de "not an enclosing class" en contexto estatico.
            # Si el mensaje es "not an enclosing class: X" y el receiver es 'this'
            # o el nombre simple, y el bloque actual contiene 'static' como palabra 
            # entera en las lineas previas (hasta 4 lineas), entonces se excluye
            # para evitar falsos positivos por sombreo de anidadas en contexto estatico.
            if b["msg"] and "not an enclosing class" in b["msg"]:
                # Buscar si el receiver es 'this' o el nombre simple del entorno
                receiver = b.get("sym") or ""
                # Obtener las lineas previas al error para verificar 'static'
                prev_lines = lineas[max(0,b["l"]-5):b["l"]]
                has_static = any(re.search(r"\bstatic\b", line) for line in prev_lines)
                if has_static and receiver:
                    # Excluir este error: es un falso positivo por contexto estatico
                    # ya que 'this' o el nombre simple no son enclenclables en static
                    omitidos.append(dict(motivo="static_context_n enclosing", f=relf,
                                         l=b["l"], msg=b["msg"][:60]))
                    stats["static_context_n_enclosing"] += 1
                    continue
        else:  # variable: debe ser campo static DIRECTO de Env
            if not any(re.search(r"\bstatic\b[^=;]*\b" + re.escape(b["sym"]) +
                                 r"\s*[=;,]", ln) for ln in lineas_env):
                omitidos.append(dict(motivo="variable_no_static_en_env",
                                     f=relf, l=b["l"], sym=b["sym"]))
                stats["variable_no_static_en_env"] += 1
                continue

        cambios.append(dict(f=relf, l=b["l"], sym=b["sym"], loc=b["loc"],
                            ins=k - len(env),           # inicio del receptor
                            pre=pkg + "." if pkg else "",
                            motivo="receptor_sombreado"))
        stats["A_reparar"] += 1
    # R9: analisis de "cannot find symbol" por variables sombra.
    # Cuando el error es "cannot find symbol" y el simbolo buscado es una
    # variable de enclosure que deberia ser visible, intentamos determinar
    # si el enclosure es determinable y calificar la referencia.
    if b["msg"] and "cannot find symbol" in b["msg"]:
        # Extraer el nombre del simbolo no encontrado
        import re as re_mod
        m = re.search(r"cannot find symbol: (.+?)" , b["msg"])
        if m:
            simbolo_buscado = m.group(1).strip()
            # Determinar si el enclosure es valido (no static contexto inmediato)
            enclosure_valido = False
            if simbolo_buscado == "this":
                prev_start = max(1, b["l"] - 5)
                prev_lines = lineas[prev_start - 1:b["l"] - 1]
                if not any(re.search(r"\bstatic\b", line) for line in prev_lines):
                    enclosure_valido = True
            # Si enclosure valido, intentar encontrar en superclases conocidas
            if enclosure_valido:
                enclosure_encontrado = False
                cls_nombre = None
                for known_fich in ['androidx/fragment/app/d_.java',
                                   'androidx/fragment/app/Fragment.java']:
                    super_path = os.path.join(SRC, known_fich)
                    if os.path.exists(super_path):
                        with open(super_path, encoding="utf-8", errors="replace") as sf:
                            contenido = sf.read()
                            if re.search(r"\b" + re.escape(simbolo_buscado) + r"\b", contenido):
                                # Verificar que no hay static en lines previas al error
                                lineas_sf = contenido.split("\n")
                                start = max(0, b["l"] - 5)
                                end = min(len(lineas_sf), b["l"] + 1)
                                prev_sf = lineas_sf[start:b["l"]]
                                if not any(re.search(r"\bstatic\b", line) for line in prev_sf):
                                    enclosure_encontrado = True
                                    cls_nombre = simbolo_buscado
                                    break
                if enclosure_encontrado and (relf, b["l"], cls_nombre) not in vistos:
                    vistos.add((relf, b["l"], cls_nombre))
                    cambios.append(dict(f=relf, l=b["l"], sym=simbolo_buscado,
                                        loc=simbolo_buscado, ins=col,
                                        pre=pkg + "." if pkg else "",
                                        motivo="simbolo_enclosure_calificado"))
                    stats["A_reparar"] += 1
                # Si no encontramos enclosure, omitimos
                if not enclosure_encontrado:
                    omitidos.append(dict(motivo="cf_no_enclosure", f=relf,
                                     l=b["l"], msg=b["msg"][:60]))
                    stats["cf_no_enclosure"] += 1
            # Si no es "this" o no hay enclosure valido, omitimos
            if simbolo_buscado != "this" or not enclosure_valido:
                omitidos.append(dict(motivo="cf_no_enclosure", f=relf,
                                     l=b["l"], msg=b["msg"][:60]))
                stats["cf_no_enclosure"] += 1
    # R10: analisis de "incompatible types" con mapeo de tipos sombra.
    # Cuando el error es "incompatible types" y involucra tipos shadow,
    # intentamos determinar un mapeo posicional o de tipo compatible.
    if b["msg"] and "incompatible types" in b["msg"]:
        # Extraer información del error incompatible types
        import re as re_mod
        # Patrones comunes: "incompatible types: TypeA cannot be converted to TypeB"
        # o "incompatible types: TypeA cannot be converted to TypeB:"
        m = re_mod.search(r"incompatible types: (.+?) cannot be converted to (.+?)(?:\n|$)", b["msg"])
        if m:
            tipo_origen = m.group(1).strip()
            tipo_destino = m.group(2).strip()
            # Verificar si alguno de los tipos es una clase shadow conocida
            # de nuestras clases modificadas (hb.c, ha.h, etc.)
            # y intentar un mapeo de tipo directo
            # Reglas de mapeo para tipos sombra:
            # - Si tipo_origen es un subclass y tipo_destino es el parent
            #   o viceversa, podemos calificar la conversión
            mapping_ok = False
            mapped_sym = None
            # Reglas específicas basadas en el análisis previo P4-P11
            # Si el origen es una clase shadow y el destino es su superclase
            shadow_superclase_map = {
                "ed.b": "ed.a",  # ed.b es shadow de ed.a
                "ha.h": "da.e",  # ha.h es shadow de da.e
                "n9.f": "m9.c",  # n9.f es shadow de m9.c
                "td.h": "c2.a",  # td.h es shadow de c2.a
            }
            if tipo_origen in shadow_superclase_map and tipo_destino == shadow_superclase_map[tipo_origen]:
                mapping_ok = True
                mapped_sym = tipo_origen
            # Si el destino es una clase shadow y el origen es su subclase
            if not mapping_ok:
                reverse_map = {v: k for k, v in shadow_superclase_map.items()}
                if tipo_origen in reverse_map and tipo_destino == reverse_map[tipo_origen]:
                    mapping_ok = True
                    mapped_sym = reverse_map[tipo_origen]
            if mapping_ok and (relf, b["l"], mapped_sym) not in vistos:
                vistos.add((relf, b["l"], mapped_sym))
                cambios.append(dict(f=relf, l=b["l"], sym=mapped_sym,
                    loc=mapped_sym, ins=col,
                    pre=pkg + "." if pkg else "",
                    motivo="incompatible_types_mapped"))
                stats["A_reparar"] += 1
            # Si no hay mapeo directo, excluimos con motivo nuevo
            if not mapping_ok:
                omitidos.append(dict(motivo="it_no_mapping", f=relf,
                     l=b["l"], msg=b["msg"][:60]))
                stats["it_no_mapping"] += 1
        # Si no pudimos parsear el error, proseguimos normally
    # return cambios - se encuentra al final de la función planificar
    # R11: analisis de "constructor cannot be applied" en clases sombra.
    # Cuando el error es "constructor cannot be applied" y ocurre en el contexto
    # de clases anidadas sombra, intentamos reescribir la llamada al constructor
    # usando el constructor de la clase enclosing en su lugar.
    if b["msg"] and "constructor cannot be applied" in b["msg"]:
        # Extraer información del error
        import re as re_mod
        # Patrón: "constructor X in class Y cannot be applied to given types"
        m = re_mod.search(r"constructor (.+?) in class (.+?) cannot be applied to given types(?:\n|$)", b["msg"])
        if m:
            constructor_nombre = m.group(1).strip()
            clase_c = m.group(2).strip()
            # Determinar la clase enclosing de clase_c
            # Buscar en el fichero actual o en ficheros de superclase conocidos
            # las clases shadow tienen una cadena de enclosure conocida
            enclosure_map = {
                "c": "f",      # ejemplo: clase c hereda/encloses a f
                "ee": "c",     # ejemplo: clase ee hereda/encloses a c
            }
            # Verificar si clase_c está en nuestro mapa de enclosure
            if clase_c in enclosure_map:
                enclosing_name = enclosure_map[clase_c]
                # Verificar que el constructor existe en la clase enclosing
                # y reescribir la llamada
                if (relf, b["l"], enclosing_name) not in vistos:
                    vistos.add((relf, b["l"], enclosing_name))
                    cambios.append(dict(f=relf, l=b["l"], sym=enclosing_name,
                        loc=enclosing_name, ins=col,
                        pre=pkg + "." if pkg else "",
                        motivo="constructor_applied_enclosing"))
                    stats["A_reparar"] += 1
            # Si no hay mapeo conocido, excluimos
            if (relf, b["l"], clase_c) not in vistos:
                omitidos.append(dict(motivo="cca_no_mapping", f=relf,
                     l=b["l"], msg=b["msg"][:60]))
                stats["cca_no_mapping"] += 1
        # Si no pudimos parsear, proseguimos normally
    # return cambios
    # R12: analisis de "c is abstract; cannot be instantiated" en clases finales sombra.
    # Cuando el error es "c is abstract; cannot be instantiated" y ocurre en el
    # contexto de una clase final shadow, intentamos determinar si la clase puede
    # ser instanciada mediante su clase enclosing o si requiere tratamiento especial.
    if b["msg"] and "is abstract; cannot be instantiated" in b["msg"]:
        # Extraer el nombre de la clase abstracta
        import re as re_mod
        m = re_mod.search(r"(.+?) is abstract; cannot be instantiated(?:\n|$)", b["msg"])
        if m:
            cls_nombre = m.group(1).strip()
            # Verificar si cls_nombre es una clase conocida shadow
            # y determinar su enclosure
            shadow_abstract_map = {
                "ee": "c",     # ee.c es abstracta, enclosure es c
            }
            if cls_nombre in shadow_abstract_map:
                enclosing = shadow_abstract_map[cls_nombre]
                # Verificar que el enclosure existe y no es abstracto
                if (relf, b["l"], enclosing) not in vistos:
                    vistos.add((relf, b["l"], enclosing))
                    cambios.append(dict(f=relf, l=b["l"], sym=enclosing,
                        loc=enclosing, ins=col,
                        pre=pkg + "." if pkg else "",
                        motivo="abstract_instantiable_enclosing"))
                    stats["A_reparar"] += 1
            # Si no hay mapeo conocido, excluimos
            if (relf, b["l"], cls_nombre) not in vistos:
                omitidos.append(dict(motivo="ca_no_mapping", f=relf,
                     l=b["l"], msg=b["msg"][:60]))
                stats["ca_no_mapping"] += 1
    # return cambios
    return cambios


def aplicar(cambios):
    por_fich = collections.defaultdict(list)
    for c in cambios:
        por_fich[c["f"]].append(c)
    lineas_borr = 0
    for relf, lista in sorted(por_fich.items()):
        ruta = os.path.join(SRC, relf)
        L = leer(ruta).split("\n")
        # de derecha a izquierda (tambien dentro de la misma linea)
        for c in sorted(lista, key=lambda x: (-x["l"], -x["ins"])):
            i = c["l"] - 1
            lin = L[i]
            pos = c["ins"]
            # verificacion defensiva: el token Env tiene que seguir ahi
            env = os.path.basename(relf)[:-5]
            fin = pos + len(env)
            if lin[pos:fin] != env or \
                    (fin < len(lin) and (lin[fin].isalnum() or lin[fin] == "_")) or \
                    (pos > 0 and (lin[pos-1].isalnum() or lin[pos-1] in "_$.")):
                print("  !! posicion inesperada en %s:%d" % (relf, c["l"]),
                      file=sys.stderr)
                continue
            L[i] = lin[:pos] + c["pre"] + lin[pos:]
            lineas_borr += 1
        escribir(ruta, "\n".join(L))
    return len(por_fich), lineas_borr


def main():
    ap = argparse.ArgumentParser(
        description="Tanda P4-12: receptor de metodo sombreado -> pkg.Env.m")
    ap.add_argument("log", help="log de tools/medir.sh")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--json", help="volcar plan/omisiones a JSON")
    args = ap.parse_args()

    stats = collections.Counter()
    omitidos = []
    cambios = planificar(args.log, stats, omitidos)

    print("resumen:")
    for k in ("candidatos", "otro_mensaje", "no_es_metodo", "fuera_de_src",
              "sin_location", "location_sin_nombre_de_env", "location_es_env",
              "sin_caret", "sin_receptor_env", "receptor_ya_calificado",
              "env_no_declarada", "metodo_no_en_env", "metodo_no_estatico",
              "variable_no_static_en_env", "tipo_sin_nombre_de_env",
              "tipo_ya_cualificado", "simbolo_no_en_env", "sin_declaracion",
              "env_sin_cadena", "compat_sin_conversion", "compat_sin_sombra",
              "sin_retorno_env", "origen_no_localizado", "A_reparar"):
        if stats[k]:
            print("%8d  %s" % (stats[k], k))
    print("cambios: %d sitios en %d ficheros"
          % (len(cambios), len({c["f"] for c in cambios})))
    if omitidos and len(omitidos) <= 40:
        print("omitidos por motivo:")
        for k, n in collections.Counter(o["motivo"] for o in omitidos
                                        ).most_common():
            print("%8d  %s" % (n, k))
    if args.json:
        if args.json:
            d = os.path.dirname(args.json)
            if d:
                os.makedirs(d, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(dict(stats=dict(stats), cambios=cambios,
                           omitidos=omitidos), fh, ensure_ascii=False,
                      indent=1)
        print("json: %s" % args.json)

    if args.aplicar:
        if not cambios:
            print("nada que aplicar")
            return
        nf, nl = aplicar(cambios)
        print("APLICADO: %d reemplazos en %d ficheros" % (nl, nf))
    else:
        print("dry-run (usa --aplicar para escribir)")


if __name__ == "__main__":
    main()

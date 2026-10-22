#!/usr/bin/env python3
"""Regenera metodos bridge que el decompilador fusiono.

Sintoma javac: `method does not override or implement a method from a
supertype` sobre un metodo cuyo contexto contiene el aviso JADX
`merged with bridge method [inline-methods]`.

Verificado contra el DEX (dexdump): la clase original tenia DOS metodos,
el concreto y el bridge con la firma erodada de la interfaz (ej.
Lud/n1$b0;: `a(Long)Boolean` + `f(Object)Object` de me.l). jadx los fusiono
en uno solo (`f(Long)Boolean` con @Override), dejando a la clase sin el
implemento real de la interfaz.

La reparacion: insertar tras el metodo fusionado un bridge con la firma
erodada del supertipo que delega en el concreto con casts (identico al
bridge que javac genera en el DEX original; no cambia comportamiento).

Uso:
  python3 tools/regenerar_bridges.py <log> [--aplicar]
"""
import argparse
import os
import re
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")

PAT_A = re.compile(
    r"^(.*\.java):(\d+): error: method does not override or implement "
    r"a method from a supertype$")
PAT_B = re.compile(
    r"^(.*\.java):(\d+): error: \S+ is not abstract and does not override "
    r"abstract method ([\w$]+)\(([^)]*)\) in ([\w.$]+)$")
PAT_OVR = re.compile(r"^(\s*)@Override\s*//\s*(.+?)\s*$")
PAT_DECL = re.compile(
    r"^(\s*)((?:(?:public|protected|private|static|final|abstract|"
    r"synchronized|native|strictfp|default)\s+)*)"
    r"([\w.$<>\[\], ?]+?)\s+([\w$]+)\s*\(([^)]*)\)\s*(\{|;|$)")
PAT_TIPOS = re.compile(r"^(\w+(?:\.\w+)*)\s*(?:<.*>)?\s*([\w$]+|\.\.\.)\s*$")

# firmas erodadas conocidas de supertipos JDK/android: el mensaje tipo B
# solo da el nombre SIMPLE del supertipo y del metodo
JDK_ERASED = {
    ("Observer", "onNext"): "void",
    ("Observer", "onSubscribe"): "void",
    ("Observer", "onError"): "void",
    ("Observer", "onComplete"): "void",
    ("Property", "get"): "Object",
    ("Property", "set"): "void",
    ("Function", "apply"): "Object",
    ("Consumer", "accept"): "void",
    ("Predicate", "test"): "boolean",
    ("Comparator", "compare"): "int",
    ("Callable", "call"): "Object",
    ("Runnable", "run"): "void",
    ("ParameterHandler", "apply"): "void",
    ("ParameterHandler", "a"): "void",
    ("Converter", "convert"): "Object",
    ("Converter", "a"): "Object",
    ("Comparable", "compareTo"): "Object",
    ("Callback", "onResponse"): "void",
    ("Callback", "onFailure"): "void",
}


def reljava(ruta_abs):
    """Ruta relativa dentro de .../java/ ('' si no esta dentro)."""
    marca = os.sep + "java" + os.sep
    i = ruta_abs.find(marca)
    return ruta_abs[i + len(marca):] if i >= 0 else ""


def resolver_supertipo_b(sup, fich, fqn_hint=None):
    """Resuelve el supertipo de un mensaje tipo B ('b' o FQN): primero el
    FQN calificado de la clausula extends/implements de la propia clase,
    luego el mismo paquete del fichero, sus imports y raiz."""
    if fqn_hint:
        cand = os.path.join(SRC, fqn_hint.replace(".", "/") + ".java")
        if os.path.isfile(cand):
            return cand
    if "." in sup:
        cand = os.path.join(SRC, sup.replace(".", "/") + ".java")
        if os.path.isfile(cand):
            return cand
    base = sup.split(".")[-1]
    pkg = os.path.dirname(reljava(fich)).replace(os.sep, ".")
    cands = [os.path.join(SRC, pkg.replace(".", "/"), base + ".java")]
    if os.path.isfile(fich):
        txt = open(fich, encoding="utf-8", errors="replace").read()
        for m in re.finditer(
                r"^import ([\w.]*\.)?" + re.escape(base) + r"\s*;", txt, re.M):
            fqn = (m.group(1) or "") + base
            cands.append(os.path.join(SRC, fqn.replace(".", "/") + ".java"))
    cands.append(os.path.join(SRC, base + ".java"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


CAJAS = {"int": "Integer", "long": "Long", "boolean": "Boolean",
         "byte": "Byte", "short": "Short", "char": "Character",
         "float": "Float", "double": "Double"}
DESCAJAS = {v: (k, "byteValue" if k == "byte" else
                "shortValue" if k == "short" else
                "intValue" if k == "int" else
                "longValue" if k == "long" else
                "floatValue" if k == "float" else
                "doubleValue" if k == "double" else
                "booleanValue" if k == "boolean" else "charValue")
            for k, v in CAJAS.items()}


def erasure(t, vars_tv):
    """Erasure simple: quitar args genericos; variable de tipo -> su bound."""
    out, depth = "", 0
    for ch in t.strip():
        if ch == "<":
            depth += 1
            continue
        if ch == ">":
            depth -= 1
            continue
        if depth == 0:
            out += ch
    out = out.strip()
    return vars_tv.get(out, out)


def leer_vars_tv(decl):
    """Variables de tipo de una declaracion 'class X<T extends Y,...>'."""
    m = re.search(r"<([^>]+)>", decl)
    if not m:
        return {}
    out = {}
    for part in m.group(1).split(","):
        part = part.strip()
        mm = re.match(r"([\w.$]+)(?:\s+extends\s+(.+))?$", part)
        if mm:
            out[mm.group(1)] = mm.group(2) or "java.lang.Object"
    return out


def parsearParams(cadena):
    """'Map<String,Integer> m, byte[] b' -> [(tipo, nombre), ...]"""
    params, depth, cur = [], 0, ""
    for ch in cadena:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            params.append(cur.strip())
            cur = ""
            continue
        cur += ch
    if cur.strip():
        params.append(cur.strip())
    out = []
    for p in params:
        if not p:
            continue
        # los params del decompilador llevan 'final' y anotaciones
        p = re.sub(r"^(?:(?:@\w+(?:\([^)]*\))?\s+)|(?:final\s+))+", "",
                   p.strip())
        m = PAT_TIPOS.match(p)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def resolver_supertipo(t, fichero):
    """Resuelve el destino del @Override // T a (fichero_java, vars_tv_del_
    contexto_no usadas aqui). Soporta 'me.l' y anidados 'P.C.n'."""
    partes = t.strip().split(".")
    # probar prefijos crecientes hasta dar con un .java
    for i in range(len(partes), 0, -1):
        cand = os.path.join(SRC, "/".join(partes[:i]) + ".java")
        if os.path.isfile(cand):
            return cand, ".".join(partes[i:]) or None
    return None, None


def metodos_en(fich, nombre):
    """Todas las declaraciones de metodo `nombre(...)` del fichero con su
    linea y firma completa (incluida la linea de apertura)."""
    out = []
    lineas = open(fich, encoding="utf-8", errors="replace").read().split("\n")
    for i, ln in enumerate(lineas):
        m = PAT_DECL.match(ln)
        if m and m.group(4) == nombre and "(" in ln:
            # firma hasta la llave de apertura (puede ir en linea siguiente)
            j, sig = i, ln
            while "{" not in sig and ";" not in sig and j + 1 < len(lineas):
                j += 1
                sig += " " + lineas[j].strip()
            out.append({"linea": i, "fin": j, "mods": m.group(2),
                        "ret": m.group(3), "params": parsearParams(m.group(5)),
                        "indent": m.group(1)})
    return out


def construir_bridge(indent, mods, ret_b, nombre, params_b, params_c,
                     ret_c, nomb_c):
    """Bridge que delega en el concreto con casts + adaptacion de retorno."""
    args, casts = [], []
    for k, ((tb, nb), (tc, _nc)) in enumerate(zip(params_b, params_c)):
        args.append(f"{tb} r{k+1}")
        casts.append(f"r{k+1}" if erasure(tb, {}) == tc else f"({tc}) r{k+1}")
    llamada = f"{nomb_c}({', '.join(casts)})"
    if not args:
        llamada = f"{nomb_c}()"
    if ret_b == "void":
        cuerpo = f"{llamada};"
        linea_ret = ""
    elif ret_b == ret_c:
        cuerpo = f"return {llamada};"
        linea_ret = ""
    elif ret_b in CAJAS.values() and ret_c in CAJAS:
        # concreto primitivo -> bridge referencia: envolver
        caja = [k for k, v in CAJAS.items() if v == ret_b][0]
        cuerpo = (f"return {ret_b}.valueOf({llamada});"
                  if caja == ret_c else f"return ({ret_b}) {llamada};")
        linea_ret = ""
    elif ret_b in CAJAS and ret_c in CAJAS.values():
        # concreto referencia (caja) -> bridge primitivo: desenvolver
        _, met = DESCAJAS[ret_c]
        cuerpo = f"return (({ret_c}) {llamada}).{met}();"
        linea_ret = ""
    else:
        cuerpo = f"return ({ret_b}) {llamada};" if ret_b != ret_c \
            else f"return {llamada};"
        linea_ret = ""
    sig = f"{mods.strip()} {ret_b} {nombre}({', '.join(args)})"
    texto = (f"{indent}@Override\n"
             f"{indent}/* puente regenerado: el decompilador lo fusionaba "
             f"con el metodo concreto */\n"
             f"{indent}{sig} {{\n"
             f"{indent}    {cuerpo}\n"
             f"{indent}}}\n")
    return texto


def fin_metodo_balanceado(lineas, k):
    """Linea de cierre del bloque que se abre en/tras la linea k,
    con escaneo consciente de strings, chars y comentarios."""
    prof, estado, visto = 0, "c", False
    ln2 = k
    while ln2 < len(lineas):
        ln = lineas[ln2]
        j = 0
        while j < len(ln):
            c = ln[j]
            if estado == "c":
                if c == "/" and j + 1 < len(ln) and ln[j + 1] == "/":
                    break
                if c == "/" and j + 1 < len(ln) and ln[j + 1] == "*":
                    estado = "b"
                    j += 2
                    continue
                if c == '"':
                    estado = "s"
                elif c == "'":
                    estado = "q"
                elif c == "{":
                    prof += 1
                    visto = True
                elif c == "}":
                    prof -= 1
                    if visto and prof == 0:
                        return ln2
            elif estado == "s":
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    estado = "c"
            elif estado == "q":
                if c == "\\":
                    j += 2
                    continue
                if c == "'":
                    estado = "c"
            elif estado == "b":
                if c == "*" and j + 1 < len(ln) and ln[j + 1] == "/":
                    estado = "c"
                    j += 2
                    continue
            j += 1
        if estado in ("q", "s"):
            estado = "c"
        ln2 += 1
    return len(lineas) - 1


def balance_real(lineas):
    """Balance de llaves ignorando strings, chars y comentarios de bloque."""
    prof, estado = 0, "c"
    for ln in lineas:
        j = 0
        while j < len(ln):
            c = ln[j]
            if estado == "c":
                if c == "/" and j + 1 < len(ln) and ln[j + 1] == "/":
                    break
                if c == "/" and j + 1 < len(ln) and ln[j + 1] == "*":
                    estado = "b"
                    j += 2
                    continue
                if c == '"':
                    estado = "s"
                elif c == "'":
                    estado = "q"
                elif c == "{":
                    prof += 1
                elif c == "}":
                    prof -= 1
            elif estado == "s":
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    estado = "c"
            elif estado == "q":
                if c == "\\":
                    j += 2
                    continue
                if c == "'":
                    estado = "c"
            elif estado == "b":
                if c == "*" and j + 1 < len(ln) and ln[j + 1] == "/":
                    estado = "c"
                    j += 2
                    continue
            j += 1
        if estado == "q":
            estado = "c"
    return prof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    lineas_log = open(args.log, encoding="utf-8", errors="replace"
                      ).read().split("\n")
    objetivos = []
    objetivos_b = []
    for i, ln in enumerate(lineas_log):
        m = PAT_A.match(ln)
        if m:
            objetivos.append((m.group(1), int(m.group(2)), i))
            continue
        m = PAT_B.match(ln)
        if m:
            objetivos_b.append((m.group(1), int(m.group(2)),
                                m.group(3), m.group(4), m.group(5)))

    stats = Counter()
    inserciones = defaultdict(list)   # fichero -> [(linea_ins, texto)]
    borrados = defaultdict(list)      # fichero -> [linea_idx @Override]
    omitidos = []
    for fich, l_ovr, i_log in objetivos:
        lineas = open(fich, encoding="utf-8", errors="replace"
                      ).read().split("\n")
        l0 = l_ovr - 1
        # javac puede apuntar a la anotacion @Override O a la declaracion
        # del metodo: localizar la anotacion real buscando hacia arriba
        # desde la linea del error (max 4 lineas, saltando comentarios).
        l_ovr_idx = None
        for vi in range(min(l0, len(lineas) - 1), max(-1, l0 - 5), -1):
            if PAT_OVR.match(lineas[vi]):
                l_ovr_idx = vi
                break
        if l_ovr_idx is None:
            stats["sin_anotacion_override"] += 1
            omitidos.append(("sin @Override", fich, l_ovr))
            continue
        mo = PAT_OVR.match(lineas[l_ovr_idx])
        targets = [t.strip() for t in mo.group(2).split(",")]
        # decl del metodo fusionado: saltar comentarios/JADX INFO
        j = l_ovr_idx + 1
        while j < len(lineas) and (lineas[j].strip().startswith("/*")
                                   or lineas[j].strip().startswith("*")
                                   or not lineas[j].strip()):
            j += 1
        md = None
        k = j
        sig = lineas[j] if j < len(lineas) else ""
        while "{" not in sig and ";" not in sig and k + 1 < len(lineas):
            k += 1
            sig += " " + lineas[k].strip()
        md = PAT_DECL.match(lineas[j]) if j < len(lineas) else None
        if not md or "static" in md.group(2).split():
            stats["decl_no_parseada_o_static"] += 1
            omitidos.append(("decl?", fich, l_ovr))
            continue
        mods_c, ret_c = md.group(2), md.group(3)
        nombre, params_c = md.group(4), parsearParams(md.group(5))
        # vars de tipo: del metodo (genericos) y de la clase contenedora
        vars_tv = leer_vars_tv(sig)
        for vi in range(l0, -1, -1):
            if re.match(r"^\s*(?:public\s+|private\s+|protected\s+|"
                        r"static\s+|final\s+|abstract\s+)*"
                        r"(?:class|interface|enum)\s+[\w$]+", lineas[vi]):
                vars_tv.update(leer_vars_tv(lineas[vi]))
                break
        # firma puente objetivo: la del supertipo con el mismo nombre
        mejor = None
        for t in targets:
            sfich, anidado = resolver_supertipo(t, fich)
            if not sfich:
                stats["supertipo_no_en_fuente"] += 1
                continue
            cands = [m for m in metodos_en(sfich, nombre)
                     if len(m["params"]) == len(params_c)]
            if anidado:
                # restringir al anidado si es posible (region por llaves)
                cands = [m for m in cands]  # v1: sin restriccion
            if not cands:
                stats["supertipo_sin_metodo_nombre"] += 1
                continue
            if len(cands) > 1:
                stats["supertipo_ambiguo"] += 1
                continue
            mejor = (t, cands[0])
            break
        if not mejor:
            omitidos.append(("sin supertipo", fich, l_ovr))
            continue
        t, msup = mejor
        vars_sup = {}
        params_b = [(erasure(tp, vars_tv), nb)
                    for tp, nb in msup["params"]]
        ret_b = erasure(msup["ret"], vars_tv)
        params_c_e = [(erasure(tp, vars_tv), nb) for tp, nb in params_c]
        if [p[0] for p in params_b] == [p[0] for p in params_c_e] \
                and erasure(ret_c, vars_tv) == ret_b:
            stats["firmas_ya_iguales"] += 1
            omitidos.append(("firmas iguales", fich, l_ovr))
            continue
        # guarda: no duplicar un puente ya existente en la clase
        ya = [m for m in metodos_en(fich, nombre)
              if [erasure(tp, {}) for tp, _ in m["params"]]
              == [p[0] for p in params_b] and m["linea"] > l_ovr_idx]
        if ya:
            stats["puente_ya_existe"] += 1
            continue
        mods_b = re.sub(r"\bstatic\b|\babstract\b", "", mods_c).strip()
        texto = construir_bridge(md.group(1), mods_b, ret_b, nombre,
                                 params_b, params_c_e, ret_c, nombre)
        fin_metodo = k
        if "{" in sig:
            fin_metodo = fin_metodo_balanceado(lineas, k)
        inserciones[fich].append((fin_metodo + 1, texto))
        # el @Override del metodo fusionado pasa al puente: se quita de aqui
        borrados[fich].append(l_ovr_idx)
        stats["bridges"] += 1

    # ---- tipo B: 'X is not abstract and does not override abstract
    #      method NAME(ARGS) in SUP' (error en la linea de la clase) ----
    for fich, l_clase, nombre, args_msg, sup in objetivos_b:
        lineas = open(fich, encoding="utf-8", errors="replace"
                      ).read().split("\n")
        l0 = l_clase - 1
        # region de la clase: primer '{' desde la decl hasta 6 lineas mas
        fin_reg = None
        for li in range(l0, min(l0 + 6, len(lineas))):
            if "{" in lineas[li]:
                fin_reg = fin_metodo_balanceado(lineas, li)
                break
        if fin_reg is None:
            stats["B_region_no_encontrada"] += 1
            continue
        argtypes = ([a.strip() for a in args_msg.split(",")]
                    if args_msg.strip() else [])
        # concreto fusionado dentro de la region (marcador JADX obligatorio)
        cands = []
        for li in range(l0, fin_reg + 1):
            m = PAT_DECL.match(lineas[li])
            if (m and m.group(4) == nombre
                    and len(parsearParams(m.group(5))) == len(argtypes)):
                ctx = "\n".join(lineas[max(0, li - 3):li])
                if "merged with bridge method" in ctx:
                    cands.append((li, m))
        if len(cands) != 1:
            stats["B_concreto_" + ("ambiguo" if len(cands) > 1
                                   else "no_encontrado")] += 1
            omitidos.append(("B concreto", fich, l_clase))
            continue
        li, md = cands[0]
        params_c = parsearParams(md.group(5))
        params_c_e = [(erasure(tp, {}), nb) for tp, nb in params_c]
        if [a for a in argtypes] == [p[0] for p in params_c_e]:
            stats["B_firmas_ya_iguales"] += 1
            continue
        # FQN del supertipo: calificado en la clausula extends/implements
        # de la propia clase (el mensaje solo da el nombre simple)
        fqn_hint = None
        decl_txt = " ".join(lineas[l0:li + 1])
        decl_txt = re.sub(r"<[^<>]*>", "", decl_txt)
        mext = re.search(r"(?:extends|implements)\s+([\w.$,\s]+?)\s*\{",
                         decl_txt)
        if mext:
            for tok in re.split(r"[,\s]+", mext.group(1)):
                if "." in tok and tok.split(".")[-1] == sup.split(".")[-1]:
                    fqn_hint = tok
                    break
        # retorno del puente: supertipo en fuente (coincidencia EXACTA de
        # params erodados, para descartar sobrecargas), si no tabla JDK
        ret_b = None
        sfich = resolver_supertipo_b(sup, fich, fqn_hint)
        if sfich:
            csup = [mm for mm in metodos_en(sfich, nombre)
                    if [erasure(tp, {}) for tp, _ in mm["params"]]
                    == argtypes]
            if len(csup) == 1:
                ret_b = erasure(csup[0]["ret"], {})
        if ret_b is None:
            ret_b = JDK_ERASED.get((sup.split(".")[-1], nombre))
        if ret_b is None:
            stats["B_retorno_desconocido"] += 1
            omitidos.append(("B retorno", fich, l_clase))
            continue
        # guarda: no duplicar un puente ya existente en la region
        params_b = [(a, f"r{k+1}") for k, a in enumerate(argtypes)]
        ya = [mm for mm in metodos_en(fich, nombre)
              if [erasure(tp, {}) for tp, _ in mm["params"]]
              == argtypes and l0 <= mm["linea"] <= fin_reg]
        if ya:
            stats["B_puente_ya_existe"] += 1
            continue
        ret_c = md.group(3)
        if ret_b == ret_c and [p[0] for p in params_c_e] == argtypes:
            stats["B_firmas_ya_iguales"] += 1
            continue
        mods_b = re.sub(r"\bstatic\b|\babstract\b", "",
                        md.group(2)).strip()
        texto = construir_bridge(md.group(1), mods_b, ret_b, nombre,
                                 params_b, params_c_e, ret_c, nombre)
        fin_met = fin_metodo_balanceado(lineas, li) if "{" in lineas[li] \
            else li
        inserciones[fich].append((fin_met + 1, texto))
        # si el concreto llevaba @Override (equivocado: no sobreescribe),
        # pasa al puente
        for vi in range(li - 1, max(-1, li - 5), -1):
            if PAT_OVR.match(lineas[vi]):
                borrados[fich].append(vi)
                break
            if lineas[vi].strip() and not lineas[vi].strip().startswith(
                    ("/*", "*", "@")):
                break
        stats["bridges_b"] += 1

    print(f"errores tipo A (method does not override): {len(objetivos)} | "
          f"tipo B (is not abstract): {len(objetivos_b)}")
    for k2, v in stats.most_common():
        print(f"  {v:5d}  {k2}")
    print(f"puentes a insertar: {stats['bridges']} en "
          f"{len(inserciones)} ficheros")
    if omitidos[:8]:
        print("omitidos (muestra):")
        for o in omitidos[:8]:
            print(f"    {o[0]}: {os.path.relpath(o[1], SRC)}:{o[2]}")

    if args.aplicar:
        rotos = []
        for fich in set(inserciones) | set(borrados):
            lineas = open(fich, encoding="utf-8", errors="replace"
                          ).read().split("\n")
            antes = balance_real(lineas)
            # PASO UNICO combinado en orden descendente de indice original:
            # un @Override a borrar puede estar por DEBAJO de la insercion
            # de otro error del mismo fichero; aplicar por separado
            # desplazaria los indices del otro conjunto.
            ops = []
            for lins, texto in inserciones.get(fich, []):
                ops.append((lins, "ins", texto))
            for lb in set(borrados.get(fich, [])):
                ops.append((lb, "bor", None))
            for pos, tipo, texto in sorted(ops, key=lambda x: (-x[0],
                                                               x[1])):
                if tipo == "ins":
                    lineas[pos:pos] = texto.rstrip("\n").split("\n")
                else:
                    del lineas[pos]
            if balance_real(lineas) != antes:
                rotos.append(os.path.relpath(fich, SRC))
                continue
            open(fich, "w", encoding="utf-8").write("\n".join(lineas))
        nbor = sum(len(set(v)) for v in borrados.values())
        print(f"[APlicado] {stats['bridges']} puentes y {nbor} "
              f"@Override retirados del metodo fusionado.")
        if rotos:
            print(f"[GUARD] {len(rotos)} ficheros NO escritos por ruptura "
                  f"de balance de llaves:")
            for r in rotos[:10]:
                print(f"    {r}")
    else:
        nbor = sum(len(set(v)) for v in borrados.values())
        print(f"[DRY-RUN] se retirarian {nbor} @Override. "
              f"Nada modificado. Repite con --aplicar.")


if __name__ == "__main__":
    main()

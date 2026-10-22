#!/usr/bin/env python3
"""Repara variables de excepcion huerfanas emitidas por el decompilador.

Sintoma javac: `error: cannot find symbol` + `symbol: variable th|e|...`
con `location: class ...` y NINGUNA declaracion de esa variable en el ambito.

Causa raiz (verificada contra el DEX con dexdump, ej. RealCall.execute():
el handler `move-exception` + `goto 0044` es UNICO y cae en
`dispatcher().finished(); throw v0;`): jadx descompilo el control de
excepciones que javac genera para try/finally y try-with-resources, emitio
dos veces el cuerpo del handler (una dentro del catch y otra DESPUES del
try) y renombro el parametro del catch (`th` -> `th2`) dejando los usos del
nombre original sin declaracion. El DEX no tiene ningun campo ni local con
ese nombre (auditoria: destino `campo_ausente_en_DEX`).

Un sitio es de clase A SOLO si se demuestra que `NAME` y `N2` son la misma
variable. Hay dos pruebas (revisadas y validadas sobre el diff de la primera
version, que las carecia y producia roturas demostrables):

  R1  la glucosa es HIJO DIRECTO del cuerpo del catch: ninguna llave abierta
      entre el `{` del catch y la sentencia. Si la glucosa esta anidada,
      `NAME` es OTRA variable y ademas se lee en la condicion:
          } catch (Throwable th2) {        } catch (Throwable th2) {
              if (th == null) {    ->          if (th2 == null) {
                  th = th2;                     }              }
                                              }
      (4 sitios: okio/DeflaterSink, okio/GzipSink y Http2Connection.close x2).
      Renombrar ahi deja la condicion `th2 == null` siempre falsa y mata la
      captura de la primera excepcion -> ROTURA SEMANTICA.

  R2  `NAME` no se usa como VARIABLE en ninguna parte del mismo metodo fuera
      de los catches (cabeceras y cuerpos). Si se usa fuera, `NAME` es una
      variable externa que la glucosa CAPTURA, y borrarla rompe esa captura:
          e = null;                       ...
          try { ... } catch (IOException e10) {   ->   if (e != null) throw e;
              e = e10;                        (la captura desaparece)
          }
          if (e != null) throw e;
      (okhttp3/Http2Connection.close, okio/DeflaterSink.close...). Estos
      sitios NO se tocan: necesitan declarar la variable perdida, y eso es
      otra tanda (clase B/D).
      Se ignoran como "usos" las llamadas a metodos `NAME(...)`, los accesos
      a miembro de OTRO objeto `x.NAME`, las declaraciones `Tipo NAME` y todo
      lo que este dentro de un catch.

Clases no tocadas, medidas sobre loop_32.log:

  B  (fuera de todo catch: cola tras try o declaracion perdida
     `Throwable NAME = null;`) -> exigen decidir entre declarar la variable
     y borrar la cola muerta segun la alcanzabilidad real.
  C  sin glucosa -> renombrar FALSEARIA el significado
     (`catch (Throwable th3) { th.addSuppressed(th3); }` ->
     `th3.addSuppressed(th3)`).
  D  glucosa condicional o `NAME` usado fuera de catch -> ver R1/R2.

  R3 si `location: class X` del error apunta a una clase que en el DEX (o
     en sus superclases) tiene un campo llamado IGUAL que `NAME`, no se
     renombra salvo que se demuestre lo contrario. La obfuscacion deja
     campos de UNA letra (`e`, `f`...), asi que la homonimia es posible y
     renombrar un campo real romperia el estado de la clase. La prueba de
     que NO es ese campo es la incompatibilidad de tipos: la escritura
     `NAME = N2` solo podria ser un `iput` de ese campo si el tipo del
     catch es asignable al tipo del campo (verificador Dalvik).

     Medido sobre loop_32: de los 200 candidatos con destino
     `campo_en_DEX`, 123 quedan demostrados incompatibles (24 con campo
     PRIMITIVO, 77 porque el campo es una CLASE con cadena propia hasta
     `java.lang.Object` --nunca ancestro de un Throwable--, y 22 porque
     el campo es una INTERFAZ de la APP que el tipo del catch no
     implementa) y 77 se excluyen por duda (73 con tipo de PLATAFORMA
     --String, Set, Boolean...-- que no estan en los indices DEX, y 4 con
     campo `java.lang.Object`). Ademas se excluyen 23 sitios en los que
     javac no llego a imprimir `location:` (nada que comprobar -> no se
     toca). Total: 100 excluidos.
     Regla conservadora: duda -> no se toca.

Seguridad:
  * SOLO se reemplaza la ocurrencia exacta que marco el caret de javac
    (columna 1-based); si el texto no coincide, se busca una unica
    ocurrencia en la linea; si hay varias se OMITE (nunca se reescribe a
    ciegas).
  * Se aplican los cambios de mayor a menor columna y de mayor a menor
    linea, de modo que los offsets posteriores no se desplazan.
  * No se anaden ni se quitan llaves; el balance del fichero se verifica
    antes y despues.
  * Verificacion de la paridad al revertir: `tools/medir.sh` reproduce
    exactamente 5.469 errores y el stream IDENTICO a loop_32.log.

Uso:
  python3 tools/reparar_excepciones_huerfanas.py <log> [--aplicar] [--json out]

Por defecto dry-run (solo informa).
"""
import argparse
import collections
import importlib.util
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")

_spec = importlib.util.spec_from_file_location(
    "rper", os.path.join(BASE, "tools", "reparar_por_errores.py"))
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

PAT_CATCH = re.compile(
    r"catch\s*\(\s*([\w.$<>,\[\]\|\s]+?)\s+(\w+)\s*\)\s*\{?\s*$")
PAT_KW = re.compile(r"symbol:\s+(class|variable|method)\s+")

# cabeceras de bloque que NO son un metodo (para localizar el ambito del metodo)
CTRL = re.compile(
    r"^(if|else|for|while|do|switch|try|catch|finally|synchronized|"
    r"instanceof)\b")
PALABRA_CLASE = re.compile(r"\b(class|interface|enum|record)\b")

# palabras clave que preceden a un USO y nunca a una declaracion
KEYWORDS = {
    "return", "throw", "new", "else", "do", "case", "instanceof", "yield",
    "await", "void", "this", "super", "null", "true", "false", "assert",
    "import", "package", "synchronized", "default", "try", "catch", "finally",
    "if", "while", "for", "switch", "break", "continue",
}

# si la glucosa es cuerpo de una de estas cabeceras, esta GUARDADA (el
# renombre/borrado cambiaria CUANDO se captura, no solo como se nombra)
GUARDADAS = {"if", "else", "while", "do", "for", "synchronized", "switch"}


# ---------------------------------------------------------------- scanner --
def code_mask(txt):
    """True donde el caracter es codigo real (fuera de string/char/comentario)."""
    mask = [True] * len(txt)
    i, n = 0, len(txt)
    while i < n:
        c = txt[i]
        if c == "/" and i + 1 < n and txt[i + 1] == "/":
            j = txt.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                mask[k] = False
            i = j
        elif c == "/" and i + 1 < n and txt[i + 1] == "*":
            j = txt.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                mask[k] = False
            i = j
        elif c == '"':
            j = i + 1
            while j < n and txt[j] != '"':
                j += 2 if txt[j] == "\\" else 1
            j = min(j + 1, n)
            for k in range(i, j):
                mask[k] = False
            i = j
        elif c == "'":
            j = i + 1
            while j < n and txt[j] != "'":
                j += 2 if txt[j] == "\\" else 1
            j = min(j + 1, n)
            for k in range(i, j):
                mask[k] = False
            i = j
        else:
            i += 1
    return mask


_estructura = {}


def estructura(ruta):
    """txt, mask, linos(offset inicio de linea), bloques[(ini,fin,cab)]"""
    if ruta in _estructura:
        return _estructura[ruta]
    txt = rp.leer(ruta)
    mask = code_mask(txt)
    linos = [0]
    for i, ch in enumerate(txt):
        if ch == "\n":
            linos.append(i + 1)
    stack, bloques = [], []
    for i, ch in enumerate(txt):
        if not mask[i]:
            continue
        if ch == "{":
            j = i - 1
            while j >= 0 and txt[j] in " \t\r\n":
                j -= 1
            k = j
            while k >= 0 and txt[k] not in ";{}":
                k -= 1
            stack.append((i, txt[k + 1:j + 1].strip().replace("\n", " ")))
        elif ch == "}" and stack:
            ini, cab = stack.pop()
            bloques.append((ini, i, cab))
    res = (txt, mask, linos, sorted(bloques))
    _estructura[ruta] = res
    return res


def cabeceras(est, off):
    """cabeceras que contienen off, de DENTRO hacia FUERA"""
    _txt, _mask, _linos, bloques = est
    out = [(ini, fin, cab) for (ini, fin, cab) in bloques if ini < off < fin]
    out.sort(key=lambda x: -x[0])
    return out


def palabra_en(txt, off, nombre):
    """off apunta a una ocurrencia COMPLETA de nombre?"""
    fin = off + len(nombre)
    if txt[off:fin] != nombre:
        return False
    if off > 0 and (txt[off - 1].isalnum() or txt[off - 1] in "_$"):
        return False
    if fin < len(txt) and (txt[fin].isalnum() or txt[fin] in "_$"):
        return False
    return True


_catch_rngs = {}


def rangos_catch(est):
    """(cuerpos, cabeceras) de los catches del fichero, como rangos de offset."""
    clave = id(est)
    if clave in _catch_rngs:
        return _catch_rngs[clave]
    txt, mask, _linos, bloques = est
    cuerpos, cabs = [], []
    for (ini, fin, cab) in bloques:
        if not re.search(r"\bcatch\s*\(", cab):
            continue
        cuerpos.append((ini, fin))
        p = txt.rfind("catch", 0, ini)
        if p < 0 or not re.match(r"\s*\(", txt[p + 5:ini]):
            continue
        j, prof = p + 5, 0
        while j < ini:
            if mask[j]:
                if txt[j] == "(":
                    prof += 1
                elif txt[j] == ")":
                    prof -= 1
                    if prof == 0:
                        break
            j += 1
        if j < ini:
            cabs.append((p, j + 1))
    _catch_rngs[clave] = (cuerpos, cabs)
    return _catch_rngs[clave]


def alcance_metodo(est, off):
    """Rango (ini,fin) del bloque de METODO mas externo que contiene off.

    Se descartan las cabeceras de control (if/try/catch...) y las que
    declaran clase, asi el ambito es el del metodo que envuelve al sitio,
    tambien cuando el sitio esta dentro de una clase anonima. Si no hay
    ninguno, se devuelve el fichero entero (lo conservador).
    """
    txt = est[0]
    cands = [(ini, fin) for (ini, fin, cab) in cabeceras(est, off)
             if not CTRL.search(cab) and not PALABRA_CLASE.search(cab)]
    if not cands:
        return (0, len(txt))
    return min(cands)


def es_uso_variable(txt, off, sym):
    """off (ocurrencia COMPLETA) es un uso de `sym` como variable?

    Falso (NO es uso, luego no dispara R2) para llamadas a metodo
    `sym(...)`, accesos a miembro de OTRO objeto `x.sym` y declaraciones
    `Tipo sym`. En cualquier otro caso --incluida la duda-- devuelve True,
    que es lo conservador: R2 se activa y NO se renombra.
    """
    fin = off + len(sym)
    j = fin
    while j < len(txt) and txt[j] in " \t":
        j += 1
    if j < len(txt) and txt[j] == "(":
        return False                     # llamada:  sym(...)
    k = off - 1
    while k >= 0 and txt[k] in " \t":
        k -= 1
    if k >= 0 and txt[k] == ".":
        return False                     # miembro de otro objeto:  x.sym
    if k >= 0 and (txt[k].isalnum() or txt[k] in "_$"):
        e = k
        while e >= 0 and (txt[e].isalnum() or txt[e] in "_$"):
            e -= 1
        token = txt[e + 1:k + 1]
        if token and token not in KEYWORDS and not token[0].isdigit():
            return False                 # declaracion:  Tipo sym
    return True


def usos_fuera_de_catches(est, off, sym):
    """True si `sym` se usa como variable en el metodo, fuera de los catches."""
    txt = est[0]
    ini_m, fin_m = alcance_metodo(est, off)
    cuerpos, cabs = rangos_catch(est)
    patron = re.compile(r"(?<![\w$])%s(?![\w$])" % re.escape(sym))
    for mm in patron.finditer(txt, ini_m, fin_m):
        o = mm.start()
        if any(a < o < b for (a, b) in cuerpos):
            continue
        if any(a <= o < b for (a, b) in cabs):
            continue
        if es_uso_variable(txt, o, sym):
            return True
    return False


def cabecera_previa(txt, mask, pos):
    """Palabra de control cuyo cuerpo SIN llaves empieza en `pos`.

    Devuelve 'if'/'while'/... si la sentencia que empieza en `pos` es el
    cuerpo sin llaves de una cabecera de control; None en caso contrario.
    Cubre DOS formas, porque ambas guardan la glucosa:
      * cuerpo tras condicion entre parenteses:  `if (x) NAME = N2;`
      * cuerpo suelto tras `else` o `do`:        `else NAME = N2;`
    (el `case`/`label` NO guarda: es una etiqueta, no una condicion).
    """
    k = pos - 1
    while k >= 0 and txt[k] in " \t\r\n":
        k -= 1
    if k < 0:
        return None
    if txt[k] != ")":
        if not (txt[k].isalnum() or txt[k] in "_$"):
            return None                 # `;` `}` `{` `:` ... -> sin cabecera
        e = k
        while e >= 0 and (txt[e].isalnum() or txt[e] in "_$"):
            e -= 1
        token = txt[e + 1:k + 1]
        return token if token in ("else", "do") else None
    prof, j = 0, k
    while j >= 0:
        if mask[j]:
            if txt[j] == ")":
                prof += 1
            elif txt[j] == "(":
                prof -= 1
                if prof == 0:
                    break
        j -= 1
    if j < 0:
        return None
    e = j - 1
    while e >= 0 and txt[e] in " \t":
        e -= 1
    s = e
    while s >= 0 and (txt[s].isalnum() or txt[s] in "_$"):
        s -= 1
    return txt[s + 1:e + 1] or None


# ------------------------------------------------------------------ R3 ----
# El DEX tiene campos con nombres de UNA letra (obfuscacion), asi que un
# `location: class X` + `symbol: variable e` puede coincidir con un campo
# REAL de la clase. Renombrar ahi seria fatal si `e` fuera ese campo.
# Prueba de exclusucion: la escritura `sym = n2` solo puede ser un `iput`
# de ese campo si el tipo del catch (n2) es asignable al tipo del campo
# (el verificador Dalvik lo exige). Si NO lo es, `sym` no puede ser ese
# campo y el renombre es inocuo. Duda -> NO se toca.
PRIM_DEX = set("ZBSIJCFDV")
ACC_INTERFACE = 0x0200
# tipos de plataforma cuya jerarquia SIEMPRE acaba en Throwable/Object
PLATAFORMA_THROW = {
    "Ljava/lang/Throwable;", "Ljava/lang/Exception;",
    "Ljava/lang/RuntimeException;", "Ljava/lang/Error;",
    "Ljava/io/IOException;", "Ljava/lang/ExceptionInInitializerError;",
}
PLATAFORMA_OBJECT = "Ljava/lang/Object;"
_dex = {"listo": False, "ok": False, "meta": {}, "dotted": {}, "rev": {},
        "imports": {}}


def cargar_dex():
    if _dex["listo"]:
        return _dex["ok"]
    _dex["listo"] = True
    med = os.path.join(BASE, "mediciones")
    fi = os.path.join(med, "dex_indice.tsv")
    fm = os.path.join(med, "dex_miembros.tsv")
    if not (os.path.isfile(fi) and os.path.isfile(fm)):
        print("aviso: faltan mediciones/dex_indice.tsv o dex_miembros.tsv "
              "(regenerar con `python3 tools/dex_indice.py`). R3 no puede "
              "demostrar NADA sobre campos homonimos, asi que no se "
              "renombra ningun candidato.", file=sys.stderr)
        return False
    meta, dotted = {}, {}
    with open(fi, encoding="utf-8") as fh:
        for ln in fh:
            d, sup, fl, ifz = ln.rstrip("\n").split("\t")
            meta[d] = {"super": sup or None,
                       "flags": int(fl, 16) if fl else 0,
                       "ifaces": [x for x in ifz.split(",") if x],
                       "campos": {}}
            dotted.setdefault(d[1:-1].replace("/", "."), d)
            dotted.setdefault(d[1:-1].replace("/", ".").replace("$", "."), d)
    with open(fm, encoding="utf-8") as fh:
        for ln in fh:
            d, kind, nom, tipo = ln.rstrip("\n").split("\t")
            if d in meta and kind == "C":
                meta[d]["campos"].setdefault(nom, tipo)
    rev = {}
    fr = os.path.join(med, "mapa_renames.json")
    if os.path.isfile(fr):
        for k, nuevo in rp.cargar_mapa(fr)[0].items():
            pkg, viejo = k.split("::")
            rev[(pkg, nuevo)] = viejo
    _dex.update(meta=meta, dotted=dotted, rev=rev, ok=True)
    return True


def cierre(d, con_ifaces):
    """Superclases (e interfaces, si con_ifaces) alcanzables desde d.

    Solo se sigue dentro de lo que conocen los indices DEX: si la cadena
    se corta en un tipo de plataforma desconocido, el cierre queda corto
    y eso NO prueba nada (el llamante debe tratarlo como duda).
    """
    out, seen, cola = [], set(), [d]
    while cola:
        x = cola.pop(0)
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
        if x == PLATAFORMA_OBJECT:
            continue
        if x in PLATAFORMA_THROW:
            cola += ["Ljava/lang/Throwable;", PLATAFORMA_OBJECT]
            continue
        if x not in _dex["meta"]:
            continue                      # plataforma desconocida: me corto
        m = _dex["meta"][x]
        cola.append(m["super"])
        if con_ifaces:
            cola += m["ifaces"]
    return out


def descriptor_de(nombre, pkg, ruta):
    """Nombre de tipo de la fuente -> descriptor DEX (None si no resuelve)."""
    if not nombre:
        return None
    if ruta not in _dex["imports"]:
        _dex["imports"][ruta] = re.findall(
            r"^\s*import\s+([\w.$]+)\s*;", rp.leer(ruta), re.M)
    imps = _dex["imports"][ruta]
    if "." not in nombre:
        cands = [f"{pkg}.{nombre}"]
        cands += [i for i in imps if i.rsplit(".", 1)[-1] == nombre]
        v = _dex["rev"].get((pkg, nombre))
        if v:
            cands += [f"{pkg}.{v}", v]
        cands += [nombre, f"java.lang.{nombre}"]
    else:
        cands = [nombre] + [i for i in imps
                            if i == nombre or i.endswith("." + nombre)]
    for c in cands:
        if c in _dex["dotted"]:
            return _dex["dotted"][c]
    for c in cands:
        if c.startswith(("java.", "javax.")):
            return "L" + c.replace(".", "/") + ";"
    return None


# declaraciones de un fichero (misma idea que auditar_familias.PAT_DECL)
PAT_DECL = re.compile(r"\b(?:class|interface|enum|record)\s+(\w+)")
_dex["nombres"] = {}


def _nombres_declarados(ruta):
    if ruta not in _dex["nombres"]:
        _dex["nombres"][ruta] = set(PAT_DECL.findall(rp.leer(ruta)))
    return _dex["nombres"][ruta]


def _desc_src(loc, pkg, ruta):
    """Descriptor como lo construye auditar_familias.desc_src (renombre inv.)"""
    top_new = os.path.basename(ruta)[:-5]
    old = _dex["rev"].get((pkg, top_new), top_new)
    segs = loc.split(".")
    resto = segs[1:] if segs[0] in (top_new, old) else segs
    cuerpo = (pkg.replace(".", "/") + "/" if pkg else "") + old + "".join(
        f"${s}" for s in resto)
    return "L" + cuerpo + ";"


def _descriptor_de_clase(loc, pkg, ruta):
    """`location:` de javac -> descriptor DEX (o _NO_DEX, o None si no resuelve).

    Misma precedencia que auditar_familias.resolver_loc: primero las
    declaraciones del PROPIO fichero (que sombrian a todo lo demas), luego
    el DEX por paquete, luego el paquete explicito y las particiones.
    """
    if not loc:
        return None
    segs = loc.split(".")
    nombres = _nombres_declarados(ruta)
    if segs[0] in nombres:                      # clase/anaidada del fichero
        return _desc_src(loc, pkg, ruta)
    rel = f"{pkg}.{loc}" if pkg else None
    for cand in (rel, loc):
        if cand and cand in _dex["dotted"]:
            return _dex["dotted"][cand]
    viejo = _dex["rev"].get((pkg, loc))
    for cand in ((f"{pkg}.{viejo}", viejo) if viejo else ()):
        if cand in _dex["dotted"]:
            return _dex["dotted"][cand]
    return None


def campo_dex_en_conflicto(f, l, sym, n2, tipo_n2, loc):
    """True si NO se puede demostrar que `sym` NO es el campo homonimo.

    Se renombra solo con PRUEBA de incompatibilidad de tipos: la sentencia
    `sym = n2` no podria ser un `iput` de ese campo si el tipo del catch no
    es asignable al tipo del campo (el verificador Dalvik lo exige). Cualquier
    hueco -> True (no se toca).

    Demostraciones que permiten renombrar:
      * sin `location`, o la clase no declara ese campo  -> no hay campo
      * campo PRIMITIVO                                  -> no admite objetos
      * campo CLASE cuya cadena llega a Object sin
        familia Throwable                                -> no puede ser
        ancestro de un Throwable
      * campo CLASE con cadena y T con cadena completas
        y F no aparece en la de T                        -> T no es subtipo
      * campo INTERFAZ definido en el DEX y F no esta en
        el cierre de interfaces de T (una clase de
        plataforma no puede implementar una interfaz de
        la APP, asi que el cierre DEX basta)
    """
    if not loc:
        # javac no llego a decir la clase: no hay por donde comprobar la
        # homonimia en el DEX -> misma regla que todo lo demas: sin
        # evidencia, no se toca.
        _dex["motivo"] = "sin_location"
        return True
    if not cargar_dex():
        # sin indices no hay PRUEBA posible -> no se toca (misma regla que
        # `sin_location`); el aviso ya lo ha impuesto cargar_dex()
        _dex["motivo"] = "sin_indices_DEX"
        return True
    # las rutas del log son absolutas; el paquete sale de la relativa a SRC
    ruta = f if os.path.isabs(f) else os.path.join(SRC, f)
    rel = ruta[len(SRC) + 1:] if ruta.startswith(SRC) else f
    pkg = os.path.dirname(rel).replace("/", ".")
    desc = _descriptor_de_clase(loc, pkg, ruta)
    if desc is None:
        _dex["motivo"] = "location_no_resuelve"
        return True                      # `location` no resuelve: duda
    if desc not in _dex["meta"]:
        _dex["motivo"] = "clase_no_en_DEX"
        return True                      # el nombre no cuadra con el DEX: duda
    campo = None
    for a in cierre(desc, False):
        if sym in _dex["meta"].get(a, {}).get("campos", {}):
            campo = _dex["meta"][a]["campos"][sym]
            break
    if campo is None:
        _dex["motivo"] = "campo_no_existe"
        return False                     # demostrado: la clase no lo tiene
    if campo in PRIM_DEX:
        _dex["motivo"] = "campo_primitivo"
        return False                     # demostrado: un int no admite objetos
    if campo == PLATAFORMA_OBJECT:
        _dex["motivo"] = "campo_Object"
        return True                      # T SI cabe: ambiguo
    if campo not in _dex["meta"]:
        _dex["motivo"] = "campo_plataforma"
        return True                      # tipo de plataforma: no esta el indice

    es_ifaz = (_dex["meta"][campo]["flags"] & ACC_INTERFACE) != 0
    tdesc = descriptor_de(tipo_n2, pkg, ruta)
    if es_ifaz:
        if tdesc is None:
            _dex["motivo"] = "interfaz_T_sin_resolver"
            return True                  # duda sobre T
        amb = campo in cierre(tdesc, True)
        _dex["motivo"] = ("interfaz_en_cierre_T" if amb
                          else "interfaz_fuera_de_T")
        return amb

    fc = cierre(campo, False)
    if (PLATAFORMA_OBJECT in fc) and not (set(fc) & PLATAFORMA_THROW):
        _dex["motivo"] = "campo_clase_raiz"
        return False                     # F es clase raiz: no de Throwable
    if tdesc is None:
        _dex["motivo"] = "T_sin_resolver"
        return True                      # duda sobre T
    tc = cierre(tdesc, False)
    if PLATAFORMA_OBJECT not in tc:
        _dex["motivo"] = "T_cadena_cortada"
        return True                      # cadena de T cortada: duda
    amb = campo in tc
    _dex["motivo"] = ("T_es_subtipo_del_campo" if amb
                      else "T_no_es_subtipo")
    return amb                           # True -> T si es subtipo de F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    bloques = rp.parsear_bloques(args.log)

    # keyword (class/variable/method) por (fichero, linea) — como en
    # auditar_familias.py: PAT_SYM captura el nombre, aqui hace falta la keyword
    kw, cur = {}, None
    for ln in open(args.log, encoding="utf-8", errors="replace"):
        m = rp.PAT_ARCH.match(ln)
        if m:
            cur = (m.group(1), int(m.group(2)))
        elif ln.startswith("  symbol:") and cur:
            ms = PAT_KW.search(ln)
            if ms:
                kw.setdefault(cur, ms.group(1))

    stats = collections.Counter()
    omitidos = []
    cambios = collections.defaultdict(list)   # ruta -> [(linea, col, viejo, nuevo, nota)]
    borrar = collections.defaultdict(set)     # ruta -> {linea} (glucosa autoasignada)

    for b in bloques:
        f, l, msg, sym, car = b["f"], b["l"], b["msg"], b["sym"], b["car"]
        loc = b.get("loc")
        if msg != "cannot find symbol" or not sym:
            continue
        if kw.get((f, l)) != "variable":
            continue
        stats["candidatos"] += 1

        est = estructura(f)
        txt, mask, linos, _bloques = est
        if l - 1 >= len(linos):
            omitidos.append(("linea_fuera_de_rango", f, l, sym, ""))
            stats["omitido_linea"] += 1
            continue
        off_linea = linos[l - 1]
        fin_linea = txt.find("\n", off_linea)
        fin_linea = len(txt) if fin_linea < 0 else fin_linea
        linea = txt[off_linea:fin_linea]

        # --- localizar la ocurrencia exacta que marco el caret de javac
        col = car  # 1-based
        off = off_linea + col - 1 if col else -1
        if not (col and palabra_en(txt, off, sym)):
            occ = [m.start() for m in re.finditer(
                r"(?<![\w$])%s(?![\w$])" % re.escape(sym), linea)]
            if len(occ) == 1:
                off = off_linea + occ[0]
            else:
                stats["omitido_caret"] += 1
                omitidos.append(("caret_ambiguo", f, l, sym,
                                 linea.strip()[:70]))
                continue

        # --- ambito: primer catch (de dentro afuera) que contiene al sitio
        catch_int = None
        for (ini, fin, cab) in cabeceras(est, off):
            m = PAT_CATCH.search(cab)
            if m:
                catch_int = (ini, fin, m.group(2), m.group(1).strip())
                break
        if catch_int is None:
            stats["B_fuera_de_catch"] += 1
            omitidos.append(("B_fuera_de_catch", f, l, sym, linea.strip()[:70]))
            continue
        ini_c, fin_c, n2, tipo_n2 = catch_int
        if n2 == sym:
            stats["C_catch_homonimo"] += 1
            omitidos.append(("C_catch_homonimo", f, l, sym, linea.strip()[:70]))
            continue

        # --- glucosa  `sym = n2 ;`  dentro del cuerpo del catch (en codigo)
        cuerpo = txt[ini_c:fin_c]
        cmask = mask[ini_c:fin_c]
        plano = "".join(c if m else " " for c, m in zip(cuerpo, cmask))
        gluches = list(re.finditer(
            r"\b%s\s*=\s*%s\s*;" % (re.escape(sym), re.escape(n2)), plano))
        if not gluches:
            stats["C_sin_glucosa"] += 1
            omitidos.append(("C_sin_glucosa", f, l, sym, linea.strip()[:70]))
            continue

        # --- R1: TODAS las gluches son hijo directo del cuerpo del catch y
        #     no son cuerpo de una cabecera de control (glucosa guardada)
        anidada = guardada = False
        for g in gluches:
            g_off = ini_c + g.start()
            seg = txt[ini_c + 1:g_off]
            segm = mask[ini_c + 1:g_off]
            prof = (sum(1 for c, m in zip(seg, segm) if m and c == "{") -
                    sum(1 for c, m in zip(seg, segm) if m and c == "}"))
            if prof != 0:
                anidada = True
            cab_prev = cabecera_previa(txt, mask, g_off)
            if cab_prev in GUARDADAS:
                guardada = True
        if anidada:
            stats["R1_glucosa_anidada"] += 1
            omitidos.append(("R1_glucosa_anidada", f, l, sym,
                             linea.strip()[:70]))
            continue
        if guardada:
            stats["R1_glucosa_guardada"] += 1
            omitidos.append(("R1_glucosa_guardada", f, l, sym,
                             linea.strip()[:70]))
            continue

        # --- R2: `sym` no se usa como variable en el metodo fuera de catches
        if usos_fuera_de_catches(est, off, sym):
            stats["R2_sym_fuera_de_catch"] += 1
            omitidos.append(("R2_sym_fuera_de_catch", f, l, sym,
                             linea.strip()[:70]))
            continue

        # --- R3: `sym` podria ser un campo REAL homonimo del DEX
        if campo_dex_en_conflicto(f, l, sym, n2, tipo_n2, loc):
            stats["R3_campo_DEX_ambiguo"] += 1
            omitidos.append(("R3_campo_DEX_ambiguo", f, l, sym,
                             "[%s] %s" % (_dex.get("motivo", "?"),
                                          linea.strip()[:60])))
            continue

        cambios[f].append((l, off, sym, n2, _dex.get("motivo", "A_renombrar")))
        stats["A_renombrar"] += 1

        # --- la linea ES la glucosa `sym = n2;` -> tras el renombrado quedaria
        #     `n2 = n2;` (autoasignacion sin efecto): se marca para borrar.
        #     Se comprueba sobre el ORIGINAL con la mascara (la mascara y la
        #     linea tienen la misma longitud; el texto ya renombrado NO, por
        #     eso no se puede comprobar despues del replace).
        plano_linea = "".join(c if mm else " "
                              for c, mm in zip(linea, mask[off_linea:fin_linea]))
        if re.match(r"^\s*%s\s*=\s*%s\s*;\s*$"
                    % (re.escape(sym), re.escape(n2)), plano_linea):
            borrar[f].add(l)

    print("resumen:")
    for k, v in stats.most_common():
        print(f"  {v:5d}  {k}")
    n_oc = len({(f, it[1]) for f, v in cambios.items() for it in v})
    print(f"cambios: {len(cambios)} ficheros, "
          f"{n_oc} ocurrencias unicas, "
          f"{sum(len(v) for v in borrar.values())} lineas de glucosa a borrar")

    if omitidos:
        por_motivo = collections.Counter(o[0] for o in omitidos)
        print("\nomitidos por motivo:")
        for k, v in por_motivo.most_common():
            print(f"  {v:5d}  {k}")
        print("muestra:")
        for o in omitidos[:15]:
            rel = os.path.relpath(o[1], SRC)
            print(f"    {o[0]}: {rel}:{o[2]} sym={o[3]} :: {o[4]}")

    if args.json:
        json.dump({"stats": dict(stats),
                   "omitidos": [{"motivo": m, "f": os.path.relpath(f, SRC),
                                 "l": l, "sym": s, "cod": c}
                                for (m, f, l, s, c) in omitidos],
                   "cambios": [{"f": os.path.relpath(f, SRC), "l": l,
                                "sym": sv, "n2": nv, "motivo": mot}
                               for f, items in sorted(cambios.items())
                               for (l, _off, sv, nv, mot) in
                               sorted(items, key=lambda x: x[0])],
                   "borrar_glucosa": {os.path.relpath(f, SRC): sorted(ls)
                                      for f, ls in sorted(borrar.items())},
                   "ficheros": sorted(os.path.relpath(f, SRC)
                                      for f in cambios)},
                  open(args.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"JSON -> {args.json}")

    if not args.aplicar:
        print("\n[DRY-RUN] nada modificado. Repite con --aplicar.")
        return

    # ---- aplicar (de abajo arriba, de derecha a izquierda)
    for f, items in cambios.items():
        txt = rp.leer(f)
        bal0 = txt.count("{") - txt.count("}")
        vistos = set()
        for (l, off, viejo, nuevo, _nota) in sorted(
                items, key=lambda x: (-x[1],)):
            if off in vistos:
                continue          # mismo error repetido en el log
            vistos.add(off)
            assert txt[off:off + len(viejo)] == viejo, (f, l, viejo)
            txt = txt[:off] + nuevo + txt[off + len(viejo):]
        lineas = txt.split("\n")
        for l in sorted(borrar.get(f, ()), reverse=True):
            del lineas[l - 1]
        nuevo_txt = "\n".join(lineas)
        bal1 = nuevo_txt.count("{") - nuevo_txt.count("}")
        if bal0 != bal1:
            print(f"  ABORTO {os.path.relpath(f, SRC)}: balance "
                  f"{bal0} -> {bal1}", file=sys.stderr)
            sys.exit(3)
        rp.escribir(f, nuevo_txt)
    print(f"[APlicado] {len(cambios)} ficheros")


if __name__ == "__main__":
    main()

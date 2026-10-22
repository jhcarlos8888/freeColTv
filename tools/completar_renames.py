#!/usr/bin/env python3
"""Segundo pase IDEMPOTENTE del renombrado de clases tapadoras.

Completa lo que el primer pase dejo a medias por dos motivos medidos:

  1) La declaracion top-level 'public abstract /* synthetic */ class t' lleva un
     comentario entre modificadores y la palabra class: el regex del primer pase
     no la veia, asi que 25 clases no se renombraron.
  2) El detector de tipos anidados tenia el mismo problema, por lo que pudo
     omitir anidados en CHOQUE (riesgo de rotura silenciosa) que hay que
     pre-reparar.

Uso:  python3 tools/completar_renames.py [--aplicar]
"""
import argparse
import json
import os
import re
import shutil
import importlib.util

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("rt", os.path.join(BASE, "tools", "renombrar_clases_tapadoras.py"))
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

SRC = rt.SRC
MAPA = os.path.join(BASE, "mediciones", "mapa_renames.json")


def ficheros_clase(pkg, C):
    d = os.path.join(SRC, pkg.replace(".", "/"))
    viejo = os.path.join(d, C + ".java")
    return d, viejo


def anidados_de(ruta):
    return set(rt.PAT_ANIDADO.findall(rt.sin_comentarios(rt.leer(ruta))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    mapa = json.load(open(MAPA))
    idx_base = rt.errores_baseline(os.path.join(BASE, "mediciones", "baseline_paridad.log"))
    hechos = 0
    pre_nuevas = 0
    ctors = 0
    pendientes = []
    choques_nuevos = []

    for clave, nuevo in sorted(mapa.items()):
        pkg, C = clave.split("::")
        d, viejo = ficheros_clase(pkg, C)
        destino = os.path.join(d, nuevo + ".java")
        if os.path.isfile(viejo):
            actual = viejo
        elif os.path.isfile(destino):
            actual = destino
        else:
            pendientes.append(clave)
            continue

        # 1) anidados con el detector corregido y choque con el paquete raiz
        anid = anidados_de(actual)
        raiz_tipos = rt.tipos_paquete(C)
        choque = anid & raiz_tipos
        if choque:
            choques_nuevos.append((clave, sorted(choque)))

        # 2) pre-reparar C.N -> nuevo.N donde hoy enlaza a la CLASE
        for f in sorted(os.listdir(d)) if choque else []:
            if not f.endswith(".java"):
                continue
            ruta = os.path.join(d, f)
            txt = rt.leer(ruta)
            if rt.declara_variable(txt, C):
                continue
            pat_imp = re.compile(r"^import\s+([\w.]+)\." + re.escape(C) + r"\s*;", re.M)
            if any(q != pkg for q in pat_imp.findall(txt)):
                continue
            mar = rt.mapa_codigo(txt)
            # SOLO choque: N anidado de C que TAMBIEN existe en el paquete raiz C.
            # Son los unicos casos de rotura SILENCIOSA; el resto, si rompen, los
            # repara el bucle guiado por javac (y asi no reescribimos de mas).
            pat = re.compile(
                r"(?<![\w.$])(" + re.escape(C) + r")\s*\.\s*("
                + "|".join(map(re.escape, sorted(choque))) + r")\b"
            )
            cambios = []
            for m in pat.finditer(txt):
                if not mar[m.start(1)]:
                    continue
                linea = txt.count("\n", 0, m.start()) + 1
                ini = txt.rfind("\n", 0, m.start(2)) + 1
                col = m.start(2) - ini + 1
                if col in idx_base.get((ruta, str(linea)), ()):
                    continue
                cambios.append((m.start(1), m.end(1), m.group(2)))
            if cambios:
                pre_nuevas += len(cambios)
                if args.aplicar:
                    for a, b, _n in sorted(cambios, reverse=True):
                        txt = txt[:a] + nuevo + txt[b:]
                    rt.escribir(ruta, txt)

        # 3) constructores: en Java el constructor se llama como la clase, asi
        #    que al renombrarla hay que renombrarlos TAMBIEN (si no, javac
        #    aborta en fase de parseo con 'invalid method declaration').
        #    Solo declaraciones: 'private l1() {' con prefijo de modificadores.
        if os.path.isfile(destino):
            txt = rt.leer(destino)
            plano = rt.sin_comentarios(txt)
            cambios = rt.posiciones_constructores(plano, C)
            if cambios:
                for a, b in sorted(cambios, reverse=True):
                    txt = txt[:a] + nuevo + txt[b:]
                rt.escribir(destino, txt)
                ctors += len(cambios)

        # 4) declaracion + fichero, si aun no se hizo
        if os.path.isfile(viejo):
            if args.aplicar:
                txt = rt.leer(viejo)
                plano = rt.sin_comentarios(txt)
                m = rt.PAT_TOP.search(plano)
                if m and plano[m.start(1):m.end(1)] == C:
                    rt.escribir(viejo, txt[: m.start(1)] + nuevo + txt[m.end(1):])
                    shutil.move(viejo, destino)
                    hechos += 1
                else:
                    pendientes.append(clave)
            else:
                hechos += 1

    print(f"clases con choque de anidados (riesgo silencioso): {len(choques_nuevos)}")
    for k, ch in choques_nuevos[:30]:
        print(f"    {k}  {ch}")
    print(f"\nrenombrados pendientes que completaria: {hechos}")
    print(f"constructores renombrados: {ctors}")
    print(f"pre-reparaciones nuevas: {pre_nuevas}")
    print(f"sin localizar aun: {len(pendientes)} {pendientes}")
    if not args.aplicar:
        print("\n[DRY-RUN] nada modificado.")


if __name__ == "__main__":
    main()

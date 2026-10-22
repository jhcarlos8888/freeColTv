#!/usr/bin/env python3
"""Analiza un log de errores de javac/Gradle y clasifica por familias.

Familias relevantes para la reconstruccion:
  * R              : 'package R does not exist' / referencias a RooSeveLt.InT
  * SOMBRA         : 'cannot find symbol' cuyo simbolo existe como .java en el
                     PAQUETE RAIZ y en el paquete del archivo hay una clase con
                     el mismo nombre que el paquete raiz (clase-tapadora).
  * ANIDADO-DEX    : simbolo inexistente en fuente (tipo anidado perdido por jadx)
  * resto          : otras familias (viene intacto del decompilador)

Uso:
  tools/analizar_errores.py <log> [--json salida.json] [--detallar paquete]
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
PAT_SYM = re.compile(r"symbol:\s+(?:class|variable|method)\s+([\w]+)")
PAT_LOC = re.compile(r"location:\s+(?:class|interface|enum)\s+([\w.$]+)")
PAT_RESUMEN = re.compile(r"^(\d+) errors?$")


def raices():
    return {d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d))}


def analizar(log_path):
    raiz = raices()
    lineas = open(log_path, encoding="utf-8", errors="replace").read().split("\n")

    familias = collections.Counter()
    sombra_clases = collections.Counter()   # (pkg, clase) -> errores
    sombra_sin_tapadora = 0
    resumen_javac = None
    total = 0

    i = 0
    while i < len(lineas):
        mr = PAT_RESUMEN.match(lineas[i])
        if mr:
            resumen_javac = int(mr.group(1))
        m = PAT_ARCH.match(lineas[i])
        if m:
            total += 1
            msg = m.group(3)
            if "package R does not exist" in msg or "RooSeveLt.InT" in msg:
                familias["R"] += 1
            elif msg.startswith("package io.reactivex"):
                familias["rx"] += 1
            elif msg.startswith("cannot find symbol"):
                familias["cannot_find_symbol"] += 1
                if i + 4 < len(lineas):
                    ms = PAT_SYM.search(lineas[i + 3])
                    ml = PAT_LOC.search(lineas[i + 4])
                    if ms and ml:
                        loc = ml.group(1).split(".")[-1]
                        sym = ms.group(1)
                        if loc in raiz and os.path.isfile(os.path.join(SRC, loc, sym + ".java")):
                            rel = m.group(1).replace(SRC + os.sep, "").replace(SRC + "/", "")
                            pkg = os.path.dirname(rel).replace("/", ".")
                            if pkg and os.path.isfile(
                                os.path.join(SRC, pkg.replace(".", "/"), loc + ".java")
                            ):
                                familias["SOMBRA"] += 1
                                sombra_clases[(pkg, loc)] += 1
                            else:
                                familias["SOMBRA_sin_tapadora"] += 1
                                sombra_sin_tapadora += 1
                        else:
                            familias["ANIDADO_DEX"] += 1
            elif "method does not override" in msg:
                familias["override"] += 1
            elif msg.startswith("incompatible types") or msg.startswith("incomparable"):
                familias["tipos"] += 1
            elif msg.startswith("cannot infer type"):
                familias["inferencia"] += 1
            elif "cannot be applied" in msg:
                familias["sobrecarga"] += 1
            else:
                familias["otro"] += 1
        i += 1

    return {
        "log": log_path,
        "errores_contados": total,
        "resumen_javac": resumen_javac,
        "familias": dict(familias.most_common()),
        "sombra_clases_distintas": len(sombra_clases),
        "sombra_por_clase": [
            {"clase": f"{p}::{c}", "errores": n}
            for (p, c), n in sombra_clases.most_common()
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--json", help="vuelca el resultado a JSON")
    ap.add_argument("--detallar", help="lista los errores de sombra de un paquete")
    args = ap.parse_args()

    if not os.path.isfile(args.log):
        sys.exit(f"no existe el log: {args.log}")

    r = analizar(args.log)
    print(f"log              : {r['log']}")
    print(f"errores contados : {r['errores_contados']}")
    print(f"resumen javac    : {r['resumen_javac']}")
    print("familias:")
    for k, v in r["familias"].items():
        print(f"   {v:7d}  {k}")
    print(f"sombra: {r['sombra_clases_distintas']} clases tapadoras distintas")

    if args.detallar:
        sel = [x for x in r["sombra_por_clase"] if x["clase"].startswith(args.detallar + "::")]
        print(f"\ntapadoras de {args.detallar}: {len(sel)}")
        for x in sel:
            print(f"   {x['clase']}  {x['errores']}")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)) or ".", exist_ok=True)
        json.dump(r, open(args.json, "w"), indent=2, ensure_ascii=False)
        print(f"\nJSON -> {args.json}")


if __name__ == "__main__":
    main()

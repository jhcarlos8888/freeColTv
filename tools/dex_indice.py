#!/usr/bin/env python3
"""Índice DEX con miembros (PLAN_P3 paso 1).

Lee la salida de `dexdump` (sin -d: ya incluye campos y miembros, sin volcar
bytecode) en streaming y escribe:

  mediciones/dex_indice.tsv    descriptor<TAB>super<TAB>flags<TAB>interfaces
  mediciones/dex_miembros.tsv  descriptor<TAB>C|M<TAB>nombre<TAB>tipo

C = campo (tipo = descriptor del campo), M = método (tipo = proto completo,
p.ej. `(Ll/b;)V`).

Ground truth de la APK: salida de la herramienta oficial del SDK
(build-tools/34.0.0/dexdump; NO está en PATH).

Formato real verificado de dexdump (035):

  Class #0            -
    Class descriptor  : 'La8/a;'        <- nivel clase (2 espacios)
    Access flags      : 0x0001 (PUBLIC)
    Superclass        : 'Ljava/lang/RuntimeException;'
    Interfaces        -
      #0              : 'L...;'         <- entradas de interfaces (4)
    Static fields     -
    Instance fields   -
      #0              : (in La8/a;)     <- miembro (4)
        name          : 'a'             <- miembro (6)
        type          : 'I'
        access        : 0x0002 (PRIVATE)

Uso:  python3 tools/dex_indice.py [fichero.dex ...]
      (por defecto todos los *.dex de XuperDorado_project/apktool_decoded)
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "XuperDorado_project")
DEXDIR = os.path.join(SRC, "apktool_decoded")
MED = os.path.join(BASE, "mediciones")
DEXDUMP = os.path.expanduser("~/Android/Sdk/build-tools/34.0.0/dexdump")

PAT_CLASE = re.compile(r"^Class #\d+")
PAT_DESC = re.compile(r"^  Class descriptor\s*:\s*'(.+?)'")
PAT_FLAGS = re.compile(r"^  Access flags\s*:\s*(0x[0-9a-fA-F]+)")
PAT_SUPER = re.compile(r"^  Superclass\s*:\s*'(.+?)'")
PAT_IFACE_HDR = re.compile(r"^  Interfaces\b")
PAT_IFACE = re.compile(r"^    #\d+\s*:\s*'(.+?)'")
PAT_SECC = re.compile(
    r"^  (Static fields|Instance fields|Direct methods|Virtual methods)\s*-\s*$")
PAT_MIEMBRO = re.compile(r"^    #\d+\s*:\s*\(in ")
PAT_NAME = re.compile(r"^      name\s*:\s*'(.+?)'")
PAT_TYPE = re.compile(r"^      type\s*:\s*'(.+?)'")


def dex_files(argv):
    if len(argv) > 1:
        return argv[1:]
    return sorted(
        os.path.join(DEXDIR, f) for f in os.listdir(DEXDIR)
        if f.endswith(".dex"))


def main():
    dexes = dex_files(sys.argv)
    if not dexes:
        print("ERROR: no hay *.dex en", DEXDIR, file=sys.stderr)
        return 2
    if not os.path.isfile(DEXDUMP):
        print("ERROR: no existe", DEXDUMP, file=sys.stderr)
        return 2

    os.makedirs(MED, exist_ok=True)
    t0 = time.time()
    n_clases = n_campos = n_metodos = n_ifaces = 0
    desc = super_ = flags = None
    ifaces = []
    seccion = None      # None | 'C' | 'M'
    pendiente = None    # nombre del miembro pendiente de su 'type'
    iface_mode = False

    def cerrar(fi):
        nonlocal n_clases, desc, super_, flags, ifaces, seccion, pendiente
        if desc is not None:
            fi.write(f"{desc}\t{super_ or ''}\t{flags or ''}\t"
                     f"{','.join(ifaces)}\n")
            n_clases += 1
        desc, super_, flags, ifaces = None, None, None, []
        seccion, pendiente, iface_mode = None, None, False

    # iface_mode se resetea fuera de la función; se gestiona con lista porque
    # la sentencia nonlocal cubriría sólo variables actuales del alcance
    estado = {"iface_mode": False}

    with open(os.path.join(MED, "dex_indice.tsv"), "w",
              encoding="utf-8") as fi, \
         open(os.path.join(MED, "dex_miembros.tsv"), "w",
              encoding="utf-8") as fm:
        for dex in dexes:
            proc = subprocess.Popen(
                [DEXDUMP, dex],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace")
            for ln in proc.stdout:
                ln = ln.rstrip("\n")
                if PAT_CLASE.match(ln):
                    cerrar(fi)
                    estado["iface_mode"] = False
                    continue
                m = PAT_DESC.match(ln)
                if m:
                    desc = m.group(1)
                    continue
                m = PAT_FLAGS.match(ln)
                if m:
                    flags = m.group(1)
                    continue
                m = PAT_SUPER.match(ln)
                if m:
                    super_ = m.group(1)
                    continue
                if PAT_IFACE_HDR.match(ln):
                    estado["iface_mode"] = True
                    seccion = None
                    pendiente = None
                    continue
                m = PAT_SECC.match(ln)
                if m:
                    estado["iface_mode"] = False
                    pendiente = None
                    seccion = "M" if m.group(1).endswith("methods") else "C"
                    continue
                if estado["iface_mode"]:
                    mi = PAT_IFACE.match(ln)
                    if mi:
                        ifaces.append(mi.group(1))
                        n_ifaces += 1
                        continue
                    # cualquier otra línea a 2 espacios cierra interfaces
                    if re.match(r"^  \S", ln):
                        estado["iface_mode"] = False
                    elif seccion is None:
                        continue
                if seccion is None:
                    continue
                if PAT_MIEMBRO.match(ln):
                    pendiente = None
                    continue
                mn = PAT_NAME.match(ln)
                if mn:
                    pendiente = mn.group(1)
                    continue
                mt = PAT_TYPE.match(ln)
                if mt and pendiente is not None:
                    if seccion == "M":
                        fm.write(f"{desc}\tM\t{pendiente}\t{mt.group(1)}\n")
                        n_metodos += 1
                    else:
                        fm.write(f"{desc}\tC\t{pendiente}\t{mt.group(1)}\n")
                        n_campos += 1
                    pendiente = None
                    continue
            proc.stdout.close()
            if proc.wait() != 0:
                print(f"ERROR: dexdump falló en {dex}", file=sys.stderr)
                return 1
        cerrar(fi)

    dt = time.time() - t0
    resumen = {
        "clases": n_clases,
        "interfaces_declaradas": n_ifaces,
        "campos": n_campos,
        "metodos": n_metodos,
        "dex": [os.path.basename(d) for d in dexes],
        "segundos": round(dt, 1),
    }
    with open(os.path.join(MED, "dex_indice_resumen.json"), "w",
              encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    print(f"clases={n_clases} ifaces={n_ifaces} campos={n_campos} "
          f"metodos={n_metodos} ({dt:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

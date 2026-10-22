#!/usr/bin/env python3
"""P4-9b: forwarder CompatStatics para static imports bloqueados.

Tras importar_paquetes_sombreados.py, 12 sitios quedaron con error
visible: los `import static e.b.d` / `e.b.c` / `f.c.l` / `w.g.b` /
`w.g.g` insertados quedan BLOQUEADOS por miembros homonimos de
instancia (JLS 15.12.1: si la clase tiene metodos con ese nombre, los
static imports homonimos se ignoran y si ninguno aplica -> error) y,
para `w.g`, por la clase `g` del MISMO paquete recyclerview.widget
(preferida al simple name frente al import).

Solucion: clase publica `androidx.appcompat.widget.CompatStatics` con
metodos estaticos que DELEGAN en el FQN correcto. Los call sites
 fallidos pasan a `CompatStatics.x(...)` (sin sombreado posible: simple
name nuevo). Se eliminan los static imports inutiles.

Metodos (firmas verificadas contra el fuente):
  e.b.c  -> ColorStateList c(Context, int)
  e.b.d  -> Drawable       d(Context, int)
  f.c.l  -> Drawable       l(Context, Resources, XmlPullParser,
                             AttributeSet, Resources.Theme) throws ...
           (f.c.c extends f.f__ extends f.d extends Drawable)
  w.g.b  -> void           b(boolean, Object)
  w.g.g  -> Object         g(Object)

Uso: python3 tools/aplicar_compat_statics.py [--aplicar]
"""
import argparse
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = os.path.join(BASE, "XuperDorado_project", "app", "src", "main", "java")

FWD = "androidx/appcompat/widget/CompatStatics.java"

FORWARDER = '''package androidx.appcompat.widget;

import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.Resources;
import android.graphics.drawable.Drawable;
import android.util.AttributeSet;
import java.io.IOException;
import org.xmlpull.v1.XmlPullParser;
import org.xmlpull.v1.XmlPullParserException;

public class CompatStatics {
    private CompatStatics() {
    }

    public static ColorStateList c(Context context, int i10) {
        return e.b.c(context, i10);
    }

    public static Drawable d(Context context, int i10) {
        return e.b.d(context, i10);
    }

    public static Drawable l(Context context, Resources resources, XmlPullParser xmlPullParser, AttributeSet attributeSet, Resources.Theme theme) throws XmlPullParserException, IOException {
        // f.c.l() declara retorno 'c', que en su propio cuerpo resuelve a f.d.c
        // (miembro heredado de f.d, no es Drawable); cast via Object.
        return (Drawable) (Object) f.c.l(context, resources, xmlPullParser, attributeSet, theme);
    }

    public static void b(boolean z10, Object obj) {
        w.g.b(z10, obj);
    }

    public static Object g(Object obj) {
        return w.g.g(obj);
    }
}
'''

# (fichero relativo, substring exacto a buscar, sustitucion, veces)
CALLS = [
    ("androidx/appcompat/widget/Toolbar.java",
     "setCollapseIcon(d(getContext(), i10));",
     "setCollapseIcon(CompatStatics.d(getContext(), i10));", 1),
    ("androidx/appcompat/widget/Toolbar.java",
     "setLogo(d(getContext(), i10));",
     "setLogo(CompatStatics.d(getContext(), i10));", 1),
    ("androidx/appcompat/widget/Toolbar.java",
     "setNavigationIcon(d(getContext(), i10));",
     "setNavigationIcon(CompatStatics.d(getContext(), i10));", 1),
    ("com/google/android/material/textfield/TextInputLayout.java",
     "setEndIconDrawable(i10 != 0 ? d(getContext(), i10) : null);",
     "setEndIconDrawable(i10 != 0 ? CompatStatics.d(getContext(), i10) : null);", 1),
    ("com/google/android/material/textfield/TextInputLayout.java",
     "setErrorIconDrawable(i10 != 0 ? d(getContext(), i10) : null);",
     "setErrorIconDrawable(i10 != 0 ? CompatStatics.d(getContext(), i10) : null);", 1),
    ("com/google/android/material/textfield/TextInputLayout.java",
     "setPasswordVisibilityToggleDrawable(i10 != 0 ? d(getContext(), i10) : null);",
     "setPasswordVisibilityToggleDrawable(i10 != 0 ? CompatStatics.d(getContext(), i10) : null);", 1),
    ("com/google/android/material/textfield/TextInputLayout.java",
     "setStartIconDrawable(i10 != 0 ? d(getContext(), i10) : null);",
     "setStartIconDrawable(i10 != 0 ? CompatStatics.d(getContext(), i10) : null);", 1),
    ("com/google/android/material/textfield/TextInputLayout.java",
     "ColorStateList colorStateListC = c(context2, R.color.mtrl_filled_background_color);",
     "ColorStateList colorStateListC = CompatStatics.c(context2, R.color.mtrl_filled_background_color);", 1),
    ("androidx/appcompat/app/f.java",
     "setBackgroundDrawable(d(getContext(), i10));",
     "setBackgroundDrawable(CompatStatics.d(getContext(), i10));", 1),
    ("androidx/appcompat/widget/c2.java",
     "return l(context, context.getResources(), xmlPullParser, attributeSet, theme);",
     "return CompatStatics.l(context, context.getResources(), xmlPullParser, attributeSet, theme);", 1),
    ("androidx/recyclerview/widget/RecyclerView.java",
     "g.b(xVar != null, \"'listener' arg cannot be null.\");",
     "CompatStatics.b(xVar != null, \"'listener' arg cannot be null.\");", 1),
    ("androidx/recyclerview/widget/RecyclerView.java",
     "g.g(lVar);",
     "CompatStatics.g(lVar);", 1),
]

QUITAR = [
    "import static e.b.d;",
    "import static e.b.c;",
    "import static f.c.l;",
    "import w.g;",
]

IMPORT_FWD = "import androidx.appcompat.widget.CompatStatics;"


def insertar_import(texto):
    if IMPORT_FWD in texto:
        return texto, False
    lineas = texto.split("\n")
    ult = max((i for i, l in enumerate(lineas)
               if l.startswith("import ")), default=None)
    if ult is None:
        raise SystemExit("sin imports")
    lineas.insert(ult + 1, IMPORT_FWD)
    return "\n".join(lineas), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    cambios = {}
    for rel, viejo, nuevo, n in CALLS:
        p = os.path.join(J, rel)
        t = cambios.get(p) or open(p, encoding="utf-8").read()
        if t.count(viejo) != n:
            raise SystemExit(f"DESAJUSTE {rel}: {viejo[:60]!r} x{t.count(viejo)} != {n}")
        cambios[p] = t.replace(viejo, nuevo)

    # quitar imports inutiles + anadir import del forwarder donde falta
    fwd_pkgs = ("androidx/appcompat/app/", "com/google/android/material/",
                "androidx/recyclerview/")  # Toolbar y c2: mismo paquete
    for p, t in list(cambios.items()):
        rel = os.path.relpath(p, J)
        for imp in QUITAR:
            t = t.replace(imp + "\n", "")
        if rel.startswith(fwd_pkgs):
            t, _ = insertar_import(t)
        cambios[p] = t

    for rel, viejo, nuevo, _n in CALLS:
        print(f"  {rel}: {viejo[:70]}")

    if args.aplicar:
        os.makedirs(os.path.dirname(os.path.join(J, FWD)), exist_ok=True)
        with open(os.path.join(J, FWD), "w", encoding="utf-8") as f:
            f.write(FORWARDER)
        print(f"[escrito] {FWD}")
        for p, t in cambios.items():
            open(p, "w", encoding="utf-8").write(t)
        print(f"[Aplicado] {len(cambios)} ficheros + forwarder.")
    else:
        print("\n[DRY-RUN] nada modificado. Repite con --aplicar.")


if __name__ == "__main__":
    main()

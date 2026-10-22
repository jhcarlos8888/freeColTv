# Plan P3 — Diagnóstico y ataque de las familias residuales (loop_6: 15.186)

Estado de partida (medido, commits `154da03` y `a7da383`):

- N0 baseline Gradle = 19.028 · tras Estrategia B + bucle R1/R2/R3 = **15.186**
  (`tools/medir.sh mediciones/loop_6.log`, ~10 s, paridad exacta con Gradle).
- Auditoría normalizada: 15.025 preexistentes (del decompilador) · **161 nuevos**
  (cascadas de renombres; R1/R2/R3 en punto fijo).
- Ground truth DEX disponible: `tools/inventario_dex.sh` →
  `mediciones/dex_clases.txt` (16.466 clases DEX vs 7.535 fuentes); `dexdump`
  vive en `~/Android/Sdk/build-tools/34.0.0/dexdump` (NO está en PATH).

## Objetivo

Reducir los 15.186 errores de javac a 0 recuperando desde el ground-truth DEX
y el classpath de Gradle los tipos/miembros/imports que la fuente no tiene,
en tandas de una familia cada vez, cada una verificada con `tools/medir.sh` y
sin regresiones (errores nuevos ≈ 0), hasta `gradle :app:assembleDebug` en 0.

## No está en alcance

- Reescribir lógica de la app ni cambiar su comportamiento observable.
- Desactivar/relajar comprobaciones (`-nowarn`, bajar `-Xmaxerrs`, etc.).
- Parchear errores "a ojo" sin evidencia DEX/classpath (regla de oro hasta aquí).
- Familias residuales no derivables de ninguna fuente: se documentan, no se maquillan.

## Clasificación medida de los 15.186 (loop_6, por causa verificable)

| palanca | nº | hipótesis a confirmar en el paso 2 |
|---|---:|---|
| clase top-level existe en DEX en OTRO paquete | 2.253 | falta `import` |
| NO_en_DEX (SDK/android.jar, jars de deps, homónimos) | 1.361 | import de plataforma o sombra homónima |
| variables/campos "raíz" (sin error-tipo previo en el fichero) | 1.096 | campo no emitido / referencia a clase renombrada |
| variables en ficheros con error-tipo previo | 2.040 | **cascada** (caerá al arreglar raíces) |
| clase top-level en DEX del mismo paquete y ausente en fuente | 1.496 | renombre/fusión/pérdida |
| métodos ausentes (`symbol: method`) | 1.012 | tipo roto o método no emitido |
| anidados (`location: class Q.x`) | 353 | anidado perdido o referencia a paquete raíz |
| otras familias (override/tipos/sobrecarga/inferencia/otro) | 5.575 | en parte cascada (1.718 en ficheros con error-tipo previo) |

Diagnósticos ya cerrados con evidencia (no reabrir):

- Referencias a paquete raíz renderizadas por jadx (`l.b`, `d.a.C0153a`): 91
  sombreadas por tipos anidados + 109 sin destino; ojo: `import l.b;` no sirve
  si el propio fichero declara un anidado homónimo (p.ej. `o.b`).
- 10 llamadas a métodos homónimos renombradas por error → revertidas (`a7da383`).
- El parser de logs debe mapear rutas/nombres viejos para comparar con baseline.

## Archivos afectados

- `tools/dex_indice.py` (nuevo) → `mediciones/dex_indice.tsv` (+ resumen): clases,
  super, interfaces y **miembros (campos/métodos) por clase** desde los DEX.
- `tools/auditar_familias.py` (nuevo) → `mediciones/auditoria_familias.json`:
  clasificación exacta por familia (raíz|cascada) × (DEX|classpath|ninguno) ×
  (miembro presente/ausente).
- Reglas nuevas en `tools/reparar_por_errores.py` o scripts dedicados por tanda.
- `XuperDorado_project/app/src/main/java/**` (sólo escritura en tandas P4).
- `mediciones/LEEME.md` y este plan (estado final).

## Pasos

1. **Índice DEX con miembros** — `tools/dex_indice.py` parsea `dexdump -d` en
   streaming (sin volcar texto gigante) y escribe el TSV.
   → verificación: nº de clases del índice = 16.466 (paridad con
   `inventario_dex.sh`); spot-check `Landroidx/fragment/app/o;` contiene el
   método `N0` con proto `(Ll/b;)V`; conteo de campos/métodos > 0.
2. **Auditoría por familia** — `tools/auditar_familias.py` cruza errores de
   `loop_6.log` con índice DEX, mapa de renames, fuentes y classpath de Gradle
   (`app/build/...` vía `dump_classpath.gradle`).
   → verificación: la suma de familias = 15.186; 10 muestras revisadas a mano;
   JSON versionado.
3. **Sub-plan P4 por familia** (tamaño × mecánicidad): cada tanda = regla nueva
   → `tools/medir.sh` → auditoría de no-regresión (161 nuevos no crecen) →
   commit. Orden provisional: (A) imports, (B) clases top ausentes,
   (C) campos, (D) anidados, (E) métodos, (F) otras familias.

> Un plan de más de 7 pasos se parte: P3 termina en el paso 3; P4 se redacta
> con los números reales de la auditoría (no con estos estimados).

## Criterios de aceptación (final)

- `gradle -I tools/dump_classpath.gradle -q :app:dumpCp` y
  `tools/medir.sh mediciones/final.log` → `0 errors`.
- `gradle :app:assembleDebug` → BUILD SUCCESSFUL y existe
  `XuperDorado_project/app/build/outputs/apk/debug/app-debug.apk`.
- `~/Android/Sdk/build-tools/34.0.0/aapt dump badging <apk>` →
  `package="RooSeveLt.InT"`.
- Ninguna comprobación desactivada; auditoría de no-regresión limpia.

## Riesgos

- **Cascadas**: los conteos por familia caen solos al arreglar raíces →
  re-clasificar tras cada tanda; no atacar síntomas de cascada.
- **Recuperación de anidados**: si el cuerpo real es imprescindible, decompilar
  con jadx headless (jar disponible en
  `~/.local/share/reverse-engineering/jadx/`) en vez de inventar cuerpos stub.
- **Orden de ficheros**: sólo `tools/medir.sh` (paridad Gradle); el total de
  errores es sensible al orden.
- **Comparaciones**: normalizar siempre a ruta/nombre viejo
  (`mediciones/mapa_renames.json`).

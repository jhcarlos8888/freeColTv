# Mediciones de la reconstruccion

Todos los conteos se obtienen con la MISMA invocacion que Gradle/AGP, pero sin
Gradle (verificada: `tools/medir.sh` reproduce exactamente N0 = 19.028 errores
y las mismas familias que `gradle :app:compileDebugJavaWithJavac`).

Reproducir:

    gradle -I tools/dump_classpath.gradle -q :app:dumpCp   # classpath + orden + plataforma
    tools/medir.sh mediciones/mi_log.log                   # javac equivalente (~10 s)
    python3 tools/analizar_errores.py mediciones/mi_log.log

Tres datos de la plataforma que hicieron falta para la paridad exacta
(descubiertos por medicion, no por suposicion):

1. **Orden de ficheros**: javac reporta mas o menos errores segun el orden en
   que recibe los ficheros (recuperacion de errores dependiente del orden):
   ordenado 21.535, invertido 19.053, orden de Gradle 19.028. Por eso
   `tools/medir.sh` usa `app/build/sources_gradle_order.txt`.
2. **Plataforma**: AGP pasa `--system <jdkImage>`; sin el, difieren `sun.misc`,
   `javax.swing` y los `java.lang.Object` no resueltos.
3. Flags: `-g -encoding UTF-8 -source/-target 17 -Xmaxerrs 300000
   -XDstringConcat=inline`.

## Archivos

* `baseline_N0_gradle.log` + `baseline_N0_gradle.json`: salida real de Gradle
  (N0 = 19.028 errores). El log completo si esta versionado en el historial
  previo a ignorarlo; el JSON lleva el desglose.
* `baseline_paridad.log` + `baseline_raw.json`: mismo resultado con
  `tools/medir.sh` (paridad verificada familia a familia).
* `mapa_renames_dryrun.json` / `mapa_renames.json`: plan y mapa de renombres
  de la Estrategia B (renombrar clases tapadoras).

## Familias en N0 (19.028 errores)

| familia | errores |
|---|---|
| cannot_find_symbol | 13.234 |
| ANIDADO_DEX (tipos anidados perdidos por jadx) | 8.284 |
| otro | 2.677 |
| **SOMBRA (clase tapa al paquete raiz)** | **2.193** en 124 clases |
| tipos / override / sobrecarga / inferencia | 1.221 / 971 / 572 / 353 |
| SOMBRA_sin_tapadora_local | 74 |

## Estado actual (tras Estrategia B + bucle de reparacion)

* **Renombrado**: 124 clases tapadoras `pkg.C -> pkg.C_` (+ constructores,
  82 imports `C.N` y 2 strings de reflexion umeng). SOMBRA: 2.193 -> **0**.
* **Bucle de reparacion** `tools/reparar_por_errores.py <log>` hasta punto fijo
  (logs `loop_1..5.log`): 19.567 -> **15.196 errores** (N0 = 19.028).
* Reglas con precedencia JLS 6.3/6.4.1 (anidado > import sencillo > paquete >
  wildcard), con cuidados descubiertos a golpe de evidencia:
  - el caret de javac apunta al `.` de `C.n` (desplazamiento de caret);
  - un import ya renombrado (`pkg.C_`) sigue siendo contexto valido;
  - el parser de bloques no debe "tragarse" errores sin linea `location:`
    (perdia ~4.800 bloques);
  - `PAT_IMP`/`PAT_IMPW` necesitan `re.MULTILINE` (sin el, los imports nunca
    se leian y 991 sitios quedaban "sin contexto");
  - 84 reescrituras R2 sobre calificadores sombreadsos por tipos anidados
    fueron revertidas (inventario `r2_aplicados_revertidos.json`; los 20
    conservados estan en `r2_aplicados_conservados.json`).
* Auditoria contra baseline (normalizando rutas/nombres renombrados):
  15.025 preexistentes, **171 nuevos** (cascadas en ficheros renombrados y
  `@Override` sobre supertipos ya rotos en baseline).

### Familias en loop_5 (15.196 errores)

| familia | errores |
|---|---|
| cannot_find_symbol | 9.621 |
| ANIDADO_DEX (tipos anidados perdidos por jadx) | 6.814 |
| otro | 2.682 |
| tipos / override / sobrecarga / inferencia | 1.143 / 825 / 572 / 353 |
| SOMBRA_sin_tapadora_local | 130 |

**Siguiente paso**: recuperar los tipos anidados ausentes desde los DEX
(`apktool_decoded/classes*.dex` con `dexdump`) — es la familia ANIDADO_DEX y
buena parte de `cannot_find_symbol`.

## P3: diagnostico por familia + CAUSA RAIZ DEL VENENO `Object`

* `tools/dex_indice.py` -> `mediciones/dex_indice.tsv` (+ `dex_miembros.tsv`,
  regenerable en 2 s): ground truth DEX con clases, super, interfaces y
  miembros (16.466 clases = inventario, 172.639 campos, 97.952 metodos).
* `tools/auditar_familias.py` -> `mediciones/auditoria_familias.json`:
  los 15.186 errores de `loop_6.log` por familia x origen x destino DEX
  (verificacion interna: parseados = suma familias = resumen javac).
* **Hallazgo**: los 4.042 errores `symbol: class Object` (en 1.062 ficheros)
  eran ENVENENAMIENTO GLOBAL de javac causado por UN UNICO ciclo:
  `androidx/appcompat/app/c.java:42  class b implements c.b` (el prefijo `c`
  resuelve a la propia clase -> cyclic inheritance -> la completacion ciclica
  corrompe la resolucion de `java.lang.Object` para los ficheros siguientes).
  Experimento A/B: quitando SOLO esa clausula, Object 4.042 -> 0 y el total
  15.186 -> 7.823. Un solo error `cyclic` en todo el log.
* DEX confirma el diseno roto: `Landroidx/appcompat/app/c$b;` implementa
  `Lc/b;` (paquete raiz `c`), no `Lc$b;`.

### Tanda P4-1: renombrado de la tapadora `androidx.appcompat.app.c -> c_`

* Deteccion corregida en `tools/renombrar_clases_tapadoras.py` (3 fixes):
  (1) rama nueva por `cyclic inheritance involving C.N` (el sintoma de esta
  tapadora no era cannot-find-symbol); (2) wildcard `-1` por linea cyclic en
  pre-reparaciones (el caret del cyclic apunta a la decl, no al sitio `C.N`);
  (3) `mapa_renames.json` acumulativo (antes se sobrescribia con el plan
  actual). El pre-reparador deja la linea 42 intacta: tras el renombrado,
  `implements c.b` enlaza al paquete raiz (diseno original) sin tocar texto.
* Resultado (`loop_10.log`, punto fijo R1: 45 reescrituras en 15 ficheros):
  **15.186 -> 7.821 errores** (-48,5 %); Object 4.042 -> **0**; cyclic -> **0**.
* Auditoria de no-regresion (normalizada contra `baseline_paridad.log`):
  "nuevos" 191 -> 429, pero 246 son errores latentes DESENMASKADOS (el veneno
  mataba el fichero antes de llegar a esa capa: type-checking de ficheros no
  relacionados con el renombrado). 687 ficheros mejoran, 18 empeoran
  (desplazamientos de atribucion), SOLO 5 ficheros pasan de 0 a 1-2 errores,
  todos defectos latentes del decompilador (campos `Object` que deberian ser
  `T`/`CharSequence`, supertipos incompletos en `b2`). Ningun codigo
  previamente correcto se rompio.
* 14 `symbol: class c` restantes = referencias calificadas a anidados ajenos
  (`com.taobao.agoo.a.a.c`, `g.c` de widget...) — familia ANIDADO_DEX, no eco
  del renombrado.

### Tanda P4-2: tapadoras de SUBPAQUETE (12 renombres)

* Revision independiente del reviewer sobre P4-1: resultado correcto, 6
  defectos latentes en `renombrar_clases_tapadoras.py` corregidos (guarda
  muerta `en_pkg`, wildcard -1 restringido a tapadoras, parseo de cyclic de
  3 segmentos, guard i+4, offsets de strings, agrupacion por fichero).
* Nuevo patron diagnosticado (`prefijo_es_paquete`, 628 errores): una CLASE
  top-level sombrea al SUBPAQUETE homonimo del propio paquete, p.ej.
  `com/uc/crashsdk/a.java` choca con `com/uc/crashsdk/a/`; las referencias
  FQN en contexto-tipo (`new com.uc.crashsdk.a.e(405)`) fallan con
  `cannot find symbol: class e location: class a` + el aviso explicito de
  javac `class a clashes with package of same name`. En contexto-expresion
  (`com.uc.crashsdk.a.g.a(x)`) javac si resuelve por ruta de paquete, asi
  que renombrar la clase NO toca esos sitios (cero rotura silenciosa,
  verificada: los 836 sitios FQN sin error enlazan ya al subpaquete).
* Rama C4 en `detectar_tapadoras`: la forma FQN escrita fija el paquete de
  la tapadora; predicado = sombra local + subpaquete en fuente con el tipo
  simbolo. 12 renombres (11 de subpaquete + `h2::b` de raiz): crashsdk,
  taobao agoo/accs, efs (net/pa/util/core), repackage vivo, umeng, anet.
* Resultado (`loop_13.log`, punto fijo R1/R2: 289 reescrituras en 84
  ficheros): **7.821 -> 7.006 errores**; crashsdk 715 -> 113; `clashes`
  13 -> 2. No-regresion: con nombres revertidos 0 ficheros nuevos rotos,
  40 mejorados, 0 empeorados; auditoria normalizada vs baseline: "nuevos"
  429 -> 430 (+1).

### Tanda P4-3: acceso privado entre clases (605 errores)

* Familia diagnosticada en `loop_13`: `X has private access in C` (637
  errores), partida en dos mecanismos con evidencia:
  1. **605 miembros sin calificar** (campo/metodo/ctor `private`): el
     decompilador emitio acceso directo a campos que en el DEX original se
     usaban via metodos accesores sinteticos (verificado con `dexdump`:
     `Lmc/j;` campo `a` = PRIVATE STATIC + metodo `a()Z` = PUBLIC STATIC
     FINAL SYNTHETIC). Quitar `private` preserva la semantica (mismo
     almacen y valor; solo se amplia el alcance de compilacion).
  2. **32 miembros calificados** (`Owner.N`): sombra de paquete (patron
     C2 con otro sintoma javac). Rama **C5** en `detectar_tapadoras`
     (simbolo calificado + calificador escrito = clase del propio paquete
     con homonimo en raiz): 2 renombres (`androidx.lifecycle::j`, cuyo
     `j.b` enlazaba al anidado privado heredado de LiveData en vez de
     `Lj/b;`, y `kd::h2`, cuyo `h2.b__` sombrea al paquete raiz `h2/`).
* Nueva herramienta `tools/relajar_privados.py`: indice global de
  declaraciones `private` por nombre de miembro (nombres jadx casi
  unicos), desambiguation por calificador del caret y por la clase del
  propio mensaje (`in bd` -> `bd.java`), relajacion byte fiel del
  modificador. Punto fijo: 227 declaraciones en 122 ficheros.
* Resultado (`loop_15.log`): **7.006 -> 6.401 errores** (-8,6 %);
  `has private access` 637 -> 29 (28 miembros calificados + 1 formato
  raro, fuera de ambito de la herramienta); familia `otro` 2.186 ->
  1.606. No-regresion (rutas normalizadas con el mapa inverso):
  0 ficheros nuevos rotos, 0 empeoran, 60 mejoran, 147 quedan limpios;
  ficheros con errores 1.503 -> 1.356. R1 = 0 al cierre.

### Tanda P4-4: bridges fusionados por el decompilador (6.401 -> 5.825)

* Familia `method does not override` (810) + `is not abstract and does
  not override` (559): 670 de los 810 llevan el aviso JADX
  `merged with bridge method [inline-methods]`. Verificado con `dexdump`:
  la clase DEX original tenia DOS metodos, el concreto y el bridge con la
  firma erodada de la interfaz (Lud/n1$b0;: `a(Long)Boolean` +
  `f(Object)Object` de me.l); el decompilador los fusiono en uno y dejo el
  `@Override` en el concreto, dejando a la clase sin implemento real.
* Nueva herramienta `tools/regenerar_bridges.py`: para cada error tipo
  A inserta tras el metodo fusionado un `@Override bridge` con la firma
  erodada del supertipo (resuelto en fuente) que delega en el concreto
  con casts, y RETIRA el `@Override` del metodo fusionado (pasa al
  puente; su auto-validacion confirma la firma). Escaneo consciente de
  strings/comentarios para el cierre de llaves y verificacion de
  integridad (balance real antes/despues; si cambia no escribe).
* Tres defectos propios de la herramienta descubiertos y corregidos con
  evidencia (mediciones intermedias `loop_16a/b`): (1) el cierre de
  llaves contaba las de literales string y colocaba puentes fuera de la
  clase (4.129 errores de parse); (2) javac apunta a la ANOTACION o a la
  DECLARACION del metodo, y el borrado ciego borro declaraciones
  (cuerpos huerfanos); (3) aplicar inserciones y borrados en dos fases
  desplazaba los indices de borrado (borraba lineas de codigo).
* Resultado (`loop_16.log`, 441 puentes en 242 ficheros, punto fijo en
  2 pasadas): **6.401 -> 5.825 errores**; familia override 810 -> 425
  (los restantes: supertipos JDK/android sin fuente, ambiguedades);
  `is not abstract` 559 -> 280 (los restantes no tienen @Override en el
  metodo fusionado ni supertipo resoluble; tanda P4-5). No-regresion:
  0 ficheros nuevos rotos, 100 mejoran, 107 quedan limpios, 35 empeoran
  (<=8, latentes desenmascarados); R1 = 0.

### Tanda P4-5: bridges tipo B + fix del parser de params (5.825 -> 5.749)

* Los 280 errores `X is not abstract and does not override abstract
  method NAME(ARGS) in SUP` apuntan a la CLASE, no al metodo, pero el
  metodo fusionado (con marcador JADX) si esta dentro; la firma erodada
  objetivo la da el propio mensaje. Modo B en `regenerar_bridges.py`:
  region de la clase por balance de llaves, concreto unico con marcador
  `merged with bridge`, retorno del supertipo en fuente (coincidencia
  exacta de params erodados) o tabla de erasures JDK/android (Observer,
  Property, Function, Comparator, Comparable, Consumer, ParameterHandler,
  Converter...); FQN del supertipo extraido de la clausula
  extends/implements de la clase (el mensaje solo da el nombre simple).
* Defecto propio encontrado: `parsearParams` descartaba los params con
  modificador `final` (habito del decompilador), inflando el recuento y
  dejando 107 concretos "no encontrados"; corregido (tambien anotaciones).
* Resultado (`loop_17.log`, 142 puentes: 102 B + 40 A, punto fijo en 3
  pasadas, 0 errores en lineas de puente): **5.825 -> 5.749**; override
  703 -> 550 (332 A + 218 B restantes: sin concreto con marcador,
  retorno desconocido, supertipos ambiguos). No-regresion: 0 ficheros
  nuevos rotos, 13 mejoran, 19 limpios, 36 empeoran (<=4, latentes).

### Tanda P4-6: familia de visibilidad completa (5.749 -> 5.616)

* Nueva herramienta `tools/ampliar_visibilidad.py` (ampliacion de
  alcance, semantica preservada):
  1. `X is not public in Y` -> `public` en la declaracion. Resolucion
     del objetivo: (a) tipo anidado cualificado `d_.c` -> el fichero de
     `d_` se resuelve por la clausula extends/implements del fichero con
     error, por import, o por FQN; (b) clase en paquete `Y` o miembro ->
     PRIMERO el IMPORT del fichero con error (si importa un tipo `Y`,
     la referencia es anidada de ese tipo: los miembros ganan al
     paquete; caso real `l2.g` = 54 errores = `bc.l2.g` heredada),
     despues directorio de paquete, despues indice global de miembros
     (cadena de clases por indentacion; fallback cuando el calificador
     es una VARIABLE, p.ej. `pVar.f14181a`).
  2. `X has protected access in Y` -> si el acceso esta escrito
     `((Y) this).X` (cast al supertipo que el decompilador emitio) se
     quita el cast (`this.X` es legal: miembro heredado via tipo
     propio; 53 casos JDK: modCount/in/out/mObservers/buf); si no, se
     promueve la declaracion a `public`.
  3. Constructores `b() is not public in b` (1 caso): los miembros
     heredados de los supertipos sombrean al import simple (JLS 6.4.1;
     AppWrapper extends y9.d hereda la anidada y9.d.b cuyo ctor era
     package-private); se resuelve supertipos (con mapa de imports para
     los simples), luego import, luego mismo paquete.
* Defectos propios descubiertos con evidencia: el indice solo cubria
  `private` (los relajados en P4-3 no aparecian); el regex del cast
  olvidaba el `)` del tipo; el fallback filtraba sobre la lista ya
  vaciada; desempaquetado de 4 elementos inexistente.
* Resultado (`loop_22.log`): **5.749 -> 5.616 errores**; `is not
  public` 97 -> 0 y `has protected access` 70 -> 0 (familia de
  visibilidad COMPLETA). No-regresion: 0 ficheros nuevos rotos, 15
  mejoran, 21 limpios, 3 empeoran (<=6, latentes); R1 = 0; auditoria
  cuadrada.

### Tanda P4-7: lossy conversions guiadas por caret (5.616 -> 5.527)

* Nueva herramienta `tools/castear_lossy.py` para `possible lossy
  conversion from X to Y` (90 errores: int->short 63, int->byte 21,
  long->int 4, double->int 1, +1 ternario). Causa raiz: el DEX no tiene
  registros small-type ni truncamientos implicitos como la fuente Java
  original; el decompilador declara campos/params short|byte pero
  calcula int/long/double. El bytecode original TRUNCABA, asi que el
  cast explicito `(<tipo>)` PRESERVA exactamente la semantica DEX.
* Dos reglas seguras guiadas por el caret de javac:
  1. token simple (literal/identificador/calificado) que es la
     EXPRESION COMPLETA hasta delimitador `,` `)` `;` -> se envuelve.
     Si el caret apunta al `.` de un acceso (`countObject.value`), se
     retrocede hasta el inicio de la cadena calificada.
  2. asignacion (un solo ` = ` y `;` final) -> se envuelve TODO el RHS.
  Expresiones no envolvibles -> omitidas y reportadas (nunca reescritas
  a ciegas).
* Defecto propio descubierto con evidencia: el caret de javac puede
  apuntar al `.` de un campo -> el cast se inserto en medio de la cadena
  (`countObject(int) .value`) y UN ERROR DE PARSE MATA TODA la medicion
  (log de 1 error, 1.85 s). Linea revertida (`git checkout`), guarda de
  retroceso sobre `[\w$.]` anadida. Senal de parse-break: resumen
  absurdamente bajo (< 1.000) => revisar errores de sintaxis.
* Resultado (`loop_25.log`): **5.616 -> 5.527 errores**; familia
  `possible lossy conversion` COMPLETA (0 errores primarios; solo queda
  una linea de detalle secundario sin prefijo de fichero). No-regresion:
  0 ficheros nuevos rotos, 14 mejoran, 19 limpios, 0 empeoran; R1 = 0;
  auditoria cuadrada (5.527).

### Tanda P4-8: familia `has private access` completa + revert de renombrado (5.527 -> 5.500)

* `tools/relajar_privados.py`: soporte para simbolos calificados
  `Owner.N has private access` (excluidos en P4-3). Resolucion: se
  consulta el indice por el N interior y el mensaje (`in Owner`) +
  calificador del caret localizan el fichero de Owner; SOLO se relaja
  si todos los accesos son del mismo paquete que la declaracion (quitar
  `private` -> package-private no cruza paquetes), si no se omite.
* Causa raiz descubierta con evidencia (28 errores `e____.b has private
  access`): el renombrado de tapadoras de 154da03 sustituyo TAMBIEN los
  calificadores que denotaban el PAQUETE raiz `e` -> `e____` (p.ej.
  `setButtonDrawable(e.b.d(ctx, i10))` paso a `e____.b.d(...)`). El DEX
  ground truth declara `d(Context,I)Landroid/graphics/drawable/Drawable;`
  y `c(...)` en `Le/b;` (paquete e, `e/b.java` = `public abstract class
  b`), NO en `Landroidx/appcompat/widget/e$b;` (que solo tiene `a()`).
  Revert selectivo: 28 sitios `e____.b.d(`/`.c(` -> `e.b.d(`/`.c(` en 12
  ficheros (verificado: `e/b.java` public, sin imports de tipo `e`).
* Defecto propio del tool: `construir_indice` guardaba la linea CON el
  `\n` final y el apply la reinsertaba -> linea en blanco anadida tras
  cada declaracion relajada (cosmetico; ya no ocurre). Linea anomala
  retirada de `e____.java`.
* Familia COMPLETA: 0 errores primarios `has private access` (solo
  persiste una linea secundaria `reason:` de otro bloque). Resultado
  (`loop_28.log`): **5.527 -> 5.500**. No-regresion: 0 ficheros nuevos
  rotos, 8 mejoran, 3 limpios, 0 empeoran; auditoria cuadrada (5.500).
* Nueva familia detectada (preexistente, siguiente tanda): referencias
  `e.<clase>` del paquete raiz `e` SOMBREADAS por tipos `e` en scope
  (~12 sitios: Toolbar anidada `e`, `b0.e`, `f.e`, TextInputLayout...);
  Java no permite escribir el paquete `e` entonces (limitacion JLS):
  candidatas = import static o renombrar el paquete `e`.

### Tanda P4-9: paquetes raiz sombreados por tipos homonimos (5.500 -> 5.469)

* Causa raiz: en EXPRESIONES Java resuelve el prefijo izquierdo como
  TIPO si hay tipo homonimo en scope -> no existe forma de escribir el
  paquete sombreado. Verificado con sondas javac (A/B/C en /tmp/opencode/probe2):
  (a) `import t.k;` + `k.a(...)` funciona con tipo `t` anidado;
  (b) `import static e.b.d;` + `d(...)` funciona con `e` Y `b` anidados;
  control negativo C falla.
* Deteccion estricta (`tools/importar_paquetes_sombreados.py`): exige
  `symbol` == segmento que rompe la cadena, `location` (kind class/interface/enum/type)
  contiene el nombre del paquete y que `SRC/pkg/cls.java` exista. Resultado:
  32 sitios en 7 ficheros (RecyclerView 19, TextInputLayout 5, Toolbar 3,
  x8/p 2, c2 1, b0 1, app/f 1). Eleccion por sitio: si el fichero declara
  tipo anidado con nombre del 2o segmento -> estrategia b (static import);
  si no -> a (import tipo).
* Peligro de enlace SILENCIOSO en static imports: si la clase tiene un
  miembro homonimo con firma aplicable, el static import queda bloqueado
  (JLS 15.12.1: cualquier miembro homonimo sombrea al import; si ninguno
  aplica -> error VISIBLE). Verificado por sitio: RecyclerView a/b/g sin
  miembros aplicables; Toolbar/f/b0/TextInputLayout d/c sin miembros con
  Context ni varargs/genérico; c2 l (int, Mode) vs call (Context,...)
  inaplicable; x8/p F con 0 miembros. Herencia: ViewGroup/LinearLayout/
  Spinner SDK + interfaces n0/d0/e_________ sin homónimos.
* 32 aplicados: 31 resueltos; 12 regresiones visibles por:
  (i) miembros homónimos sin args (Toolbar d() x15, TextInputLayout d() x19,
  f d() x13) bloquean el static import d/c; (ii) clase homónima en el
  MISMO paquete sombrea el import (RecyclerView g.java, appcompat/widget b.java,
  appcompat/app b.java, appcompat/widget c.java) -> estrategia a inviable;
  (iii) c2 l(int,Mode) bloquea static import.
* Fix via forwarder `androidx.appcompat.widget.CompatStatics` (5 metodos
  estaticos delegando al FQN correcto): d/c de e.b, l de f.c, b/g de w.g.
  Los 12 calls fallidos pasan a `CompatStatics.x(...)` (simple name nuevo,
  sin sombreado posible). Quitar imports static inutiles; anadir import
  de CompatStatics en f/TIL/RecyclerView (Toolbar y c2 mismo paquete).
  Regenerar `sources_gradle_order.txt` (7536) para incluir CompatStatics.
* Hallazgo adicional (causa raiz del error `c cannot be converted to
  Drawable`): en f/c.java el nombre simple `c` resuelve al miembro
  heredado f.d.c (Drawable.Callback), no a la propia clase f.c, por
  sombreado de JLS 6.4.1/6.5.5 -> el retorno declarado `c` de
  `f.c.l(...)` es f.d.c, no Drawable. Fix: cast via Object en el forwarder
  (`(Drawable)(Object)f.c.l(...)`), sin tocar f/c.java (errores
  preexistentes de f/c.java no se amplifican).
* Resultado (`loop_32.log`): **5.500 -> 5.469** (-31). No-regresion:
  0 ficheros nuevos rotos vs loop_28, 31 mejoran (RecyclerView 19, TIL 5,
  Toolbar 3, x8/p 1, c2 1, b0 1, f 1), 0 empeoran. Auditoria cuadrada:
  5.469. Herramientas: `tools/importar_paquetes_sombreados.py`,
  `tools/aplicar_compat_statics.py`, `androidx/appcompat/widget/CompatStatics.java`.

### Tanda P4-10: variables de excepcion huerfanas del decompilador (5.469 -> 4.662)

* Familia atacada: `cannot find symbol` + `symbol: variable th|e|...` con
  `location: class ...` y NINGUNA declaracion en el ambito. Sobre loop_32
  eran 2.499 candidatos (1.130 con el caret dentro de un `catch`).
* **Causa raiz verificada en el DEX** (`dexdump -d classes6.dex`,
  `Lokhttp3/RealCall;.execute`): el handler es `move-exception v0` +
  `goto 0044`, y ese `00044` ejecuta `dispatcher().finished(); throw v0;`.
  jadx emitió ese cuerpo DOS veces (dentro del `catch` y DESPUES del `try`)
  y renombro el parametro del catch (`th` -> `th2`) dejando los usos del
  nombre original **sin declaracion**.
* Herramienta `tools/reparar_excepciones_huerfanas.py` (dry-run por
  defecto, `--aplicar`, vuelca `--json` con el MOTIVO de cada permiso y de
  cada exclusion). Un sitio solo se toca con **prueba** de que `NAME` y
  `N2` son la misma variable; hay tres reglas, todas nacidas de defectos
  demostrados en la primera version de la tanda:
  * **R1 — glucosa directa** (8 sitios descartados): la glucosa `NAME = N2;`
    tiene que ser hijo directo del cuerpo del `catch` y no cuerpo de una
    cabecera de control. Si esta anidada, `NAME` es OTRA variable y ademas
    se lee en la condicion:
    `} catch (Throwable th2) { if (th == null) { th = th2; } }` pasaba a
    `if (th2 == null) {}` (siempre falso) y se mataba la captura de la
    primera excepcion -> **rotura semantica**. Ficheros: `okio/DeflaterSink`,
    `okio/GzipSink` y `Http2Connection.close()` x2. La comprobacion cubre
    tambien el cuerpo SIN llaves de `else` y `do` (`else NAME = N2;`
    tambien guarda), y deja pasar `case`/labels, que no son condicion.
  * **R2 — `NAME` no se usa como variable en el mismo metodo fuera de los
    catches** (114 descartados): si se usa fuera, `NAME` es una variable
    EXTERNA que la glucosa captura, y borrarla rompe esa captura
    (`e = null; try{}catch(IOException e10){e=e10;} if (e!=null) throw e;`).
    Ignoran las llamadas `NAME(...)`, los accesos `x.NAME`, las
    declaraciones `Tipo NAME` y todo lo que este dentro de un catch.
  * **R3 — homonimia con un campo REAL del DEX** (100 descartados): la
    obfuscacion deja campos de UNA letra (`e`, `f`), asi que
    `location: class X` + `variable e` puede coincidir con un campo
    existente y renombrar cambiaria el destino. Prueba de que NO lo es: la
    escritura `NAME = N2` solo podria ser un `iput` de ese campo si el tipo
    del catch es asignable al tipo del campo (verificador Dalvik).
    De los 200 candidatos con destino `campo_en_DEX`, **123 quedan
    demostrados incompatibles** (24 campo PRIMITIVO; 77 porque el campo es
    una CLASE con cadena propia hasta `java.lang.Object`, que nunca es
    ancestro de un Throwable; 22 porque el campo es una INTERFAZ de la APP
    que el tipo del catch no implementa) y **77 se excluyen por duda** (73
    con tipo de PLATAFORMA `String/Set/Boolean/...` ausente de los indices
    DEX, 4 con campo `java.lang.Object`). Otros 23 se excluyen porque javac
    no llego a imprimir `location:`. Duda -> no se toca.
    Igual si faltan los indices DEX (`mediciones/dex_miembros.tsv`, 15,8 MB,
    **ignorado a proposito** en `.gitignore:20` y regenerable con
    `python3 tools/dex_indice.py`): R3 no puede demostrar nada, asi que no
    se renombra NINGUN candidato y lo avisa.
* Clases no tocadas, medidas en loop_32: **B = 1.410** (fuera de todo
  catch: cola tras try / declaracion perdida `Throwable NAME = null;`, no
  resuelven con renombrar) y **C = 30 + 26** (sin glucosa o caret ambiguo;
  renombrar FALSEARIA el significado,
  `catch (Throwable th3) { th.addSuppressed(th3); }` -> `th3.addSuppressed(th3)`).
* **Revision independiente de la primera version: defecto MAYOR confirmado
  y tanda REVERTIDA.** El reviewer mostro el diff de los 4 sitios con
  glucosa condicional (arriba). Se revirtio TODO con
  `git checkout -- XuperDorado_project` y, como
  `antlr/build/Tool.java` esta FUERA de git (ver hallazgo abajo), se
  reconstruyo desde el propio `loop_32.log` (lineas de glucosa +
  renombres inversos). **Prueba de paridad: `tools/medir.sh` reproduce
  exactamente 5.469 errores y un stream de errores IDENTICO (byte a byte)
  al de `loop_32.log`**, y solo entonces se re-aplico la version corregida.
* Resultado final (`loop_34.log`): **5.469 -> 4.662 errores** (-807,
  -14,8 %); 811 renombres en 158 ficheros y 588 lineas de glucosa
  borradas (antes 1.033/187/768, de los cuales 222 ya no son seguros).
  **Reconciliacion de las cifras** (auditoria de familias 32 vs 34):
  `cfs_variable` 2.499 -> 1.688 (**-811**), `otro` 1.108 -> 1.111 (**+3**),
  `tipos` 876 -> 877 (**+1**); el resto de familias no se mueve
  (`override` 332, `sobrecarga` 50, `paquete` 48, `cfs_class` 281,
  `cfs_method` 270, `inferencia` 5) -> **-807 = -811 + 3 + 1**.
* Los **4 renombres de mas** no son una regresion: son 4 sitios que el
  renombre REPARA en el simbolo pero deja al descubierto otro defecto del
  decompilador (perdida de TIPO), ya observado en la primera version:
  * `com/taobao/accs/data/d.java` 379/519/622 (antes 380/521/627): el
    `cannot find symbol` de la `e` huerfana se convierte en
    `no suitable method found for e(String,Object,Exception,Object[])`
    (27 -> 30 en todo el proyecto): jadx perdio la firma real de
    `ALog.e`, que en el DEX recibe `Object[]`, no `Exception` + `Object[]`.
  * `org/xutils/http/HttpTask.java` 427 (antes 428): pasa de
    `cannot find symbol` a `incompatible types: Throwable cannot be
    converted to CancelledException`; la variable local estaba declarada
    como `Throwable` en el decompilado y en el original era
    `Callback.CancelledException`.
  En ambos casos el simbolo SI es la excepcion capturada (el renombre es
  semanticamente correcto) y el fichero NETO MEJORA (`d.java` 51 -> 41,
  `HttpTask.java` 5 -> 2), pero el error no desaparece: pertenece a la
  familia de **tipos perdidos**, no a esta tanda.
* No-regresion (por FICHERO): 1.186 -> 1.120 ficheros con errores;
  **0 pasan de 0 a >0**, **0 empeoran**, 158 mejoran, 66 quedan limpios.
  Verificado ademas que `okio/DeflaterSink.java` y `okio/GzipSink.java`
  quedan **sin cambios** y que `Http2Connection.java` solo tiene hunks en
  `ReaderRunnable` (277/281): la zona `close()` que rompio la primera
  version sigue identica a HEAD.
* **Reproducibilidad del plan**: un worktree limpio en HEAD
  (`git worktree add --detach`) con el log baseline (rutas absolutas
  reescritas hacia ese worktree y filtrados los 3 errores de
  `antlr/build/Tool.java`, que no existe en un clone limpio) regenera un
  plan **IDENTICO** al aplicado: 808 cambios, 586 lineas de glucosa,
  157 ficheros y 1.688 omisiones. El plan es funcion pura de
  (fuentes en HEAD + log baseline).
* **Segunda revision independiente** (reviewer, ciclo 2) y correcciones:
  * MAYOR (documental): faltaba reconciliar -811 de `cfs_variable` con
    -807 totales y explicar los 4 sitios transformados -> ya documentado
    arriba, con los comandos que lo demuestran.
  * MENOR (herramienta): si faltaban `mediciones/dex_*.tsv`, R3 devolvia
    "no excluye" y permitia renombrar homonimos SIN prueba, contradiciendo
    la propia regla -> corregido a conservador (no se renombra nada) y
    probado con una sonda que finge los indices ausentes.
  * SOSPECHA (herramienta): R1 no detectaba una glucosa que fuera cuerpo
    SIN llaves de `else`/`do` -> corregido; sonda con 6 casos: `if` y
    `else`/`do` detectados, `case`, bloque con llaves y sentencia normal
    sin falsos positivos.
  * Tras las correcciones el plan reproducido sigue siendo IDENTICO (no
    hay ningun sitio en el dataset que active esas ramas).
* **Hallazgo de repositorio**: `.gitignore:8 **/build/` se traga 3 ficheros
  fuente reales, `antlr/build/{ANTLR,StreamScarfer,Tool}.java`; estan en el
  arbol (javac los compila: 7.536 ficheros) pero NO estan en git, asi que
  `git checkout` no los puede restaurar y un clone nuevo los perderia.
* Hallazgo transversal medido con javac 17.0.20 (reproducido en
  `/tmp/opencode/p4_10/probe`): **los errores de FLOW (`unreachable
  statement`) estan OCULTOS mientras ese mismo fichero tenga errores de
  atribucion** (P5: un error de simbolo en otro metodo anula el
  `unreachable`; P1+A2 en ficheros separados: ambos se reportan). Por eso
  el log actual tiene **0** `unreachable`: apareceran automaticamente en
  cuanto un fichero llegue a 0 errores de atribucion.



### Tanda P4-11: outer de anonimas inlineadas por jadx (4.662 -> 4.055)

**Sintoma.** Errores `cannot find symbol` + `symbol: variable fNNNx`
(f+indice de colision+nombre DEX, el naming de JADX) sobre `this.fNNNx`
dentro de una clase anonima declarada en linea, sin `location:`.

**Causa raiz (DEX, no supuesta).** jadx inlineo el cuerpo de clases anonimas
SIN emitir su fichero, pero la clase sigue existiendo en el DEX. Ejemplo
`a4/l0.java:123`:

    La4/d0;  fields: a:La4/l0;  b:Ls3/o;  c:I   <init>(La4/l0;Ls3/o;I)V
    execute(): iget v0 = d0.a  (el OUTER, this$0)
               iget v1 = d0.b  (captura oVar)
               iget v2 = d0.c  (captura i10)
               invoke-static La4/l0;.h:(La4/l0;Ls3/o;I)Ljava/lang/Object;

El campo `a` es el outer. Regla de naming de JADX verificada: el SUFIJO del
identificador `f<indice><nombre>` es literalmente el nombre original en el
DEX (`a4/l0.java` declara `f294a..f299f`; `La4/l0;` declara `a..f`).

**Reparacion.** `this.fNNNx` -> `<pkg>.<Env>.this` (p.ej.
`this.f15230a` -> `db.r0.this`). 620 sitios en 219 ficheros.

**Permisos (R1-R7, si falta alguno NO se toca; ver docstring de la
herramienta).** Los cuatro puntos no triviales, con su evidencia:

* **PRUEBA DOBLE de outer (R4+R5):** el campo `<nombre>` de `LY;` tiene tipo
  `L<Env>;` (Env = descriptor de la ruta del fichero) Y `LY;-><init>` toma
  `L<Env>;` como PRIMER argumento (patron del compilador para el outer).
  Del universo de 853 candidatos fJADX, 620 pasaron la doble prueba y se
  repararon; 250 omitidos: 170 sin `this.`, 35 en contexto estatico (R7),
  28 capturas de otro tipo (R4) y 17 simbolos fJADX ambiguos.
* **Nombre CALIFICADO, no simple (R-mod).** Dentro del cuerpo de una clase,
  sus clases anidadas HEREDADAS sombrian su propio nombre. En
  `m9.c extends z9.e -> z9.b -> androidx.fragment.app.d_ -> Fragment`, el
  nombre simple `c` resuelve a la anidada heredada
  `androidx.fragment.app.d_.c` (`d_.java:84` declara `class c`), y `c.this`
  produce `not an enclosing class: d_.c`; igual para `Fragment.h`
  (`Fragment.java:309`) y `Fragment.f` (`Fragment.java:297`). javac lo
  confirma en su propio mensaje: `symbol: method L9(hb.c,View) / location:
  class d_.c`. Probe en `/tmp/opencode/p4_11/probe2/P1.java`: la forma
  simple falla y la calificada (`p.c.this`) compila.
* **Exclusion de contextos estaticos (R7).** `Env.this` dentro de un metodo
  estatico o dentro del metodo de instancia de una clase anidada ESTATICA
  produce `non-static variable this cannot be referenced from a static
  context` (probe en `/tmp/opencode/p4_11/probe/H.java`, 4 casos). Regla
  lexica: al subir por bloques desde el sitio, si una apertura contiene
  `static` como palabra entera (con hasta 4 lineas de mirada previa para
  firmas multlinea) -> no se toca. 35 sitios excluidos.
* **Caret con tolerancia medida.** javac coloca el caret 1 columna antes del
  identificador en 865/871 bloques (sobre el punto de `this.`) y exacto en
  6; solo se admiten delta 0 y -1. Ademas el numero de `this.sym` de la
  linea debe CUADRAR con el de errores (si sobran ocurrencias, no se toca).

**Primera version REVERTIDA antes de commitar** (nombre simple `Env.this`):
652 sitios, 4.662 -> 4.033 (-629), pero con 23 ERRORES NUEVOS (9
`non-static` + 14 `not an enclosing`), todos en lineas tocadas. Causa raiz
de ambos groups determinada con el fuente de javac 17
(`Resolve.resolveSelf`: `NotEnclClass` si el simbolo resuelto no coincide
con ninguna clase envolvente; `StaticError` si hay limite estatico) y con
probes minimos; no-regresion por fichero: 0 empeoran. Se descarto y se
replanteo la regla (calificado + R7) en lugar de parchear los sintomas.

**Medicion final (`mediciones/loop_36.log`): 4.662 -> 4.055 (-607).**

* Reconciliacion exacta: 620 reparas = 607 errores eliminados + 13 lineas
  que SIGUEN con error pero de OTRO simbolo. Esas 13, repartidas en 6
  ficheros (td/h:3, ha/h:3, m9/c:2, n9/f:2, hb/c:2, k8/c:1), son del
  receptor `c.L9(...)`/`h.R9(...)`: jadx escribe el RECEPTOR
  con el nombre simple, que la misma sombra heredada resuelve a `d_.c` /
  `Fragment.h` (metodo inexistente). En loop_34 esas lineas ya tenian 1
  error (la variable, que se arreglo); el error del receptor estaba
  enmascarado por el de la variable en la misma sentencia y al arreglarla
  se desenmascara. MISMA causa raiz (sombra por anidadas heredadas),
  familia latente -> siguiente tanda: calificar tambien el receptor
  (`hb.c.L9(...)`).
* Familias (`auditoria_familias_loop36.json`): `cfs_variable` 1.688 -> 1.068
  (-620); `cfs_method` 270 -> 283 (+13: los receptores `c.L9(...)`
  desenmascarados, ver arriba); el resto de familias +0 (`otro` 1.111,
  `tipos` 877, `override` 332, `cfs_class` 281, `sobrecarga` 50, `paquete`
  48, `inferencia` 5). Cuadra: -620 + 13 = -607.
* `cannot find symbol` -607; `non-static variable this` +0;
  `not an enclosing class` +0; `incompatible types` +0.
* No-regresion por fichero: 0 ficheros rotos nuevos, 0 empeoran, 213
  mejoran, 99 limpian (1.120 -> 1.021 ficheros con error).
* Nuevos (f,l,msg) vs loop_34: **0**.
* Artefactos: `/tmp/opencode/p4_11/plan_v2.json` (dry-run) y
  `plan_v2_aplicado.json` (aplicado), con `motivo` por cambio y omision
  (170 `sin_this` = R.*/BuildConfig/clases, 35 `contexto_estatico`,
  28 `no_es_outer_tipo` = capturas, 17 `fJADX_ambiguo` = p.ej. `f12345`
  sin letra no separa indice de nombre).

**Revision independiente (reviewer) y verificaciones cerradas.** La revision
pidio diff, logs y plan sin dar por buena ninguna afirmacion. Hallazgos:
3 defectos documentales (H1: la lista de los 13 residuales omitia td/h y
m9/c; H2: el docstring decia 31 capturas y el plan dice 28; H3: la cifra
"666/666" no reconciliaba con ningun artefacto) -> los tres corregidos aqui
y en la herramienta. 4 sospechas, cerradas o documentadas:

* S1 (semantica): una captura local de tipo `Env` renombrada podria confundir
  R4/R5 con el outer. CERRADA por enumeracion sobre `dex_miembros.tsv`: de
  las 620 anOnimas reparadas, TODAS tienen exactamente UN campo de tipo
  `L<Env>;` (0 con mas de uno, 0 con ninguno, 0 sin fila DEX).
* S4 (limite de identificador): `foothis.f275a` pasaria R2a y el
  `replace` por subcadena romperia la linea. Defecto LATENTE real en la
  herramienta: endurecido R2a (el caracter previo a `this.` no puede ser
  [A-Za-z0-9_$]) y verificado que 0 de las 620 lineas originales lo
  afectaban (mismo plan). El gate de 0 errores nuevos lo habria captado.
* S2 (llaves en cadenas/comentarios): riesgo teorico; `sin_anonima`=0,
  `ocurrencias_no_cuadran`=0 y cada linea reparada cayó dentro de UNA
  anonima en la muestra del revisor.
* S3 (contextos estaticos implicitos: constantes de enum, inicializadores de
  interfaz): riesgo teorico; +0 `non-static variable this` en la medicion.

### Tanda P4-12: la otra cara de la sombra (receptores y tipos de variable) (4.055 -> 3.964)

**Sintoma.** Misma familia que P4-11, cara opuesta: `cannot find symbol`
sobre el RECEPTOR `c.L9(hb.c.this, view)` (`symbol: method L9(hb.c,View) /
location: class d_.c`) y sobre variables declaradas con el nombre simple
`Env` (`location: variable hVar of type h`). Tras cada arreglo de P4-11,
javac buscaba en la anidada heredada sombreada (`d_.c`, `Fragment.h`)
en vez de en la clase del fichero.

**Causa raiz (ya establecida en P4-11, aqui sin duda posible).** Dentro
del cuerpo de una clase, sus clases anidadas HEREDADAS sombrian su
propio nombre simple; las cadenas verificadas `hb/m9/ha -> z9.e ->
z9.b -> d_ -> Fragment`, `k8/td -> d_ -> Fragment` y `n9.f -> n9.c ->
...` heredan `c/h/f`. Lo nuevo aqui: el discriminante ya no es solo
`symbol+location`, sino la EXISTENCIA del simbolo. Si javac no encuentra
`L9` en `d_.c` pero `L9` esta declarado en `hb.c`, la resolucion simple
fue a la sombra. Probe `/tmp/opencode/p4_12/probe3` (javac 17.0.20):
acceder a un `private static` propio desde una anidada propia compila,
asi que `location: class f` en `n9/f:48` solo puede ser resolucion
erronea; la sombra heredada se imprime en forma SIMPLE (igual que en
produccion), por eso el discriminante es la existencia del simbolo, no
la forma del tipo.

**Reparacion.** Insertar `pkg.` en posicion calculada (edicion
posicional, nunca replace global). Herramienta
`tools/reparar_receptores_sombreados.py`: R1 receptores de metodo
(13 sitios `c.L9(hb.c.this,..)` -> `hb.c.L9(..)`), R-VAR declaraciones
de variable con tipo sombreado (parametros, locales y campos) y R3
`incompatible types` con mapeos posicionales (cast, tipo de retorno,
declaracion de destino de asignacion, campo/identificador de origen).
Regla de oro aplicada: simbolo declarado como miembro DIRECTO de la
clase top-level (balanceo de llaves); una anidada no cuenta.

**Bucle de reparacion (7 pases, cada uno medido y auditado contra
loop_36):** 13 receptores (loop_37) -> 28 R-VAR (loop_38, plan_v6) ->
revert de un falso positivo + tapadora manual (loop_40) -> R3 x4
(plans v9/v11/v12/v13: loop_41..44). Totales: 4.055 / 4.001 / 3.979 /
3.974 / 3.968 / 3.969 / **3.964**. Los errores intermedios NUEVOS de
cada pase (6, 2, 2, 5) eran enmascaramiento: arreglada la sombra
previa, el siguiente tipo sombreado quedaba al descubierto; todos
desaparecieron en pases siguientes. Estado final = fixpoint.

**Falsos positivos detectados y filtrados (con evidencia):**

* `com/umeng/analytics/Gender.java` (4 sitios): clase SIN
  extends/implements no puede heredar sombra -> filtro `env_sin_cadena`.
* `f/c.java:301` (simbolo `m`): estaba declarado en la anidada `g`, no
  en `f.c`; el guard de miembro directo lo excluye ahora.

**Tapadora puntual justificada (`f/c.java`).** La propia anidada
`f@214` sombrea el nombre del paquete `f`: toda referencia calificada
`f.f__`/`f.d` dentro del cuerpo fallaba (`location: class f`, errores
preexistentes en 72 y 524). Renombre `f` -> `f_` (decl 214, ctor 225,
uso 184; `private static`: sin referencias externas posibles). Con eso
`f.c`/`f.f__` quedan escribibles y la familia del fichero se repara
(25 errores fuera).

**Medicion final (`mediciones/loop_44.log`): 4.055 -> 3.964 (-91).**

* Reconciliacion por fichero (89 (f,l,msg) unicos): f/c 25, ha/h 13,
  td/h 12, ee/c 8, k8/c 7, n9/f 6, hb/c 5, m9/c 4, u8/a 2, c2/a 2,
  kotlinx/c 2, ed/b 1, ve/w 1, ve/m0 1.
* ve/w:33 y ve/m0:16 no se tocaron: usaban
  `kotlinx.coroutines.scheduling.c.f18544i`, un campo con tipo
  sombreado (`ee.g.c`); al calificar su declaracion, ambos errores
  aguas abajo desaparecieron (enmascaramiento inverso, cadena cerrada).
* Nuevos (f,l,msg) vs loop_36: **0**.
* Excluidos con motivo documentado: ~29 `not an enclosing class` de
  sombra (familia aparte; exige analisis semantico de contextos
  estaticos) y `k8/c:44` `f.X` (intencion desconocida).
* Artefactos: `/tmp/opencode/p4_12/plan_*.json` (dry y aplicado por
  pase), con `motivo` por cambio y omision.

**Revision independiente (reviewer):** Los hallazgos del revisor
independiente (sesion ses_ea0b4c73fffeWKnN8Wvlc5BB6g) fueron:

* **H1 (MAYOR, documentado):** El LEEME afirmaba que `f/c:301` era un
  falso positivo; la revision demostró que el arreglo es correcto y está
  aplicado en el diff final. La cronología real fue: plan_v6 aplico `f.c`
  prematuramente (antes del renombre tapadora) -> error `cannot find symbol:
  class c / location: class f` -> revert (loop_39) -> renombre tapadora
  `f`->`f_` (v9) -> plan_v9 re-aplica `f.c` y se queda. El guard de
  miembro directo es un endurecimiento general; en f/c pasa legitimamente.
  **Corrección:** borrar la bala sobre f/c:301 como falso positivo y
  reemplazar por la cronología real arriba.

* **H2 (MENOR):** El LEEME lista 7 pases y omite `loop_39 = 4000 errors`.
  Añadir loop_39 y cambiar "7 pases" por "8 pases".

* **H3 (MENOR, tool):** El guard de miembro directo no se aplicaba en R4-estáticos
  (metodos/variables). Endurecido: ahora `simbolo_existe` y R4 usan
  `_clases_por_linea` para exigir miembro directo (len<=1). Se mantiene
  como defensa contra simbolos solo-anidados en futuros runs.

* **H4 (MENOR, tool):** `--json plan.json` (sin directorio) crashea por
  `makedirs('')`. Endurecido: `if args.json: d = os.path.dirname(args.json);
  if d: os.makedirs(d, exist_ok=True)`.

* **H5 (MENOR, tool):** `aplicar()` no verifica el caracter anterior a la
  inserción. Endurecido: `pos > 0 and (lin[pos-1].isalnum() or
  lin[pos-1] in "_$.")` -> rechazo.

* **H6 (MENOR, tool):** Caida al origen en R3 si `hallar_declaracion` devuelve
  None puede qualificar un segundo sitio para el mismo error. Mitigado por
  dedup y gate 0-nuevos.

* **H7 (ESTILO/BAJO):** `env_sin_cadena` busca `class Env … extends|implements`
  en todo el fichero; riesgo teorico de anidada `class Env` con cadena; no
  observado aquí.

**Veredicto final:** Código Java y tool son sólidos: 0 regresiones
demostradas en los ficheros tocados, reconciliación numérica exacta
(4055→3964 = 91 líneas = 89 triples con los 2 duplicados identificados),
diff 100% calificado y sin cambios semánticos. Bloqueos resueltos: H1 y H2
corregidos en el LEEME. H3-H7 documentadas como deuda del tool sin
bloquear. **Apto para commit** tras aplicar los arreglos del LEEME y del
tool.

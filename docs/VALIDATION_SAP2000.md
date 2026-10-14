# SAP2000: validación de queries B1.1–B1.3 y Command B1.4

## Preparación

- Windows, Python >= 3.11 y SAP2000 con `SAP2000v1.Helper` registrado.
- SAP2000 abierto con un `.sdb` existente cargado. Usar la misma sesión de
  Windows y nivel de privilegios para Python y SAP2000.
- Desde la raíz del repositorio, instalar `python -m pip install -e ".[dev,sap2000]"`.
  `comtypes` es opcional y solo se instala en Windows; el core no lo importa.
- Si hay varias instancias, `cHelper.GetObject` selecciona la instancia activa
  según CSI. Este spike no añade selección por proceso ni reconexión automática.

## Diagnóstico

1. Registrar el modelo abierto, unidades y estado de cambios pendientes. Opcionalmente
   registrar el SHA256 del `.sdb` con `Get-FileHash -LiteralPath 'C:\modelos\modelo.sdb'`.
2. Ejecutar `python -m jym_structural.adapters.sap2000`.
3. Esperar código de salida 0 y únicamente un JSON en stdout, por ejemplo:

   ```json
   {
     "software": "SAP2000",
     "version": "26.2.0",
     "model_name": "modelo.sdb",
     "model_path": "C:\\modelos\\modelo.sdb",
     "units": "kgf_m_C"
   }
   ```

4. Comprobar que nombre (con extensión), ruta y unidades coinciden con SAP2000.
   No debe cambiar el estado de edición, las unidades ni los resultados del modelo.
   Si se registró el hash, comprobar que sigue igual.
5. Para comprobar la salud de la misma conexión, ejecutar:

   ```python
   from jym_structural.adapters.sap2000 import ComSap2000Gateway

   gateway = ComSap2000Gateway()
   assert gateway.health_check() is False
   info = gateway.connect_to_running_instance()
   assert gateway.health_check() is True
   ```

   En una prueba manual separada, tras cerrar SAP2000, la misma conexión debe
   devolver `False` al consultar su salud. No inicia ni reconecta SAP2000.
6. Sin instancia accesible, o sin modelo guardado cargado, el diagnóstico debe
   terminar con código 1, mensaje en stderr y sin JSON parcial en stdout.

## Decisiones del adaptador

- En las queries B1.1–B1.3 se crea únicamente el helper COM; `GetObject` adjunta una instancia existente.
  No se llama a ApplicationStart, InitializeNewModel, Save, SetPresentUnits ni RunAnalysis.
- Las únicas consultas de conexión B1.1 son `GetVersion`, `GetModelFilename(True)` y
  `GetPresentUnits`. `health_check()` repite estas lecturas sin efectos de escritura.
- Se valida el retorno CSI de `GetVersion`; los otros dos métodos retornan
  directamente una cadena y el enum de unidades. La salida tipada de comtypes
  para GetVersion es `(version, version_number, return_code)`.
- Los 16 valores de `eUnits` se traducen a nombres estables del adaptador; un
  valor desconocido produce error. Solo sale `ModelInfo` hacia el core.
- `ComSap2000Gateway` implementa explícitamente `Sap2000ConnectionGateway` (B1.1)
  y `Sap2000ModelReader` (B1.2/B1.3). B1.4 añade `Sap2000AnalysisRunner` como
  Command explícito. No implementa `Sap2000ResultsReader`; no se añaden métodos vacíos.
- Se mantiene la conexión en el hilo COM que la creó. Los errores se presentan
  como `Sap2000Error`, conservando su causa; la salud se informa como booleano.
- Referencia primaria: `SAP2000v1.dll` y `CSI_OAPI_Documentation.chm` de la instalación
  SAP2000 26. Las firmas de lectura y los nombres de eUnits se contrastaron con
  la DLL instalada. Véase también [documentación API de CSI](https://www.csiamerica.com/developer).

## Registro de ejecución — 13 de octubre de 2026 (America/Lima)

- Windows; comtypes 1.4.17; SAP2000 26.2.0.
- Modelo existente: `pm_corregido.sdb` (carpeta Downloads del usuario).
- Diagnóstico real: salida 0 y JSON con nombre/ruta correctos y `units: kgf_m_C`.
- Conexión real seguida de `health_check()`: `True`.
- SHA256 del `.sdb` idéntico antes y después de conectar y consultar salud:
  `42F0CC0DDC6D6D5156C42A7820668C5DF21D7047879FA820D57483F354A3ED10`.
- Dentro del aislamiento del agente, GetObject devolvió `None`; fuera del
  aislamiento se completaron las lecturas. El diagnóstico informa este fallo
  sin crear otra instancia.
- No se cerró SAP2000 ni se cambió el modelo para probar errores. Los casos de
  desconexión, falta de instancia, modelo sin guardar, retornos CSI fallidos y
  unidades inválidas se verifican mediante dobles en los tests unitarios.
- El hash acredita que el archivo persistido no cambió; no mide el estado en
  memoria. La prueba automatizada restringe el modelo doble a las tres consultas
  permitidas y comprueba la secuencia de llamadas.

## Pruebas automatizadas

```powershell
python -m pytest -q -p no:cacheprovider
python -m ruff check src tests
```

Se pueden ejecutar sin SAP2000, COM ni Windows. Cubren normalización, las 16
unidades, validación de errores, salud, y los canales y códigos de salida del CLI.

## B1.2: inventario estructural

Ejecutar, con un `.sdb` existente abierto:

```powershell
python -m jym_structural.adapters.sap2000 --inventory
```

Sin `--inventory` se mantiene el diagnóstico de conexión B1.1. El inventario incluye
`model`, `counts`, `sources`, `sections` y `members`. Las dos consultas del gateway
retornan exclusivamente listas de `Section` y `Member` del core. El CLI añade
el contexto de procedencia y unidades al JSON, sin tipos COM.

### Firmas contrastadas con SAP2000 26.2.0

Se inspeccionaron `SAP2000v1.dll`, los `paramflags` del módulo generado por comtypes
y respuestas reales. Los parámetros `[in,out]` se pueden omitir en estas llamadas
tipadas: comtypes los devuelve en el orden declarado, seguidos de `pRetVal` (CSI).
Los inputs con nombre evitan confundir argumentos opcionales con parámetros de salida.

| Consulta | Inputs utilizados | Salidas comtypes, en orden verificado |
| --- | --- | --- |
| `FrameObj.GetNameList` | ninguno | `NumberNames, MyName, pRetVal` |
| `PropFrame.GetNameList` | ninguno; `PropType=0` por defecto (todas) | `NumberNames, MyName, pRetVal` |
| `FrameObj.GetPoints` | `Name=frame` | `Point1, Point2, pRetVal` |
| `FrameObj.GetSection` | `Name=frame` | `PropName, SAuto, pRetVal` |
| `PropFrame.GetMaterial` | `Name=section` | `MatProp, pRetVal` |
| `PointObj.GetCoordCartesian` | `Name=point, CSys="Global"` | `X, Y, Z, pRetVal` |

El adaptador mapea explícitamente las salidas por sus nombres y valida cada código
CSI antes de consumir datos. No busca el código por tipo o valor (un cero puede
ser coordenada, conteo o status). Rechaza formas u órdenes no verificados en vez
de reinterpretarlos silenciosamente. Normaliza SAFEARRAY como lista/tupla y admite
`None` solo para el array vacío con conteo cero; valida conteo, nombres y duplicados.

### Semántica y límites de los datos

- Los frames y secciones se ordenan por identificador/nombre, de forma lexicográfica,
  independiente del orden devuelto por CSI. `Member.id` y `Member.name` conservan
  el nombre único del objeto frame; no son índices del array ni nombres de elementos
  de análisis.
- `start_node` y `end_node` son `Point1` (I) y `Point2` (J), sin intercambiar extremos.
- `Member.section` conserva `GetSection.PropName`, la propiedad concreta actual.
  `SAuto` es una lista de selección automática distinta: no se sustituye por ella
  la propiedad concreta ni se ejecuta análisis para resolverla. Una asignación
  vacía o `"None"` se expresa como `null`.
- `list_sections()` enumera todas las propiedades frame definidas, incluidas las
  no utilizadas. `Section.material` procede de `PropFrame.GetMaterial`, nunca
  del nombre del perfil. Se puede asociar mediante `member.section == section.name`.
  Describe el material de la propiedad, sin afirmar un material efectivo del frame
  ante posibles overrides. No se añaden campos al core.
- Un material vacío se expresa como `null`; un fallo CSI al consultar cualquier
  propiedad, incluso una especial que no admita esa consulta, produce error explícito.
  No se deduce un material ni se devuelve un inventario parcial como si fuera completo.
  `Section.family` queda `null`, sin clasificaciones inferidas.
- `Member.length` es un dato **derivado**: distancia euclídea I-J calculada con XYZ
  de ambos puntos en `Global`, en las unidades de longitud activas. No es longitud
  de análisis, longitud libre entre offsets ni longitud de arco de un objeto curvo.
  Las coordenadas se guardan solo durante cada llamada para reutilizar puntos comunes;
  se vuelven a leer en el siguiente inventario. Se rechazan coordenadas/longitudes
  no finitas.
- Las consultas requieren conexión explícita B1.1. No reconectan, cambian unidades,
  seleccionan objetos ni bloquean el modelo. Ejecutar con el modelo en reposo:
  estas lecturas sucesivas no constituyen una transacción ante ediciones concurrentes.

### Repetición manual y comprobación del archivo

1. Ejecutar el diagnóstico B1.1 y registrar ruta, versión y unidades.
2. Registrar SHA256 y `LastWriteTimeUtc` del `.sdb` con `Get-FileHash` y `Get-Item`.
3. Ejecutar dos veces `--inventory`, guardar ambos JSON fuera del archivo del modelo
   y comprobar que son iguales, que los conteos coinciden y que las referencias
   `member.section` se encuentran en `sections` (salvo asignaciones `null`).
4. Comprobar `health_check()`, repetir metadatos/unidades y comparar hash y fecha
   del `.sdb`. Comprobar en SAP2000 que no cambió el estado de edición.
5. Conservar el JSON real y los hashes como evidencia. No usar comandos de guardar,
   análisis ni cambios de unidades como parte de la prueba.

### Registro real B1.2 — 13 de octubre de 2026 (America/Lima)

- SAP2000 **26.2.0**, comtypes **1.4.17**, modelo `pm_corregido.sdb`, unidades `kgf_m_C`.
- Dos ejecuciones completas del CLI, salida **0**, JSON idéntico: **19 secciones,
  449 frames**. Todas las referencias de sección se encontraron en el catálogo.
- `health_check()`: **True**; metadatos y unidades idénticos tras ambas ejecuciones.
- SHA256 antes y después:
  `42f0cc0ddc6d6d5156c42a7820668c5df21d7047879fa820d57483f354a3ed10`.
- Fecha de modificación del `.sdb` sin cambios. No se usaron operaciones de escritura
  ni análisis. El hash/fecha verifican el archivo persistido; no acreditan por sí
  solos el estado de edición en memoria. Los dobles restringen las APIs del inventario
  a las seis consultas de lectura indicadas arriba.
- JSON real completo: [examples/sap2000_inventory.json](examples/sap2000_inventory.json).
  Ejemplo extraído de ese inventario (longitud en metros):

  ```json
  {
    "section": {"name": "W10X39", "material": "A36", "family": null},
    "member": {
      "id": "1", "name": "1", "section": "W10X39",
      "start_node": "1", "end_node": "2", "length": 5.86
    }
  }
  ```

Pruebas B1.2 adicionales: topología y materiales, geometría 3D, coordenadas globales,
arrays reordenados/inválidos, errores de las seis APIs CSI, modelo vacío, conexión
requerida, desconexión COM, asignaciones sin sección/material y CLI sin salida parcial
ante fallo. Los tests B1.1 siguen verificando la conexión y las unidades.

Resultado de cierre: `pytest -q`: **61 passed**, con una advertencia de permisos al
escribir la caché de pytest; `ruff check src tests`: **All checks passed**;
`git diff --check`: sin errores de whitespace.

## B1.3: Structural Core Geometry

### Contrato neutral y decisiones

- `Point3D(x, y, z)` valida números finitos en el Core (NaN e infinitos se rechazan).
- `Node(id, position)` conserva el identificador fuente y una posición cartesiana.
- `StructuralModel(model_info, length_unit, nodes, sections, members)` agrega los
  modelos del Core. `length_unit` es obligatorio y no vacío: se aplica a XYZ y
  longitudes. No interpreta enums SAP2000 ni convierte automáticamente a SI.
- Se mantienen `ModelInfo`, `Member` y `Section` compatibles con B1.1/B1.2.
  `Section.name` es la clave de sección existente. `Member.start_node/end_node`
  siguen siendo IDs, sin objetos Node incrustados. Aunque un Member aislado puede
  omitir extremos por compatibilidad, dentro de StructuralModel ambos son obligatorios
  y deben referenciar nodos existentes.
- Un validador Pydantic en `StructuralModel` rechaza IDs duplicados de nodos/miembros,
  nombres duplicados de secciones y referencias a nodos/secciones inexistentes.
  Una sección nula se permite. Las colecciones de entrada son listas: no se convierten
  a diccionarios antes de validar ni se descartan duplicados. Un modelo sin miembros
  puede tener colecciones vacías o nodos aislados aportados por otros adapters.
- Estas invariantes se comprueban al construir/deserializar el modelo; si un consumidor
  edita posteriormente listas u objetos, debe revalidar antes de tratarlos como snapshot.
  El Core no contiene dependencias, códigos ni tipos CSI/COM.

### Lectura SAP2000

```python
from jym_structural.adapters.sap2000 import ComSap2000Gateway

gateway = ComSap2000Gateway()
gateway.connect_to_running_instance()
model = gateway.read_structural_model()
print(len(model.nodes), len(model.members), len(model.sections), model.length_unit)
# Con pm_corregido.sdb: 254 449 19 m
```

`Sap2000ModelReader` incorpora `read_structural_model()`. La implementación comparte
con `list_members()` la lectura de extremos y coordenadas: una consulta por nodo único
durante cada snapshot, usada también para calcular las longitudes I-J. Los nodos se
ordenan lexicográficamente por ID sin renumerar, recortar ni normalizar los nombres.
Compartir un mismo extremo entre miembros crea una única entidad Node; no es un
descarte de entidades fuente duplicadas.

El snapshot incluye **solo los nodos referenciados por frames**; no enumera puntos
aislados mediante una API adicional. Incluye todas las secciones del inventario B1.2.
Usa exclusivamente las consultas ya validadas: `FrameObj.GetNameList/GetPoints/GetSection`,
`PropFrame.GetNameList/GetMaterial`, `PointObj.GetCoordCartesian(Name=..., CSys="Global")`
y las tres consultas de metadatos B1.1. Se mantienen los códigos CSI y órdenes de
salidas documentados arriba. La finitud de XYZ se valida mediante Point3D; el adapter
traduce fallos de coordenadas a Sap2000Error conservando la causa de Pydantic.

La unidad se obtiene dentro del adapter del enum ya normalizado en `ModelInfo.units`
(`kgf_m_C` → `m`, `kip_ft_F` → `ft`). Las coordenadas y longitudes se conservan
numéricamente en esas unidades. Se releen metadatos/unidades al terminar para rechazar
cambios detectables durante la lectura. No se bloquea ni modifica el modelo; se
mantiene la recomendación de ejecutarlo en reposo, sin garantía de transacción ante
ediciones concurrentes.

### Registro real B1.3 — 13 de octubre de 2026 (America/Lima)

Se siguió la misma comprobación de hash y fecha descrita en B1.2, usando
`read_structural_model()` dos veces y validando el modelo completo con el Core.

| Comprobación | Resultado |
| --- | --- |
| SAP2000 | 26.2.0 |
| Archivo | `pm_corregido.sdb`, mismo archivo de B1.2 |
| Nodos únicos de extremos | **254** |
| Frames | **449**, esperado 449 |
| Secciones | **19**, esperado 19 |
| Unidades fuente / longitud | `kgf_m_C` / **m** |
| Dos snapshots consecutivos | Idénticos |
| Salud posterior | True |
| Validadores del Core sobre modelo completo | Aprobados |

SHA256 **antes y después**:
`42f0cc0ddc6d6d5156c42a7820668c5df21d7047879fa820d57483f354a3ed10`.

Fecha de modificación **antes y después (UTC)**:
`2026-10-12T05:45:32.091158+00:00`.
También se comparó el valor de precisión original `mtime_ns`: `1791783932091158100`,
idéntico. Estas comprobaciones acreditan que el archivo persistido no cambió, no
constituyen por sí solas una inspección de la memoria de SAP2000.

Ejemplo pequeño real: [examples/structural_model_excerpt.json](examples/structural_model_excerpt.json).
Contiene los conteos completos, evidencia antes/después y un `structural_model_excerpt`
validado por el Core con 2 miembros, sus 4 nodos y 2 secciones. No es otro volcado del
modelo completo. El inventario grande anterior de B1.2 se conserva sin duplicarlo.

Las pruebas nuevas cubren modelo válido y round-trip JSON, duplicados de las tres
colecciones, referencias de ambos extremos, sección inexistente/nula, NaN/Inf en
los tres ejes, modelo vacío, conservación de IDs y de unidades no SI, fallos CSI
de coordenadas y cambios de unidades durante la lectura. Se mantienen los tests
de B1.1 y B1.2.

Resultado de cierre B1.3: `pytest -q`: **91 passed** (una advertencia de permisos
al escribir la caché); `ruff check src tests`: **All checks passed**;
`git diff --check`: sin errores.

## B1.4: SAP2000 Analysis Command

### Frontera de comando

`ComSap2000Gateway.run_analysis() -> None` requiere conexión B1.1 ya establecida.
Solo esa llamada explícita ejecuta análisis. Se mantiene `Sap2000AnalysisRunner`
como protocolo independiente de conexión, lectura de modelo y lectura de resultados.
El Structural Core y StructuralModel no cambian y no contienen estado ni resultados CSI.

El comando llama **una sola vez** a `SapModel.Analyze.RunAnalysis()` con las opciones
de casos que ya tenga el modelo. No reconecta ni reintenta, no cambia selección de
casos/combinaciones, unidades, geometría, cargas ni propiedades, no llama a File.Save
y no bloquea/desbloquea mediante SetModelIsLocked. La propia ejecución CSI puede
cambiar estado de análisis, bloqueo y archivos: B1.4 no es read-only.

### Firma exacta y documentación contrastada

- DLL instalada SAP2000 26: `SAP2000v1.cAnalyze`: **`Int32 RunAnalysis()`**.
- Typelib comtypes 1.4.17: `RunAnalysis`, `restype=HRESULT`, un único parámetro
  `POINTER(c_long)` con `paramflags=((10, 'pRetVal'),)`: `[out, retval]`.
  No hay parámetros de entrada. El HRESULT de transporte COM no es el código CSI.
- Documentación instalada `CSI_OAPI_Documentation.chm`, tema
  `SAP2000_API_Fuctions/Analyze/RunAnalysis.htm`: **`Function RunAnalysis() As Long`**,
  sin parámetros. CSI crea el modelo de análisis como parte de la operación.
  El modelo debe tener ruta definida; B1.1 ya exige un modelo existente guardado.
  No se crea ni guarda uno nuevo para satisfacer la precondición.
- comtypes devuelve un **entero escalar**, no una tupla/lista: `0` indica ejecución
  satisfactoria de la operación según CSI; cualquier entero distinto de cero produce
  Sap2000Error. No se inventan significados específicos para otros códigos.
- Un fallo COM se envuelve en Sap2000Error con `raise ... from exc`; un retorno de
  forma no verificada (None, lista, booleano, etc.) se rechaza. No se añade
  compatibilidad especulativa con respuestas alternativas.

### CLI e intención explícita

```powershell
python -m jym_structural.adapters.sap2000                # B1.1: solo lectura
python -m jym_structural.adapters.sap2000 --inventory    # B1.2: solo lectura
python -m jym_structural.adapters.sap2000 --run-analysis # B1.4: COMMAND
```

Las opciones `--inventory` y `--run-analysis` son mutuamente excluyentes: combinarlas
produce salida 2 antes de conectar. No se añaden pipelines automáticos. Al completar
la llamada CSI, el comando imprime `{"command": "run_analysis", "status": "completed"}`;
esto no certifica la validez ingenieril del modelo ni interpreta resultados de casos.
Un error produce salida 1, mensaje en stderr y ninguna salida de éxito en stdout.

### Evidencia automatizada de separación Query / Command

- Las pruebas de B1.4 comprueban conexión obligatoria, una sola llamada CSI sin
  argumentos, éxito 0, error no cero, rechazo de respuestas no verificadas y
  conservación de la causa COM sin reintento ni reconexión.
- Un doble estricto del modelo exige que run_analysis solo llame a
  `Analyze.RunAnalysis`: no puede guardar, modificar unidades ni leer resultados.
- El doble de inventario dispone de un espía Analyze.RunAnalysis. La prueba ejecuta
  conexión, health_check, list_sections, list_members, read_structural_model y los
  CLI sin flag/con --inventory, y comprueba que el espía nunca se llamó.
- Se comprueba por separado health_check, el CLI explícito y sus fallos. El CLI de
  análisis no llama al inventario. Los tests anteriores de B1.1–B1.3 siguen activos.

### Procedimiento de validación real

1. Conservar el archivo y la instancia originales. Copiar el `.sdb` de B1.3 a una
   carpeta desechable y abrir la copia en una instancia SAP2000 26.2.0 separada.
   Esta preparación pertenece al ensayo, no al adapter productivo.
2. Conectar B1.1 a esa instancia ya abierta y comprobar que la ruta es la de la copia.
   Registrar hash, LastWriteTimeUtc, tamaño, metadatos, unidades y health_check.
3. Para observar únicamente el estado, usar las consultas documentadas de diagnóstico
   `GetModelIsLocked() -> bool` y
   `Analyze.GetCaseStatus() -> (NumberItems, CaseName, Status, pRetVal)`.
   Validar el código CSI de GetCaseStatus y correspondencia entre conteo y arrays.
   Estados CSI: 1=no ejecutado, 2=no pudo iniciar, 3=no finalizado, 4=finalizado.
   Estas consultas son solo instrumentación del ensayo, sin extender el gateway
   con lectura de casos, fuerzas, desplazamientos ni reacciones.
4. Invocar exactamente una vez `gateway.run_analysis()`. No reintentar, guardar,
   ajustar casos ni desbloquear el modelo si falla.
5. Repetir las lecturas de estado y archivo; verificar acceso, metadatos y unidades.
   Investigar cambios del `.sdb`, sin imponer igualdad de hash a un Command.
6. Cerrar solo la instancia desechable sin guardar explícitamente y preservar la
   instancia original. Registrar los cambios en disco y memoria observables.

### Registro real B1.4 — 13 de octubre de 2026 (America/Lima)

- SAP2000 **26.2.0**, comtypes **1.4.17**. Se copió `pm_corregido.sdb` a
  `.venv/b14-validation/pm_corregido_b14.sdb`, sin archivos previos de análisis.
- Preparación aislada del ensayo: `cHelper.CreateObjectProgID` y
  `ApplicationStart(Visible=False, FileName=copia)` abrieron una instancia nueva.
  El gateway recibió una referencia a esa instancia ya abierta mediante su punto
  de inyección de conexión B1.1. El adapter productivo sigue usando GetObject;
  no crea instancias ni incluye lógica de preparación de pruebas.
- Se invocó **una vez** `gateway.run_analysis()`. Una frontera instrumental registró
  el retorno real **`0`** (int) y únicamente `Analyze.RunAnalysis` durante el comando.
  Esa frontera solo expuso las tres consultas de metadatos y Analyze.RunAnalysis:
  no ofreció acceso a File.Save, setters ni resultados.
- Ruta/nombre de la copia y unidades **`kgf_m_C`** idénticos antes/después;
  health_check **True → True**. No se seleccionaron casos ni se tocaron sus opciones.
- Estado observado mediante las consultas read-only del ensayo:
  **7 casos en estado 1 (no ejecutado) → 7 casos en estado 4 (finalizado)**;
  `GetModelIsLocked`: **False → True**, cambio natural de SAP2000 al analizar.
  El adapter no llamó SetModelIsLocked ni intentó revertir ese estado.
- El log de SAP2000 registró una ejecución y su finalización satisfactoria. No se
  consultaron fuerzas, desplazamientos, reacciones ni resultados de diseño.

La copia **sí cambió en disco** durante RunAnalysis, antes de cerrar la instancia:

| Dato de la copia | Antes | Después |
| --- | --- | --- |
| SHA256 | `42f0cc0ddc6d6d5156c42a7820668c5df21d7047879fa820d57483f354a3ed10` | `4a076e1f4c673e37575fe88be7f6ac43eb034b334e0b3e9f342d8508b944ace0` |
| LastWriteTimeUtc | `2026-10-12T05:45:32.091158+00:00` | `2026-10-14T04:01:04.001472+00:00` |
| mtime_ns | `1791783932091158100` | `1791950464001471500` |
| Tamaño | 120555 bytes | 116679 bytes |

Se investigó el cambio antes de dar por aprobada la validación:

- La ayuda instalada `SAP2000.chm`, tema `Menus/File/Save_and_Save_As.htm`, indica
  que SAP2000 guarda automáticamente el modelo cuando se ejecuta análisis.
  La misma explicación está en la [documentación oficial CSI de Save/Save As](https://docs.csiamerica.com/help-files/sap/Menus/File/Save_and_Save_As.htm).
- El `.sbk` automático tiene SHA256 idéntico al `.sdb` previo al Command; también
  aparecieron `.$2k`, `.LOG`, `.OUT` y archivos de análisis de SAP2000.
- La copia mantuvo su hash/fecha posteriores tras `ApplicationExit(False)`, usado
  únicamente para cerrar la instancia desechable sin guardar desde nuestro código.
  Por tanto, el cambio ocurrió durante RunAnalysis, no durante ese cierre.
- La instancia original siguió abierta y sus metadatos se conservaron. El `.sdb`
  original mantuvo exactamente su hash
  `42f0cc0ddc6d6d5156c42a7820668c5df21d7047879fa820d57483f354a3ed10`
  y su fecha `2026-10-12T05:45:32.091158+00:00`.

Este es un guardado interno documentado de SAP2000 durante análisis, **no una llamada
del adapter a File.Save**. No se exige igualdad de hash para B1.4 ni se intenta
impedir/revertir el comportamiento natural del programa. La validación no certifica
la corrección ingenieril de los casos; solo la frontera de ejecución y sus efectos
observables. No se implementa B1.5.

Evidencia compacta de antes/después y llamadas:
[examples/sap2000_analysis_validation.json](examples/sap2000_analysis_validation.json).

Resultado automático B1.4: **109 tests aprobados**, incluyendo 18 casos adicionales
sobre la base B1.3; advertencia de permisos de caché de pytest. Ruff y
`git diff --check` sin errores.

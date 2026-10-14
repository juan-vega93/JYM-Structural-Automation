# SAP2000 B1.1 y B1.2: validación de solo lectura

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

- Se crea únicamente el helper COM; `GetObject` adjunta una instancia existente.
  No se llama a ApplicationStart, InitializeNewModel, Save, SetPresentUnits ni RunAnalysis.
- Las únicas consultas de conexión B1.1 son `GetVersion`, `GetModelFilename(True)` y
  `GetPresentUnits`. `health_check()` repite estas lecturas sin efectos de escritura.
- Se valida el retorno CSI de `GetVersion`; los otros dos métodos retornan
  directamente una cadena y el enum de unidades. La salida tipada de comtypes
  para GetVersion es `(version, version_number, return_code)`.
- Los 16 valores de `eUnits` se traducen a nombres estables del adaptador; un
  valor desconocido produce error. Solo sale `ModelInfo` hacia el core.
- `ComSap2000Gateway` implementa explícitamente `Sap2000ConnectionGateway` (B1.1)
  y `Sap2000ModelReader` (B1.2). No implementa `Sap2000AnalysisRunner` ni
  `Sap2000ResultsReader`; no se añaden implementaciones vacías.
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

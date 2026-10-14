# SAP2000 B1.1: validación de solo lectura

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
- Las únicas consultas del modelo son `GetVersion`, `GetModelFilename(True)` y
  `GetPresentUnits`. `health_check()` repite estas lecturas sin efectos de escritura.
- Se valida el retorno CSI de `GetVersion`; los otros dos métodos retornan
  directamente una cadena y el enum de unidades. La salida tipada de comtypes
  para GetVersion es `(version, version_number, return_code)`.
- Los 16 valores de `eUnits` se traducen a nombres estables del adaptador; un
  valor desconocido produce error. Solo sale `ModelInfo` hacia el core.
- `ComSap2000Gateway` implementa el subconjunto B1.1 del contrato previsto.
  Los métodos de miembros, secciones, análisis y resultados del protocolo existente
  quedan para sus respectivos issues; no se añaden implementaciones vacías.
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

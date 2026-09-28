# Glass Master Inventario — versión revisada

Esta entrega conserva la interfaz de Streamlit y las cuatro sucursales del programa enviado. Las operaciones se procesan mediante `InventarioAPI.gs`, un servicio en Google Apps Script que controla las escrituras de todas las sucursales. **No basta con sustituir solamente `app.py`: también hay que configurar el servicio y sus secretos.**

## Archivos

| Archivo | Función |
|---|---|
| `app.py` | Interfaz corregida; formularios, roles, consulta y seguimiento de operaciones. |
| `gac_client.py` | Comunicación entre Streamlit y Apps Script. Debe estar junto a `app.py`. |
| `InventarioAPI.gs` | Validación, inventario, traslados, historial, bloqueo y reintentos. |
| `appsscript.json` | Configuración del proyecto de Apps Script y servicio Sheets v4. |
| `secrets.example.toml` | Ejemplo de configuración, sin contraseñas reales. |
| `requirements.txt` | Dependencias de ejecución verificadas en esta revisión. |
| `Informe_GAC.md` | Hallazgos, cambios, resultados y límites de la validación. |
| `tests/` | Generador y ejecutores reproducibles, sin acceso a Google real. |
| `resultados/` | Resultados individuales de 5,000 casos por versión y controles adicionales. |

El `logo.png` original no se adjuntó. Puedes colocar el que ya usas junto a `app.py`; si falta, la aplicación puede iniciar con el icono de respaldo.

## Configuración inicial en una copia del inventario

1. Crea una copia de tu archivo de Google Sheets. Usa esa copia para la primera configuración y las pruebas de aceptación. Conserva el archivo y código anteriores como respaldo.
2. Crea **un solo proyecto de Google Apps Script** para las cuatro sucursales. Pega `InventarioAPI.gs` en un archivo del proyecto. No crees cuatro proyectos: el bloqueo se comparte dentro de un mismo proyecto.
3. En Configuración del proyecto, muestra el manifiesto `appsscript.json` y coloca el contenido incluido. Comprueba que el servicio avanzado **Google Sheets API v4**, con identificador `Sheets`, esté habilitado. Si usas un proyecto de Google Cloud propio, habilita también la API de Sheets allí.
4. En Propiedades del script agrega `GAC_SHEET_ID`, con el ID del archivo copiado, y `GAC_API_TOKEN`, con un secreto aleatorio de al menos 32 caracteres. Para generar el secreto en tu equipo puedes ejecutar `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Este secreto no es una contraseña de sucursal y no se comparte con los operadores.
5. Revisa los encabezados indicados abajo. Desde el editor ejecuta `prepararSistema()` y autoriza el acceso a la hoja. Se agregarán IDs a los traslados pendientes, columnas de seguimiento y la pestaña `Operaciones`. Se conservan las cantidades registradas. La preparación puede repetirse sin reemplazar los IDs existentes.
6. Implementa el proyecto como **Aplicación web**, ejecutada como su propietario. El endpoint debe admitir las solicitudes del servidor de Streamlit sin una pantalla de inicio de sesión de Google; para esta variante se configura acceso **Cualquier persona** y la API valida el secreto en cada solicitud. Si la política de tu organización impide esa modalidad, esta variante requiere adaptar la autenticación; no habilites permisos diferentes suponiendo que funcionarán igual. Usa la URL terminada en `/exec`.
7. En el servidor de Streamlit coloca `app.py`, `gac_client.py`, `requirements.txt` y tu `logo.png`, si lo tienes. Copia los campos de `secrets.example.toml` a los Secrets de la aplicación, con la URL y el mismo token de Apps Script. Configura las cinco contraseñas en `[passwords]`. El código ya no contiene las contraseñas del adjunto. La cuenta de servicio de gspread deja de usarse en esta versión.
8. Instala y ejecuta con Python 3.12:

   ```bash
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```

9. En la copia, prueba un alta, una venta, un traslado con recepción parcial, una cancelación del saldo y una baja inmediata. Usa dos sesiones de sucursales distintas y verifica cantidades, permisos e historial. Esta aceptación sobre Google real queda pendiente: las pruebas entregadas usan un simulador.
10. Para operar sobre el archivo real, configura su ID, ejecuta la preparación y cambia la aplicación a esta versión. Detén antes la versión anterior y cualquier otro escritor. **Todas las escrituras deben pasar por este mismo proyecto de Apps Script.** La edición manual de celdas, scripts externos o aplicaciones antiguas no participan en su bloqueo.

Las columnas de inventario y pendientes deben contener datos, no fórmulas utilizadas como fuente de stock. La consolidación reescribe los valores de esas tablas. El servicio rechaza encabezados o datos en columnas adicionales para evitar sobrescribir un esquema diferente; si tienes extensiones propias, hay que adaptar el esquema antes de usarlo.

## Encabezados esperados

| Pestañas | Encabezados iniciales, en orden |
|---|---|
| `Inventario_Suc1` a `Inventario_Suc4` | `CLAVE, NOMBRE, RACK, CANTIDAD, FECHA` |
| `Traslados_Pendientes` | `FECHA, CLAVE, NOMBRE, CANTIDAD, ORIGEN, DESTINO` |
| `Movimientos` | `FECHA, CLAVE, TIPO, DETALLE, CANTIDAD, PRECIO, USUARIO, SUCURSAL` |

Una pestaña vacía debe tener al menos su fila de encabezados. La preparación también acepta el esquema ya actualizado.

Se añaden `ID_TRASLADO` y `RACK_ORIGEN` a pendientes; `ID_OPERACION` e `ID_TRASLADO` a movimientos; y `FECHA, ID_OPERACION, HUELLA, RESPUESTA` en `Operaciones`. No borres ni edites estos identificadores o comprobantes. En traslados anteriores se asigna un ID `LEGACY-...`; su rack de origen se deja vacío porque el dato no existía. Al cancelar se sigue solicitando el rack de retorno.

## Uso diario y conexión interrumpida

- Al confirmar un movimiento, aparece su comprobante. Pulsa **Registrar otra operación** para iniciar el siguiente. Esto también permite repetir intencionalmente una compra idéntica con un ID nuevo.
- Si una solicitud no recibe respuesta, conserva el ID mostrado y pulsa **Reintentar operación pendiente**. Se envían exactamente el mismo ID y contenido. Si ya se guardó, el servidor devuelve el comprobante sin repetir el movimiento.
- No cierres ni recargues la sesión con una operación pendiente: el comando se conserva en la sesión de Streamlit. Si se pierde la sesión, el administrador debe buscar el ID, usuario, clave y hora en `Operaciones` y `Movimientos` antes de volver a capturar. Un nuevo ID representa una nueva operación; el sistema no puede adivinar que dos capturas manuales fueron la misma compra física.
- Si Google devuelve un resultado de escritura indeterminado, el servidor conserva `GAC_ESCRITURA_INCIERTA` y bloquea nuevas escrituras. La consulta sigue disponible. Un reintento puede confirmar el comprobante y retirar el bloqueo. Si no existe comprobante, el sistema NO reenvía la escritura automáticamente: puede seguir pendiente en Google. El administrador debe revisar las ejecuciones, el ID y las hojas, confirmar que no hay solicitud en curso y resolver el incidente antes de retirar manualmente ese marcador. Nunca se borra para “probar de nuevo” sin conciliación.
- El inventario se actualiza al interactuar cuando han pasado 30 segundos, al registrar una operación o al pulsar **Actualizar datos**. No es una suscripción en vivo. Cada escritura valida el stock actual del servidor, independientemente de la vista abierta.
- La cantidad debe ser entera, positiva y no mayor de 1,000,000,000; un saldo almacenado sí puede ser cero. Pedidos admite hasta 1,000 líneas por envío. Una línea inválida rechaza el pedido completo.
- Los ceros iniciales de una clave se conservan si la hoja los almacena como texto. No se reconstruyen ceros que ya se hubieran perdido.

## Reproducir las pruebas sin usar el inventario real

Entorno utilizado: Python 3.12.14, Node 24.19.0 y las versiones de `requirements.txt`. Necesitas Node 20 o posterior para ejecutar el simulador. Los archivos de pruebas no requieren tokens, cuentas ni conexión a Google.

```bash
python -m pip install -r requirements-test.txt
python tests/cases.py
python tests/run_original.py
node tests/run_corrected.cjs
node tests/run_extra.cjs
python -m pytest -q tests/test_integration.py
```

`run_original.py` reproduce los fallos como resultados `FAIL` del programa original; no significa que el ejecutor se haya roto. La matriz tiene 40 familias y 125 variantes por familia, semilla 28092026. Los casos corregidos incluyen entradas inválidas cuya respuesta esperada es el rechazo sin efectos. El simulador verifica solicitudes atómicas, estados y errores inyectados; no mide cuotas, latencia ni capacidad real de Google.

## Fundamento técnico

Google documenta que `spreadsheets.batchUpdate` aplica juntas las solicitudes de un lote y rechaza todo el lote si alguna es inválida. El bloqueo de `LockService.getScriptLock()` coordina las ejecuciones que usan el mismo proyecto. Se necesitan ambos: la atomicidad de una escritura no protege por sí sola la lectura previa frente a otro escritor.

Referencias oficiales consultadas el 28 de septiembre de 2026:

- [Sheets: batchUpdate](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate)
- [Apps Script: LockService](https://developers.google.com/apps-script/reference/lock/lock-service)
- [Apps Script: aplicaciones web](https://developers.google.com/apps-script/guides/web)
- [Sheets: UpdateCellsRequest](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateCellsRequest)

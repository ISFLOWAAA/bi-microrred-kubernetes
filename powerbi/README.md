# powerbi/

Proyecto de Power BI en formato **PBIP**: carpetas de archivos de texto (modelo en TMDL, reporte en PBIR),
así que se versionan en Git y se pueden revisar con un *diff*. Un `.pbix` es un binario y no.

| Carpeta / archivo | Qué es |
|---|---|
| `Microrred.pbip` | El archivo que se abre (doble clic) |
| `Microrred.SemanticModel/` | Modelo (TMDL): 13 tablas importadas, 4 de apoyo (medidas, balance y 2 parámetros), 17 relaciones y 39 medidas DAX |
| `Microrred.Report/` | Reporte (`report.json`, formato clásico): 3 páginas con navegación, segmentaciones y drill-down |
| `generar_proyecto.py` | Regenera todo lo anterior desde el esquema real de la base |

## Cómo abrirlo (3 pasos)

1. Que la solución esté levantada (`k8s\levantar.ps1`): Power BI lee **PostgreSQL en `localhost:5434`**.
2. Doble clic en **`Microrred.pbip`**.
3. Cuando pida credenciales (una sola vez), elige **Base de datos** y escribe:
   - Usuario: `powerbi_lector` (solo lectura sobre `gold`; no ve los datos originales de `bronze`)
   - Contraseña: `POWERBI_DB_PASSWORD` del archivo `.env`
   - Si pregunta por cifrado, deja **desmarcada** la casilla "Cifrar conexión" (la base local no usa SSL).

La primera carga lee unas 800 000 filas por minuto y tarda 2 o 3 minutos; cuando termina, pulsa **Cerrar** en el cuadro de carga.

## Las 3 páginas

| Página | Para quién | Qué responde |
|---|---|---|
| **Resumen ejecutivo** | Dirección | ¿Cuánta energía da el sol frente a la red? ¿Cuánto cuesta la red y cuánto se ahorra? ¿Mejora mes a mes? |
| **Balance y batería** | Dirección y mantenimiento | ¿De dónde viene y a dónde va la energía? ¿Cuánto se pierde? ¿Se usa bien la batería? ¿Cuánto tiempo en isla? |
| **SolarBI y escenarios** | Investigadores y finanzas | ¿Cuánta energía consume cada modelo? ¿A qué hora conviene entrenar? ¿Qué pasa si cambia la tarifa o sube la generación solar? |

Arriba de cada página hay un **navegador de páginas** y segmentaciones de **Inversor** y **Periodo**.

## Cómo se cumple lo que pide el enunciado (§4 G)

| Requisito | Dónde |
|---|---|
| Conexión a la base de datos, no a archivos | `Microrred.SemanticModel/definition/expressions.tmdl` (`PostgreSQL.Database`) |
| Relaciones correctas | `relationships.tmdl`: estrellas con las dimensiones conformadas (fecha, hora, inversor, dispositivo) |
| Tabla de fechas propia | Tabla `Fecha`, marcada como tabla de fechas (`dataCategory: Time`, columna `Fecha` como llave) |
| Inteligencia de tiempo | `Energía solar mes anterior (kWh)` (`DATEADD`), `Variación solar vs mes anterior (%)` y `Energía solar acumulada del año (kWh)` (`TOTALYTD`) |
| Tres páginas con navegación, segmentaciones y drill-down | Navegador de páginas; segmentaciones; el gráfico de energía de la página 1 baja de **mes → día** con las flechas ⤵ |
| Balance energético | Página 2: tabla `Balance energético` + medida `Energía del concepto (kWh)` |
| Parámetro what-if | Tablas `Parámetro tarifa` (600–1 500 COP/kWh) y `Parámetro solar` (0–100 % más de generación): medidas de la carpeta *Escenarios*. Sin elegir valores, el escenario supone +20 % de generación solar y la tarifa base |

## Decisiones de diseño del modelo

- **Reporte en formato clásico, no PBIR:** PBIR (un archivo JSON por visual) es una opción en vista previa que hay
  que activar en Power BI Desktop; con ella apagada el reporte abría en blanco. El formato clásico lo lee cualquier
  versión sin configurar nada. El modelo sí va en TMDL (un archivo por tabla), que es lo que importa para el *diff* en Git.
- **Hora local calculada en PostgreSQL:** `gold.v_pbi_evento` y `gold.v_pbi_tarea` entregan las marcas de tiempo ya en
  la hora del sitio; convertir zonas horarias en Power Query falló en el conector de PostgreSQL (el 100 % de las filas daba error).

- **Energía oficial = la de `fact_energia_diaria`** (contador del inversor, o integración si ese día no hay
  contador), igual que en Grafana y en las consultas SQL: las tres herramientas dan las mismas cifras.
- **Solo histórico:** `Energía por minuto` filtra `origen = 'historico'`; las filas del simulador no entran.
- **Sin medidas implícitas** (`discourageImplicitMeasures`): todos los números son medidas DAX explícitas,
  agrupadas por carpeta (*Energía, Balance, Economía, Calidad, Tiempo, Escenarios, SolarBI, Eventos*).
- **Tarifa:** la base (864,06 COP/kWh) sale de la tabla `Tarifa`; el segmentador de escenario la reemplaza.
  Para ver el caso comercial, elegir 1 040 en el segmentador (1 036,88 en la tabla).
- **Supuesto del escenario solar:** la generación extra reduce la importación de la red kWh por kWh, sin
  exportación y sin límite de batería. Es un cálculo de orden de magnitud, no una simulación.
- **Hora local:** las marcas de tiempo se convierten a la hora del sitio (UTC+8).
- **Colores** (los mismos de Grafana): solar amarillo, consumo azul, red violeta, batería verde.

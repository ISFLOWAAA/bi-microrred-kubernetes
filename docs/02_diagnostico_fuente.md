# Diagnóstico de la fuente (§4 A)

Fuente: OpenCEM v1.0.0 (`datos/zenodo/opencem-v1.0.0.sqlite`, capa Bronze).
Cifras obtenidas con [`etl/inventario_fuente.py`](../etl/inventario_fuente.py) y
[`etl/diagnostico_calidad.py`](../etl/diagnostico_calidad.py). Inventario completo en
[`01_inventario_fuente.md`](01_inventario_fuente.md).

## 1. Qué es la fuente

Microrred real de un campus en Longgang, Shenzhen (China), hora local Asia/Shanghai (UTC+8).
Dos subsistemas independientes; cada uno con un inversor híbrido, un canal FV, un banco de baterías
de litio de 48 V y entrada de red. Las cargas son estaciones de cómputo con GPU y climatización.

| Tabla | Qué contiene | Filas | Uso en el taller |
|---|---|---|---|
| `analog_measurements` | Lecturas instantáneas: batería, FV, salida AC, red, temperaturas | 2 989 759 | **Hecho principal** (lecturas) |
| `statistics` | Contadores de energía del día y acumulados que calcula el inversor | 2 285 904 | **Conciliación** de energía |
| `status` | Estados de operación, carga y banderas de alarma | 2 240 052 | Eventos operativos |
| `fault_history` | Historial de las 32 últimas fallas del inversor (JSON + hora) | 2 129 517 | Eventos de falla |
| `context` | Anotaciones JSON: tareas de cómputo, eventos de Windows, calendario, red caída | 25 178 | **Dimensión de actividad** y eventos |
| `settings` | 174 parámetros de configuración del inversor | 2 284 775 | Candidata a SCD (cambios de configuración) |
| `specs` | Identificación del equipo (fabricante, firmware) | 1 333 174 | Dimensión inversor |
| `totals` | Potencias agregadas del sistema | 2 279 918 | Validación cruzada |

## 2. Cobertura en el tiempo

| | Inversor 1 | Inversor 2 |
|---|---|---|
| Primera lectura (local) | 2025-07-12 21:31 | 2025-07-14 13:53 |
| Última lectura (local) | 2026-07-13 13:13 | **2026-06-22 13:35** |
| Días con datos | 336 | 306 |
| Cadencia mediana | 12,6 s | 12,6 s |
| Huecos > 60 s | 47 959 | 47 560 |
| Huecos > 1 día | 3 | 3 |
| Horas perdidas en huecos | ≈ 2 729 h | ≈ 2 834 h |

- El inversor 2 deja de reportar 3 semanas antes que el inversor 1: los comparativos entre inversores
  deben hacerse sobre el **periodo común**.
- `specs` termina el 2026-02-03: los datos del equipo se toman como constantes después de esa fecha.
- `context` cubre desde mayo de 2024 (calendario académico) hasta julio de 2026: más amplio que la telemetría.

## 3. Problemas de calidad detectados

| # | Problema | Evidencia | Filas | Tratamiento propuesto |
|---|---|---|---|---|
| Q1 | Filas sin ninguna medición (solo `read_ts` e `inverter`) | Fallas de comunicación Modbus | 55 613 (inv. 2) + 1 (inv. 1) | Descartar en Silver; cuentan como **no disponibles** |
| Q2 | Nulos sueltos en columnas de medida | ~58 000 nulos por columna (validación de los autores) | ~2 % | Excluir la lectura del cálculo de la variable afectada |
| Q3 | Huecos entre lecturas > 60 s | Ver tabla de cobertura | ~95 000 huecos | No se imputan; se miden con el KPI de **disponibilidad** |
| Q4 | Batería a 0 V | Una batería de 48 V nunca marca 0 V con el inversor encendido | 3 | Inválido → descartar la lectura |
| Q5 | Temperatura interna < 0 °C | Clima subtropical; rango típico 11–45 °C | 100 | Inválido → anular `temper1` |
| Q6 | Picos de carga > 3 000 W | p99,9 = 1 667 W; aislados | 23 | Revisar contra la capacidad nominal; marcar como atípico |
| Q7 | Potencia de red negativa | Mínimo −146 W, muy esporádico | 9 | Ruido de medida → recortar a 0 |
| Q8 | Columnas siempre en 0 | `normalloadw_a`, `sir` | todas | No se cargan |
| Q9 | Columnas JSON (`*reserve`, `faulthistoryrecordNN`, `sysalarmflag`) | Texto con arreglos JSON | — | Se parsean en el ETL o quedan en `jsonb` |
| Q10 | Hora en UTC, sitio en UTC+8 | Diccionario de columnas: "fractional Unix timestamp in UTC" | todas | Convertir a hora local para día, mes y franja horaria |
| Q11 | Capacidad de batería sin configurar en el inversor 2 | `settings.battpackrateah` = 0 en el inv. 2 (200 Ah en el inv. 1) | todas (inv. 2) | Supuesto declarado: mismo banco de 200 Ah |

## 4. Dato inválido vs. evento operativo real

El criterio: **un dato es inválido si es físicamente imposible; un evento es real si es físicamente
posible y otra fuente lo confirma.**

| Caso | ¿Inválido o evento? | Por qué |
|---|---|---|
| Batería a 0 V | Inválido | Imposible con el inversor encendido; 3 lecturas aisladas |
| `linevolta = 0` (red sin tensión) | **Evento real** | 11,7 % de las lecturas, en episodios largos y continuos, confirmados por 56 eventos `grid_unavailable_or_islanded` en `context` |
| Fila sin mediciones | Ni lo uno ni lo otro: **falta de registro** | Se mide en la disponibilidad, no se convierte en ceros |
| FV = 0 de noche | Normal | Es lo esperado; se validará cruzando con los periodos `solar_daylight` de `context` |

**Hallazgo clave:** desde el **2026-05-03 15:50** la microrred opera aislada de la red pública:

| Inversor | Episodios de red caída de más de 1 h |
|---|---|
| 1 | 2026-05-03 → 05-07 (102 h), 05-07 → 05-12 (117 h), **05-12 → 07-13 (1 483 h, hasta el fin del registro)** |
| 2 | 2026-05-03 → 05-12 (cuatro tramos, 218 h en total); luego vuelve a la red |

Esto parte el año en dos regímenes (conectado a la red / aislado) y debe ser un atributo del modelo.

## 5. Consistencia física (evidencia de unidades)

- **Unidades:** las declara el diccionario de los autores (`opencem-v1.0.0/documentation/column_dictionary.csv`)
  y se confirman con valores físicos:
  - `battvolt` mediana 53,5 V → consistente con un banco de litio de 48 V nominales (p. ej. 16 celdas LFP de 3,2–3,4 V).
  - `linevolta` mediana 235 V y `linefreq` 50,0 Hz → red pública china (220 V / 50 Hz).
  - `battsoc` entre 6 y 100 → porcentaje.
  - `pvgeneratenergytoday` hasta 12,8 por día con `pv1power` máximo de ~3,9 kW → kWh.
  - `battcurr` con signo: positivo = descarga, negativo = carga (según el diccionario).
- **Balance de potencias** `FV + red + batería(descarga) − carga`: mediana +107 W (p5 −32, p95 238 W).
  El residuo positivo y estable corresponde al autoconsumo y a las pérdidas del inversor.
- **Conciliación preliminar con los contadores del inversor** (503 días comparados):
  - Carga integrada / contador de consumo = **0,99**: cuadra.
  - FV integrada / contador FV = **0,91**: los huecos sin lectura hacen que la integración se quede
    corta. Para la energía diaria se priorizan los contadores del inversor y la integración sirve de validación.

## 6. Limitaciones para el análisis

1. **No hay irradiancia ni temperatura de módulo:** no se puede calcular el *Performance Ratio* ni el
   rendimiento de referencia (va al análisis crítico de §4 B). Las imágenes de cielo no reemplazan
   un piranómetro.
2. **Un solo canal FV por inversor** (`pv1*`): no se pueden comparar strings.
3. **El contexto está desbalanceado:** el 95 % de los registros de `context` es del inversor 1
   (estaciones de trabajo 1 y 2), así que el análisis de consumo por tipo de tarea es más sólido para ese inversor.
4. **No hay medidor de exportación:** la potencia de red es prácticamente siempre importación.
5. **Sin tarifa en la fuente:** el indicador económico depende de la tarifa en COP/kWh que elijamos.
6. **Huecos de comunicación:** ~11 % del tiempo sin lectura; toda energía integrada es un límite inferior.

# Negocio e indicadores (§4 A y B)

## 0. Enfoque de profundización: **SolarBI**

> **SolarBI: perfil de consumo de cargas de cómputo con bitácoras JSON y telemetría eléctrica.**
> ¿Cuánta energía consume cada tipo de tarea de cómputo, de dónde sale (sol, batería o red) y cuánto cuesta?

**Por qué este enfoque.** La tabla `context` registra cerca de 15 000 tareas de cómputo en el inversor 1
entre el 2025-10-29 y el 2026-01-11 (≈ 12 000 compilaciones en CPU y ≈ 3 000 entrenamientos de redes
neuronales en GPU, con modelo, épocas y *batch size*). Cruzarlas con la telemetría permite asignar
energía, origen y costo a cada tarea, algo que ningún tablero eléctrico tradicional responde.

**Evidencia de que es viable** (inversor 1, ventana de tareas, promedios por minuto):

| Estado del minuto | Minutos | Carga media | FV media | Red media |
|---|---|---|---|---|
| Entrenamiento en GPU activo | 20 819 | **371 W** | 109 W | 353 W |
| Solo compilación en CPU | 19 866 | 289 W | 91 W | 283 W |
| Sin tarea registrada | 58 004 | 276 W | 83 W | 284 W |

- Un entrenamiento en GPU suma **≈ 95 W** sobre la línea base; una compilación en CPU, ≈ 13 W.
- **El 55 % de los minutos de GPU ocurre de noche** (sin sol): ahí la red aporta ≈ 531 W de media.
  Es una oportunidad directa de gestión de cargas: mover entrenamientos a horas de sol.

## 1. Usuarios (stakeholders) y preguntas de negocio

| Usuario | Qué decide | Preguntas de negocio | Herramienta | Frecuencia |
|---|---|---|---|---|
| **Dirección de infraestructura** | Inversiones: más paneles, más batería, gestión de cargas | P1. ¿Cuánta energía aporta el sol frente a la red, por inversor y mes? · P2. ¿Cuánto cuesta la energía comprada y cuánto se ahorra con el sol? · P3. ¿La batería se usa bien o está sobredimensionada? · P4. ¿Qué pasaría con la tarifa comercial o con más capacidad FV? | Power BI | Mensual |
| **Equipo de mantenimiento** | Intervenir el sistema | P5. ¿Cómo está cada inversor ahora (SoC, red, temperatura, carga)? · P6. ¿Hay red o estamos en isla? · P7. ¿Dejaron de llegar datos? | Grafana + alertas | Casi en tiempo real |
| **Investigadores / usuarios de cómputo** (SolarBI) | Cuándo lanzar tareas | P8. ¿Cuánta energía consume cada tipo de tarea y modelo? · P9. ¿Qué parte de esa energía es solar? · P10. ¿En qué horario conviene entrenar para usar más sol? | Power BI | Semanal |
| **Finanzas** | Presupuesto de energía | P11. ¿Cuánto cuesta la energía de cada tarea y de cada mes? | Power BI | Mensual |
| **Área de TI** | Operar la plataforma | P12. ¿La solución se levanta, escala y recupera sola en Kubernetes? | `kubectl`, sondas | Continua |

## 2. Tarifa elegida

| | Valor |
|---|---|
| Fuente | EPM, *Tarifas y Costo de Energía Eléctrica – Mercado Regulado – abril de 2026*, Antioquia, Nivel I, propiedad EPM ([publicación oficial](https://www.epm.com.co/content/dam/epm/clientes-y-usuarios/energia/tarifas-energia/Tarifas%202026/4.PublicacionTarifasAbril162026_ANT_OM.pdf)) |
| **Tarifa base: Oficial y exentos de contribución** | **864,06 COP/kWh** |
| Escenario what-if: Industrial y comercial (CU + 20 % de contribución) | 1 036,88 COP/kWh |
| Horaria oficial: punta (9–12 h y 18–21 h) / fuera de punta | 870,79 / 852,67 COP/kWh |

**Justificación.** La Institución Universitaria Pascual Bravo es una institución pública, así que le
corresponde la tarifa *Oficial* (sin contribución). Es la publicación oficial de EPM más reciente que
pudimos verificar; las cifras posteriores solo aparecían en sitios de terceros. Supuesto explícito: los
datos son de Shenzhen, y la tarifa se aplica **como si** el campus estuviera en Medellín. La tarifa queda
en una tabla de parámetros (no en el código) para poder actualizarla.

## 3. Catálogo de indicadores

Notación: Δt = tiempo hasta la siguiente lectura válida, limitado a 60 s (si hay un hueco no se
extrapola). Energía [kWh] = Σ P[W] · Δt[s] / 3 600 000. Hora local Asia/Shanghai.
Granularidad base: **inversor × minuto** (capa Silver), agregable a hora, día, mes y periodo.

### 3.1 Obligatorios

| ID | Indicador | Fórmula | Unidad | Granularidad | Meta / umbral | Fuente | Usuario |
|---|---|---|---|---|---|---|---|
| K1 | Energía solar generada | Σ `pv1power` · Δt (validada contra `statistics.pvgeneratenergytoday`) | kWh | Inversor, día, mes, periodo | Seguimiento; alerta si el día soleado < 50 % de la media móvil de 7 días | `analog_measurements`, `statistics` | Dirección |
| K2 | Energía entregada a la carga | Σ `outw_a` · Δt (validada contra `usedenergytoday`) | kWh | Inversor, día, mes, periodo | Seguimiento | `analog_measurements`, `statistics` | Dirección, Finanzas |
| K3 | Energía importada de la red | Σ max(`linepowerw_a`, 0) · Δt | kWh | Inversor, día, mes, periodo | Reducir mes a mes | `analog_measurements` | Dirección, Finanzas |
| K4 | Disponibilidad del registro | Minutos con al menos una lectura / minutos del periodo | % | Inversor, día, mes | ≥ 95 % | `analog_measurements` | Mantenimiento, TI |
| K5 | Porcentaje de datos válidos | Lecturas que pasan todas las reglas de limpieza / lecturas recibidas | % | Inversor, día, mes | ≥ 98 % | ETL (log de calidad) | TI |

### 3.2 Propios de un sistema híbrido (no mencionados en el enunciado)

| ID | Indicador | Fórmula | Unidad | Meta / umbral | Justificación |
|---|---|---|---|---|---|
| K6 | **Autosuficiencia** (*self-sufficiency*) | 1 − K3 / K2 | % | Línea base del año: inv. 1 ≈ 43 %, inv. 2 ≈ 30 %. Meta: +10 puntos (≥ 53 % y ≥ 40 %) | Resume en un número cuánto depende el campus de la red; es el KPI rector para decidir más FV o más batería |
| K7 | **Ciclos equivalentes de batería** | Energía descargada / capacidad nominal. Capacidad = `settings.battpackrateah` (200 Ah) × 48 V ≈ 9,6 kWh | ciclos/día | ≤ 1 ciclo/día | Mide el desgaste: muchos ciclos significan reemplazo anticipado y pocos, batería sobredimensionada (P3). *Supuesto:* el inversor 2 reporta 0 Ah (sin configurar); se asume el mismo banco de 200 Ah |
| K8 | **Tiempo en modo isla** | Minutos con `linevolta` = 0 / minutos disponibles | % y horas | Seguimiento; alerta si > 5 min | Desde el 2026-05-03 la microrred opera aislada; mide la resiliencia real del sistema |
| K9 | **Pérdidas y autoconsumo del inversor** | (FV + red + descarga − carga − carga de batería) / entradas | % | ≤ 15 % | El balance tiene un residuo estable (mediana ≈ 107 W); cuantifica cuánta energía se pierde en la conversión |

### 3.3 Económicos (COP)

| ID | Indicador | Fórmula | Unidad | Usuario |
|---|---|---|---|---|
| K10 | Costo de la energía importada | K3 × tarifa | COP | Finanzas, Dirección |
| K11 | **Ahorro por autogeneración** | (K2 − K3) × tarifa: energía que no hubo que comprar | COP | Dirección |
| K12 | Costo horario (punta / fuera de punta) | K3 de la franja × tarifa horaria de la franja | COP | Dirección |

### 3.4 SolarBI (enfoque de profundización)

| ID | Indicador | Fórmula | Unidad | Granularidad | Usuario |
|---|---|---|---|---|---|
| S1 | Energía incremental por tarea | Σ (carga del minuto − línea base) · Δt durante la tarea; línea base = mediana de la carga en minutos sin tarea, por franja horaria | kWh | Tarea, tipo, modelo, estación de trabajo | Investigadores |
| S2 | Energía por época de entrenamiento | S1 / `epochs` | Wh/época | Modelo de red neuronal | Investigadores |
| S3 | **Fracción solar del cómputo** | Energía FV en minutos con tarea / energía de carga en esos minutos | % | Tipo de tarea, franja horaria | Investigadores, Dirección |
| S4 | Costo por tarea | S1 × (1 − S3) × tarifa | COP | Tarea, tipo, modelo | Finanzas |
| S5 | **Cómputo en horas de sol** | Minutos de GPU con FV > 0 / minutos de GPU | % | Mes, estación de trabajo | Dirección (hoy ≈ 45 %; meta ≥ 70 %) |

### 3.5 Operativos (Grafana y alertas)

| ID | Indicador | Umbral de alerta | Justificación del umbral |
|---|---|---|---|
| O1 | Estado de carga (SoC) actual | < 20 % durante 5 min | El propio inversor alarma al 15 % (`batsoclowalarm`), pasa a la red al 10 % (`inv2linesoc`) y corta al 5 % (`batstopsoc`). Avisar al 20 % da margen para actuar antes que el equipo; en modo isla no hay red de respaldo |
| O2 | Red disponible | `linevolta` = 0 durante más de 5 min | Distingue un parpadeo de un corte real; los episodios reales duran horas |
| O3 | Temperatura del inversor (`temper1`) | > 45 °C | El p99,9 histórico es 44,8 °C: por encima es anómalo |
| O4 | Frescura de los datos | Sin lecturas durante más de 2 min | La cadencia normal es 12,6 s; dos minutos son ~10 lecturas perdidas |

## 4. Análisis crítico: el indicador que no se puede calcular

El indicador clásico de una planta fotovoltaica es el **Performance Ratio (PR)** (IEC 61724):

PR = (E_AC / P_nominal) / (H_POA / G_STC)

Requiere la **irradiancia en el plano de los módulos** (H_POA) y la **potencia nominal instalada**.
OpenCEM no trae piranómetro ni temperatura de módulo, y la potencia nominal FV no está en la base. Sin
ellos no se puede saber si poca generación se debe a nubes o a una falla (suciedad, sombra, string
dañado). Por la misma razón tampoco se pueden calcular el *Specific Yield* normalizado ni las pérdidas
por temperatura.

**Qué haríamos:**
1. **Corto plazo (proxy):** con la latitud y longitud del sitio (presentes en `context`) calcular la
   irradiancia de cielo despejado (modelo `pvlib`) o descargar la irradiancia satelital histórica (por
   ejemplo NASA POWER u Open-Meteo para Shenzhen) y estimar un *PR aproximado*, declarándolo como tal.
2. **Mediano plazo:** instalar una celda de referencia o un piranómetro y un sensor de temperatura de
   módulo, y registrar la potencia nominal de los paneles en la dimensión inversor.
3. Mientras tanto, usar K1 comparado contra su propia media móvil como indicador de degradación relativa.

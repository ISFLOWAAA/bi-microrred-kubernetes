# Hallazgos y recomendaciones (historia con datos)

> Cifras de `gold.v_kpi_mensual`, `gold.v_solarbi_perfil` y `gold.fact_evento_operativo` (histórico julio de 2025 a julio de 2026).
> Costos con la tarifa oficial de EPM de abril de 2026 (864,06 COP/kWh) aplicada **como si** el campus estuviera en Medellín.

## El hilo de la historia

> *Una microrred solar con batería cubre hoy menos de la mitad de lo que consume; cuando quedó aislada de la red, descubrió que el sol
> sí alcanza. El cómputo en GPU, el mayor consumidor flexible, trabaja la mitad del tiempo de noche, cuando no hay sol.*

## Hallazgos

| # | Hallazgo | Evidencia | Qué significa |
|---|---|---|---|
| **H1** | La autosuficiencia del año es **40 %** (inversor 1) y **28 %** (inversor 2) | 1 109 y 3 008 kWh importados de la red frente a 1 851 y 4 188 kWh de consumo | La red sigue cargando la mayor parte del consumo; hay margen de mejora |
| **H2** | Entre abril y junio de 2026 el inversor 1 pasó de **43 % a 100 %** de autosuficiencia, y al quedar **aislada** (mayo) la red se dejó de usar | La generación subió de 108 a 189 kWh/mes y el consumo bajó de 245 a 136 kWh/mes; la importación de red cayó de 140 a 0 kWh/mes | Con menos carga y más sol, la generación bastó: cuando no hay red, la carga se ajusta a lo que da el sol |
| **H3** | El **50 %** de los minutos de GPU ocurre de noche; solo el **38 %** con sol | `gold.fact_energia_minuto` × `dim_actividad_computo` | El mayor consumo flexible no aprovecha la generación |
| **H4** | La fracción solar del entrenamiento es **0 %** de noche y madrugada, **69 %** en la mañana y **49 %** en la tarde | `v_solarbi_perfil` por franja | La hora de inicio decide cuánto cuesta cada entrenamiento |
| **H5** | **`swin_v2_s` gasta 17,9 Wh por época**: 4 veces más que `densenet121` (4,5) y 10 veces más que `resnet18` (1,9) | S2 por modelo | La arquitectura elegida pesa más que el tamaño del modelo en parámetros |
| **H6** | La red estuvo caída **17 veces, 1 837 h**; la batería bajó del 20 % en **28 episodios, 178 h** | Eventos `RED_CAIDA` y `SOC_BAJO` | En modo isla no hay respaldo: la batería es el único colchón |
| **H7** | La batería hace **0,14 a 0,30 ciclos por día** (meta ≤ 1) | K7 | Se usa poco: no es el cuello de botella |
| **H8** | La **disponibilidad del registro** es 75 % (inv. 1) y 59 % (inv. 2), por debajo de la meta del 95 % | K4; 149 huecos de datos que suman 2 914 h | Gran parte del año no se midió; toda energía integrada es un límite inferior |
| **H9** | El inversor 2 **dejó de alimentar su carga y su FV el 6 de abril de 2026** | Carga en 0 desde el 6-abr y FV en 0 desde el 10-abr con lecturas válidas | Cambio de operación (climatización apagada), no un error de datos |

## Recomendaciones para la Dirección de Infraestructura

| # | Recomendación | Impacto estimado | Cómo se mide |
|---|---|---|---|
| **R1** | **Programar los entrenamientos de GPU entre las 9 y las 15 h** | Los entrenamientos de noche y madrugada (15,3 kWh incrementales) costaron 13 238 COP; con la fracción solar de la mañana (69 %) costarían ≈ 4 100 COP: **−9 100 COP, el 46 % del costo de la GPU**, sin comprar nada | S3 y S5 (hoy 38 %; meta ≥ 70 %) |
| **R2** | **Elegir el modelo por Wh por época**: usar `resnet18` o `vgg` cuando la precisión lo permita y reservar `swin_v2_s` | Un entrenamiento con `resnet18` gasta la décima parte | S2 |
| **R3** | **Añadir generación fotovoltaica antes que batería** | La batería trabaja 0,14–0,30 ciclos/día: está sobrada. En el escenario de Power BI, +20 % de generación sube la autosuficiencia y baja el costo de la red | K6 y *what-if* de Power BI |
| **R4** | **Mantener la gestión de cargas en modo isla**: avisar a los usuarios de cómputo cuando SoC < 30 % y posponer entrenamientos | Evita los 28 episodios bajo 20 % | Alerta O1 de Grafana |
| **R5** | **Corregir la recolección de datos** (watchdog del registrador y alerta O4) | Llevar la disponibilidad de 59–75 % a ≥ 95 % | K4 |
| **R6** | **Revisar la tarifa**: pasar a la franja fuera de punta | La diferencia punta / fuera de punta es de 18 COP/kWh (870,79 frente a 852,67) | K12 |

## Limitaciones que hay que decir en voz alta

- **El costo es un cálculo de referencia:** los datos son de Shenzhen y la tarifa es de Medellín.
- **La energía integrada subestima** por los huecos de comunicación; por eso los indicadores usan los **contadores del inversor** y,
  cuando no hay contador válido (181 días, 28 % de los días con datos), la integración.
- **R1 es una estimación:** supone que un entrenamiento movido de hora conserva su energía incremental y obtiene la fracción solar
  de la franja nueva; no considera la disponibilidad real de sol cada día.
- **Falta irradiancia:** no se puede calcular el *Performance Ratio* ni separar nubes de fallas (ver `docs/03`, §4).
- **Un solo canal de FV por inversor** y un registro de bitácoras casi solo del inversor 1: SolarBI es más sólido para ese inversor.

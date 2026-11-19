# simulador/

Genera telemetría "en vivo" para Grafana: repite un **día histórico completo** (el mismo minuto del día)
con la hora actual, le agrega un ruido de ±2,5 % y lo inserta en `gold.fact_energia_minuto` con
`origen = 'simulado'`. Power BI filtra solo el histórico; Grafana ve ambos.

- Cada ejecución rellena los minutos que faltan desde el último simulado (máximo `MAX_MINUTOS`): sirve
  igual en bucle (`docker compose`) que como `CronJob` de Kubernetes (`MODO=una_vez`).
- El día de referencia se elige entre los días con cobertura ≥ 95 % en los dos inversores y queda fijo
  durante todo el día simulado, para que las curvas sean continuas.
- Borra las filas simuladas con más de `RETENCION_DIAS` días.

## Escenarios (para probar las alertas en la sustentación)

| `ESCENARIO` | Qué hace | Alerta que dispara |
|---|---|---|
| `normal` | Repite el día de referencia | — |
| `red_caida` | Tensión y potencia de red en 0, régimen "Isla" | O2 (red caída > 5 min) |
| `soc_bajo` | SoC limitado a 15 % | O1 (SoC < 20 % por 5 min) |
| `temp_alta` | Temperatura del inversor en 48 °C | O3 (> 45 °C) |
| `sin_datos` | No inserta nada | O4 (sin datos > 2 min) |

```bash
ESCENARIO=red_caida docker compose up -d simulador     # cambiar de escenario en local
```

## Variables

`PGHOST`, `PGPORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `MODO` (`bucle` / `una_vez`),
`INTERVALO_S` (60), `ESCENARIO` (`normal`), `RUIDO_PCT` (5), `MAX_MINUTOS` (60), `RETENCION_DIAS` (7).

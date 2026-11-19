# grafana/

Tablero operativo y alertas, **100 % por provisioning**: al arrancar, Grafana lee estos archivos y queda
configurado sin un solo clic. Lo que se ve en pantalla es exactamente lo que está en Git.

| Archivo | Qué configura |
|---|---|
| `provisioning/datasources/postgres.yaml` | Fuente `Microrred`: PostgreSQL por nombre del Service, usuario `grafana_lector` (solo lectura) |
| `provisioning/dashboards/proveedor.yaml` | Carga los tableros de `tableros/` en la carpeta *Microrred* (no editables desde la interfaz) |
| `provisioning/alerting/alertas.yaml` | Las 2 alertas (O1 y O2) |
| `tableros/microrred.json` | Tablero *Microrred · Operación* (página de inicio) |

Acceso: <http://localhost:3001> · usuario `admin` · clave `GRAFANA_ADMIN_PASSWORD` del `.env`.

## El tablero: una pantalla, tres preguntas

```
┌ Inversor ▾ ───────────────────────────────────────────────────────────────┐
│ Batería 99 %  │ Red: Conectada │ Temperatura 21 °C │ Último dato hace 0,4 m │  ¿Está todo bien ahora?
├──────────────────────────────────────────────┬────────────────────────────┤
│ Flujo de energía (W): Solar · Consumo · Red  │ Energía en el periodo (kWh)│  ¿De dónde sale la energía?
├───────────────────────────┬──────────────────┼────────────────────────────┤
│ Batería (%) · zona < 20 % │ Autosuficiencia  │ Alertas                    │  ¿Hay que actuar?
└───────────────────────────┴──────────────────┴────────────────────────────┘
```

**Decisiones de diseño**

- **Arriba, el semáforo:** cuatro números grandes con color solo cuando importa (verde / naranja / rojo,
  con los umbrales de O1–O4). Nada de gráficos dentro de los indicadores.
- **Tres colores fijos y con significado** en todo el tablero: solar amarillo, consumo azul, red violeta;
  la batería, verde. El mismo color significa lo mismo en cada panel.
- **Una variable**: el inversor (con su carga: GPU o climatización). Todo el tablero responde a ella.
- Cada panel tiene una descripción (ícono ⓘ) que dice qué mide y qué umbral usa.
- Rango por defecto: 3 h, refresco cada minuto (el simulador escribe un dato por minuto).

## Alertas

| Alerta | Condición | Por qué ese umbral |
|---|---|---|
| **O1 · Batería baja** | SoC < 20 % en **todos** los minutos de los últimos 5 | El inversor alarma al 15 % y corta al 5 %: el 20 % deja margen para actuar; los 5 min evitan falsas alarmas por un parpadeo |
| **O2 · Red caída** | Tensión de red = 0 en **todos** los minutos de los últimos 5 | Distingue un parpadeo de un corte real (los cortes reales duran horas: 17 episodios, 1 836 h en el histórico) |

Se evalúan cada minuto y generan una instancia por inversor. Para probarlas en vivo se cambia el escenario
del simulador:

```powershell
kubectl -n taller6 patch configmap config-microrred -p '{\"data\":{\"ESCENARIO\":\"red_caida\"}}'   # o soc_bajo
kubectl -n taller6 patch configmap config-microrred -p '{\"data\":{\"ESCENARIO\":\"normal\"}}'
```

No hay canal de notificación configurado (correo o chat): las alertas se ven en el panel *Alertas* y en
*Alerting* de Grafana. En producción se agregaría un *contact point*.

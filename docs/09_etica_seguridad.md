# Ética y seguridad (§4 J)

## 1. La tabla `context` frente a la Ley 1581 de 2012

**Qué es la Ley 1581 de 2012.** Es el régimen colombiano de protección de datos personales (*habeas data*). Define como
**dato personal** cualquier información vinculada o que pueda asociarse a una persona natural determinada o determinable.

**Por qué `context` es delicada.** Aunque parece una tabla técnica, registra **actividad de personas**: los equipos de cómputo
los usan investigadores concretos. Lo que se encontró en el JSON de `context` (25 178 registros, 56 tipos):

| Campo del JSON | Qué puede revelar | Riesgo |
|---|---|---|
| `command`, `example_commands_redacted`, `command_hints_redacted`, `command_families` | Qué comandos escribió alguien y con qué parámetros | Perfilar hábitos de trabajo; a veces contienen nombres de proyecto o de archivos |
| `directory`, `cwd_redacted` | Rutas de carpetas (con nombre de usuario, proyecto o repositorio) | Identificar a la persona o su proyecto |
| `windows_event.sanitized_message` y `sample_*` | Mensajes del sistema operativo con usuarios y servicios | Identificación indirecta |
| Eventos de inicio y cierre de sesión (`interactive_or_remote_logon`, `remote_desktop_logon`…) | Cuándo se conectó alguien, desde dónde, a qué horas | **Control de horarios del trabajador**; es el más sensible |
| Entradas manuales (`manual entry`) | Texto libre ("Office used by group member with additional laptop") | Datos de terceros sin estructura |
| Tareas de cómputo (modelo, épocas, dispositivo) | Qué entrena cada estación y cuándo | Medir la productividad de una persona si se cruza con quién usa el equipo |

**Principios de la ley y cómo se aplican en la solución**

| Principio | Cómo se cumple |
|---|---|
| **Finalidad** | Los datos se usan solo para medir el consumo energético del cómputo, no para evaluar personas |
| **Necesidad y minimización** | El ETL elimina las claves personales (regla **C1**: 18 454 de 25 178 registros contenían alguna) al pasar a `silver.contexto`. Las columnas `command`, `directory`, `sanitized_message`, etc. **no llegan a Gold, a Grafana ni a Power BI** |
| **Seguridad** | `bronze.context` conserva el JSON original, pero **ningún rol de consumo puede leerlo** (`06_seguridad.sql`: `REVOKE ALL ON SCHEMA bronze FROM rol_lectura_bi`). Grafana y Power BI usan usuarios de solo lectura sobre `gold` |
| **Circulación restringida** | Los indicadores se publican **por dispositivo e inversor, nunca por persona**: no existe una dimensión "usuario" |
| **Calidad y transparencia** | Cada regla de limpieza queda registrada con conteos en `silver.calidad_log`; el tratamiento se documenta (este documento y `docs/06_etl_calidad.md`) |
| **Temporalidad** | Se propone borrar `bronze.context` cuando termine el taller; en un despliegue real, definir un plazo de retención |

**Lo que no se cumple del todo (y se dice).** La fuente es un conjunto de datos **público** (Zenodo, CC BY 4.0) que sus autores
ya redactaron (`<redacted>`, `<user>`), así que el riesgo de reidentificación es bajo. Aun así se trató como si no lo fuera:
`bronze.context` sigue teniendo el JSON original y quien tenga acceso de administrador a la base puede leerlo. En una
institución real haría falta, además, **autorización del titular o base legal**, **política de tratamiento de datos**,
informar la finalidad a los investigadores y, si aplica, el registro de la base de datos ante la SIC (RNBD).

**Consideración ética más allá de la ley.** Un indicador como "energía por tarea" (S1) podría usarse para vigilar el
rendimiento de un investigador. Se decidió no modelar usuarios y usar los resultados solo para **programar mejor el cómputo**
(entrenar con sol), no para evaluar personas.

## 2. Seguridad de acceso

### 2.1 Tableros

| Medida | Estado |
|---|---|
| Grafana exige usuario y contraseña (`admin` + `GRAFANA_ADMIN_PASSWORD` del Secret); sin acceso anónimo | Aplicada |
| Tablero y alertas **no editables desde la interfaz** (`allowUiUpdates: false`, `editable: false`): el oficial es el de Git | Aplicada |
| Telemetría de Grafana, avisos de actualización y noticias desactivados | Aplicada |
| Power BI entra con `powerbi_lector` (solo lectura) y pide credenciales al abrir el proyecto; no se guardan en el repositorio | Aplicada |
| Grafana (3001) y PostgreSQL (5434) se publican con `LoadBalancer`; en Docker Desktop escuchan en **`0.0.0.0`** (todas las interfaces), no solo en `localhost` | **Riesgo conocido**: los protege la contraseña, pero conviene una regla de Firewall de Windows que bloquee esos puertos desde otras máquinas |
| Roles de Grafana (visor / editor) por tipo de usuario, SSO | **Pendiente** (un solo usuario administrador) |
| HTTPS en Grafana | **Pendiente** (HTTP local) |

### 2.2 Base de datos: mínimo privilegio

| Rol | Puede | No puede |
|---|---|---|
| `rol_etl` (sin login) | Escribir en `bronze`, `silver`, `gold` | — |
| `rol_lectura_bi` (sin login) | `SELECT` en `gold` | Ver `bronze` y `silver`; escribir |
| `grafana_lector`, `powerbi_lector` (con login, miembros de `rol_lectura_bi`) | Leer `gold` | Todo lo demás. Un usuario por herramienta permite revocar o auditar cada una por separado |
| `rol_simulador` | Insertar en `gold.fact_energia_minuto` | Tocar otras tablas |

> **Pendiente:** hoy el Job del ETL y el CronJob del simulador se conectan con el usuario administrador (`POSTGRES_USER` del Secret). Los roles `rol_etl` y `rol_simulador` están definidos, pero no se les ha creado un usuario con login ni un Secret propio. Es el siguiente paso de mínimo privilegio: un usuario por carga de trabajo.
| Nadie | Crear objetos en `public` (`REVOKE CREATE ON SCHEMA public FROM PUBLIC`) | — |

Las contraseñas de los usuarios de consumo **no están en ningún `.sql`**: llegan por variable de entorno al script
`sql/07_usuarios_consumo.sh`, que crea los roles al iniciar la base vacía.

### 2.3 Credenciales dentro del clúster

**Mecanismo elegido: `Secret` de Kubernetes creado en el despliegue desde `.env`.**

```
.env (solo en el equipo, ignorado por Git)
   └─ levantar.ps1: kubectl create secret generic pg-credenciales --from-env-file=.env | kubectl apply
        └─ pods: variables de entorno por secretRef / secretKeyRef  (nunca en la imagen ni en el manifiesto)
```

| Verificado | Evidencia |
|---|---|
| Las imágenes no contienen contraseñas | Los `Dockerfile` no las referencian; la fuente va por volumen |
| El repositorio solo trae una plantilla | `.env.example` con `cambia_esta_clave`; `.gitignore` excluye `.env` y `*secret.yaml` |
| La salida de `kubectl describe` no revela valores | `docs/evidencias/`: solo se ve `<set to the key '…' in secret 'pg-credenciales'>` |
| Las claves se generan aleatorias | `secrets.token_urlsafe(12)` para Grafana y Power BI |

**Por qué un Secret y no otra opción:** un ConfigMap guardaría la clave en texto plano; ponerla en el manifiesto la subiría a Git;
un gestor externo (Vault, *External Secrets*) es la solución de producción pero excede el nivel básico del taller.

**Limitaciones reconocidas (qué falta para producción)**

| Riesgo | Mitigación recomendada |
|---|---|
| Un Secret está solo codificado en base64 y **no cifrado** en `etcd` por defecto | Activar cifrado en reposo o usar *Sealed Secrets* / Vault |
| Cualquiera con acceso al clúster (`kubectl get secret -o yaml`) puede leerlo | RBAC: cuentas de servicio con permisos mínimos por namespace |
| El tráfico entre pods y hacia la base va sin cifrar | TLS en PostgreSQL (`sslmode=require`) y en Grafana |
| Todos los pods se ven entre sí | `NetworkPolicy`: solo ETL, simulador y Grafana hablan con PostgreSQL |
| `.env` queda en texto plano en el disco del equipo | Permisos del archivo; en producción, un gestor de secretos |
| Contenedores | Ya corren sin root (`uid 10001`) y con versión fija de imagen; faltaría `readOnlyRootFilesystem` y `securityContext` en los manifiestos |

> Una contraseña pegada en un chat, un correo o una captura deja de ser secreta: en ese caso hay que rotarla
> (`ALTER ROLE … PASSWORD`, actualizar `.env` y volver a ejecutar `levantar.ps1`).

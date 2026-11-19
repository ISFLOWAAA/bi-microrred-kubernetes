"""Genera el proyecto de Power BI (formato PBIP) a partir del esquema real de gold.

    python powerbi/generar_proyecto.py

Escribe Microrred.pbip, Microrred.SemanticModel (TMDL) y Microrred.Report (PBIR).
Los archivos generados son los que se versionan; este script solo documenta cómo se hicieron
y permite regenerarlos si cambia el modelo. Para leer las columnas usa el .env (PG en localhost:5434).
"""
import json
import shutil
import uuid
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent
MODELO = RAIZ / "Microrred.SemanticModel"
REPORTE = RAIZ / "Microrred.Report"
SERVIDOR, BASE = "localhost:5434", "microrred"


def env():
    d = {}
    for l in (RAIZ.parent / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1)
            d[k.strip()] = v.strip()
    return d


# ---------------------------------------------------------------- tablas del modelo
# tabla_db: (nombre en Power BI, tipo, columnas visibles {col_db: nombre visible}, orden por columna)
FECHA_COLS = {"fecha": "Fecha", "anio": "Año", "trimestre": "Trimestre", "mes": "Nº de mes", "nombre_mes": "Mes",
              "dia_mes": "Día", "nombre_dia": "Día de la semana", "anio_mes": "Año-Mes", "semana_iso": "Semana ISO",
              "dia_semana": "Nº día semana", "es_fin_de_semana": "Fin de semana", "tipo_dia": "Tipo de día",
              "periodo_academico": "Periodo académico"}
TABLAS = {
    "dim_fecha": ("Fecha", FECHA_COLS, {"nombre_mes": "mes", "nombre_dia": "dia_semana"},
                  {"mes", "dia_semana", "trimestre", "semana_iso"}),
    "dim_hora": ("Hora", {"hora": "Hora", "minuto": "Minuto", "hora_texto": "Hora (HH:MM)", "franja_dia": "Franja del día",
                          "franja_tarifaria": "Franja tarifaria"}, {"hora_texto": "hora_key"}, {"minuto"}),
    "dim_inversor": ("Inversor", {"nombre": "Nombre", "cargas": "Cargas que alimenta", "prioridad_carga": "Prioridad de carga",
                                  "prioridad_salida": "Prioridad de salida", "vigente_desde": "Vigente desde",
                                  "vigente_hasta": "Vigente hasta", "es_vigente": "Versión vigente"}, {}, set()),
    "dim_estado_operativo": ("Estado operativo", {"modo_salida": "Modo de salida", "estado_carga": "Estado de carga",
                                                   "regimen_red": "Régimen de red"}, {}, set()),
    "dim_actividad_computo": ("Actividad de cómputo", {"descripcion": "Actividad", "categoria": "Categoría de actividad"}, {}, set()),
    "dim_tipo_evento": ("Tipo de evento", {"codigo": "Código", "nombre": "Evento", "categoria": "Categoría de evento",
                                           "severidad": "Severidad", "es_calidad_dato": "Es de calidad de datos"}, {}, set()),
    "dim_perfil_tarea": ("Perfil de tarea", {"categoria": "Categoría de tarea", "modelo": "Modelo", "dataset": "Conjunto de datos",
                                             "optimizador": "Optimizador", "libreria": "Librería",
                                             "esfuerzo_estimado": "Esfuerzo estimado"}, {}, set()),
    "dim_dispositivo": ("Dispositivo", {"nombre": "Dispositivo", "tipo": "Tipo de dispositivo", "hardware": "Hardware"}, {}, set()),
    "dim_tarifa": ("Tarifa", {"tipo_tarifa": "Tipo de tarifa", "franja": "Franja"}, {}, set()),
    "fact_energia_diaria": ("Energía diaria", {}, {}, set()),
    "fact_energia_minuto": ("Energía por minuto", {"ts_minuto": "Minuto"}, {}, set()),
    "fact_evento_operativo": ("Eventos", {"ts_inicio": "Inicio", "ts_fin": "Fin", "duracion_min": "Duración (min)"}, {}, set()),
    "fact_tarea_computo": ("Tareas de cómputo", {"tarea_id": "Tarea", "ts_inicio": "Inicio", "ts_fin": "Fin",
                                                 "duracion_min": "Duración (min)"}, {}, set()),
}
# Tablas que se leen desde una vista de gold (hora local ya calculada) y filtros de filas del modelo
FUENTE = {"fact_evento_operativo": "v_pbi_evento", "fact_tarea_computo": "v_pbi_tarea"}
FILTROS = {"dim_fecha": "[fecha_key] > 0 and [fecha] <= #date(2026, 7, 31)",   # sin el miembro "Sin dato" ni días futuros
           "dim_inversor": "[inversor_sk] <> 0", "dim_perfil_tarea": "[perfil_tarea_key] <> 0"}
MINUTO_COLS = ["ts_minuto", "inversor_id", "fecha_key", "hora_key", "inversor_sk", "estado_key", "actividad_key",
               "n_lecturas", "n_lecturas_validas", "segundos_cubiertos", "e_fv_wh", "e_carga_wh", "e_red_wh",
               "e_bat_carga_wh", "e_bat_descarga_wh", "p_fv_w", "p_carga_w", "p_red_w", "soc_pct", "temp_max_c"]
EXCLUIR = {"detalle", "origen_id", "fuente", "origen"}   # JSON y textos técnicos que no aportan
MT = {"integer": ("int64", "Int64.Type"), "smallint": ("int64", "Int64.Type"), "bigint": ("int64", "Int64.Type"),
      "numeric": ("double", "type number"), "double precision": ("double", "type number"),
      "text": ("string", "type text"), "boolean": ("boolean", "type logical"), "date": ("dateTime", "type date"),
      "timestamp with time zone": ("dateTime", "type datetime"),
      "timestamp without time zone": ("dateTime", "type datetime")}


def q(n):
    return "'" + n.replace("'", "''") + "'"


def esquema():
    e = env()
    with psycopg.connect(host="127.0.0.1", port=5434, connect_timeout=15, dbname=e["POSTGRES_DB"], user=e["POSTGRES_USER"],
                         password=e["POSTGRES_PASSWORD"]) as con:
        filas = con.execute("""SELECT table_name, column_name, data_type FROM information_schema.columns
                               WHERE table_schema = 'gold' ORDER BY table_name, ordinal_position""").fetchall()
    out = {}
    for t, c, d in filas:
        out.setdefault(t, []).append((c, d))
    return out


def nombre(tabla_db, col):
    return TABLAS[tabla_db][1].get(col, col)


def C(tabla_db, col):
    return f"{q(TABLAS[tabla_db][0])}[{nombre(tabla_db, col)}]"


# ---------------------------------------------------------------- TMDL: tablas importadas
def tabla_tmdl(tdb, columnas):
    pb, visibles, orden, ocultas_extra = TABLAS[tdb]
    cols = [(c, d) for c, d in columnas if c not in EXCLUIR and (tdb != "fact_energia_minuto" or c in MINUTO_COLS)]
    es_dim = tdb.startswith("dim_")
    L = [f"table {q(pb)}"]
    if tdb == "dim_fecha":
        L.append("\tdataCategory: Time")
    L.append("")
    for c, d in cols:
        tipo, _ = MT[d]
        mostrar = c in visibles and c not in ocultas_extra
        if tdb == "dim_tarifa" and c in ("valor_cop_kwh", "es_base"):
            mostrar = True
        L.append(f"\tcolumn {q(nombre(tdb, c))}")
        L.append(f"\t\tdataType: {tipo}")
        if tipo == "dateTime":
            L.append("\t\tformatString: dd/mm/yyyy hh:nn" if c.startswith("ts_") else "\t\tformatString: dd/mm/yyyy")
        elif tipo == "int64":
            L.append("\t\tformatString: 0")
        if tdb == "dim_fecha" and c == "fecha":
            L.append("\t\tisKey")
        if not mostrar:
            L.append("\t\tisHidden")
        L.append("\t\tsummarizeBy: none")
        L.append(f"\t\tsourceColumn: {c}")
        if c in orden:
            L.append(f"\t\tsortByColumn: {q(nombre(tdb, orden[c]))}")
        L.append("")
    if tdb == "dim_fecha":
        L += ["\thierarchy Calendario", "\t\tlevel Año", f"\t\t\tcolumn: {q('Año')}", "\t\tlevel Mes",
              f"\t\t\tcolumn: {q('Mes')}", "\t\tlevel Día", f"\t\t\tcolumn: {q('Día')}", ""]
    # Consulta M: navegación + (filtro) + tipos
    sel = [c for c, d in cols if d != "timestamp with time zone"]   # los ts_* se arman con fecha_key + hora_key
    pasos = ['\t\t\t\t\tOrigen = PostgreSQL.Database(ServidorPG, BasePG),',
             f'\t\t\t\t\tTabla = Origen{{[Schema = "gold", Item = "{FUENTE.get(tdb, tdb)}"]}}[Data],']
    ult = "Tabla"
    if tdb == "fact_energia_minuto":
        pasos.append('\t\t\t\t\tHistorico = Table.SelectRows(Tabla, each [origen] = "historico"),')
        pasos.append("\t\t\t\t\tColumnas = Table.SelectColumns(Historico, {" + ", ".join(f'"{c}"' for c in sel) + "}),")
        ult = "Columnas"
    else:
        base = "Tabla"
        if tdb in FILTROS:
            pasos.append(f"\t\t\t\t\tFiltrado = Table.SelectRows(Tabla, each {FILTROS[tdb]}),")
            base = "Filtrado"
        pasos.append(f"\t\t\t\t\tColumnas = Table.SelectColumns({base}, {{" + ", ".join(f'"{c}"' for c in sel) + "}),")
        ult = "Columnas"
    ts = [c for c, d in cols if d == "timestamp with time zone"]
    # Las marcas de tiempo se arman en hora local con fecha_key (AAAAMMDD) y hora_key (minuto del día), que ya
    # vienen en la hora del sitio: así no dependen de zonas horarias ni de cómo el conector entrega timestamptz.
    inicio = ('each if [fecha_key] > 0 and [hora_key] >= 0 then #datetime(Number.IntegerDivide([fecha_key], 10000), '
              'Number.Mod(Number.IntegerDivide([fecha_key], 100), 100), Number.Mod([fecha_key], 100), '
              'Number.IntegerDivide([hora_key], 60), Number.Mod([hora_key], 60), 0) else null')
    fin = 'each if [ts_inicio] = null or [duracion_min] = null then null else [ts_inicio] + #duration(0, 0, [duracion_min], 0)'
    for i, c in enumerate(ts):
        pasos.append(f'\t\t\t\t\tHora{i} = Table.AddColumn({ult}, "{c}", {fin if c == "ts_fin" else inicio}, type datetime),')
        ult = f"Hora{i}"
    tipos = ", ".join(f'{{"{c}", {MT[d][1]}}}' for c, d in cols if d != "timestamp with time zone")
    pasos.append(f"\t\t\t\t\tTipos = Table.TransformColumnTypes({ult}, {{{tipos}}})")
    L += [f"\tpartition {q(pb)} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet"] + pasos + \
         ["\t\t\t\tin", "\t\t\t\t\tTipos", ""]
    return pb, "\n".join(L), cols


# ---------------------------------------------------------------- TMDL: tablas calculadas y medidas
def calculada(nombre_t, expr, columnas, ocultar=False, extra=""):
    L = [f"table {q(nombre_t)}", ""]
    for col, tipo, origen, props in columnas:
        L += [f"\tcolumn {q(col)}", f"\t\tdataType: {tipo}"] + [f"\t\t{p}" for p in props] + \
             ["\t\tisHidden"] * ocultar + ["\t\tsummarizeBy: none", f"\t\tsourceColumn: [{origen}]", "\t\ttype: calculatedTableColumn", ""]
    fuente = [f"\t\tsource = {expr}"] if "\n" not in expr else \
        ["\t\tsource ="] + ["\t\t\t\t" + l for l in expr.split("\n")]
    L += [extra, f"\tpartition {q(nombre_t)} = calculated", "\t\tmode: import"] + fuente + [""]
    return "\n".join(L)


def medida(nombre_m, expr, fmt, carpeta):
    lineas = expr.strip().split("\n")
    cuerpo = lineas[0] if len(lineas) == 1 else "\n" + "\n".join("\t\t\t" + l for l in lineas)
    return (f"\tmeasure {q(nombre_m)} = {cuerpo}\n\t\tformatString: {fmt}\n\t\tdisplayFolder: {carpeta}\n")


def medidas():
    d = lambda c: C("fact_energia_diaria", c)
    m = lambda c: C("fact_energia_minuto", c)
    t = lambda c: C("fact_tarea_computo", c)
    S, CO, R = "[Energía solar (kWh)]", "[Consumo (kWh)]", "[Importación de red (kWh)]"
    BC, BD = "[Carga de batería (kWh)]", "[Descarga de batería (kWh)]"
    A = "Energía"
    ms = [
        ("Energía solar (kWh)", f"SUM({d('e_fv_kwh_oficial')})", "#,0.0", A),
        ("Consumo (kWh)", f"SUM({d('e_carga_kwh_oficial')})", "#,0.0", A),
        ("Importación de red (kWh)", f"SUM({d('e_red_kwh_oficial')})", "#,0.0", A),
        ("Carga de batería (kWh)", f"SUM({d('e_bat_carga_kwh_oficial')})", "#,0.0", A),
        ("Descarga de batería (kWh)", f"SUM({d('e_bat_descarga_kwh_oficial')})", "#,0.0", A),
        ("Autosuficiencia (%)", f"DIVIDE({CO} - {R}, {CO})", "0.0%", A),
        ("Pérdidas del inversor (kWh)", f"{S} + {R} + {BD} - {CO} - {BC}", "#,0.0", "Balance"),
        ("Pérdidas del inversor (%)", f"DIVIDE([Pérdidas del inversor (kWh)], {S} + {R} + {BD})", "0.0%", "Balance"),
        ("Energía del concepto (kWh)",
         'SWITCH(\n    SELECTEDVALUE(\'Balance energético\'[Concepto]),\n'
         f'    "Solar", {S},\n    "Red", {R},\n    "Descarga de batería", {BD},\n    "Consumo", {CO},\n'
         f'    "Carga de batería", {BC},\n    "Pérdidas", [Pérdidas del inversor (kWh)]\n)', "#,0.0", "Balance"),
        ("Tarifa base (COP/kWh)", f"CALCULATE(MAX({C('dim_tarifa', 'valor_cop_kwh')}), {C('dim_tarifa', 'es_base')} = TRUE())",
         "#,0.00", "Economía"),
        ("Tarifa aplicada (COP/kWh)",
         "SELECTEDVALUE('Parámetro tarifa'[Tarifa (COP/kWh)], [Tarifa base (COP/kWh)])", "#,0.00", "Economía"),
        ("Costo de la red (COP)", f"{R} * [Tarifa aplicada (COP/kWh)]", "$#,0", "Economía"),
        ("Ahorro por autogeneración (COP)", f"({CO} - {R}) * [Tarifa aplicada (COP/kWh)]", "$#,0", "Economía"),
        ("Disponibilidad (%)", f"AVERAGE({d('disponibilidad_pct')}) / 100", "0.0%", "Calidad"),
        ("Datos válidos (%)", f"DIVIDE(SUM({m('n_lecturas_validas')}), SUM({m('n_lecturas')}))", "0.0%", "Calidad"),
        ("Horas en modo isla", f"SUM({d('minutos_en_isla')}) / 60", "#,0", "Calidad"),
        ("Tiempo en modo isla (%)", f"DIVIDE(SUM({d('minutos_en_isla')}), SUM({d('minutos_con_datos')}))", "0.0%", "Calidad"),
        ("Ciclos de batería por día",
         f"DIVIDE({BD}, MAX({C('dim_inversor', 'capacidad_bateria_kwh')}) * COUNTROWS('Energía diaria'))", "0.000", "Calidad"),
        # inteligencia de tiempo
        ("Energía solar mes anterior (kWh)", f"CALCULATE({S}, DATEADD({C('dim_fecha', 'fecha')}, -1, MONTH))", "#,0.0", "Tiempo"),
        ("Variación solar vs mes anterior (%)",
         f"DIVIDE({S} - [Energía solar mes anterior (kWh)], [Energía solar mes anterior (kWh)])", "+0.0%;-0.0%;0.0%", "Tiempo"),
        ("Energía solar acumulada del año (kWh)", f"TOTALYTD({S}, {C('dim_fecha', 'fecha')})", "#,0.0", "Tiempo"),
        # escenarios (what-if)
        ("Aumento de generación solar", "SELECTEDVALUE('Parámetro solar'[Aumento de generación solar (%)], 20) / 100", "0%", "Escenarios"),
        ("Importación de red del escenario (kWh)", f"MAX(0, {R} - {S} * [Aumento de generación solar])", "#,0.0", "Escenarios"),
        ("Costo de la red del escenario (COP)", "[Importación de red del escenario (kWh)] * [Tarifa aplicada (COP/kWh)]", "$#,0", "Escenarios"),
        ("Ahorro adicional del escenario (COP)", "[Costo de la red (COP)] - [Costo de la red del escenario (COP)]", "$#,0", "Escenarios"),
        ("Autosuficiencia del escenario (%)", f"DIVIDE({CO} - [Importación de red del escenario (kWh)], {CO})", "0.0%", "Escenarios"),
        # SolarBI
        ("Tareas de cómputo", "COUNTROWS('Tareas de cómputo')", "#,0", "SolarBI"),
        ("Energía incremental (kWh)", f"SUM({t('e_incremental_wh')}) / 1000", "#,0.00", "SolarBI"),
        ("Energía por tarea (Wh)", f"DIVIDE(SUM({t('e_incremental_wh')}), COUNTROWS('Tareas de cómputo'))", "#,0.0", "SolarBI"),
        ("Energía por época (Wh)", f"DIVIDE(SUM({t('e_incremental_wh')}), SUM({t('epocas')}))", "#,0.00", "SolarBI"),
        ("Fracción solar del cómputo (%)", f"MIN(1, DIVIDE(SUM({t('e_fv_wh')}), SUM({t('e_carga_wh')})))", "0.0%", "SolarBI"),
        ("Costo del cómputo (COP)",
         f"SUMX('Tareas de cómputo', MAX({t('e_incremental_wh')}, 0) / 1000 * (1 - COALESCE({t('fraccion_solar')}, 0)) "
         "* [Tarifa aplicada (COP/kWh)])", "$#,0", "SolarBI"),
        ("Minutos de GPU", f"CALCULATE(COUNTROWS('Energía por minuto'), {C('dim_actividad_computo', 'gpu_activa')} = TRUE())", "#,0", "SolarBI"),
        ("Cómputo GPU en horas de sol (%)",
         f"DIVIDE(CALCULATE(COUNTROWS('Energía por minuto'), {C('dim_actividad_computo', 'gpu_activa')} = TRUE(), {m('p_fv_w')} > 0), [Minutos de GPU])",
         "0.0%", "SolarBI"),
        ("Mensaje de autosuficiencia",
         f'"El " & FORMAT([Autosuficiencia (%)], "0%") & " del consumo no vino de la red"', "@", "Mensajes"),
        ("Mensaje de ahorro",
         '"El sol ahorró " & FORMAT([Ahorro por autogeneración (COP)] / 1000000, "0.0") & " millones de COP"', "@", "Mensajes"),
        ("Mensaje de cómputo",
         '"El " & FORMAT([Cómputo GPU en horas de sol (%)], "0%") & " del entrenamiento en GPU ocurre con sol"', "@", "Mensajes"),
        ("Eventos operativos", "COUNTROWS('Eventos')", "#,0", "Eventos"),
        ("Horas de eventos", f"SUM({C('fact_evento_operativo', 'duracion_min')}) / 60", "#,0.0", "Eventos"),
    ]
    return ms


def tabla_medidas():
    L = ["table Medidas", "", "\tcolumn Columna", "\t\tdataType: int64", "\t\tisHidden", "\t\tsummarizeBy: none",
         "\t\tsourceColumn: [Value]", "\t\ttype: calculatedTableColumn", ""]
    L += [medida(*m) for m in medidas()]
    L += ["\tpartition Medidas = calculated", "\t\tmode: import", "\t\tsource = {1}", ""]
    return "\n".join(L)


PARAM = ("\t\textendedProperty ParameterMetadata =\n\t\t\t\t{\n\t\t\t\t  \"version\": 3,\n\t\t\t\t  \"kind\": 2\n\t\t\t\t}")


def parametro(nombre_t, col, serie):
    L = [f"table {q(nombre_t)}", "", f"\tcolumn {q(col)}", "\t\tdataType: int64", "\t\tsummarizeBy: none",
         "\t\tsourceColumn: [Value]", "\t\ttype: calculatedTableColumn", "", PARAM, "",
         f"\tpartition {q(nombre_t)} = calculated", "\t\tmode: import", f"\t\tsource = GENERATESERIES({serie})", ""]
    return "\n".join(L)


BALANCE = """DATATABLE(
    "Concepto", STRING, "Orden", INTEGER, "Tipo", STRING,
    {
        {"Solar", 1, "Entra"}, {"Red", 2, "Entra"}, {"Descarga de batería", 3, "Entra"},
        {"Consumo", 4, "Sale"}, {"Carga de batería", 5, "Sale"}, {"Pérdidas", 6, "Sale"}
    }
)"""


def tabla_balance():
    return calculada("Balance energético", BALANCE, [
        ("Concepto", "string", "Concepto", ["sortByColumn: Orden"]),
        ("Orden", "int64", "Orden", []),
        ("Tipo", "string", "Tipo", [])]).replace("\t\tdataType: int64\n\t\tsummarizeBy: none\n\t\tsourceColumn: [Orden]",
                                                  "\t\tdataType: int64\n\t\tisHidden\n\t\tsummarizeBy: none\n\t\tsourceColumn: [Orden]")


# ---------------------------------------------------------------- relaciones
def relaciones():
    pares = [("fact_energia_diaria", "fecha_key", "dim_fecha", "fecha_key"), ("fact_energia_diaria", "inversor_sk", "dim_inversor", "inversor_sk"),
             ("fact_energia_minuto", "fecha_key", "dim_fecha", "fecha_key"), ("fact_energia_minuto", "hora_key", "dim_hora", "hora_key"),
             ("fact_energia_minuto", "inversor_sk", "dim_inversor", "inversor_sk"),
             ("fact_energia_minuto", "estado_key", "dim_estado_operativo", "estado_key"),
             ("fact_energia_minuto", "actividad_key", "dim_actividad_computo", "actividad_key"),
             ("fact_tarea_computo", "fecha_key", "dim_fecha", "fecha_key"), ("fact_tarea_computo", "hora_key", "dim_hora", "hora_key"),
             ("fact_tarea_computo", "inversor_sk", "dim_inversor", "inversor_sk"),
             ("fact_tarea_computo", "dispositivo_key", "dim_dispositivo", "dispositivo_key"),
             ("fact_tarea_computo", "perfil_tarea_key", "dim_perfil_tarea", "perfil_tarea_key"),
             ("fact_evento_operativo", "fecha_key", "dim_fecha", "fecha_key"), ("fact_evento_operativo", "hora_key", "dim_hora", "hora_key"),
             ("fact_evento_operativo", "inversor_sk", "dim_inversor", "inversor_sk"),
             ("fact_evento_operativo", "tipo_evento_key", "dim_tipo_evento", "tipo_evento_key"),
             ("fact_evento_operativo", "dispositivo_key", "dim_dispositivo", "dispositivo_key")]
    out = []
    for f, fc, dm, dc in pares:
        out.append(f"relationship {uuid.uuid5(uuid.NAMESPACE_DNS, f + fc + dm)}\n\tfromColumn: {q(TABLAS[f][0])}.{q(nombre(f, fc))}\n"
                   f"\ttoColumn: {q(TABLAS[dm][0])}.{q(nombre(dm, dc))}\n")
    return "\n".join(out)


def escribir(ruta, texto):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8", newline="\n")


def modelo():
    if MODELO.exists():
        shutil.rmtree(MODELO)
    esq = esquema()
    nombres = []
    for tdb in TABLAS:
        pb, txt, _ = tabla_tmdl(tdb, esq[FUENTE.get(tdb, tdb)])
        escribir(MODELO / "definition" / "tables" / f"{pb}.tmdl", txt)
        nombres.append(pb)
    extras = {"Medidas": tabla_medidas(), "Balance energético": tabla_balance(),
              "Parámetro tarifa": parametro("Parámetro tarifa", "Tarifa (COP/kWh)", "600, 1500, 10"),
              "Parámetro solar": parametro("Parámetro solar", "Aumento de generación solar (%)", "0, 100, 5")}
    for n, txt in extras.items():
        escribir(MODELO / "definition" / "tables" / f"{n}.tmdl", txt)
        nombres.append(n)
    escribir(MODELO / "definition.pbism", json.dumps({"version": "4.0", "settings": {}}, indent=2))
    escribir(MODELO / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    escribir(MODELO / "definition" / "model.tmdl",
             "model Model\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n\n"
             + "\n".join(f"ref table {q(n)}" for n in nombres) + "\n\nref expression ServidorPG\nref expression BasePG\n")
    meta = 'meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
    escribir(MODELO / "definition" / "expressions.tmdl",
             f'expression ServidorPG = "{SERVIDOR}" {meta}\n\tannotation PBI_ResultType = Text\n\n'
             f'expression BasePG = "{BASE}" {meta}\n\tannotation PBI_ResultType = Text\n')
    escribir(MODELO / "definition" / "relationships.tmdl", relaciones())


# ---------------------------------------------------------------- reporte (PBIR)
ESQ = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
AMARILLO, AZUL, VIOLETA, VERDE = "#F2B705", "#3D7DD8", "#9B7BC9", "#2BA672"
# versiones más oscuras para texto y valores (el amarillo claro no se lee sobre blanco)
T_SOLAR, T_CONSUMO, T_RED, T_VERDE = "#C98A00", "#2F6FCB", "#7B5BB5", "#1F8F5F"
TEXTO, GRIS, LINEA = "#111827", "#6B7280", "#E6E8EC"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def solido(hex_):
    return {"solid": {"color": lit(f"'{hex_}'")}}


def campo(entidad, prop, medida=False, activo=False):
    tipo = "Measure" if medida else "Column"
    p = {"field": {tipo: {"Expression": {"SourceRef": {"Entity": entidad}}, "Property": prop}}, "queryRef": f"{entidad}.{prop}"}
    if activo:
        p["active"] = True
    return p


def M(prop):
    return campo("Medidas", prop, medida=True)


def contenedor(nombre_v, x, y, w, h, tipo, consulta=None, titulo=None, objetos=None, fondo=True, z=0):
    vco = {}
    if titulo:
        vco["title"] = [{"properties": {"show": lit("true"), "text": lit(f"'{titulo}'"), "fontSize": lit("11D"),
                                        "fontColor": solido(GRIS), "bold": lit("true")}}]
    if fondo:
        vco["background"] = [{"properties": {"show": lit("true"), "color": solido("#FFFFFF"), "transparency": lit("0D")}}]
        vco["border"] = [{"properties": {"show": lit("true"), "color": solido(LINEA), "radius": lit("10D")}}]
        vco["padding"] = [{"properties": {"top": lit("6D"), "bottom": lit("6D"), "left": lit("8D"), "right": lit("8D")}}]
    v = {"visualType": tipo, "drillFilterOtherVisuals": True}
    if consulta:
        v["query"] = {"queryState": {k: {"projections": p} for k, p in consulta.items()}}
    if objetos:
        v["objects"] = objetos
    if vco:
        v["visualContainerObjects"] = vco
    return {"$schema": f"{ESQ}/visualContainer/1.0.0/schema.json", "name": nombre_v,
            "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": v}


def texto(n, x, y, w, h, titulo, subtitulo):
    parrafos = [{"textRuns": [{"value": titulo, "textStyle": {"fontWeight": "bold", "fontSize": "18pt", "color": TEXTO,
                                                               "fontFamily": "Segoe UI Semibold"}}]},
                {"textRuns": [{"value": subtitulo, "textStyle": {"fontSize": "10pt", "color": GRIS}}]}]
    return contenedor(n, x, y, w, h, "textbox", None, None, {"general": [{"properties": {"paragraphs": parrafos}}]}, fondo=False)


def tarjeta(n, x, y, w, h, medida_, titulo, color=TEXTO, tam="28D"):
    return contenedor(n, x, y, w, h, "card", {"Values": [M(medida_)]}, titulo,
                      {"labels": [{"properties": {"fontSize": lit(tam), "color": solido(color), "labelDisplayUnits": lit("1D")}}],
                       "categoryLabels": [{"properties": {"show": lit("false")}}]})


def mensaje(n, x, y, w, h, medida_, color):
    """Frase en lenguaje claro (medida de texto) en una tarjeta baja."""
    return contenedor(n, x, y, w, h, "card", {"Values": [M(medida_)]}, None,
                      {"labels": [{"properties": {"fontSize": lit("13D"), "color": solido(color)}}],
                       "categoryLabels": [{"properties": {"show": lit("false")}}]})


def segmentador(n, x, y, w, h, entidad, col, modo="Dropdown", unico=False, titulo=None, horizontal=False):
    obj = {"data": [{"properties": {"mode": lit(f"'{modo}'")}}],
           "header": [{"properties": {"show": lit("false")}}],
           "items": [{"properties": {"fontSize": lit("11D"), "fontColor": solido(TEXTO)}}]}
    if unico:
        obj["selection"] = [{"properties": {"singleSelect": lit("true")}}]
    if horizontal:
        obj["general"] = [{"properties": {"orientation": lit("1D")}}]
    return contenedor(n, x, y, w, h, "slicer", {"Values": [campo(entidad, col)]}, titulo, obj)


def estilo(color=None, etiquetas=False, linea=False):
    o = {"legend": [{"properties": {"show": lit("true"), "position": lit("'Top'"), "fontSize": lit("10D"),
                                    "labelColor": solido(GRIS)}}],
         "categoryAxis": [{"properties": {"showAxisTitle": lit("false"), "fontSize": lit("10D"), "labelColor": solido(GRIS)}}],
         "valueAxis": [{"properties": {"showAxisTitle": lit("false"), "fontSize": lit("10D"), "labelColor": solido(GRIS),
                                       "gridlineColor": solido("#EEF0F3")}}],
         "labels": [{"properties": {"show": lit("true" if etiquetas else "false"), "fontSize": lit("9D"), "color": solido(TEXTO),
                                "labelPosition": lit("'OutsideEnd'")}}]}
    if color:
        o["dataPoint"] = [{"properties": {"fill": solido(color)}}]
    if linea:
        o["lineStyles"] = [{"properties": {"strokeWidth": lit("3D"), "showMarker": lit("true"), "markerSize": lit("5D")}}]
    return o


def grafico(n, tipo, x, y, w, h, categorias, valores, titulo, serie=None, y2=None, color=None, etiquetas=False):
    c = {"Category": [campo(e, p, activo=(i == 0)) for i, (e, p) in enumerate(categorias)],
         "Y": [M(v) for v in valores]}
    if y2:
        c["Y2"] = [M(v) for v in y2]
    if serie:
        c["Series"] = [campo(*serie)]
    return contenedor(n, x, y, w, h, tipo, c, titulo, estilo(color, etiquetas, linea="line" in tipo.lower()))


def tabla(n, x, y, w, h, cols, titulo):
    return contenedor(n, x, y, w, h, "tableEx", {"Values": cols}, titulo,
                      {"columnHeaders": [{"properties": {"fontColor": solido(GRIS), "fontSize": lit("10D")}}],
                       "values": [{"properties": {"fontSize": lit("10D"), "fontColor": solido(TEXTO)}}]})


def navegador(n, x=620):
    return {"$schema": f"{ESQ}/visualContainer/1.0.0/schema.json", "name": n,
            "position": {"x": x, "y": 14, "z": 100, "height": 44, "width": 640, "tabOrder": 100},
            "visual": {"visualType": "pageNavigator", "drillFilterOtherVisuals": True}}


SECCIONES = []


def a_clasico(v):
    """Convierte un visual (estructura PBIR) al contenedor del formato clásico de report.json."""
    pos = v["position"]
    vis = v["visual"]
    sv = {"visualType": vis["visualType"], "drillFilterOtherVisuals": True}
    consulta = vis.get("query", {}).get("queryState")
    if consulta:
        alias, desde, sel, proy = {}, [], [], {}
        for rol, d in consulta.items():
            proy[rol] = []
            for pr in d["projections"]:
                (tipo, f), = pr["field"].items()
                ent = f["Expression"]["SourceRef"]["Entity"]
                if ent not in alias:
                    alias[ent] = f"t{len(alias)}"
                    desde.append({"Name": alias[ent], "Entity": ent, "Type": 0})
                nombre_q = pr["queryRef"]
                sel.append({tipo: {"Expression": {"SourceRef": {"Source": alias[ent]}}, "Property": f["Property"]}, "Name": nombre_q})
                item = {"queryRef": nombre_q}
                if pr.get("active"):
                    item["active"] = True
                proy[rol].append(item)
        sv["projections"] = proy
        sv["prototypeQuery"] = {"Version": 2, "From": desde, "Select": sel}
    if "objects" in vis:
        sv["objects"] = vis["objects"]
    if "visualContainerObjects" in vis:
        sv["vcObjects"] = vis["visualContainerObjects"]
    cfg = {"name": v["name"], "layouts": [{"id": 0, "position": {"x": pos["x"], "y": pos["y"], "z": pos["z"],
                                                                   "width": pos["width"], "height": pos["height"],
                                                                   "tabOrder": pos["tabOrder"]}}],
           "singleVisual": sv}
    return {"config": json.dumps(cfg, ensure_ascii=False), "filters": "[]", "height": float(pos["height"]),
            "width": float(pos["width"]), "x": float(pos["x"]), "y": float(pos["y"]), "z": float(pos["z"])}


def pagina(carpeta, nombre_p, visuales):
    SECCIONES.append({
        "config": json.dumps({"objects": {"background": [{"properties": {"color": solido("#F4F5F7"), "transparency": lit("0D")}}]}},
                             ensure_ascii=False),
        "displayName": nombre_p, "displayOption": 1, "filters": "[]", "height": 720.0, "name": carpeta,
        "visualContainers": [a_clasico(v) for v in visuales], "width": 1280.0})


def reporte():
    if REPORTE.exists():
        shutil.rmtree(REPORTE)
    escribir(REPORTE / "definition.pbir", json.dumps({"version": "1.0", "datasetReference": {
        "byPath": {"path": "../Microrred.SemanticModel"}, "byConnection": None}}, indent=2))
    tema = {"name": "Microrred", "dataColors": [AMARILLO, AZUL, VIOLETA, VERDE, "#E5634D", "#8A94A6"],
            "background": "#FFFFFF", "foreground": TEXTO, "tableAccent": AZUL,
            "textClasses": {"label": {"fontFace": "Segoe UI"}, "callout": {"fontFace": "Segoe UI Semibold"},
                            "title": {"fontFace": "Segoe UI Semibold"}, "header": {"fontFace": "Segoe UI Semibold"}}}
    escribir(REPORTE / "StaticResources" / "RegisteredResources" / "MicrorredTema.json", json.dumps(tema, ensure_ascii=False, indent=2))
    SECCIONES.clear()

    INV, PER = ("Inversor", "Nombre"), ("Fecha", "Año-Mes")
    mes = [("Fecha", "Año-Mes"), ("Fecha", "Día")]                           # drill-down: mes → día
    anio_mes = [("Fecha", "Año-Mes")]

    def cabecera(p, titulo, sub):
        return [texto(f"{p}_tit", 20, 2, 590, 68, titulo, sub), navegador(f"{p}_nav"),
                segmentador(f"{p}_s_inv", 20, 72, 300, 44, *INV, modo="Basic", horizontal=True),
                segmentador(f"{p}_s_per", 332, 72, 240, 44, *PER)]

    pagina("resumen", "Resumen ejecutivo", cabecera("r", "Resumen ejecutivo", "¿Cuánta energía da el sol y cuánto cuesta la red?") + [
        mensaje("r_m1", 588, 72, 330, 44, "Mensaje de autosuficiencia", T_VERDE),
        mensaje("r_m2", 930, 72, 330, 44, "Mensaje de ahorro", T_SOLAR),
        tarjeta("r_c1", 20, 128, 232, 100, "Energía solar (kWh)", "Energía solar (kWh)", T_SOLAR),
        tarjeta("r_c2", 264, 128, 232, 100, "Consumo (kWh)", "Consumo (kWh)", T_CONSUMO),
        tarjeta("r_c3", 508, 128, 232, 100, "Importación de red (kWh)", "Importación de red (kWh)", T_RED),
        tarjeta("r_c4", 752, 128, 232, 100, "Autosuficiencia (%)", "Autosuficiencia", T_VERDE),
        tarjeta("r_c5", 996, 128, 264, 100, "Ahorro por autogeneración (COP)", "Ahorro por autogeneración (COP)", T_VERDE),
        grafico("r_g1", "lineClusteredColumnComboChart", 20, 240, 800, 232, mes,
                ["Energía solar (kWh)", "Consumo (kWh)", "Importación de red (kWh)"],
                "Energía por mes y autosuficiencia · usa ⤵ para ver los días de cada mes", y2=["Autosuficiencia (%)"]),
        grafico("r_g2", "columnChart", 836, 240, 424, 232, anio_mes, ["Ahorro por autogeneración (COP)"],
                "Ahorro por mes (COP)", color=VERDE),
        grafico("r_g3", "lineChart", 20, 484, 620, 226, anio_mes, ["Energía solar (kWh)", "Energía solar mes anterior (kWh)"],
                "Energía solar frente al mes anterior"),
        tabla("r_t1", 656, 484, 604, 226, [campo("Fecha", "Año-Mes"), M("Costo de la red (COP)"),
              M("Ahorro por autogeneración (COP)"), M("Variación solar vs mes anterior (%)")], "Costo y ahorro por mes")])

    pagina("balance", "Balance y batería", cabecera("b", "Balance y batería", "¿De dónde viene la energía, a dónde va y cómo trabaja la batería?") + [
        tarjeta("b_c1", 20, 128, 300, 100, "Pérdidas del inversor (%)", "Pérdidas del inversor", T_RED),
        tarjeta("b_c2", 332, 128, 300, 100, "Ciclos de batería por día", "Ciclos de batería por día", T_VERDE),
        tarjeta("b_c3", 644, 128, 300, 100, "Tiempo en modo isla (%)", "Tiempo en modo isla", T_CONSUMO),
        tarjeta("b_c4", 956, 128, 304, 100, "Disponibilidad (%)", "Disponibilidad del registro", T_SOLAR),
        grafico("b_g1", "barChart", 20, 240, 620, 470, [("Balance energético", "Concepto")], ["Energía del concepto (kWh)"],
                "¿De dónde viene y a dónde va la energía? (kWh)", serie=("Balance energético", "Tipo"), etiquetas=True),
        grafico("b_g2", "columnChart", 656, 240, 604, 232, anio_mes, ["Ciclos de batería por día"],
                "Ciclos de batería por día", color=VERDE),
        grafico("b_g3", "lineChart", 656, 484, 604, 226, anio_mes, ["Tiempo en modo isla (%)"],
                "Tiempo en modo isla por mes", color=VIOLETA)])

    pagina("solarbi", "SolarBI y escenarios", [
        texto("s_tit", 20, 2, 590, 68, "SolarBI y escenarios", "¿Cuándo conviene entrenar y qué pasa si cambia la tarifa?"),
        navegador("s_nav"),
        segmentador("s_s1", 20, 72, 300, 44, "Perfil de tarea", "Categoría de tarea", modo="Basic", horizontal=True),
        segmentador("s_s2", 332, 72, 240, 44, *PER),
        mensaje("s_m1", 588, 72, 672, 44, "Mensaje de cómputo", T_CONSUMO),
        grafico("s_g1", "barChart", 20, 128, 620, 292, [("Perfil de tarea", "Modelo")], ["Energía por época (Wh)"],
                "Energía por época de entrenamiento (Wh)", color=AZUL, etiquetas=True),
        grafico("s_g2", "columnChart", 20, 432, 620, 278, [("Hora", "Hora")], ["Fracción solar del cómputo (%)"],
                "¿A qué hora conviene entrenar? Fracción solar según la hora de inicio", color=AMARILLO),
        segmentador("s_w1", 656, 128, 296, 80, "Parámetro tarifa", "Tarifa (COP/kWh)", unico=True, titulo="Escenario · tarifa (COP/kWh)"),
        segmentador("s_w2", 964, 128, 296, 80, "Parámetro solar", "Aumento de generación solar (%)", unico=True,
                    titulo="Escenario · más generación solar (%)"),
        tarjeta("s_c1", 656, 220, 296, 92, "Costo de la red (COP)", "Costo de la red hoy", T_RED, "24D"),
        tarjeta("s_c2", 964, 220, 296, 92, "Costo de la red del escenario (COP)", "Costo de la red en el escenario", T_CONSUMO, "24D"),
        tarjeta("s_c3", 656, 324, 296, 92, "Ahorro adicional del escenario (COP)", "Ahorro adicional", T_VERDE, "24D"),
        tarjeta("s_c4", 964, 324, 296, 92, "Autosuficiencia del escenario (%)", "Autosuficiencia en el escenario", T_VERDE, "24D"),
        grafico("s_g3", "columnChart", 656, 428, 604, 282, anio_mes, ["Costo de la red (COP)", "Costo de la red del escenario (COP)"],
                "Costo de la red por mes: hoy frente al escenario")])

    cfg = {"version": "5.55", "themeCollection": {"baseTheme": {"name": "CY24SU06", "version": "5.55", "type": 2},
                                                  "customTheme": {"name": "MicrorredTema.json", "version": "5.55", "type": 1}},
           "activeSectionIndex": 0, "defaultDrillFilterOtherVisuals": True,
           "settings": {"useNewFilterPaneExperience": True, "allowChangeFilterTypes": True, "useStylableVisualContainerHeader": True}}
    escribir(REPORTE / "report.json", json.dumps({
        "config": json.dumps(cfg, ensure_ascii=False), "layoutOptimization": 0,
        "resourcePackages": [
            {"resourcePackage": {"disabled": False, "items": [{"name": "CY24SU06", "path": "BaseThemes/CY24SU06.json", "type": 202}],
                                 "name": "SharedResources", "type": 2}},
            {"resourcePackage": {"disabled": False, "items": [{"name": "MicrorredTema.json", "path": "MicrorredTema.json", "type": 201}],
                                 "name": "RegisteredResources", "type": 1}}],
        "sections": SECCIONES}, ensure_ascii=False, indent=2))


def main():
    modelo()
    reporte()
    escribir(RAIZ / "Microrred.pbip", json.dumps({"version": "1.0", "artifacts": [{"report": {"path": "Microrred.Report"}}],
                                                  "settings": {"enableAutoRecovery": True}}, indent=2))
    print("Proyecto generado en", RAIZ)


if __name__ == "__main__":
    main()

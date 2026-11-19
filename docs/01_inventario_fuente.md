# Inventario de la fuente (capa Bronze)

- Archivo: `opencem-v1.0.0.sqlite` (4.44 GB), abierto en solo lectura.
- Generado con `etl/inventario_fuente.py` el 2026-11-19 14:36 en 5 s.
- Las marcas de tiempo de la base son segundos Unix en UTC; se muestran también en hora local del sitio (Asia/Shanghai, UTC+8).

## Resumen

| Tabla | Columnas | Filas | Desde | Hasta | Días |
|---|---|---|---|---|---|
| `analog_measurements` | 44 | 2,989,759 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) | 365.7 |
| `context` | 5 | 25,178 | 2024-04-30 16:00:00 UTC (2024-05-01 00:00 local) | 2026-07-22 15:59:59 UTC (2026-07-22 23:59 local) | 813.0 |
| `fault_history` | 66 | 2,129,517 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) | 365.7 |
| `settings` | 176 | 2,284,775 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) | 365.7 |
| `specs` | 16 | 1,333,174 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-02-02 18:40:30 UTC (2026-02-03 02:40 local) | 205.2 |
| `statistics` | 31 | 2,285,904 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) | 365.7 |
| `status` | 20 | 2,240,052 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) | 365.7 |
| `totals` | 21 | 2,279,918 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) | 365.7 |

## Detalle por tabla

### `analog_measurements`

- Columnas (44): `read_ts`, `inverter`, `battvolt`, `battcurr`, `battsoc`, `battchgpower`, `linechgcurr`, `pvchgcurr`, `battreserve`, `pv1volt`, `pv1curr`, `pv1power`, `pvreserve`, `outvolta`, `outcurra`, `outfreq`, `invcurra`, `outw_a`, `outva_a`, `loadpercenta`, `normalloadw_a`, `outsumw`, `outsumva`, `sumloadpercent`, `generatedpowerp_a`, `generatedpowers_a`, `generatedpowerq_a`, `linevolta`, `linecurra`, `linefreq`, `linepowerva_a`, `linepowerw_a`, `busvoltp`, `busvoltn`, `temper1`, `temper2`, `temper3`, `temper4`, `sir`, `fanduty`, `otherreserve`, `gridpowerw_a`, `gridcurr_a`, `grid_reserve`

| Inversor | Filas | Desde | Hasta |
|---|---|---|---|
| 1 | 1,610,276 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) |
| 2 | 1,379,483 | 2025-07-14 05:53:32 UTC (2025-07-14 13:53 local) | 2026-06-22 05:35:24 UTC (2026-06-22 13:35 local) |

### `context`

- Columnas (5): `id`, `recorded`, `start`, `end`, `value`

- Campo `recorded` (cuándo se anotó): 2024-07-27 10:00:00 UTC (2024-07-27 18:00 local) → 2026-07-14 10:59:48 UTC (2026-07-14 18:59 local)
- Campo `value`: JSON con claves comunes `source`, `device`, `inverter`, `context_type`.
- Tipos de contexto distintos: 56

| Fuente (`source`) | Filas |
|---|---|
| workstation2_log | 8,902 |
| windows_event_log | 6,271 |
| workstation1_log | 6,028 |
| derived_context_pipeline | 3,708 |
| wsl_bash_history | 204 |
| manual entry | 60 |
| manual_workload_entry | 5 |

| Dispositivo (`device`) | Filas |
|---|---|
| workstation2 | 11,671 |
| workstation1 | 9,746 |
| inverter | 2,379 |
| installation | 1,329 |
| (sin valor) | 53 |

| Tipo (`context_type`), 15 más frecuentes | Filas |
|---|---|
| cpu_compilation_workload | 11,974 |
| gpu_cnn_training_workload | 2,955 |
| windows_update_maintenance_window | 2,438 |
| battery_charging | 1,058 |
| wsl_virtualization_network_activity | 1,021 |
| battery_discharging | 659 |
| virtualized_disk_io_summary | 647 |
| pv_generation_active | 443 |
| calendar_day | 333 |
| solar_civil_twilight_morning | 332 |
| solar_daylight | 332 |
| solar_civil_twilight_evening | 331 |
| interactive_or_remote_logon | 329 |
| remote_access_or_ssh_activity | 286 |
| system_time_adjustment | 234 |


### `fault_history`

- Columnas (66): `read_ts`, `inverter`, `faulthistoryrecord00`, `faulthistoryrecord01`, `faulthistoryrecord02`, `faulthistoryrecord03`, `faulthistoryrecord04`, `faulthistoryrecord05`, `faulthistoryrecord06`, `faulthistoryrecord07`, `faulthistoryrecord08`, `faulthistoryrecord09`, `faulthistoryrecord10`, `faulthistoryrecord11`, `faulthistoryrecord12`, `faulthistoryrecord13`, `faulthistoryrecord14`, `faulthistoryrecord15`, `faulthistoryrecord16`, `faulthistoryrecord17`, `faulthistoryrecord18`, `faulthistoryrecord19`, `faulthistoryrecord20`, `faulthistoryrecord21`, `faulthistoryrecord22`, `faulthistoryrecord23`, `faulthistoryrecord24`, `faulthistoryrecord25`, `faulthistoryrecord26`, `faulthistoryrecord27`, `faulthistoryrecord28`, `faulthistoryrecord29`, `faulthistoryrecord30`, `faulthistoryrecord31`, `faulthistoryrecord00_time`, `faulthistoryrecord01_time`, `faulthistoryrecord02_time`, `faulthistoryrecord03_time`, `faulthistoryrecord04_time`, `faulthistoryrecord05_time`, `faulthistoryrecord06_time`, `faulthistoryrecord07_time`, `faulthistoryrecord08_time`, `faulthistoryrecord09_time`, `faulthistoryrecord10_time`, `faulthistoryrecord11_time`, `faulthistoryrecord12_time`, `faulthistoryrecord13_time`, `faulthistoryrecord14_time`, `faulthistoryrecord15_time`, `faulthistoryrecord16_time`, `faulthistoryrecord17_time`, `faulthistoryrecord18_time`, `faulthistoryrecord19_time`, `faulthistoryrecord20_time`, `faulthistoryrecord21_time`, `faulthistoryrecord22_time`, `faulthistoryrecord23_time`, `faulthistoryrecord24_time`, `faulthistoryrecord25_time`, `faulthistoryrecord26_time`, `faulthistoryrecord27_time`, `faulthistoryrecord28_time`, `faulthistoryrecord29_time`, `faulthistoryrecord30_time`, `faulthistoryrecord31_time`

| Inversor | Filas | Desde | Hasta |
|---|---|---|---|
| 1 | 1,175,134 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) |
| 2 | 954,383 | 2025-07-14 05:53:32 UTC (2025-07-14 13:53 local) | 2026-06-22 05:35:24 UTC (2026-06-22 13:35 local) |

### `settings`

- Columnas (176): `read_ts`, `inverter`, `outpriority`, `outvoltset`, `outfreqset`, `linerangeset`, `paramodeset`, `ecoen`, `chgpriority`, `maxchgcurrset`, `chgcurrbypvset`, `chgcurrbylineset`, `commidset`, `muteen`, `ongirdset`, `chgfullcurrset`, `ng_funcen`, `leakagechecken`, `userpassword`, `passwordset`, `ctrlflag1`, `battactiveset`, `ongridactivepowerset`, `ongridreactivepowerset`, `hybirdpriorityen`, `ongridpfset`, `gridstandardset`, `isodetecten`, `lowisovalue`, `maxlinepower`, `extctgethosten`, `outphasediffset`, `powerturboen`, `acoverlaodrestaren`, `gridconnectvoltmax`, `gridconnectvoltmin`, `gridconnectfreqmax`, `gridconnectfreqmin`, `gridreconnectvoltmax`, `gridreconnectvoltmin`, `gridreconnectfreqmax`, `gridreconnectfreqmin`, `gridovlevel1`, `gridovdelaytime1`, `gridovlevel2`, `gridovdelaytime2`, `griduvlevel1`, `griduvdelaytime1`, `griduvlevel2`, `griduvdelaytime2`, `ov10minprotectvalue`, `gridoflevel1`, `gridofdelaytime1`, `gridoflevel2`, `gridofdelaytime2`, `griduflevel1`, `gridufdelaytime1`, `griduflevel2`, `gridufdelaytime2`, `startongriddelay`, `loadingslope`, `ongridreconnectdelay`, `reloadingslope`, `powerdynamicrate`, `islanden`, `hvrten`, `lvrten`, `constreactpoweren`, `constpfen`, `f_pcurveen`, `p_qcurveen`, `u_pcurveen`, `u_qcurveen`, `drmen`, `remoteturnoffen`, `permitservice`, `reactpowerdynamicrate`, `reserve`, `maxongridactivepower`, `maxlinecurr`, `smartmeterpower`, `battype`, `cvvolt`, `floatvolt`, `battovervolt`, `cvchgtimeset`, `cvchgbackvolt`, `inv2linevolt`, `lineback2invvolt`, `battlowvolt`, `battdelayoffvolt`, `batteodvolt`, `battdelayofftime`, `batteodbackvolt`, `bmsset`, `bmsprotocal`, `batsoclowalarm`, `batstopsoc`, `battfullsoc`, `inv2linesoc`, `lineback2invsoc`, `ontimechargeen`, `chargestarttime1`, `chargeendtime1`, `chargestarttime2`, `chargeendtime2`, `chargestarttime3`, `chargeendtime3`, `ontimedischgen`, `dischgstarttime1`, `dischgendtime1`, `dischgstarttime2`, `dischgendtime2`, `dischgstarttime3`, `dischgendtime3`, `battpacknotunion`, `forcechgstopsoc`, `battpackrateah`, `battsetreserve`, `fp_of_start`, `fp_uf_start`, `fp_of_end`, `fp_uf_end`, `fp_of_dropslope`, `fp_uf_lodingslope`, `fp_actpowerresptr`, `pq_p1`, `pq_q1`, `pq_p2`, `pq_q2`, `pq_p3`, `pq_q3`, `pq_p1n`, `pq_q1n`, `pq_p2n`, `pq_q2n`, `pq_p3n`, `pq_q3n`, `pq_enablevolt`, `pq_disablevolt`, `up_v1`, `up_p1`, `up_v2`, `up_p2`, `up_actpowerresptr`, `up_v3`, `up_p3`, `up_v4`, `up_p4`, `uq_vref`, `uq_v1`, `uq_q1`, `uq_v2`, `uq_q2`, `uq_v3`, `uq_q3`, `uq_v4`, `uq_q4`, `uq_reactpowerresptr`, `uq_vrefautoen`, `uq_vrefresptr`, `uq_enablepower`, `uq_disablepower`, `hvrt_level1`, `hvrt_level1time`, `hvrt_level2`, `hvrt_level2time`, `hvrt_level3`, `hvrt_level3time`, `lvrt_level1`, `lvrt_level1time`, `lvrt_level2`, `lvrt_level2time`, `lvrt_level3`, `lvrt_level3time`, `presenttime`

| Inversor | Filas | Desde | Hasta |
|---|---|---|---|
| 1 | 1,280,052 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) |
| 2 | 1,004,723 | 2025-07-14 05:53:32 UTC (2025-07-14 13:53 local) | 2026-06-22 05:35:24 UTC (2026-06-22 13:35 local) |

### `specs`

- Columnas (16): `read_ts`, `inverter`, `machcode`, `producttype`, `manufacturename`, `sourcesn`, `hwver_m1`, `hwver_m2`, `hwver_s1`, `hwver_s2`, `protocolver`, `bmsver`, `libver`, `cpubuidtime`, `customsn`, `prdreserve`

| Inversor | Filas | Desde | Hasta |
|---|---|---|---|
| 1 | 678,646 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-02-02 18:39:15 UTC (2026-02-03 02:39 local) |
| 2 | 654,528 | 2025-07-14 05:53:32 UTC (2025-07-14 13:53 local) | 2026-02-02 18:40:30 UTC (2026-02-03 02:40 local) |

### `statistics`

- Columnas (31): `read_ts`, `inverter`, `batchgenergylast7day`, `batdischgenergylast7day`, `linechgenergylast7day`, `loadconsumlast7day`, `loadconsumfromlinelast7day`, `energyreserved0`, `generatedacpowertoday`, `batchgenergytoday`, `batdischgenergytoday`, `pvgeneratenergytoday`, `usedenergytoday`, `workdaystotal`, `batchgenergytotal`, `batdischgenergytotal`, `pvgeneratenergytotal`, `usedenergytotal`, `linechgenergytday`, `loadconsumlinetday`, `invworktimetoday`, `lineworktimetoday`, `linechgenergytotal`, `loadconsumlinetotal`, `invworktimetotal`, `lineworktimetotal`, `generatedacpowertotal`, `energyreserved2`, `energyreserved1`, `powerontime`, `stactimeback`

| Inversor | Filas | Desde | Hasta |
|---|---|---|---|
| 1 | 1,279,772 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) |
| 2 | 1,006,132 | 2025-07-14 05:53:32 UTC (2025-07-14 13:53 local) | 2026-06-22 05:35:24 UTC (2026-06-22 13:35 local) |

### `status`

- Columnas (20): `read_ts`, `inverter`, `startupstatus`, `outstatus`, `chgstatus`, `paramode`, `ecomode`, `battselfcheck`, `drycontact1`, `drycontact2`, `passwordstatus`, `sysstateflag`, `sysalarmflag`, `deroperationstate`, `derconnectstate`, `deralarmstatus`, `derinverterstate`, `derbattstate`, `remotectrlstatus`, `statusreserve`

| Inversor | Filas | Desde | Hasta |
|---|---|---|---|
| 1 | 1,233,147 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) |
| 2 | 1,006,905 | 2025-07-14 05:53:32 UTC (2025-07-14 13:53 local) | 2026-06-22 05:35:24 UTC (2026-06-22 13:35 local) |

### `totals`

- Columnas (21): `read_ts`, `inverter`, `alarmdetail`, `bmsreqchgvolt`, `bmsreqeodvolt`, `bmsreqchgcurr`, `bmsreqdischgcurr`, `bmsreserve`, `battsumpower`, `sys_battreserve`, `extpvsumoutw_a`, `sys_pvreserve`, `backupsumoutw_a`, `backupsumoutva_a`, `normalsumloadw_a`, `normalsumloadva_a`, `generatedsumpowerp_a`, `generatedsumpowers_a`, `sys_outreserve`, `linesumpowerw_a`, `sys_linereserve`

| Inversor | Filas | Desde | Hasta |
|---|---|---|---|
| 1 | 1,262,985 | 2025-07-12 13:31:35 UTC (2025-07-12 21:31 local) | 2026-07-13 05:13:53 UTC (2026-07-13 13:13 local) |
| 2 | 1,016,933 | 2025-07-14 05:53:32 UTC (2025-07-14 13:53 local) | 2026-06-22 05:35:24 UTC (2026-06-22 13:35 local) |

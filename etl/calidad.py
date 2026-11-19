"""Bitácora de calidad: conteos antes y después de cada regla de limpieza (§4 E).

Cada regla queda como una fila en silver.calidad_log, ligada a la ejecución del ETL.
"""
from dataclasses import dataclass, field


@dataclass
class Regla:
    regla: str
    descripcion: str
    tabla: str
    filas_antes: int
    filas_afectadas: int
    filas_despues: int
    accion: str   # descartar / anular / recortar / marcar / imputar / agregar / deduplicar


@dataclass
class BitacoraCalidad:
    reglas: list = field(default_factory=list)

    def registrar(self, regla, descripcion, tabla, antes, afectadas, despues, accion):
        r = Regla(regla, descripcion, tabla, int(antes), int(afectadas), int(despues), accion)
        self.reglas.append(r)
        print(f"  [{r.regla:>4}] {r.descripcion}: {r.filas_antes:,} → {r.filas_despues:,} "
              f"({r.filas_afectadas:,} afectadas, {r.accion})")

    def filas(self, ejecucion_id):
        return [(ejecucion_id, i + 1, r.regla, r.descripcion, r.tabla, r.filas_antes,
                 r.filas_afectadas, r.filas_despues, r.accion) for i, r in enumerate(self.reglas)]

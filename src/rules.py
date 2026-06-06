"""Reglas deterministicas para el MVP de programacion PYC."""

from __future__ import annotations

import pandas as pd


TURNOS = {
    1: "0730-0930",
    2: "0930-1130",
    3: "1130-1330",
    4: "1330-1500",
}

TURNOS_POR_GRUPO = {
    "A": [1, 2, 3],
    "B": [2, 3, 4],
}

GRUPO_PRIMER_SERVICIO_DEFAULT = "A"

SUPERVISORES_ZONA = {
    "Z1": {"supervisor": "KAREN GUERRERO", "asistente": ""},
    "Z2": {"supervisor": "DANIELA SOTO", "asistente": "WILLIAM BENJUMEA"},
    "Z3": {"supervisor": "EDNA SERRATO", "asistente": "RICARDO LOZANO"},
}

TITULOS_ZONA = {
    "Z1": "ZONA 1 (Z1) AUDITORIO",
    "Z2": "ZONA 2 (Z2) SPK",
    "Z3": "ZONA 3 (Z3) EXTERIORES",
}

ESTADOS_NO_DISPONIBLES = ["sin confirmar", "declinado"]


def _position(
    zona: str,
    posicion: str,
    tipo: str,
    genero_requerido: str = "cualquiera",
    cantidad: int = 1,
    regla_especial: str = "",
) -> dict:
    turnos_obligatorios = sorted(TURNOS) if tipo == "critica" else []

    return {
        "zona": zona,
        "posicion": posicion,
        "tipo": tipo,
        "turnos_obligatorios": turnos_obligatorios,
        "genero_requerido": genero_requerido,
        "cantidad": cantidad,
        "regla_especial": regla_especial,
    }


def _crit(
    zona: str,
    posicion: str,
    genero_requerido: str = "cualquiera",
    cantidad: int = 1,
    regla_especial: str = "",
) -> dict:
    return _position(zona, posicion, "critica", genero_requerido, cantidad, regla_especial)


def _ref(
    zona: str,
    posicion: str,
    genero_requerido: str = "cualquiera",
    cantidad: int = 1,
    regla_especial: str = "",
) -> dict:
    return _position(zona, posicion, "refuerzo", genero_requerido, cantidad, regla_especial)

POSICIONES = [
    _crit("Z1", "Alfa1 - Ingreso púlpito", "H"),
    _ref("Z1", "Corredor Alfa 1-4", "M"),
    _crit("Z1", "Alfa2 - Entrada líderes"),
    _crit("Z1", "Alfa3 - Entrada auditorio"),
    _crit("Z1", "Alfa4 - Entrada prioritaria", "H"),
    _crit("Z1", "Alfa5", "M"),
    _crit("Z1", "Alfa6 - Salida interna parq."),
    _crit("Z1", "Alfa7 - Entrada padres SPK"),
    _crit("Z1", "Alfa8 - Entrada PMU"),
    _crit("Z1", "Alfa9 H - Púlpito", "H"),
    _ref("Z1", "Alfa10 - Master (refuerzo)", "M"),
    _crit("Z2", "Av. Suba ingreso"),
    _crit("Z2", "Corredor ingreso SPK", "M"),
    _ref("Z2", "Corredor ingreso (refuerzo)"),
    _ref("Z2", "Corredor evac. SP babies (ref)"),
    _crit("Z2", "Puerta acompañantes"),
    _crit("Z2", "Auditorio SPK", "M", cantidad=3, regla_especial="spk_base"),
    _ref("Z2", "Auditorio SPK (refuerzo)", "M", regla_especial="spk_refuerzo"),
    _crit("Z2", "Ascensor SPK", "M"),
    _crit("Z2", "Salida SP babies", "M"),
    _crit("Z2", "Ingreso Padres SPK 2piso"),
    _crit("Z2", "Rampa salida SPK 2 piso"),
    _ref("Z2", "Overflow salón 215 (refuerzo)"),
    _ref("Z2", "Salida puerta vidrio SPK (apoyo)", regla_especial="apoyo_evacuacion"),
    _ref("Z2", "Escaleras eléctricas 1 piso", "M", regla_especial="spk_evacuacion_1"),
    _ref("Z2", "Escaleras eléctricas 2 piso", "M", regla_especial="spk_evacuacion_2"),
    _ref("Z2", "Escaleras capacitación 1P", "M", regla_especial="spk_evacuacion_3"),
    _ref("Z2", "Escaleras capacitación 2P", regla_especial="apoyo_evacuacion"),
    _crit("Z3", "Ingreso lobby / puerta principal", regla_especial="ideal_h_m"),
    _ref("Z3", "Ingreso lobby / puerta (ref)", regla_especial="ideal_h_m"),
    _crit("Z3", "PMU - Radios chaquetas", regla_especial="pmu_luz_helena_pendiente"),
    _crit("Z3", "Ingreso AV Suba líderes"),
    _ref("Z3", "Rampa / coffee (refuerzo)"),
    _crit("Z3", "Ascensor salón VIP", "M"),
    _ref("Z3", "Pasillo lobby / VIP (ref)", "H"),
    _crit("Z3", "Salida Parque"),
    _ref("Z3", "Salida Parque (refuerzo)"),
    _crit("Z3", "MEC y baños auditorio", "M", regla_especial="mec_banos_base"),
    _ref("Z3", "MEC y baños (refuerzo)", "H", regla_especial="mec_banos_refuerzo"),
    _crit("Z3", "Baños SPK", "M"),
    _crit("Z3", "Parqueadero y edificio", "H"),
    _ref("Z3", "Edificio adm. 3P (refuerzo)"),
    _ref("Z3", "Edificio adm. 4P (refuerzo)"),
    _ref("Z3", "Edificio adm. 5P (refuerzo)"),
]

ZONAS_CONFIGURADAS = sorted(set(SUPERVISORES_ZONA) | {position["zona"] for position in POSICIONES})
ESTADOS_ZONA_FIJA = {zona: zona for zona in ZONAS_CONFIGURADAS}
ESTADOS_DISPONIBLES = ["confirmado", *ESTADOS_ZONA_FIJA.keys(), "apoyo"]
ESTADOS_VALIDOS = ESTADOS_DISPONIBLES + ESTADOS_NO_DISPONIBLES


def get_positions_df() -> pd.DataFrame:
    """Devuelve el catalogo inicial de posiciones como DataFrame."""
    return pd.DataFrame(POSICIONES)


def build_turnos_por_grupo(grupo_primer_servicio: str) -> dict[str, list[int]]:
    """Calcula los turnos de cada grupo segun quien inicia el primer servicio."""
    grupos = sorted(TURNOS_POR_GRUPO)
    primer_grupo = str(grupo_primer_servicio or GRUPO_PRIMER_SERVICIO_DEFAULT).upper()
    if primer_grupo not in grupos:
        primer_grupo = GRUPO_PRIMER_SERVICIO_DEFAULT

    if len(grupos) != 2:
        return TURNOS_POR_GRUPO.copy()

    segundo_grupo = next(grupo for grupo in grupos if grupo != primer_grupo)
    return {
        primer_grupo: [1, 2, 3],
        segundo_grupo: [2, 3, 4],
    }


def get_required_slots() -> pd.DataFrame:
    """Expande posiciones por turno y cantidad requerida u opcional."""
    slots = []

    for position in POSICIONES:
        turnos_posicion = sorted(TURNOS) if position["tipo"] == "refuerzo" else position["turnos_obligatorios"]

        for turno in turnos_posicion:
            for slot_numero in range(1, int(position["cantidad"]) + 1):
                slots.append(
                    {
                        "turno": turno,
                        "horario": TURNOS[turno],
                        "zona": position["zona"],
                        "posicion": position["posicion"],
                        "tipo": position["tipo"],
                        "genero_requerido": position["genero_requerido"],
                        "slot_numero": slot_numero,
                        "regla_especial": position.get("regla_especial", ""),
                        "obligatorio": turno in position["turnos_obligatorios"],
                    }
                )

    return pd.DataFrame(slots)

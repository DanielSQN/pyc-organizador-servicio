"""Asignador deterministico de voluntarios para el MVP."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

import pandas as pd

from src.rules import ESTADOS_ZONA_FIJA, TURNOS_POR_GRUPO, get_required_slots


UNASSIGNED_NAME = "SIN ASIGNAR"
FREE_NAME = "-- (Libre)"
PMU_FIXED_NAME = "Luz Helena Roncancio Garcia"
SPK_EVACUATION_RULES = {
    "spk_evacuacion_1": 1,
    "spk_evacuacion_2": 2,
    "spk_evacuacion_3": 3,
}
SPK_EVACUATION_POSITIONS = {
    "Escaleras eléctricas 1 piso",
    "Escaleras eléctricas 2 piso",
    "Escaleras capacitación 1P",
}
GENDER_LABELS = {
    "M": "M (mujer)",
    "H": "H (hombre)",
    "cualquiera": "cualquiera",
}
ALLOWED_REPEAT_RULES = {
    "pmu_luz_helena_pendiente",
    "spk_base",
    "spk_refuerzo",
    *SPK_EVACUATION_RULES,
}

OUTPUT_COLUMNS = [
    "Turno",
    "Horario",
    "Zona",
    "Posición",
    "Tipo",
    "Slot",
    "Obligatorio",
    "Grupo",
    "Nombre",
    "Apellido",
    "Género",
    "Estado",
    "Observaciones",
]


def generate_schedule(
    volunteers_df: pd.DataFrame,
    turnos_por_grupo: Optional[dict[str, list[int]]] = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Genera una programacion basica con reglas deterministicas."""
    volunteers = volunteers_df.copy().reset_index(drop=True)
    volunteers["_id"] = volunteers.index
    turnos_por_grupo = turnos_por_grupo or TURNOS_POR_GRUPO

    required_slots = get_required_slots()
    required_slots["_tipo_orden"] = required_slots.apply(_slot_order, axis=1)
    required_slots = required_slots.sort_values(
        ["_tipo_orden", "turno", "zona", "posicion", "slot_numero"]
    ).reset_index(drop=True)

    assigned_by_turn: dict[int, set[int]] = defaultdict(set)
    zones_by_person: dict[int, list[str]] = defaultdict(list)
    continuity_assignments: dict[tuple[str, int], int] = {}
    assignment_rows = []
    alerts: list[str] = []

    for _, slot in required_slots.iterrows():
        forced_volunteer = _forced_volunteer(
            volunteers,
            slot,
            assigned_by_turn[int(slot["turno"])],
            continuity_assignments,
            turnos_por_grupo,
        )
        if forced_volunteer is not None:
            if slot["regla_especial"] not in SPK_EVACUATION_RULES:
                _track_assignment(
                    forced_volunteer,
                    slot,
                    assigned_by_turn,
                    zones_by_person,
                    alerts,
                    repeated_zone=False,
                )
            assignment_rows.append(_assigned_row(slot, forced_volunteer))
            continue

        candidates = _compatible_candidates(
            volunteers,
            slot,
            assigned_by_turn[int(slot["turno"])],
            turnos_por_grupo,
        )
        candidates = _apply_special_filters(candidates, slot, continuity_assignments, turnos_por_grupo)

        if candidates.empty:
            if bool(slot["obligatorio"]):
                assignment_rows.append(_unassigned_row(slot))
            else:
                assignment_rows.append(_free_row(slot))
            continue

        preferred = candidates[candidates["Estado"] != "apoyo"]
        if preferred.empty:
            preferred = candidates

        no_zone_repeat = preferred[
            ~preferred["_id"].apply(lambda person_id: slot["zona"] in zones_by_person[int(person_id)])
        ]
        repeated_zone = no_zone_repeat.empty

        if not no_zone_repeat.empty:
            preferred = no_zone_repeat

        selected = preferred.sort_values(["Estado", "Grupo", "Nombre", "Apellido", "_id"]).iloc[0]
        _store_continuity_assignment(selected, slot, continuity_assignments, turnos_por_grupo)
        _track_assignment(selected, slot, assigned_by_turn, zones_by_person, alerts, repeated_zone)
        assignment_rows.append(_assigned_row(slot, selected))

    schedule_df = pd.DataFrame(assignment_rows, columns=OUTPUT_COLUMNS)
    alerts.extend(validate_schedule(schedule_df, turnos_por_grupo))

    return schedule_df, alerts


def _slot_order(slot: pd.Series) -> int:
    if slot["regla_especial"] == "pmu_luz_helena_pendiente":
        return -2
    if slot["regla_especial"] == "spk_base":
        return -1
    if slot["tipo"] == "critica":
        return 0
    if bool(slot["obligatorio"]):
        return 1
    return 2


def _forced_volunteer(
    volunteers: pd.DataFrame,
    slot: pd.Series,
    already_assigned_in_turn: set[int],
    continuity_assignments: dict[tuple[str, int], int],
    turnos_por_grupo: dict[str, list[int]],
) -> Optional[pd.Series]:
    if slot["regla_especial"] in SPK_EVACUATION_RULES:
        continuity_key = _spk_continuity_key_for_turn(
            int(slot["turno"]),
            SPK_EVACUATION_RULES[str(slot["regla_especial"])],
            turnos_por_grupo,
        )
        person_id = continuity_assignments.get(continuity_key)
        if person_id is None:
            return None

        match = volunteers[volunteers["_id"] == person_id]
        return None if match.empty else match.iloc[0]

    if slot["regla_especial"] != "pmu_luz_helena_pendiente":
        return None

    named = volunteers[volunteers.apply(lambda row: _full_name(row) == PMU_FIXED_NAME.lower(), axis=1)]
    if named.empty:
        return None

    volunteer = named.iloc[0]
    if int(volunteer["_id"]) in already_assigned_in_turn:
        return None

    return volunteer


def _compatible_candidates(
    volunteers: pd.DataFrame,
    slot: pd.Series,
    already_assigned_in_turn: set[int],
    turnos_por_grupo: dict[str, list[int]],
) -> pd.DataFrame:
    turno = int(slot["turno"])
    zona = slot["zona"]
    genero_requerido = slot["genero_requerido"]

    candidates = volunteers[
        volunteers["Grupo"].apply(lambda group: turno in turnos_por_grupo.get(group, []))
    ].copy()

    candidates = candidates[~candidates["_id"].isin(already_assigned_in_turn)]

    if genero_requerido != "cualquiera":
        candidates = candidates[candidates["Género"] == genero_requerido]

    candidates = candidates[
        candidates["Estado"].apply(lambda estado: ESTADOS_ZONA_FIJA.get(estado, zona) == zona)
    ]

    return candidates


def _apply_special_filters(
    candidates: pd.DataFrame,
    slot: pd.Series,
    continuity_assignments: dict[tuple[str, int], int],
    turnos_por_grupo: dict[str, list[int]],
) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    rule = slot["regla_especial"]
    turno = int(slot["turno"])

    if rule == "spk_base":
        required_group = _spk_group_for_turn(turno, turnos_por_grupo)
        candidates = candidates[(candidates["Grupo"] == required_group) & (candidates["Género"] == "M")]

        continuity_key = _continuity_key(slot, turnos_por_grupo)
        if continuity_key in continuity_assignments:
            return candidates[candidates["_id"] == continuity_assignments[continuity_key]]

    if rule == "spk_refuerzo":
        if turno == 4:
            return candidates.iloc[0:0]

        required_group = _spk_refuerzo_group(turnos_por_grupo)
        candidates = candidates[(candidates["Grupo"] == required_group) & (candidates["Género"] == "M")]

        continuity_key = _continuity_key(slot, turnos_por_grupo)
        if continuity_key in continuity_assignments:
            return candidates[candidates["_id"] == continuity_assignments[continuity_key]]

    if rule == "pmu_luz_helena_pendiente":
        return candidates[candidates.apply(lambda row: _full_name(row) == PMU_FIXED_NAME.lower(), axis=1)]

    return candidates


def _continuity_key(
    slot: pd.Series,
    turnos_por_grupo: Optional[dict[str, list[int]]] = None,
) -> tuple[str, int]:
    rule = str(slot["regla_especial"])
    turno = int(slot["turno"])
    slot_number = int(slot["slot_numero"])

    if rule == "spk_base":
        block = _spk_group_for_turn(turno, turnos_por_grupo or TURNOS_POR_GRUPO)
        return (f"{rule}_{block}", slot_number)

    return (rule, slot_number)


def _spk_continuity_key_for_turn(
    turno: int,
    slot_number: int,
    turnos_por_grupo: dict[str, list[int]],
) -> tuple[str, int]:
    return (f"spk_base_{_spk_group_for_turn(turno, turnos_por_grupo)}", slot_number)


def _spk_group_for_turn(turno: int, turnos_por_grupo: dict[str, list[int]]) -> str:
    groups_in_turn = [
        group for group, turnos in sorted(turnos_por_grupo.items()) if int(turno) in set(turnos)
    ]
    if int(turno) in {1, 2}:
        groups_starting_first = [
            group for group, turnos in sorted(turnos_por_grupo.items()) if 1 in set(turnos)
        ]
        if groups_starting_first:
            return groups_starting_first[0]
    if int(turno) in {3, 4}:
        groups_finishing_last = [
            group for group, turnos in sorted(turnos_por_grupo.items()) if 4 in set(turnos)
        ]
        if groups_finishing_last:
            return groups_finishing_last[0]
    return groups_in_turn[0] if groups_in_turn else "A"


def _spk_refuerzo_group(turnos_por_grupo: dict[str, list[int]]) -> str:
    groups_finishing_last = [
        group for group, turnos in sorted(turnos_por_grupo.items()) if 4 in set(turnos)
    ]
    return groups_finishing_last[0] if groups_finishing_last else _spk_group_for_turn(3, turnos_por_grupo)


def _store_continuity_assignment(
    volunteer: pd.Series,
    slot: pd.Series,
    continuity_assignments: dict[tuple[str, int], int],
    turnos_por_grupo: dict[str, list[int]],
) -> None:
    if slot["regla_especial"] not in {"spk_base", "spk_refuerzo"}:
        return

    continuity_assignments.setdefault(_continuity_key(slot, turnos_por_grupo), int(volunteer["_id"]))


def _track_assignment(
    volunteer: pd.Series,
    slot: pd.Series,
    assigned_by_turn: dict[int, set[int]],
    zones_by_person: dict[int, list[str]],
    alerts: list[str],
    repeated_zone: bool,
) -> None:
    person_id = int(volunteer["_id"])
    turno = int(slot["turno"])
    assigned_by_turn[turno].add(person_id)

    if slot["regla_especial"] in ALLOWED_REPEAT_RULES:
        zones_by_person[person_id].append(slot["zona"])
        return

    if slot["zona"] in zones_by_person[person_id]:
        repeated_zone = True
    zones_by_person[person_id].append(slot["zona"])

    if repeated_zone:
        alerts.append(
            _format_alert(
                "ADVERTENCIA",
                slot,
                f"{volunteer['Nombre']} {volunteer['Apellido']} repitió zona por falta de alternativas",
            )
        )


def _assigned_row(slot: pd.Series, volunteer: pd.Series) -> dict:
    return {
        "Turno": int(slot["turno"]),
        "Horario": slot["horario"],
        "Zona": slot["zona"],
        "Posición": slot["posicion"],
        "Tipo": slot["tipo"],
        "Slot": int(slot["slot_numero"]),
        "Obligatorio": bool(slot["obligatorio"]),
        "Grupo": volunteer["Grupo"],
        "Nombre": volunteer["Nombre"],
        "Apellido": volunteer["Apellido"],
        "Género": volunteer["Género"],
        "Estado": volunteer["Estado"],
        "Observaciones": volunteer["Observaciones"],
    }


def _unassigned_row(slot: pd.Series) -> dict:
    return {
        "Turno": int(slot["turno"]),
        "Horario": slot["horario"],
        "Zona": slot["zona"],
        "Posición": slot["posicion"],
        "Tipo": slot["tipo"],
        "Slot": int(slot["slot_numero"]),
        "Obligatorio": bool(slot["obligatorio"]),
        "Grupo": "",
        "Nombre": UNASSIGNED_NAME,
        "Apellido": "",
        "Género": "",
        "Estado": "",
        "Observaciones": "",
    }


def _free_row(slot: pd.Series) -> dict:
    return {
        "Turno": int(slot["turno"]),
        "Horario": slot["horario"],
        "Zona": slot["zona"],
        "Posición": slot["posicion"],
        "Tipo": slot["tipo"],
        "Slot": int(slot["slot_numero"]),
        "Obligatorio": bool(slot["obligatorio"]),
        "Grupo": "",
        "Nombre": FREE_NAME,
        "Apellido": "",
        "Género": "",
        "Estado": "",
        "Observaciones": "",
    }


def validate_schedule(
    schedule_df: pd.DataFrame,
    turnos_por_grupo: Optional[dict[str, list[int]]] = None,
) -> list[str]:
    """Valida una programacion generada o editada manualmente."""
    alerts: list[str] = []
    turnos_por_grupo = turnos_por_grupo or TURNOS_POR_GRUPO
    assigned = schedule_df[~schedule_df["Nombre"].isin([UNASSIGNED_NAME, FREE_NAME])].copy()

    unassigned = schedule_df[
        (schedule_df["Nombre"] == UNASSIGNED_NAME)
        & (schedule_df.get("Obligatorio", True).astype(bool))
    ]
    for _, row in unassigned.iterrows():
        alerts.append(
            _format_alert(
                "SIN ASIGNAR",
                row,
                f"Requiere género {_gender_label(_required_gender_for_row(row))}",
            )
        )

    if assigned.empty:
        return alerts

    assigned["persona"] = (
        assigned["Nombre"].astype(str).str.strip()
        + " "
        + assigned["Apellido"].astype(str).str.strip()
    ).str.strip()

    for (turno, persona), group in assigned.groupby(["Turno", "persona"]):
        regular_assignments = group[~group.apply(_is_allowed_evacuation_duplicate, axis=1)]
        if len(regular_assignments) <= 1:
            continue

        first_row = group.iloc[0]
        alerts.append(
            _format_alert(
                "ERROR",
                first_row,
                f"{persona} fue asignado más de una vez en este turno",
            )
        )

    gender_checks = assigned[
        (assigned["Género"] != "")
        & (assigned["Posición"] != "")
        & (assigned.apply(_gender_mismatch, axis=1))
    ]
    for _, row in gender_checks.iterrows():
        alerts.append(
            _format_alert(
                "ERROR",
                row,
                f"Requiere género {_gender_label(_required_gender_for_row(row))} y se asignó {_gender_label(row['Género'])}",
            )
        )

    for _, row in assigned.iterrows():
        required_zone = ESTADOS_ZONA_FIJA.get(row["Estado"])
        if required_zone and row["Zona"] != required_zone:
            alerts.append(
                _format_alert(
                    "ERROR",
                    row,
                    f"{row['Nombre']} {row['Apellido']} tiene estado {row['Estado']} y debe ir en {required_zone}",
                )
            )

    alerts.extend(_special_rule_validations(assigned, turnos_por_grupo))

    return alerts


def _special_rule_validations(
    assigned: pd.DataFrame,
    turnos_por_grupo: dict[str, list[int]],
) -> list[str]:
    alerts: list[str] = []

    pmu = assigned[assigned["Posición"] == "PMU - Radios chaquetas"]
    for _, row in pmu.iterrows():
        if _full_name(row) != PMU_FIXED_NAME.lower():
            alerts.append(
                _format_alert("ERROR", row, f"Requiere a {PMU_FIXED_NAME}")
            )

    spk = assigned[assigned["Posición"] == "Auditorio SPK"]
    for _, row in spk.iterrows():
        required_group = _spk_group_for_turn(int(row["Turno"]), turnos_por_grupo)
        if row["Grupo"] != required_group:
            alerts.append(
                _format_alert(
                    "ERROR",
                    row,
                    f"Requiere grupo {required_group} y se asignó grupo {row['Grupo']}",
                )
            )

    spk_ref = assigned[assigned["Posición"] == "Auditorio SPK (refuerzo)"]
    for _, row in spk_ref.iterrows():
        required_group = _spk_refuerzo_group(turnos_por_grupo)
        if row["Grupo"] != required_group:
            alerts.append(
                _format_alert(
                    "ERROR",
                    row,
                    f"Requiere grupo {required_group} y se asignó grupo {row['Grupo']}",
                )
            )

    alerts.extend(_validate_same_person_pair(spk, "Auditorio SPK", 1, 2))
    alerts.extend(_validate_same_person_pair(spk, "Auditorio SPK", 3, 4))
    alerts.extend(_validate_evacuation_assignments(assigned, spk))

    return alerts


def _is_allowed_evacuation_duplicate(row: pd.Series) -> bool:
    return str(row["Posición"]) in SPK_EVACUATION_POSITIONS


def _format_alert(prefix: str, row: pd.Series, message: str) -> str:
    zone = row.get("Zona", row.get("zona", ""))
    turn = row.get("Turno", row.get("turno", ""))
    schedule = row.get("Horario", row.get("horario", ""))
    turn_label = f"Turno {turn} ({str(schedule).replace('-', ' - ')})" if schedule else f"Turno {turn}"
    schedule_position = row.get("Posición", None)
    position = schedule_position if schedule_position is not None else row.get("posicion", "")
    return f"{prefix}: {zone} - {turn_label} - {position} - {message}"


def _validate_evacuation_assignments(assigned: pd.DataFrame, spk: pd.DataFrame) -> list[str]:
    alerts: list[str] = []
    position_slots = {
        "Escaleras eléctricas 1 piso": 1,
        "Escaleras eléctricas 2 piso": 2,
        "Escaleras capacitación 1P": 3,
    }

    for position, slot in position_slots.items():
        evacuation_rows = assigned[assigned["Posición"] == position]
        for _, row in evacuation_rows.iterrows():
            source = spk[(spk["Turno"] == row["Turno"]) & (spk["Slot"] == slot)]
            if source.empty:
                continue

            if _full_name(row) != _full_name(source.iloc[0]):
                alerts.append(
                    _format_alert(
                        "ERROR",
                        row,
                        f"Requiere la misma servidora del Auditorio SPK slot {slot}",
                    )
                )

    return alerts


def _validate_same_person_pair(
    rows: pd.DataFrame,
    position: str,
    first_turn: int,
    second_turn: int,
) -> list[str]:
    alerts: list[str] = []

    for slot in sorted(rows["Slot"].unique()):
        first = rows[(rows["Turno"] == first_turn) & (rows["Slot"] == slot)]
        second = rows[(rows["Turno"] == second_turn) & (rows["Slot"] == slot)]

        if first.empty or second.empty:
            continue

        first_name = _full_name(first.iloc[0])
        second_name = _full_name(second.iloc[0])
        if first_name != second_name:
            alerts.append(
                _format_alert(
                    "ERROR",
                    first.iloc[0],
                    f"Requiere la misma persona en turnos {first_turn} y {second_turn}",
                )
            )

    return alerts


def apply_manual_assignment(
    schedule_df: pd.DataFrame,
    row_index: int,
    volunteer: Optional[pd.Series],
    turnos_por_grupo: Optional[dict[str, list[int]]] = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Reasigna manualmente una fila de programacion y recalcula alertas."""
    updated_df = schedule_df.copy()

    if volunteer is None:
        updated_df.loc[row_index, ["Grupo", "Nombre", "Apellido", "Género", "Estado", "Observaciones"]] = [
            "",
            UNASSIGNED_NAME,
            "",
            "",
            "",
            "",
        ]
    else:
        updated_df.loc[row_index, ["Grupo", "Nombre", "Apellido", "Género", "Estado", "Observaciones"]] = [
            volunteer["Grupo"],
            volunteer["Nombre"],
            volunteer["Apellido"],
            volunteer["Género"],
            volunteer["Estado"],
            volunteer["Observaciones"],
        ]

    return updated_df, validate_schedule(updated_df, turnos_por_grupo)


def _required_gender_for_row(row: pd.Series) -> str:
    required_slots = get_required_slots()
    match = required_slots[
        (required_slots["turno"] == row["Turno"])
        & (required_slots["zona"] == row["Zona"])
        & (required_slots["posicion"] == row["Posición"])
        & (required_slots["slot_numero"] == row["Slot"])
    ]
    if match.empty:
        return "cualquiera"
    return str(match.iloc[0]["genero_requerido"])


def _gender_label(value: object) -> str:
    text = str(value).strip()
    return GENDER_LABELS.get(text, text)


def _gender_mismatch(row: pd.Series) -> bool:
    required_gender = _required_gender_for_row(row)
    return required_gender != "cualquiera" and row["Género"] != required_gender


def _full_name(row: pd.Series) -> str:
    return f"{row['Nombre']} {row['Apellido']}".strip().lower()

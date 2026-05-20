"""Asignador deterministico de voluntarios para el MVP."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

import pandas as pd

from src.rules import ESTADOS_ZONA_FIJA, TURNOS_POR_GRUPO, get_required_slots


UNASSIGNED_NAME = "SIN ASIGNAR"
FREE_NAME = "-- (Libre)"
PMU_FIXED_NAME = "Luz Helena Roncancio"

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


def generate_schedule(volunteers_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Genera una programacion basica con reglas deterministicas."""
    volunteers = volunteers_df.copy().reset_index(drop=True)
    volunteers["_id"] = volunteers.index

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
        forced_volunteer = _forced_volunteer(volunteers, slot, assigned_by_turn[int(slot["turno"])])
        if forced_volunteer is not None:
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

        candidates = _compatible_candidates(volunteers, slot, assigned_by_turn[int(slot["turno"])])
        candidates = _apply_special_filters(candidates, slot, continuity_assignments)

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
        _store_continuity_assignment(selected, slot, continuity_assignments)
        _track_assignment(selected, slot, assigned_by_turn, zones_by_person, alerts, repeated_zone)
        assignment_rows.append(_assigned_row(slot, selected))

    schedule_df = pd.DataFrame(assignment_rows, columns=OUTPUT_COLUMNS)
    alerts.extend(validate_schedule(schedule_df))

    return schedule_df, alerts


def _slot_order(slot: pd.Series) -> int:
    if slot["regla_especial"] == "pmu_luz_helena_pendiente":
        return -2
    if slot["regla_especial"] in {"spk_base", "spk_refuerzo"}:
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
) -> Optional[pd.Series]:
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
) -> pd.DataFrame:
    turno = int(slot["turno"])
    zona = slot["zona"]
    genero_requerido = slot["genero_requerido"]

    candidates = volunteers[
        volunteers["Grupo"].apply(lambda group: turno in TURNOS_POR_GRUPO.get(group, []))
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
) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    rule = slot["regla_especial"]
    turno = int(slot["turno"])

    if rule == "spk_base":
        required_group = "A" if turno in {1, 2} else "B"
        candidates = candidates[(candidates["Grupo"] == required_group) & (candidates["Género"] == "M")]

        continuity_key = _continuity_key(slot)
        if continuity_key in continuity_assignments:
            return candidates[candidates["_id"] == continuity_assignments[continuity_key]]

    if rule == "spk_refuerzo":
        candidates = candidates[(candidates["Grupo"] == "B") & (candidates["Género"] == "M")]

        continuity_key = _continuity_key(slot)
        if continuity_key in continuity_assignments:
            return candidates[candidates["_id"] == continuity_assignments[continuity_key]]

    if rule == "pmu_luz_helena_pendiente":
        return candidates[candidates.apply(lambda row: _full_name(row) == PMU_FIXED_NAME.lower(), axis=1)]

    return candidates


def _continuity_key(slot: pd.Series) -> tuple[str, int]:
    rule = str(slot["regla_especial"])
    turno = int(slot["turno"])
    slot_number = int(slot["slot_numero"])

    if rule == "spk_base":
        block = "A" if turno in {1, 2} else "B"
        return (f"{rule}_{block}", slot_number)

    return (rule, slot_number)


def _store_continuity_assignment(
    volunteer: pd.Series,
    slot: pd.Series,
    continuity_assignments: dict[tuple[str, int], int],
) -> None:
    if slot["regla_especial"] not in {"spk_base", "spk_refuerzo"}:
        return

    continuity_assignments.setdefault(_continuity_key(slot), int(volunteer["_id"]))


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

    if slot["zona"] in zones_by_person[person_id]:
        repeated_zone = True
    zones_by_person[person_id].append(slot["zona"])

    if repeated_zone:
        alerts.append(
            "ADVERTENCIA: "
            f"{volunteer['Nombre']} {volunteer['Apellido']} repitió {slot['zona']} "
            "por falta de alternativas"
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


def validate_schedule(schedule_df: pd.DataFrame) -> list[str]:
    """Valida una programacion generada o editada manualmente."""
    alerts: list[str] = []
    assigned = schedule_df[~schedule_df["Nombre"].isin([UNASSIGNED_NAME, FREE_NAME])].copy()

    unassigned = schedule_df[
        (schedule_df["Nombre"] == UNASSIGNED_NAME)
        & (schedule_df.get("Obligatorio", True).astype(bool))
    ]
    for _, row in unassigned.iterrows():
        alerts.append(
            "SIN ASIGNAR: "
            f"Turno {row['Turno']} {row['Horario']} / {row['Zona']} / "
            f"{row['Posición']} requiere género {_required_gender_for_row(row)}"
        )

    if assigned.empty:
        return alerts

    assigned["persona"] = (
        assigned["Nombre"].astype(str).str.strip()
        + " "
        + assigned["Apellido"].astype(str).str.strip()
    ).str.strip()

    duplicated = assigned[assigned.duplicated(["Turno", "persona"], keep=False)]
    for _, row in duplicated.drop_duplicates(["Turno", "persona"]).iterrows():
        alerts.append(
            f"ERROR: {row['persona']} fue asignado más de una vez en el turno {row['Turno']}"
        )

    gender_checks = assigned[
        (assigned["Género"] != "")
        & (assigned["Posición"] != "")
        & (assigned.apply(_gender_mismatch, axis=1))
    ]
    for _, row in gender_checks.iterrows():
        alerts.append(
            f"ERROR: {row['Posición']} turno {row['Turno']} requiere "
            f"{_required_gender_for_row(row)} pero se asignó {row['Género']}"
        )

    for _, row in assigned.iterrows():
        required_zone = ESTADOS_ZONA_FIJA.get(row["Estado"])
        if required_zone and row["Zona"] != required_zone:
            alerts.append(
                f"ERROR: {row['Nombre']} {row['Apellido']} tiene estado {row['Estado']} "
                f"pero fue asignado a {row['Zona']}"
            )

    alerts.extend(_special_rule_validations(assigned))

    return alerts


def _special_rule_validations(assigned: pd.DataFrame) -> list[str]:
    alerts: list[str] = []

    pmu = assigned[assigned["Posición"] == "PMU - Radios chaquetas"]
    for _, row in pmu.iterrows():
        if _full_name(row) != PMU_FIXED_NAME.lower():
            alerts.append(
                "ERROR: PMU - Radios chaquetas debe asignarse a "
                f"{PMU_FIXED_NAME} en el turno {row['Turno']}"
            )

    spk = assigned[assigned["Posición"] == "Auditorio SPK"]
    for _, row in spk.iterrows():
        required_group = "A" if int(row["Turno"]) in {1, 2} else "B"
        if row["Grupo"] != required_group:
            alerts.append(
                f"ERROR: Auditorio SPK turno {row['Turno']} requiere grupo "
                f"{required_group} pero se asignó grupo {row['Grupo']}"
            )

    spk_ref = assigned[assigned["Posición"] == "Auditorio SPK (refuerzo)"]
    for _, row in spk_ref.iterrows():
        if row["Grupo"] != "B":
            alerts.append(
                f"ERROR: Auditorio SPK (refuerzo) turno {row['Turno']} requiere "
                f"grupo B pero se asignó grupo {row['Grupo']}"
            )

    alerts.extend(_validate_same_person_pair(spk, "Auditorio SPK", 1, 2))
    alerts.extend(_validate_same_person_pair(spk, "Auditorio SPK", 3, 4))
    alerts.extend(_validate_same_person_pair(spk_ref, "Auditorio SPK (refuerzo)", 2, 3))

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
                f"ERROR: {position} slot {slot} debe mantener la misma persona "
                f"en turnos {first_turn} y {second_turn}"
            )

    return alerts


def apply_manual_assignment(
    schedule_df: pd.DataFrame,
    row_index: int,
    volunteer: Optional[pd.Series],
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

    return updated_df, validate_schedule(updated_df)


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


def _gender_mismatch(row: pd.Series) -> bool:
    required_gender = _required_gender_for_row(row)
    return required_gender != "cualquiera" and row["Género"] != required_gender


def _full_name(row: pd.Series) -> str:
    return f"{row['Nombre']} {row['Apellido']}".strip().lower()

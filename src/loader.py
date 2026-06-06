"""Carga, limpieza y validacion del Excel de voluntarios."""

from __future__ import annotations

import pandas as pd

from src.rules import ESTADOS_DISPONIBLES, ESTADOS_VALIDOS, ESTADOS_ZONA_FIJA, TURNOS_POR_GRUPO


REQUIRED_COLUMNS = [
    "Grupo",
    "Nombre",
    "Apellido",
    "Genero",
    "Estado",
    "Telefono",
    "Observaciones",
]

COLUMN_ALIASES = {
    "Género": "Genero",
    "Teléfono": "Telefono",
}

DISPLAY_COLUMNS = [
    "Grupo",
    "Nombre",
    "Apellido",
    "Género",
    "Estado",
    "Teléfono",
    "Observaciones",
]


def read_volunteers(file) -> pd.DataFrame:
    """Lee voluntarios desde Excel.

    Si el archivo tiene una sola hoja, usa esa hoja. Si tiene varias,
    busca una hoja llamada Voluntarios sin importar mayusculas/minusculas.
    """
    excel_file = pd.ExcelFile(file)
    sheet_names = excel_file.sheet_names

    if len(sheet_names) == 1:
        selected_sheet = sheet_names[0]
    else:
        selected_sheet = next(
            (sheet_name for sheet_name in sheet_names if sheet_name.strip().lower() == "voluntarios"),
            None,
        )
        if selected_sheet is None:
            available_sheets = ", ".join(sheet_names)
            raise ValueError(
                "El archivo tiene varias hojas y no se encontro una hoja llamada "
                f"'Voluntarios'. Hojas encontradas: {available_sheets}."
            )

    df = pd.read_excel(excel_file, sheet_name=selected_sheet, dtype=str)
    df.attrs["sheet_name"] = selected_sheet
    return df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.rename(columns=COLUMN_ALIASES).copy()
    return normalized


def _display_columns(df: pd.DataFrame) -> pd.DataFrame:
    display_df = df.rename(columns={"Genero": "Género", "Telefono": "Teléfono"}).copy()
    return display_df


def clean_volunteers(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia espacios, mayusculas/minusculas y valores vacios."""
    clean_df = _normalize_columns(df).copy()

    for column in REQUIRED_COLUMNS:
        if column not in clean_df.columns:
            clean_df[column] = ""

    clean_df = clean_df[REQUIRED_COLUMNS].fillna("")

    for column in REQUIRED_COLUMNS:
        clean_df[column] = clean_df[column].astype(str).str.strip()

    clean_df["Grupo"] = clean_df["Grupo"].str.upper()
    clean_df["Genero"] = clean_df["Genero"].str.upper()
    clean_df["Estado"] = clean_df["Estado"].apply(_normalize_estado)

    return _display_columns(clean_df)


def validate_volunteers(df: pd.DataFrame) -> list[str]:
    """Valida estructura y datos de voluntarios. Devuelve errores claros."""
    errors: list[str] = []
    normalized = _normalize_columns(df)

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in normalized.columns]
    if missing_columns:
        for column in missing_columns:
            display_column = "Género" if column == "Genero" else "Teléfono" if column == "Telefono" else column
            errors.append(f"Falta la columna requerida: {display_column}")
        return errors

    clean_df = clean_volunteers(df)
    normalized_clean = _normalize_columns(clean_df)

    for index, row in normalized_clean.iterrows():
        row_number = index + 2

        grupos_validos = sorted(TURNOS_POR_GRUPO)
        if row["Grupo"] not in grupos_validos:
            errors.append(f"Fila {row_number}: Grupo debe ser uno de: {', '.join(grupos_validos)}.")

        if row["Genero"] not in {"H", "M"}:
            errors.append(f"Fila {row_number}: Género debe ser H o M.")

        if row["Estado"] not in ESTADOS_VALIDOS:
            errors.append(
                f"Fila {row_number}: Estado '{row['Estado']}' no es válido. "
                f"Valores válidos: {', '.join(ESTADOS_VALIDOS)}."
            )

        if not row["Nombre"]:
            errors.append(f"Fila {row_number}: Nombre no puede estar vacío.")

    return errors


def get_available_volunteers(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra personas disponibles para asignar a posiciones."""
    clean_df = clean_volunteers(df)
    assignable = clean_df[
        clean_df["Estado"].isin(ESTADOS_DISPONIBLES)
        & (~clean_df["Estado"].isin(ESTADOS_ZONA_FIJA))
    ]
    return assignable.reset_index(drop=True)


def get_supervisor_volunteers(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra personas marcadas como supervisoras de zona en el Excel."""
    clean_df = clean_volunteers(df)
    return clean_df[clean_df["Estado"].isin(ESTADOS_ZONA_FIJA)].reset_index(drop=True)


def get_unavailable_volunteers(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra personas con estados no disponibles."""
    clean_df = clean_volunteers(df)
    unavailable = clean_df[
        (~clean_df["Estado"].isin(ESTADOS_DISPONIBLES))
        & (~clean_df["Estado"].isin(ESTADOS_ZONA_FIJA))
    ]
    return unavailable.reset_index(drop=True)


def get_summary(df: pd.DataFrame, available_df: pd.DataFrame) -> dict:
    """Calcula resumen operativo para la UI."""
    clean_df = clean_volunteers(df)
    supervisor_df = get_supervisor_volunteers(clean_df)
    unavailable_df = get_unavailable_volunteers(clean_df)

    return {
        "total_cargados": len(clean_df),
        "total_disponibles": len(available_df),
        "total_supervisores": len(supervisor_df),
        "total_no_disponibles": len(unavailable_df),
        "hombres_disponibles": int((available_df["Género"] == "H").sum()),
        "mujeres_disponibles": int((available_df["Género"] == "M").sum()),
        "grupo_a_disponibles": int((available_df["Grupo"] == "A").sum()),
        "grupo_b_disponibles": int((available_df["Grupo"] == "B").sum()),
        "grupos_disponibles": {
            grupo: int((available_df["Grupo"] == grupo).sum())
            for grupo in sorted(TURNOS_POR_GRUPO)
        },
    }


def _normalize_estado(value: str) -> str:
    value = str(value).strip()
    upper_value = value.upper()

    if upper_value in ESTADOS_ZONA_FIJA:
        return upper_value

    return value.lower()

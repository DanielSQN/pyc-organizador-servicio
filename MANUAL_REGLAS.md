# Manual de reglas de negocio

Este proyecto genera la programación de voluntarios usando reglas determinísticas. No usa IA para decidir asignaciones.

La lógica se divide en dos archivos principales:

- `src/rules.py`: define qué necesita el servicio.
- `src/scheduler.py`: define cómo se asignan las personas a esas necesidades.

## 1. Concepto general

El sistema funciona en tres pasos:

1. Carga voluntarios desde Excel.
2. Expande las posiciones del servicio en cupos requeridos.
3. Asigna voluntarios disponibles según reglas de negocio.

Una posición puede convertirse en varios cupos. Por ejemplo, si una posición requiere 3 personas en 4 turnos, el sistema genera 12 cupos.

## 2. Archivo `src/rules.py`

Este archivo contiene las reglas base del servicio.

Aquí se configuran:

- Turnos.
- Grupos disponibles por turno.
- Estados válidos.
- Estados de zona fija.
- Supervisores por zona.
- Catálogo de posiciones.

### Turnos

```python
TURNOS = {
    1: "0730-0930",
    2: "0930-1130",
    3: "1130-1330",
    4: "1330-1500",
}
```

### Grupos por turno

```python
TURNOS_POR_GRUPO = {
    "A": [1, 2, 3],
    "B": [2, 3, 4],
}
```

Esto significa:

- Grupo A puede trabajar turnos 1, 2 y 3.
- Grupo B puede trabajar turnos 2, 3 y 4.

### Estados de disponibilidad

```python
ESTADOS_DISPONIBLES = ["confirmado", "Z1", "Z2", "Z3", "apoyo"]
ESTADOS_NO_DISPONIBLES = ["sin confirmar", "declinado"]
```

### Estados de zona fija

```python
ESTADOS_ZONA_FIJA = {
    "Z1": "Z1",
    "Z2": "Z2",
    "Z3": "Z3",
}
```

Si una persona tiene estado `Z1`, solo puede ser asignada a Zona 1. Igual con `Z2` y `Z3`.

## 3. Agregar posiciones

Las posiciones se agregan en la lista `POSICIONES`.

Hay dos helpers:

```python
_crit(...)
```

Para posiciones críticas.

```python
_ref(...)
```

Para posiciones de refuerzo.

### Ejemplo: agregar posición crítica

```python
_crit("Z1", "Nueva posición crítica", "H")
```

Esto crea una posición:

- Zona: Z1.
- Nombre: Nueva posición crítica.
- Tipo: crítica.
- Género requerido: H.
- Cantidad: 1.
- Turnos obligatorios: 1, 2, 3 y 4.

### Ejemplo: agregar posición crítica sin género requerido

```python
_crit("Z3", "Punto de apoyo exterior")
```

Cuando no se especifica género, el sistema usa `cualquiera`.

### Ejemplo: agregar refuerzo

```python
_ref("Z2", "Nuevo refuerzo SPK")
```

Los refuerzos se muestran en todos los turnos, pero por defecto solo son obligatorios en T2 y T3.

En T1 y T4 pueden quedar como:

```text
-- (Libre)
```

### Ejemplo: posición con varias personas

```python
_crit("Z2", "Auditorio SPK", "M", cantidad=3)
```

Esto genera tres cupos por turno para esa posición.

## 4. Agregar reglas especiales

Cuando una posición necesita una lógica particular, se marca con `regla_especial`.

Ejemplo:

```python
_crit("Z3", "PMU - Radios chaquetas", regla_especial="pmu_luz_helena_pendiente")
```

Luego esa regla debe implementarse en `src/scheduler.py`.

## 5. Archivo `src/scheduler.py`

Este archivo contiene el motor de asignación.

Su función principal es:

```python
generate_schedule(volunteers_df)
```

Recibe voluntarios disponibles y devuelve:

```python
(schedule_df, alerts)
```

Donde:

- `schedule_df`: programación final.
- `alerts`: lista de alertas, advertencias y errores.

## 6. Reglas generales que ya aplica el scheduler

El scheduler actualmente:

- Asigna posiciones críticas antes que refuerzos.
- Respeta grupo disponible por turno.
- Respeta género requerido.
- Respeta estados de zona fija `Z1`, `Z2`, `Z3`.
- Evita asignar la misma persona dos veces en el mismo turno.
- Evita repetir zona para una persona cuando hay alternativa.
- Usa voluntarios con estado `apoyo` como respaldo.
- Deja `SIN ASIGNAR` cuando falta personal obligatorio.
- Deja `-- (Libre)` en refuerzos opcionales sin asignar.
- Genera alertas para posiciones sin cubrir.
- Valida errores finales de duplicados, género y zona fija.

## 7. Reglas especiales actuales

### PMU - Radios chaquetas

Regla:

```python
pmu_luz_helena_pendiente
```

Intenta asignar la posición `PMU - Radios chaquetas` a:

```text
Luz Helena Roncancio Garcia
```

### Auditorio SPK

Regla:

```python
spk_base
```

Aplica a:

```text
Auditorio SPK
```

Reglas actuales:

- Requiere género M.
- Requiere 3 personas.
- En T1 y T2 usa grupo A.
- En T3 y T4 usa grupo B.
- Mantiene continuidad por slot entre T1-T2 y T3-T4.

### Auditorio SPK refuerzo

Regla:

```python
spk_refuerzo
```

Reglas actuales:

- Requiere género M.
- Requiere grupo B.
- Mantiene continuidad entre T2 y T3.

## 8. Cómo agregar una nueva regla especial

### Paso 1: marcar la posición en `rules.py`

Ejemplo:

```python
_crit("Z1", "Nueva posición especial", regla_especial="nueva_regla")
```

### Paso 2: aplicar filtro en `scheduler.py`

En la función `_apply_special_filters`, agregar la lógica:

```python
if rule == "nueva_regla":
    candidates = candidates[candidates["Grupo"] == "A"]
```

### Paso 3: validar al final

Si la regla no debería violarse nunca, agregar una validación en:

```python
_special_rule_validations(...)
```

Ejemplo:

```python
especial = assigned[assigned["Posición"] == "Nueva posición especial"]
for _, row in especial.iterrows():
    if row["Grupo"] != "A":
        alerts.append(
            f"ERROR: Nueva posición especial requiere grupo A en turno {row['Turno']}"
        )
```

## 9. Buenas prácticas para nuevas reglas

- Primero agregar la posición en `rules.py`.
- Usar `regla_especial` solo si la regla no se puede expresar con zona, género, cantidad o tipo.
- Mantener nombres de reglas en minúscula y con guion bajo.
- Agregar validaciones finales para reglas críticas.
- Evitar reglas ambiguas.
- Probar con un Excel pequeño antes de usar datos reales.

## 10. Escalabilidad de turnos, grupos y zonas

La aplicación está preparada para crecer desde `src/rules.py`.

### Agregar un nuevo turno

Agregar el turno en `TURNOS`:

```python
TURNOS = {
    1: "0730-0930",
    2: "0930-1130",
    3: "1130-1330",
    4: "1330-1500",
    5: "1500-1700",
}
```

La vista de programación y el Excel de salida crearán la columna `T5` automáticamente.

Si un refuerzo debe ser obligatorio en ese nuevo turno, agregarlo en:

```python
TURNOS_REFUERZO_OBLIGATORIOS = [2, 3, 5]
```

### Agregar un nuevo grupo

Agregar el grupo en `TURNOS_POR_GRUPO`:

```python
TURNOS_POR_GRUPO = {
    "A": [1, 2, 3],
    "B": [2, 3, 4],
    "C": [4, 5],
}
```

La validación del Excel aceptará automáticamente el grupo `C`.

### Agregar una nueva zona

Agregar supervisor/asistente:

```python
SUPERVISORES_ZONA = {
    "Z1": {"supervisor": "KAREN GUERRERO", "asistente": ""},
    "Z2": {"supervisor": "DANIELA SOTO", "asistente": "WILLIAM BENJUMEA"},
    "Z3": {"supervisor": "EDNA SERRATO", "asistente": "RICARDO LOZANO"},
    "Z4": {"supervisor": "NOMBRE SUPERVISOR", "asistente": "NOMBRE ASISTENTE"},
}
```

Opcionalmente agregar título para reportes:

```python
TITULOS_ZONA = {
    "Z4": "ZONA 4 (Z4) NUEVA ZONA",
}
```

Luego agregar posiciones:

```python
_crit("Z4", "Ingreso zona nueva")
_ref("Z4", "Refuerzo zona nueva")
```

El estado `Z4` se vuelve válido automáticamente si la zona aparece en supervisores o posiciones.

## 11. Ejemplo completo

Queremos agregar una posición en Z3 que solo pueda cubrir grupo B.

En `rules.py`:

```python
_crit("Z3", "Control especial exterior", regla_especial="solo_grupo_b")
```

En `scheduler.py`, dentro de `_apply_special_filters`:

```python
if rule == "solo_grupo_b":
    return candidates[candidates["Grupo"] == "B"]
```

En `_special_rule_validations`:

```python
control = assigned[assigned["Posición"] == "Control especial exterior"]
for _, row in control.iterrows():
    if row["Grupo"] != "B":
        alerts.append(
            f"ERROR: Control especial exterior requiere grupo B en turno {row['Turno']}"
        )
```

## 12. Qué no debe hacerse

- No usar IA para calcular asignaciones.
- No asignar personas manualmente dentro de `rules.py`.
- No mezclar carga de Excel con reglas de asignación.
- No cambiar el scheduler sin agregar validaciones cuando la regla sea crítica.
- No eliminar alertas: las alertas ayudan al coordinador a revisar faltantes o errores.

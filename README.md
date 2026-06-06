# PYC Organizador de Servicio

MVP en Python y Streamlit para organizar voluntarios PYC mediante reglas deterministicas. La asignacion no usa IA: se calcula con reglas de negocio declaradas en el codigo.

## Ejecucion desde cero

Usa estos pasos si es la primera vez que vas a correr el proyecto en este computador.

```bash
cd pyc-organizador-servicio
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

La aplicación quedará disponible normalmente en:

```text
http://localhost:8501
```

Para detenerla, presiona `Ctrl + C` en la terminal.

Para salir del entorno virtual:

```bash
deactivate
```

## Ejecucion cuando el entorno ya existe

Usa estos pasos si la carpeta `.venv` ya existe y las dependencias ya fueron instaladas.

```bash
cd pyc-organizador-servicio
source .venv/bin/activate
streamlit run app.py
```

## Reinstalar dependencias

Si se agregan nuevas dependencias al proyecto o algo falla por paquetes faltantes:

```bash
cd pyc-organizador-servicio
source .venv/bin/activate
pip install -r requirements.txt
```

## Instalacion en otro servidor

Esta seccion sirve para instalar y ejecutar la aplicacion en un servidor Linux.

### Requisitos del servidor

- Python 3.9 o superior.
- Acceso por terminal/SSH.
- Puerto disponible para Streamlit, por defecto `8501`.
- Permisos para instalar paquetes del sistema o crear entornos virtuales.

En Ubuntu/Debian, si hace falta instalar Python y herramientas basicas:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### Copiar o clonar el proyecto

Ubica el proyecto en una carpeta del servidor. Por ejemplo:

```bash
mkdir -p ~/apps
cd ~/apps
```

Si usas Git:

```bash
git clone URL_DEL_REPOSITORIO pyc-organizador-servicio
cd pyc-organizador-servicio
```

Si lo copias manualmente, asegúrate de quedar dentro de la carpeta:

```bash
cd ~/apps/pyc-organizador-servicio
```

### Crear entorno virtual e instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Ejecutar en el servidor

Para que Streamlit escuche conexiones externas:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Luego abre en el navegador:

```text
http://IP_DEL_SERVIDOR:8501
```

Si el servidor tiene firewall, abre el puerto:

```bash
sudo ufw allow 8501/tcp
```

Para detener la aplicacion:

```bash
Ctrl + C
```

### Ejecutar como servicio con systemd

Si quieres que la aplicacion quede corriendo en segundo plano y reinicie si el servidor se reinicia, puedes crear un servicio.

Crea el archivo:

```bash
sudo nano /etc/systemd/system/pyc-organizador-servicio.service
```

Contenido de ejemplo:

```ini
[Unit]
Description=PYC Organizador de Servicio
After=network.target

[Service]
User=USUARIO_DEL_SERVIDOR
WorkingDirectory=/home/USUARIO_DEL_SERVIDOR/apps/pyc-organizador-servicio
ExecStart=/home/USUARIO_DEL_SERVIDOR/apps/pyc-organizador-servicio/.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Reemplaza `USUARIO_DEL_SERVIDOR` por el usuario real.

Activar el servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pyc-organizador-servicio
sudo systemctl start pyc-organizador-servicio
```

Ver estado:

```bash
sudo systemctl status pyc-organizador-servicio
```

Ver logs:

```bash
journalctl -u pyc-organizador-servicio -f
```

Reiniciar despues de cambios:

```bash
sudo systemctl restart pyc-organizador-servicio
```

### Actualizar la aplicacion en servidor

Si el proyecto se maneja con Git:

```bash
cd ~/apps/pyc-organizador-servicio
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart pyc-organizador-servicio
```

Si la ejecutas manualmente sin `systemd`, detén con `Ctrl + C` y vuelve a correr:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## Formato esperado del Excel

El archivo de entrada puede tener una sola hoja con cualquier nombre. Si el archivo tiene varias hojas,
el sistema buscará una hoja llamada `Voluntarios` sin importar mayúsculas/minúsculas.

La hoja leída debe tener estas columnas:

- `Grupo`
- `Nombre`
- `Apellido`
- `Género`
- `Estado`
- `Teléfono`
- `Observaciones`

Valores validos:

- `Grupo`: `A`, `B`
- `Género`: `H`, `M`
- `Estado`: `confirmado`, `sin confirmar`, `declinado`, `Z1`, `Z2`, `Z3`, `apoyo`

## Reglas implementadas

- Estados disponibles: `confirmado`, `Z1`, `Z2`, `Z3`, `apoyo`.
- Estados no disponibles: `sin confirmar`, `declinado`.
- Grupo A trabaja en turnos 1, 2 y 3.
- Grupo B trabaja en turnos 2, 3 y 4.
- Turnos:
  - Turno 1: `0730-0930`
  - Turno 2: `0930-1130`
  - Turno 3: `1130-1330`
  - Turno 4: `1330-1500`
- Se asignan primero posiciones criticas y luego refuerzos.
- El catalogo operativo incluye 44 posiciones reales de `Z1`, `Z2` y `Z3`.
- Las posiciones de `APOYO EVACUACIÓN` en `Z2` se tratan como refuerzos para los turnos 2 y 3.
- Las posiciones criticas se cubren en los cuatro turnos.
- Las posiciones de refuerzo son obligatorias en los turnos 2 y 3.
- En los turnos 1 y 4, los refuerzos aparecen como opcionales y pueden quedar como `-- (Libre)` sin generar alerta.
- `Auditorio SPK` asigna tres mujeres: grupo A en turnos 1 y 2, grupo B en turnos 3 y 4, manteniendo continuidad por slot cuando es posible.
- `Auditorio SPK (refuerzo)` asigna una mujer del grupo B en turnos 2 y 3.
- `PMU - Radios chaquetas` se reserva para `Luz Helena Roncancio Garcia`.
- Se respeta grupo disponible por turno.
- Se respeta genero requerido cuando la posicion lo define.
- `Z1`, `Z2` y `Z3` solo se asignan a su zona correspondiente.
- `confirmado` puede asignarse a cualquier zona.
- `apoyo` se usa como respaldo para cubrir vacios.
- No se asigna la misma persona dos veces en el mismo turno.
- Se evita repetir zona para una persona cuando existe alternativa.
- Si no hay persona compatible, la posicion queda como `SIN ASIGNAR` y se genera alerta.
- El coordinador puede reasignar manualmente una fila de programacion y el sistema recalcula las alertas.

## Salida

El Excel final contiene:

- `Programacion`
- `Alertas`
- `Voluntarios Disponibles`

## Pendiente para proximas versiones

- Rotacion avanzada.
- Refuerzos opcionales en turnos 1 y 4 cuando sobre personal.
- Generos pendientes por confirmar en posiciones ambiguas.
- Priorizacion operativa mas detallada por experiencia, observaciones o restricciones adicionales.

import requests
import pandas as pd
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from gestor_tickets.cliente_glpi import login as glpi_login, crear_ticket, ticket_existe, cerrar_tickets_resueltos, logout

ZABBIX_URL = "http://localhost:8080/api_jsonrpc.php"
ZABBIX_USER = "Admin"
ZABBIX_PASSWORD = "zabbix"

ACCIONES = {
    "swap": "find /tmp -type f -delete && echo 'Limpieza de temporales completada'",
    "cpu":  "top -bn1 | awk 'NR==8{print \"Proceso con mas CPU: \"$12\" (\"$9\"%)\"} END{exit 1}'",
    "memo": "echo 3 > /proc/sys/vm/drop_caches && echo 'Cache de memoria liberada'"
}

CONTENEDORES = {
    "servidor-simulado": "healops-servidor-simulado"
}

Path("logs").mkdir(exist_ok=True)

MAX_LOG_BYTES = 1 * 1024 * 1024  # 1 MB por archivo de log

def escribir_log(archivo, mensaje):
    ruta = Path(f"logs/{archivo}")
    if ruta.exists() and ruta.stat().st_size >= MAX_LOG_BYTES:
        ruta.rename(f"logs/{archivo}.old")  # rota el log cuando supera 1 MB
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {mensaje}\n")

# Metodo para obtener el token de autenticación de Zabbix
def login():
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {"username": ZABBIX_USER, "password": ZABBIX_PASSWORD},
        "id": 1
    }
    response = requests.post(ZABBIX_URL, json=payload)
    return response.json()["result"]

# Metodo para obtener las alertas de Zabbix sacando el host
def obtener_alertas(token):
    payload = {
        "jsonrpc": "2.0",
        "method": "trigger.get",
        "params": {
            "output": ["triggerid", "description", "priority"],
            "selectHosts": ["host"],  # host incluido directamente
            "only_true": True,        # solo triggers que están en estado PROBLEM
            "filter": {"value": 1}    # value=1 significa activo/disparado
        },
        "id": 2
    }
    response = requests.post(ZABBIX_URL, json=payload, headers={"Authorization": f"Bearer {token}"})
    return response.json()

SEVERIDAD = {"0": "Info", "1": "Info", "2": "Warn", "3": "Avg", "4": "HIGH", "5": "CRIT"}

def separador():
    print("  " + "─" * 60)

# Metodo para analizar las alertas y separar las reales de los falsos positivos
def analizar_alertas(alertas):
    df = pd.DataFrame(alertas["result"])
    df["host"] = df["hosts"].apply(lambda x: x[0]["host"] if x else "desconocido")
    df = df.rename(columns={"description": "nombre", "priority": "severity"})

    alertas_reales = df[df["severity"].astype(int) >= 4]
    falsos_positivos = df[df["severity"].astype(int) < 4]

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n  HealOps Engine · {ahora}")
    separador()
    print(f"  Alertas recibidas: {len(df)}   Reales: {len(alertas_reales)}   Descartadas: {len(falsos_positivos)}")
    separador()

    if not alertas_reales.empty:
        print("  ALERTAS REALES:")
        for _, row in alertas_reales.iterrows():
            print(f"    · {row['host']:<25} {row['nombre']}")
        separador()

    if not falsos_positivos.empty:
        print("  DESCARTADAS (falsos positivos):")
        for _, row in falsos_positivos.iterrows():
            print(f"    · {row['host']:<25} {row['nombre']}")
            escribir_log("falsos_positivos.log", f"{row['host']} | {row['nombre']}")
        separador()

    for _, row in df.iterrows():
        escribir_log("alertas_recibidas.log", f"{row['host']} | {row['nombre']} | severity={row['severity']}")

    return alertas_reales

# Metodo para ejecutar la corrección de la alerta en el host correspondiente
def ejecutar_correccion(host, nombre_alerta):
    comando = next((v for k, v in ACCIONES.items() if k in nombre_alerta.lower()), None)
    contenedor = CONTENEDORES.get(host, host)

    print(f"\n  ALERTA  {host} → {nombre_alerta}")

    if not comando:
        print(f"  Acción  Sin corrección definida — escalando a GLPI")
        escribir_log("corrector.log", f"SIN_ACCION | {host} | {nombre_alerta}")
        return False

    resultado = subprocess.run(
        ["docker", "exec", contenedor, "sh", "-c", comando],
        capture_output=True, text=True
    )

    if resultado.returncode == 0:
        print(f"  Acción  {resultado.stdout.strip().splitlines()[-1]}")
        print(f"  Estado  OK")
        escribir_log("corrector.log", f"OK | {host} | {nombre_alerta}")
    else:
        print(f"  Acción  Corrección fallida")
        print(f"  Estado  FALLO → abriendo ticket en GLPI")
        escribir_log("corrector.log", f"ERROR | {host} | {nombre_alerta} | {resultado.stderr.strip()}")
        session = glpi_login()
        if not ticket_existe(session, host, nombre_alerta):
            ticket_id = crear_ticket(session, host, nombre_alerta)
            print(f"  Ticket  #{ticket_id} creado en GLPI")
        else:
            print(f"  Ticket  Ya existe uno abierto — no se duplica")
        logout(session)

    return resultado.returncode == 0

token = login()
alertas = obtener_alertas(token)
alertas_reales = analizar_alertas(alertas)

print("  ACCIONES:")
for _, alerta in alertas_reales.iterrows():
    ejecutar_correccion(alerta["host"], alerta["nombre"])

# Cierra en GLPI los tickets cuya alerta ya no está activa en Zabbix
nombres_activos = alertas_reales["nombre"].tolist()
session_glpi = glpi_login()
cerrar_tickets_resueltos(session_glpi, nombres_activos)
logout(session_glpi)

separador()
print()

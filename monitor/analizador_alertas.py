import requests
import pandas as pd
import subprocess
from datetime import datetime
from pathlib import Path

ZABBIX_URL = "http://localhost:8080/api_jsonrpc.php"
ZABBIX_USER = "Admin"
ZABBIX_PASSWORD = "zabbix"

ACCIONES = {
    "swap": "find /tmp -type f -delete && echo 'Limpieza de temporales completada'"
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

# Metodo para analizar las alertas y separar las reales de los falsos positivos
def analizar_alertas(alertas):
    df = pd.DataFrame(alertas["result"])
    df["host"] = df["hosts"].apply(lambda x: x[0]["host"] if x else "desconocido")
    df = df.rename(columns={"description": "nombre", "priority": "severity"})

    alertas_reales = df[df["severity"].astype(int) >= 4]
    falsos_positivos = df[df["severity"].astype(int) < 4]

    print(f"\n[HealOps] {len(df)} alerta(s) recibida(s) — {len(alertas_reales)} real(es), {len(falsos_positivos)} falso(s) positivo(s)\n")

    for _, row in df.iterrows():
        escribir_log("alertas_recibidas.log", f"{row['host']} | {row['nombre']} | severity={row['severity']}")

    for _, row in alertas_reales.iterrows():
        print(f"  [REAL]  [{row['host']}] {row['nombre']}")

    for _, row in falsos_positivos.iterrows():
        print(f"  [SKIP]  [{row['host']}] {row['nombre']}")
        escribir_log("falsos_positivos.log", f"{row['host']} | {row['nombre']}")

    return alertas_reales

# Metodo para ejecutar la corrección de la alerta en el host correspondiente
def ejecutar_correccion(host, nombre_alerta):
    comando = next((v for k, v in ACCIONES.items() if k in nombre_alerta.lower()), None)

    if not comando:
        print(f"  [SKIP]  Sin corrección definida para: {nombre_alerta}")
        return False

    contenedor = CONTENEDORES.get(host, host)
    print(f"  [EXEC]  Ejecutando corrección en {contenedor}...")
    resultado = subprocess.run(
        ["docker", "exec", contenedor, "sh", "-c", comando],
        capture_output=True, text=True
    )

    if resultado.returncode == 0:
        print(f"  [OK]    Corrección aplicada en {host}")
        escribir_log("corrector.log", f"OK | {host} | {nombre_alerta}")
    else:
        print(f"  [ERROR] Falló en {host}: {resultado.stderr.strip()}")
        escribir_log("corrector.log", f"ERROR | {host} | {nombre_alerta} | {resultado.stderr.strip()}")
        escribir_log("tickets.log", f"PENDIENTE | {host} | {nombre_alerta}")

    return resultado.returncode == 0

token = login()
alertas = obtener_alertas(token)
alertas_reales = analizar_alertas(alertas)

for _, alerta in alertas_reales.iterrows():
    ejecutar_correccion(alerta["host"], alerta["nombre"])

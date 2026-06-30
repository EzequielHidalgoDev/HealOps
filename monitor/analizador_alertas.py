import requests
import pandas as pd

ZABBIX_URL = "http://localhost:8080/api_jsonrpc.php"
ZABBIX_USER = "Admin"
ZABBIX_PASSWORD = "zabbix"

def login():
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {"username": ZABBIX_USER, "password": ZABBIX_PASSWORD},
        "id": 1
    }
    response = requests.post(ZABBIX_URL, json=payload)
    return response.json()["result"]

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

def analizar_alertas(alertas):
    df = pd.DataFrame(alertas["result"])
    df["host"] = df["hosts"].apply(lambda x: x[0]["host"] if x else "desconocido")
    df = df.rename(columns={"description": "nombre", "priority": "severity"})

    alertas_reales = df[df["severity"].astype(int) >= 4]
    falsos_positivos = df[df["severity"].astype(int) < 4]

    print(f"\n[HealOps] {len(df)} alerta(s) recibida(s) — {len(alertas_reales)} real(es), {len(falsos_positivos)} falso(s) positivo(s)\n")

    for _, row in alertas_reales.iterrows():
        print(f"  [REAL]  [{row['host']}] {row['nombre']}")

    for _, row in falsos_positivos.iterrows():
        print(f"  [SKIP]  [{row['host']}] {row['nombre']}")

    return alertas_reales

token = login()
alertas = obtener_alertas(token)
alertas_reales = analizar_alertas(alertas)

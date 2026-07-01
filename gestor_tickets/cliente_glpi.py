import requests
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

Path("logs").mkdir(exist_ok=True)

def escribir_log(mensaje):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("logs/tickets.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {mensaje}\n")

GLPI_URL   = os.getenv("GLPI_URL",        "http://localhost:8081/apirest.php")
APP_TOKEN  = os.getenv("GLPI_APP_TOKEN",  "")
USER_TOKEN = os.getenv("GLPI_USER_TOKEN", "")

# Inicia sesión en GLPI y devuelve el token de sesión
def login():
    response = requests.get(
        f"{GLPI_URL}/initSession",
        headers={
            "App-Token": APP_TOKEN,
            "Authorization": f"user_token {USER_TOKEN}"
        }
    )
    return response.json().get("session_token")

# Comprueba si ya existe un ticket ABIERTO para el mismo host y alerta (ignora resueltos/cerrados)
def ticket_existe(session, host, alerta):
    response = requests.get(
        f"{GLPI_URL}/Ticket",
        headers={"App-Token": APP_TOKEN, "Session-Token": session},
        params={"searchText[name]": f"[HealOps] Fallo en {host}: {alerta}", "is_deleted": 0}
    )
    resultados = response.json()
    if not isinstance(resultados, list):
        return False
    return any(int(t.get("status", 1)) not in (5, 6) for t in resultados)

# Abre un ticket en GLPI con el host y la alerta que falló
def crear_ticket(session, host, alerta):
    response = requests.post(
        f"{GLPI_URL}/Ticket",
        headers={
            "App-Token": APP_TOKEN,
            "Session-Token": session,
            "Content-Type": "application/json"
        },
        json={
            "input": {
                "name": f"[HealOps] Fallo en {host}: {alerta}",
                "content": f"La remediación automática falló en el host '{host}'.\nAlerta: {alerta}\nSe requiere intervención manual.",
                "urgency": 4,   # 4 = Alta
                "priority": 4,
                "status": 1     # 1 = Nuevo
            }
        }
    )
    ticket_id = response.json().get("id")
    if ticket_id:
        print(f"  [TICKET] Ticket #{ticket_id} creado en GLPI para {host}")
        escribir_log(f"CREADO | ticket#{ticket_id} | {host} | {alerta}")
    else:
        print(f"  [TICKET] Error al crear ticket para {host}")
        escribir_log(f"ERROR | {host} | {alerta}")
    return ticket_id

# Obtiene tickets de HealOps que NO están cerrados (status 5=Resuelto, 6=Cerrado)
def obtener_tickets_abiertos(session):
    response = requests.get(
        f"{GLPI_URL}/Ticket",
        headers={"App-Token": APP_TOKEN, "Session-Token": session},
        params={"searchText[name]": "[HealOps]", "is_deleted": 0}
    )
    resultados = response.json()
    if not isinstance(resultados, list):
        return []
    return [t for t in resultados if int(t.get("status", 1)) not in (5, 6)]

# Cierra un ticket en GLPI marcándolo como resuelto
def cerrar_ticket(session, ticket_id):
    response = requests.put(
        f"{GLPI_URL}/Ticket/{ticket_id}",
        headers={
            "App-Token": APP_TOKEN,
            "Session-Token": session,
            "Content-Type": "application/json"
        },
        json={"input": {"status": 5}}  # 5 = Resuelto en GLPI
    )
    if response.status_code == 200:
        print(f"  Ticket  #{ticket_id} cerrado en GLPI — alerta resuelta en Zabbix")
        escribir_log(f"CERRADO | ticket#{ticket_id}")
    return response.status_code == 200

# Reconcilia tickets abiertos en GLPI con alertas activas en Zabbix
def cerrar_tickets_resueltos(session, nombres_alertas_activas):
    tickets = obtener_tickets_abiertos(session)
    for ticket in tickets:
        nombre = ticket.get("name", "")
        # Si ninguna alerta activa coincide con el ticket, se cierra
        sigue_activa = any(alerta.lower() in nombre.lower() for alerta in nombres_alertas_activas)
        if not sigue_activa:
            cerrar_ticket(session, ticket["id"])

# Cierra la sesión en GLPI
def logout(session):
    requests.get(
        f"{GLPI_URL}/killSession",
        headers={"App-Token": APP_TOKEN, "Session-Token": session}
    )


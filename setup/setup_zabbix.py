import requests
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ZABBIX_URL  = os.getenv("ZABBIX_URL",      "http://localhost:8080/api_jsonrpc.php")
ZABBIX_USER = os.getenv("ZABBIX_USER",     "Admin")
ZABBIX_PASS = os.getenv("ZABBIX_PASSWORD", "zabbix")

# Triggers a crear por host. Expresiones con avg(,3m) para evitar falsos positivos por picos.
# priority: 2=Warning 3=Average 4=High 5=Disaster
TRIGGERS = [
    {
        "description": "CPU Alta",
        "item_key":    "system.cpu.util",
        "expr_tpl":    "avg(/{host}/system.cpu.util,3m)>85",
        "priority":    4,
        "tags":        [{"tag": "componente", "value": "cpu"}],
    },
    {
        "description": "Carga del sistema alta",
        "item_key":    "system.cpu.load[all,avg1]",
        "expr_tpl":    "avg(/{host}/system.cpu.load[all,avg1],3m)>2",
        "priority":    3,
        "tags":        [{"tag": "componente", "value": "cpu"}],
    },
    {
        "description": "Memoria disponible baja",
        "item_key":    "vm.memory.size[pavailable]",
        "expr_tpl":    "avg(/{host}/vm.memory.size[pavailable],3m)<10",
        "priority":    4,
        "tags":        [{"tag": "componente", "value": "memoria"}],
    },
    {
        "description": "Memoria disponible critica",
        "item_key":    "vm.memory.size[pavailable]",
        "expr_tpl":    "avg(/{host}/vm.memory.size[pavailable],3m)<5",
        "priority":    5,
        "tags":        [{"tag": "componente", "value": "memoria"}],
    },
    {
        "description": "Swap bajo",
        "item_key":    "system.swap.size[,pfree]",
        "expr_tpl":    "avg(/{host}/system.swap.size[,pfree],3m)<20",
        "priority":    3,
        "tags":        [{"tag": "componente", "value": "swap"}],
    },
    {
        "description": "Disco raiz lleno",
        "item_key":    "vfs.fs.size[/,pused]",
        "expr_tpl":    "last(/{host}/vfs.fs.size[/,pused])>85",
        "priority":    4,
        "tags":        [{"tag": "componente", "value": "disco"}],
    },
    {
        "description": "Disco raiz critico",
        "item_key":    "vfs.fs.size[/,pused]",
        "expr_tpl":    "last(/{host}/vfs.fs.size[/,pused])>95",
        "priority":    5,
        "tags":        [{"tag": "componente", "value": "disco"}],
    },
    {
        "description": "Procesos zombie detectados",
        "item_key":    "proc.num[,,Z]",
        "expr_tpl":    "avg(/{host}/proc.num[,,Z],3m)>5",
        "priority":    2,
        "tags":        [{"tag": "componente", "value": "procesos"}],
    },
    {
        "description": "SSH no responde",
        "item_key":    "net.tcp.service[ssh]",
        "expr_tpl":    "last(/{host}/net.tcp.service[ssh])=0",
        "priority":    5,
        "tags":        [{"tag": "componente", "value": "red"}],
    },
]


def separador():
    print("  " + "-" * 55)


def login():
    r = requests.post(ZABBIX_URL, json={
        "jsonrpc": "2.0", "method": "user.login",
        "params": {"username": ZABBIX_USER, "password": ZABBIX_PASS},
        "id": 1
    })
    token = r.json().get("result")
    if not token:
        print(f"  [ERROR] Login fallido: {r.json()}")
        sys.exit(1)
    return token


def obtener_hosts(token):
    r = requests.post(ZABBIX_URL, json={
        "jsonrpc": "2.0", "method": "host.get",
        "params": {"output": ["hostid", "host"]},
        "id": 2
    }, headers={"Authorization": f"Bearer {token}"})
    return r.json().get("result", [])


def item_existe(token, hostid, key):
    r = requests.post(ZABBIX_URL, json={
        "jsonrpc": "2.0", "method": "item.get",
        "params": {"hostids": hostid, "search": {"key_": key}, "output": ["itemid"]},
        "id": 3
    }, headers={"Authorization": f"Bearer {token}"})
    return len(r.json().get("result", [])) > 0


def trigger_existe(token, hostid, descripcion):
    r = requests.post(ZABBIX_URL, json={
        "jsonrpc": "2.0", "method": "trigger.get",
        "params": {"hostids": hostid, "filter": {"description": descripcion}},
        "id": 4
    }, headers={"Authorization": f"Bearer {token}"})
    return len(r.json().get("result", [])) > 0


def crear_trigger(token, host, hostid, tpl):
    # Verificar que el item existe antes de intentar crear el trigger
    if not item_existe(token, hostid, tpl["item_key"]):
        print(f"    · {tpl['description']:<35} sin item '{tpl['item_key']}' — omitido")
        return

    if trigger_existe(token, hostid, tpl["description"]):
        print(f"    · {tpl['description']:<35} ya existe — omitido")
        return

    expresion = tpl["expr_tpl"].replace("{host}", host)
    r = requests.post(ZABBIX_URL, json={
        "jsonrpc": "2.0", "method": "trigger.create",
        "params": {
            "description":   tpl["description"],
            "expression":    expresion,
            "priority":      tpl["priority"],
            "tags":          tpl.get("tags", []),
            "recovery_mode": 0,
        },
        "id": 5
    }, headers={"Authorization": f"Bearer {token}"})

    resultado = r.json()
    if "result" in resultado:
        print(f"    · {tpl['description']:<35} creado OK")
    else:
        error = resultado.get("error", {}).get("data", resultado)
        print(f"    · {tpl['description']:<35} ERROR: {error}")


if __name__ == "__main__":
    print("\n  HealOps — Setup de triggers Zabbix")
    separador()

    token = login()
    hosts = obtener_hosts(token)

    if not hosts:
        print("  [!] No se encontraron hosts en Zabbix.")
        sys.exit(0)

    print(f"  Hosts encontrados: {len(hosts)}")
    separador()

    for h in hosts:
        print(f"\n  Host: {h['host']}")
        for tpl in TRIGGERS:
            crear_trigger(token, h["host"], h["hostid"], tpl)

    separador()
    print("  Setup completado.\n")

import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from monitor.analizador_alertas import ACCIONES


def _analizar(resultado_zabbix):
    """Replica la lógica de analizar_alertas sin llamar a la API."""
    df = pd.DataFrame(resultado_zabbix)
    df["host"] = df["hosts"].apply(lambda x: x[0]["host"] if x else "desconocido")
    df = df.rename(columns={"description": "nombre", "priority": "severity"})
    return df[df["severity"].astype(int) >= 4]


def test_filtra_falsos_positivos():
    alertas = [
        {"triggerid": "1", "description": "CPU Alta",  "priority": "4", "hosts": [{"host": "srv-01"}]},
        {"triggerid": "2", "description": "Info log",  "priority": "2", "hosts": [{"host": "srv-01"}]},
        {"triggerid": "3", "description": "Warning",   "priority": "1", "hosts": [{"host": "srv-02"}]},
    ]
    reales = _analizar(alertas)
    assert len(reales) == 1
    assert reales.iloc[0]["nombre"] == "CPU Alta"


def test_severity_5_es_real():
    alertas = [
        {"triggerid": "1", "description": "SSH no responde", "priority": "5", "hosts": [{"host": "srv-01"}]},
    ]
    reales = _analizar(alertas)
    assert len(reales) == 1


def test_severity_3_es_falso_positivo():
    alertas = [
        {"triggerid": "1", "description": "Swap bajo", "priority": "3", "hosts": [{"host": "srv-01"}]},
    ]
    reales = _analizar(alertas)
    assert len(reales) == 0


def test_sin_alertas():
    alertas = [
        {"triggerid": "1", "description": "Info", "priority": "1", "hosts": [{"host": "srv-01"}]},
    ]
    reales = _analizar(alertas)
    assert len(reales) == 0


def test_acciones_keyword_cpu():
    alerta = "CPU Alta en servidor"
    comando = next((v for k, v in ACCIONES.items() if k in alerta.lower()), None)
    assert comando is not None


def test_acciones_keyword_desconocido():
    alerta = "Problema desconocido XYZ"
    comando = next((v for k, v in ACCIONES.items() if k in alerta.lower()), None)
    assert comando is None

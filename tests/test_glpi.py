def test_tickets_abiertos_filtra_cerrados():
    tickets = [
        {"id": 1, "name": "CPU Alta srv-01", "status": "1"},
        {"id": 2, "name": "Disco srv-02",    "status": "5"},  # resuelto
        {"id": 3, "name": "Memoria srv-01",  "status": "6"},  # cerrado
        {"id": 4, "name": "SSH srv-03",      "status": "2"},
    ]
    abiertos = [t for t in tickets if int(t["status"]) not in (5, 6)]
    assert len(abiertos) == 2
    assert all(int(t["status"]) not in (5, 6) for t in abiertos)


def test_ticket_existe_ignora_resueltos():
    tickets = [
        {"id": 1, "name": "CPU Alta srv-01", "status": "5"},
        {"id": 2, "name": "CPU Alta srv-01", "status": "6"},
    ]
    existe = any(int(t["status"]) not in (5, 6) for t in tickets)
    assert existe is False


def test_ticket_existe_detecta_abierto():
    tickets = [
        {"id": 1, "name": "CPU Alta srv-01", "status": "1"},
    ]
    existe = any(int(t["status"]) not in (5, 6) for t in tickets)
    assert existe is True

from fastapi.testclient import TestClient

from simulator.main import app

client = TestClient(app)


def test_same_inn_gives_same_answer():
    for path in ("/egrul/7709008002", "/bki/7709008002", "/abs/7709008002/turnovers"):
        assert client.get(path).json() == client.get(path).json()


def test_different_inns_give_different_companies():
    a = client.get("/egrul/7709008002").json()["items"][0]["ЮЛ"]
    b = client.get("/egrul/6605006009").json()["items"][0]["ЮЛ"]
    assert a["НаимСокрЮЛ"] != b["НаимСокрЮЛ"]


def test_persona_profile():
    ul = client.get("/egrul/7701234560").json()["items"][0]["ЮЛ"]
    assert ul["НаимСокрЮЛ"] == "ООО «Северный ветер»"
    assert ul["Руководитель"]["ИННФЛ"] == "500100000015"

    ip = client.get("/egrul/500100000015").json()["items"][0]["ИП"]
    assert ip["ФИОПолн"] == "Смирнова Анна Викторовна"
    assert client.get("/abs/500100000015/turnovers").json()["client"] is False


def test_persona_turnovers_net_income_is_exact():
    months = client.get("/abs/7701234560/turnovers").json()["months"]
    last12 = months[-12:]
    net = sum(m["credit_turnover"] - m["debit_turnover"] for m in last12) / 12
    assert len(months) == 24
    assert abs(net - 450_000) < 1


def test_invalid_inn_is_rejected():
    assert client.get("/egrul/7701234567").status_code == 400
    assert client.get("/fns/abc").status_code == 400


def test_bki_payment_string():
    accounts = client.get("/bki/5403004007").json()["accounts"]
    closed = accounts[0]["payment_string"]
    assert closed.startswith("-") and "2" in closed  # закрыт, просрочка 30+ была
    assert closed.index("1") == closed.index("2") + 1  # к 30+ дошла через «до 30»

    for account in client.get("/bki/7701234560").json()["accounts"]:
        assert set(account["payment_string"]) == {"0"}  # платит без просрочек

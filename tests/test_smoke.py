"""
Smoke tests: solo comprueban que la app arranca y que las rutas críticas
responden sin un 500. No validan lógica de negocio.
"""


def test_health_responde_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_login_page_responde_ok(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_dashboard_sin_sesion_redirige_sin_error(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_consulta_antonia_sin_sesion_redirige_sin_error(client):
    resp = client.get("/consulta/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"

import json
import os

from inspector_raspi import create_app


def test_health_and_temp():
    app = create_app()
    client = app.test_client()
    rv = client.get('/health')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data.get('status') == 'ok'

    rv2 = client.get('/cpu-temp')
    assert rv2.status_code == 200
    data2 = rv2.get_json()
    assert 'cpu_temp_c' in data2


def test_system_info_shape():
    app = create_app()
    client = app.test_client()
    rv = client.get('/system-info')
    assert rv.status_code == 200
    data = rv.get_json()
    for key in [
        'cpu','memory','storage','gpu','os','python','network','peripherals','ml'
    ]:
        assert key in data


def test_version_and_capabilities():
    app = create_app()
    client = app.test_client()
    rv = client.get('/version')
    assert rv.status_code == 200
    v = rv.get_json()
    assert 'python' in v

    rv2 = client.get('/capabilities')
    assert rv2.status_code == 200
    caps = rv2.get_json()
    assert isinstance(caps, dict)
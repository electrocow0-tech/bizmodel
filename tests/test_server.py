import pytest
from fastapi.testclient import TestClient

from bizmodel import server
from bizmodel.schemas import Run

FIXTURE = server.ROOT / "tests" / "fixtures" / "run.json"
PARAMS = {
    "sample_size": 100,
    "deep_check": 8,
    "industries": ["B2B", "Consumer"],
    "weights": {
        "time_to_test": 30,
        "customer_access": 25,
        "time_to_payment": 15,
        "demand_proof": 10,
        "barriers": 10,
        "objections": 10,
    },
    "assumptions": {"team": "двое", "test_budget_usd": 5000, "horizon_weeks": 8},
    "profile": "dev",
    "max_usd": 2,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    reference = Run.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setenv("RUN_CODE", "secret")
    monkeypatch.setattr(server, "LEDGER", tmp_path / "spent.json")
    monkeypatch.setattr(server, "latest", lambda: reference)
    monkeypatch.setattr(server, "publish", lambda run: None)
    monkeypatch.setattr(server, "state", server.State())
    started = []
    monkeypatch.setattr(
        server.threading,
        "Thread",
        lambda target, args, daemon: type(
            "Idle", (), {"start": lambda self: started.append(args)}
        )(),
    )
    with TestClient(server.app) as client:
        client.started = started
        yield client


def test_status_shows_the_budget_left(client):
    body = client.get("/api/status").json()
    assert body["available"] and not body["running"]
    assert body["budget"]["anthropic"] == {"limit": 10, "spent": 0.0}
    assert body["budget"]["openrouter"] == {"limit": 5, "spent": 0.0}


def test_estimate_scales_with_the_funnel(client):
    small = client.post("/api/estimate", json=PARAMS | {"profile": "showcase"}).json()
    big = client.post(
        "/api/estimate", json=PARAMS | {"profile": "showcase", "sample_size": 300, "deep_check": 20}
    ).json()
    assert 0 < small["usd"]["anthropic"] < big["usd"]["anthropic"]
    assert small["minutes"] < big["minutes"]


def test_wrong_code_does_not_start_anything(client):
    response = client.post("/api/runs", json={"code": "guess", "params": PARAMS})
    assert response.status_code == 403
    assert client.started == []


def test_run_starts_with_what_is_left_of_the_budget(client):
    server.LEDGER.write_text('{"anthropic": 7.5, "openrouter": 1}', encoding="utf-8")
    response = client.post("/api/runs", json={"code": "secret", "params": PARAMS})
    assert response.status_code == 202
    ((params, budgets),) = client.started
    assert params.deep_check == 8
    assert budgets == {"anthropic": 2.5, "openrouter": 4.0}


def test_only_one_run_at_a_time(client):
    client.post("/api/runs", json={"code": "secret", "params": PARAMS})
    second = client.post("/api/runs", json={"code": "secret", "params": PARAMS})
    assert second.status_code == 409


def test_spent_budget_blocks_new_runs(client):
    server.LEDGER.write_text('{"anthropic": 10, "openrouter": 5}', encoding="utf-8")
    response = client.post("/api/runs", json={"code": "secret", "params": PARAMS})
    assert response.status_code == 402


def test_weights_must_add_up_to_a_hundred(client):
    broken = PARAMS | {"weights": PARAMS["weights"] | {"time_to_test": 90}}
    assert client.post("/api/runs", json={"code": "secret", "params": broken}).status_code == 422

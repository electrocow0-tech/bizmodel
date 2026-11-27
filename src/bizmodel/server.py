"""Живой стенд: отдаёт страницу и запускает прогон по кнопке собственника.

Один прогон за раз, вход по коду, общий потолок расхода на все запуски со стенда.
"""

import hmac
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bizmodel import config, pipeline
from bizmodel.params import Params, estimate
from bizmodel.schemas import Run

log = logging.getLogger("bizmodel")
ROOT = Path(os.environ.get("BIZMODEL_ROOT", Path(__file__).resolve().parents[2]))
SERVED = ROOT / "served"
LEDGER = ROOT / "state" / "spent.json"
DOCUMENTS = ("decisions", "limitations", "full_version")
STAGES = {
    "prescreen": "Дешёвый отсев",
    "gate": "Проверка по критериям",
    "card": "Критик, проверяющий и карточка",
    "advice": "Советник",
    "stand": "Сборка стенда",
}


class Launch(BaseModel):
    code: str
    params: Params


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.progress: dict | None = None
        self.error: str | None = None
        self.last_run: str | None = None

    def step(self, stage: str, done: int, total: int) -> None:
        self.progress = {
            "stage": stage,
            "done": done,
            "total": total,
            "message": f"{STAGES[stage]}: {done} из {total}",
        }


state = State()


def limits() -> dict[str, float]:
    return config.load(ROOT).stand.budget_usd


def spent() -> dict[str, float]:
    saved = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    return {provider: saved.get(provider, 0.0) for provider in limits()}


def remaining() -> dict[str, float]:
    used = spent()
    return {provider: max(0.0, limit - used[provider]) for provider, limit in limits().items()}


def record(run: Run) -> None:
    used = spent()
    for provider, amount in run.spent.items():
        used[provider] = round(used.get(provider, 0.0) + amount, 4)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(used, indent=1), encoding="utf-8")


def latest() -> Run:
    path = max((ROOT / "runs").glob("*/run.json"))
    return Run.model_validate_json(path.read_text(encoding="utf-8"))


def publish(run: Run) -> None:
    from bizmodel.stand import build

    documents = {}
    for name in DOCUMENTS:
        path = ROOT / f"{name.upper()}.md"
        documents[name] = path.read_text(encoding="utf-8") if path.exists() else ""
    build(run, SERVED, documents)
    state.last_run = run.id


def launch(params: Params, budgets: dict[str, float]) -> None:
    try:
        run = pipeline.run(
            ROOT, params=params, budgets=budgets, progress=state.step, report=lambda line: None
        )
        record(run)
        state.step("stand", 0, 1)
        publish(run)
    except Exception as error:
        log.exception("run failed")
        state.error = f"Прогон остановился: {error}"
    finally:
        state.progress = None
        state.running = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    publish(latest())
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def refuse(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


@app.get("/api/status")
def status() -> dict:
    used = spent()
    return {
        "available": True,
        "running": state.running,
        "progress": state.progress,
        "budget": {
            provider: {"limit": limit, "spent": round(used[provider], 2)}
            for provider, limit in limits().items()
        },
        "last_run": state.last_run,
        "error": state.error,
    }


@app.post("/api/estimate")
def cost(params: Params) -> dict:
    return estimate(params, latest())


@app.post("/api/runs", status_code=202)
def start(request: Launch):
    expected = os.environ.get("RUN_CODE", "")
    if not expected or not hmac.compare_digest(request.code.strip(), expected):
        return refuse(403, "Неверный код запуска.")
    left = remaining()
    if all(amount < 0.05 for amount in left.values()):
        return refuse(402, "Тестовый бюджет израсходован.")
    with state.lock:
        if state.running:
            return refuse(409, "Прогон уже идёт, дождитесь его окончания.")
        state.running = True
        state.error = None
        state.step("prescreen", 0, request.params.sample_size)
    threading.Thread(target=launch, args=(request.params, left), daemon=True).start()
    return {"started": True, "at": datetime.now().isoformat(timespec="seconds")}


SERVED.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=SERVED, html=True), name="stand")

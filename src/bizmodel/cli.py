from pathlib import Path

import typer
from dotenv import load_dotenv

from bizmodel import config, golden, pipeline
from bizmodel import drill as outage
from bizmodel.schemas import Run

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "data" / "golden" / "labels.csv"
RUN_ID = typer.Argument(None, help="Прогон из runs/, по умолчанию последний")

app = typer.Typer(add_completion=False, help="Конвейер проверки бизнес-моделей.")


@app.callback()
def environment() -> None:
    load_dotenv(ROOT / ".env")


@app.command()
def run(profile: str = typer.Option(None, help="Профиль моделей из config/models.yaml")) -> None:
    """Прогнать конвейер целиком и записать результат в runs/."""
    result = pipeline.run(ROOT, profile, report=typer.echo)
    typer.echo(f"Готово: runs/{result.id}/run.json")
    for cost in result.costs:
        typer.echo(f"  {cost.provider:<10} {cost.role:<9} {cost.model:<32} ${cost.usd:.3f}")


@app.command()
def stand(run_id: str = RUN_ID) -> None:
    """Собрать статический стенд в docs/ из готового прогона."""
    from bizmodel.stand import build

    result = load(run_id)
    documents = {
        name: read_or_empty(ROOT / f"{name.upper()}.md")
        for name in ("decisions", "limitations", "full_version")
    }
    build(result, ROOT / "docs", documents)
    typer.echo(f"Стенд собран из прогона {result.id}: docs/index.html")


@app.command()
def drill(run_id: str = RUN_ID) -> None:
    """Учебный сбой: выключить основного провайдера и убедиться, что сработал запасной."""
    result = load(run_id)
    result.outage_drill = outage.run(config.load(ROOT, result.profile))
    save(result)
    typer.echo(
        f"{result.outage_drill.failed_route} недоступен, "
        f"ответил {result.outage_drill.served_by} за {result.outage_drill.seconds} с"
    )


@app.command()
def labels(run_id: str = RUN_ID) -> None:
    """Выгрузить таблицу для разметки человеком: без ответов моделей."""
    if golden.answered(LABELS):
        typer.echo(f"В {LABELS.relative_to(ROOT)} уже есть ответы человека, файл не перезаписан.")
        raise typer.Exit(1)
    rows = golden.export(load(run_id), LABELS)
    typer.echo(
        f"{rows} строк: {LABELS.relative_to(ROOT)}. Заполните столбец «ответ»: да, нет, не знаю"
    )


@app.command()
def score(run_id: str = RUN_ID) -> None:
    """Сравнить разметку человека с решениями леса."""
    result = load(run_id)
    result.golden = golden.score(result, LABELS)
    save(result)
    typer.echo(f"Совпало {result.golden.agreed} из {result.golden.labelled}")
    for line in result.golden.disagreements:
        typer.echo(f"  {line}")


def load(run_id: str | None) -> Run:
    finished = sorted((ROOT / "runs").glob("*/run.json"))
    path = ROOT / "runs" / run_id / "run.json" if run_id else finished[-1]
    return Run.model_validate_json(path.read_text(encoding="utf-8"))


def save(result: Run) -> None:
    path = ROOT / "runs" / result.id / "run.json"
    path.write_text(result.model_dump_json(indent=1), encoding="utf-8")


def read_or_empty(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

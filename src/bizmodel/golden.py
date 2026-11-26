"""Эталонная разметка: человек отвечает вслепую, потом ответы сравниваются с лесом.

В таблице нет решений моделей, только компания, критерий и цитаты из источников.
Тот же набор служит проверочным для будущего дообучения.
"""

import csv
from pathlib import Path

from bizmodel.schemas import Gate, GoldenScore, Run

COLUMNS = ["компания", "чем занимается", "сайт", "критерий", "цитаты из источников", "ответ"]
ANSWERS = {"да": "pass", "нет": "fail", "не знаю": "unknown"}
IN_RUSSIAN = {"pass": "да", "fail": "нет", "unknown": "не знаю"}


def export(run: Run, path: Path) -> int:
    """Финалисты размечаются по всем критериям, контрольные отказы - по сработавшему."""
    flagged = {
        prescreen.slug: {violation.criterion for violation in prescreen.violations}
        for prescreen in run.prescreens
    }
    rows = []
    for gate in run.gates:
        company = run.companies[gate.slug]
        in_control = gate.slug in run.control.slugs
        for tree in gate.trees:
            if in_control and tree.tree_id not in flagged[gate.slug]:
                continue
            rows.append(
                {
                    "компания": company.name,
                    "чем занимается": company.one_liner,
                    "сайт": company.website,
                    "критерий": tree.title,
                    "цитаты из источников": quotes(gate, tree.path),
                    "ответ": "",
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def quotes(gate: Gate, path: list[str]) -> str:
    on_path = {f"gate.{question_id}" for question_id in path}
    return "\n".join(
        f"«{passport.quote}» ({passport.source_url})"
        for passport in gate.passports
        if passport.id in on_path and passport.quote
    )


def score(run: Run, path: Path) -> GoldenScore:
    by_name = {run.companies[gate.slug].name: gate for gate in run.gates}
    labelled, agreed, disagreements = 0, 0, []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            human = ANSWERS.get(row["ответ"].strip().lower())
            if human is None:
                continue
            gate = by_name[row["компания"]]
            tree = next(tree for tree in gate.trees if tree.title == row["критерий"])
            labelled += 1
            if tree.outcome == human:
                agreed += 1
            else:
                disagreements.append(
                    f"{row['компания']} - {tree.title}: "
                    f"человек «{IN_RUSSIAN[human]}», лес «{IN_RUSSIAN[tree.outcome]}»"
                )
    return GoldenScore(labelled=labelled, agreed=agreed, disagreements=disagreements)

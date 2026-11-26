"""Деревья решений по критериям собственника. Модели отвечают на вопросы узлов, путь выбирает код."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

from bizmodel.schemas import Answer, Outcome, TreeResult

OUTCOMES = ("pass", "fail", "unknown")


class Leaf(BaseModel):
    outcome: Outcome
    reason: str

    @model_validator(mode="before")
    @classmethod
    def from_shorthand(cls, value):
        if isinstance(value, dict) and len(value) == 1:
            ((outcome, reason),) = value.items()
            if outcome in OUTCOMES:
                return {"outcome": outcome, "reason": reason}
        return value


class Node(BaseModel):
    label: str
    ask: str
    yes: str | Leaf
    no: str | Leaf
    unknown: Leaf | None = None

    def branch(self, answer: Answer) -> str | Leaf:
        if answer == "yes":
            return self.yes
        if answer == "no":
            return self.no
        return self.unknown or Leaf(
            outcome="unknown", reason=f"Не удалось проверить: {self.label.lower()}"
        )


class Tree(BaseModel):
    id: str
    title: str
    root: str
    nodes: dict[str, Node]

    @model_validator(mode="after")
    def branches_lead_somewhere(self):
        targets = [self.root]
        for node in self.nodes.values():
            targets += [branch for branch in (node.yes, node.no) if isinstance(branch, str)]
        missing = sorted(set(targets) - set(self.nodes))
        if missing:
            raise ValueError(f"tree {self.id}: unknown nodes {missing}")
        return self


class Forest(BaseModel):
    trees: list[Tree]

    @property
    def version(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]

    @property
    def questions(self) -> dict[str, Node]:
        return {
            f"{tree.id}.{node_id}": node
            for tree in self.trees
            for node_id, node in tree.nodes.items()
        }


def load(path: Path) -> Forest:
    return Forest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def walk(tree: Tree, answer_to: Callable[[str], Answer]) -> TreeResult:
    path = []
    node_id = tree.root
    for _ in tree.nodes:
        question_id = f"{tree.id}.{node_id}"
        path.append(question_id)
        branch = tree.nodes[node_id].branch(answer_to(question_id))
        if isinstance(branch, Leaf):
            return TreeResult(
                tree_id=tree.id,
                title=tree.title,
                outcome=branch.outcome,
                path=path,
                reason=branch.reason,
            )
        node_id = branch
    raise ValueError(f"tree {tree.id} loops back on itself")


def overall(results: list[TreeResult]) -> Outcome:
    outcomes = {result.outcome for result in results}
    if "fail" in outcomes:
        return "fail"
    if outcomes == {"pass"}:
        return "pass"
    return "unknown"

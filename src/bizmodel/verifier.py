"""Проверяющий сверяет утверждение с его источником.

Он получает текст утверждения и страницу. Рассуждений критика, оценки силы
и остальных возражений в его запросе нет, и это проверяется перед каждым вызовом.
"""

from typing import Literal

from pydantic import BaseModel

from bizmodel.context import Context
from bizmodel.evidence import checked_quote
from bizmodel.llm import StepFailed
from bizmodel.schemas import Objection, Passport
from bizmodel.search import Page, window


class Finding(BaseModel):
    verdict: Literal["supported", "not_supported", "contradicts"]
    quote: str
    source_date: str
    note: str


def check(objections: list[Objection], slug: str, ctx: Context) -> list[Passport]:
    strongest = sorted(objections, key=lambda objection: -objection.strength)
    passports = []
    for objection in strongest[: ctx.settings.critic.objections_to_verify]:
        objection.sent_to_verifier = True
        others = [other for other in objections if other is not objection]
        page = verify(objection, others, slug, ctx)
        passports.append(passport_of(objection, page))
    for objection in strongest[ctx.settings.critic.objections_to_verify :]:
        passports.append(passport_of(objection, None))
    return passports


def verify(objection: Objection, others: list[Objection], slug: str, ctx: Context) -> Page | None:
    if not objection.source_url:
        objection.verdict = "no_source"
        return None
    page = ctx.search("verifier").fetch(objection.source_url)
    if page is None:
        objection.verdict = "source_unavailable"
        return None

    sections = brief(objection, page, ctx.settings.search.page_chars)
    ctx.journal.write(
        "isolation_check",
        slug=slug,
        objection=objection.id,
        leaked=leaks(sections, objection, others),
    )
    try:
        finding = ctx.llm.ask(
            "verifier",
            ctx.settings.roles.verifier,
            ctx.settings.prompt("verifier"),
            sections,
            Finding,
            slug=slug,
        )
    except StepFailed:
        objection.verifier_note = "Проверка не выполнена: модель не ответила"
        return page

    objection.verdict = finding.verdict
    objection.verifier_note = finding.note
    objection.verifier_quote = checked_quote(finding.quote, "page", {"page": page}, ctx) or None
    objection.source_date = finding.source_date or objection.source_date
    return page


def brief(objection: Objection, page: Page, page_chars: int) -> dict[str, str]:
    return {
        "Claim": objection.text,
        "Source": page.url,
        "Page text": window(page.text, objection.quote, page_chars),
    }


def leaks(sections: dict[str, str], objection: Objection, others: list[Objection]) -> list[str]:
    """Что из выводов критика попало в запрос проверяющего. Должно быть пусто."""
    visible = sections["Claim"] + sections["Source"]
    secrets = {"reasoning": objection.reasoning}
    for other in others:
        secrets[f"{other.id} text"] = other.text
        secrets[f"{other.id} reasoning"] = other.reasoning
    return [name for name, secret in secrets.items() if secret and secret in visible]


def passport_of(objection: Objection, page: Page | None) -> Passport:
    confirmed = objection.verdict in ("supported", "contradicts") and objection.verifier_quote
    if confirmed:
        method, confidence = "primary_source", "high"
    elif objection.verdict in (None, "source_unavailable"):
        method, confidence = "needs_human", "low"
    else:
        method, confidence = "model_judgment", "low"

    notes = {
        "supported": "Источник подтверждает",
        "contradicts": "Источник говорит иное",
        "not_supported": "Источник этого не утверждает",
        "no_source": "Источника нет, это суждение критика",
        "source_unavailable": "Источник не открылся",
    }
    unchecked = objection.verifier_note or "Не проверялось: вне самых сильных возражений"
    objection.passport_id = f"objection.{objection.id}"
    return Passport(
        id=objection.passport_id,
        claim=objection.text,
        origin="critic",
        method=method,
        confidence=confidence,
        source_url=objection.source_url,
        quote=objection.verifier_quote or objection.quote,
        source_date=objection.source_date,
        accessed=page.accessed if page else None,
        note=notes.get(objection.verdict, unchecked),
    )

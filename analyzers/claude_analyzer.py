"""FR-6, FR-7: Извлечение полей заемщика и проверка отчета через Claude API."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

MAX_TEXT_CHARS = 120_000


@dataclass
class Issue:
    """Замечание по проверке."""

    severity: str  # high / medium / low
    check: str
    field: str
    description: str
    evidence: str = ""


@dataclass
class AnalysisResult:
    """Результат анализа одного документа."""

    borrower_fields: dict[str, Any] = field(default_factory=dict)
    verdict: str = "insufficient_data"  # ok / issues / insufficient_data
    summary: str = ""
    issues: list[Issue] = field(default_factory=list)
    error: str | None = None


EXTRACT_TOOL = {
    "name": "report_borrower_fields",
    "description": "Сообщить извлеченные из документа поля заемщика",
    "input_schema": {
        "type": "object",
        "properties": {
            "bin_iin": {"type": ["string", "null"], "description": "БИН/ИИН заемщика, 12 цифр"},
            "borrower_name": {"type": ["string", "null"], "description": "Наименование заемщика"},
            "contract_number": {"type": ["string", "null"], "description": "Номер кредитного договора"},
            "contract_date": {"type": ["string", "null"], "description": "Дата кредитного договора ГГГГ-ММ-ДД"},
            "credit_amount": {"type": ["number", "null"], "description": "Сумма кредита, только число"},
            "credit_purpose": {"type": ["string", "null"], "description": "Цель кредита"},
            "project_address": {"type": ["string", "null"], "description": "Адрес реализации проекта"},
            "region": {"type": ["string", "null"], "description": "Регион (область/город)"},
            "monitoring_date": {"type": ["string", "null"], "description": "Дата мониторинга ГГГГ-ММ-ДД"},
            "confirmed_amount": {"type": ["number", "null"], "description": "Подтвержденная сумма целевого использования, только число"},
            "purpose_conclusion": {
                "type": ["string", "null"],
                "enum": ["соответствует", "не соответствует", "частично", None],
                "description": "Вывод о целевом использовании",
            },
            "counterparties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "bin": {"type": ["string", "null"], "description": "БИН контрагента, 12 цифр"},
                        "amount": {"type": ["number", "null"]},
                    },
                },
                "description": "Список контрагентов по оплатам",
            },
            "other_notes": {"type": ["string", "null"], "description": "Прочие замечания"},
        },
        "required": [
            "bin_iin", "borrower_name", "contract_number", "contract_date",
            "credit_amount", "credit_purpose", "project_address", "region",
            "monitoring_date", "confirmed_amount", "purpose_conclusion",
            "counterparties", "other_notes",
        ],
    },
}

CHECK_TOOL = {
    "name": "report_check_result",
    "description": "Сообщить результат проверки мониторингового отчета",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["ok", "issues", "insufficient_data"]},
            "summary": {"type": "string", "description": "Краткое резюме проверки"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                        "check": {"type": "string", "description": "Вид проверки: суммы / целевое использование / контрагенты / даты / прочее"},
                        "field": {"type": "string", "description": "Поле, к которому относится замечание"},
                        "description": {"type": "string"},
                        "evidence": {"type": "string", "description": "Обоснование, цитата из документа"},
                    },
                    "required": ["severity", "check", "field", "description"],
                },
            },
        },
        "required": ["verdict", "summary", "issues"],
    },
}

EXTRACT_PROMPT = """Из документа ниже извлеки структурированные поля заемщика и верни их через инструмент report_borrower_fields.

Правила:
- Суммы — только числа (без пробелов, валют и разделителей).
- Даты — в формате ГГГГ-ММ-ДД.
- БИН/ИИН — ровно 12 цифр.
- Если данных нет в документе — передавай null, ничего не выдумывай.

Документ:
{text}"""

CHECK_PROMPT = """Проверь мониторинговый отчет банка и верни результат через инструмент report_check_result.

Проверки:
1. Суммы: совпадает ли подтвержденная сумма целевого использования с суммами платежных документов.
2. Целевое использование: соответствуют ли фактические платежи заявленной цели кредита.
3. Контрагенты: указаны ли, есть ли БИН (12 цифр).
4. Даты: не выходят ли платежи за пределы периода мониторинга.
5. Прочее: противоречия, отсутствие обязательных данных.

Отчет:
{report_text}
{primary_section}"""


def _truncate(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[...текст обрезан...]"


def _extract_json_fallback(text: str) -> dict | None:
    """Попробовать извлечь JSON из произвольного текста ответа."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _call_tool(client: anthropic.Anthropic, model: str, prompt: str, tool: dict) -> dict | None:
    """Вызвать модель с принудительным использованием инструмента и вернуть input."""
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    # Запасной вариант: текстовый JSON
    text = "".join(b.text for b in response.content if b.type == "text")
    return _extract_json_fallback(text)


def extract_borrower_fields(
    client: anthropic.Anthropic, text: str, model: str = "claude-sonnet-4-5"
) -> dict[str, Any]:
    """FR-6: Извлечь поля заемщика из текста документа."""
    prompt = EXTRACT_PROMPT.format(text=_truncate(text))
    result = _call_tool(client, model, prompt, EXTRACT_TOOL)
    return result or {}


def analyze_document(
    client: anthropic.Anthropic,
    report_text: str,
    primary_docs_texts: list[str] | None = None,
    model: str = "claude-sonnet-4-5",
) -> dict[str, Any]:
    """FR-7: Проверить мониторинговый отчет (с опциональной сверкой с первичкой)."""
    if primary_docs_texts:
        joined = "\n\n".join(
            f"--- Первичный документ {i + 1} ---\n{_truncate(t, 30_000)}"
            for i, t in enumerate(primary_docs_texts)
        )
        primary_section = f"\n\nПервичные документы заемщика:\n{joined}"
    else:
        primary_section = "\n\nПервичные документы не предоставлены."

    prompt = CHECK_PROMPT.format(
        report_text=_truncate(report_text),
        primary_section=primary_section,
    )
    result = _call_tool(client, model, prompt, CHECK_TOOL)
    return result or {
        "verdict": "insufficient_data",
        "summary": "Не удалось получить результат анализа",
        "issues": [],
    }


def parse_issues(raw_issues: list[dict]) -> list[Issue]:
    """Преобразовать сырые замечания из ответа модели в объекты Issue."""
    issues: list[Issue] = []
    for item in raw_issues or []:
        try:
            issues.append(
                Issue(
                    severity=item.get("severity", "low"),
                    check=item.get("check", "прочее"),
                    field=item.get("field", ""),
                    description=item.get("description", ""),
                    evidence=item.get("evidence", ""),
                )
            )
        except Exception:
            continue
    return issues

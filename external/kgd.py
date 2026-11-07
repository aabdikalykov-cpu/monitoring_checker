"""FR-8: Проверка БИН контрагентов (КГД).

Полноценная проверка по реестрам КГД — точка расширения:
стабильного публичного API у КГД нет. Сейчас проверяется только формат.
"""

import re
from dataclasses import dataclass


@dataclass
class BinCheckResult:
    """Результат проверки БИН."""

    bin: str
    format_ok: bool
    message: str = ""


def validate_bin(bin_value: str | None) -> BinCheckResult:
    """Проверить формат БИН: ровно 12 цифр."""
    value = (bin_value or "").strip()
    if not value:
        return BinCheckResult(bin="", format_ok=False, message="БИН не указан")
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12:
        return BinCheckResult(bin=digits, format_ok=True)
    return BinCheckResult(
        bin=value,
        format_ok=False,
        message=f"БИН должен содержать 12 цифр (получено: {len(digits)})",
    )


def check_counterparty_bin(bin_value: str | None) -> BinCheckResult:
    """Проверка БИН контрагента. Точка расширения под реестры КГД."""
    return validate_bin(bin_value)

"""FR-8: Опциональный модуль региональных данных stat.gov (по умолчанию отключен)."""

from dataclasses import dataclass


@dataclass
class RegionData:
    """Региональные данные (заглушка для опциональной интеграции)."""

    region: str
    status: str = "disabled"  # disabled / ok / error
    message: str = ""


def get_region_data(region: str, enabled: bool = False) -> RegionData:
    """Вернуть региональные данные; модуль отключен по умолчанию."""
    if not enabled:
        return RegionData(region=region or "", status="disabled", message="Модуль отключен")
    # Точка расширения: интеграция с API Бюро национальной статистики РК.
    return RegionData(region=region or "", status="error", message="Интеграция не настроена")

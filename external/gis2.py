"""FR-8: Проверка адреса реализации проекта через 2ГИС Catalog API."""

from dataclasses import dataclass

import requests

from external.cache import FileCache

GIS2_GEOCODE_URL = "https://catalog.api.2gis.com/3.0/items/geocode"


@dataclass
class AddressCheckResult:
    """Результат проверки адреса."""

    status: str  # ok / not_found / skipped / error
    query: str
    normalized_address: str | None = None
    lat: float | None = None
    lon: float | None = None
    message: str = ""


def check_address(
    address: str,
    api_key: str | None,
    cache: FileCache | None = None,
) -> AddressCheckResult:
    """Проверить существование адреса через 2ГИС; без ключа — skipped."""
    if not address or not address.strip():
        return AddressCheckResult(status="skipped", query=address or "", message="Адрес не указан")
    if not api_key:
        return AddressCheckResult(status="skipped", query=address, message="Нет API-ключа 2ГИС")

    cache_key = f"gis2:{address.strip().lower()}"
    if cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return AddressCheckResult(**cached)

    try:
        response = requests.get(
            GIS2_GEOCODE_URL,
            params={"q": address, "key": api_key, "fields": "items.point"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        return AddressCheckResult(status="error", query=address, message=str(exc))

    items = (data.get("result") or {}).get("items") or []
    if not items:
        result = AddressCheckResult(status="not_found", query=address, message="Адрес не найден")
    else:
        item = items[0]
        point = item.get("point") or {}
        result = AddressCheckResult(
            status="ok",
            query=address,
            normalized_address=item.get("full_name") or item.get("name"),
            lat=point.get("lat"),
            lon=point.get("lon"),
        )

    if cache:
        cache.set(cache_key, result.__dict__)
    return result

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.modules.zephyrus.module import ZephyrusModule


def _mock_response(data: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = data
    return response


@pytest.fixture
async def zephyrus():
    module = ZephyrusModule()
    await module.setup({"default_location": "London", "units": "metric"})
    yield module
    await module.teardown()


@pytest.mark.asyncio
async def test_geocode_and_forecast(zephyrus):
    geocode_response = _mock_response(
        {
            "results": [
                {
                    "name": "London",
                    "latitude": 51.5,
                    "longitude": -0.12,
                    "admin1": "England",
                    "country": "United Kingdom",
                }
            ]
        }
    )
    forecast_response = _mock_response(
        {
            "current": {
                "temperature_2m": 18.5,
                "relative_humidity_2m": 65,
                "weather_code": 3,
                "wind_speed_10m": 12.0,
                "time": "2025-06-23T12:00",
            }
        }
    )

    async def mock_get(url, params=None):
        if "geocoding" in str(url):
            return geocode_response
        return forecast_response

    assert zephyrus._client is not None
    zephyrus._client.get = AsyncMock(side_effect=mock_get)

    tools = {t.definition.name: t.handler for t in zephyrus.get_tools()}
    result = await tools["zephyrus.get_current_weather"]({"location": "London"})
    data = json.loads(result)

    assert "London" in data["location"]
    assert "18.5" in data["temperature"]


@pytest.mark.asyncio
async def test_multi_day_forecast(zephyrus):
    geocode_response = _mock_response(
        {
            "results": [
                {
                    "name": "Austin",
                    "latitude": 30.27,
                    "longitude": -97.74,
                    "admin1": "Texas",
                    "country": "United States",
                }
            ]
        }
    )
    forecast_response = _mock_response(
        {
            "daily": {
                "time": ["2025-06-23", "2025-06-24", "2025-06-25"],
                "temperature_2m_max": [32.0, 33.0, 31.0],
                "temperature_2m_min": [22.0, 23.0, 21.0],
                "weather_code": [1, 2, 3],
                "precipitation_sum": [0.0, 1.2, 0.5],
            }
        }
    )

    async def mock_get(url, params=None):
        if "geocoding" in str(url):
            return geocode_response
        return forecast_response

    zephyrus._client.get = AsyncMock(side_effect=mock_get)
    tools = {t.definition.name: t.handler for t in zephyrus.get_tools()}
    result = await tools["zephyrus.get_forecast"]({"location": "Austin", "days": 3})
    data = json.loads(result)

    assert "Austin" in data["location"]
    assert len(data["forecast"]) == 3


@pytest.mark.asyncio
async def test_unknown_location_raises(zephyrus):
    empty_response = _mock_response({"results": []})
    zephyrus._client.get = AsyncMock(return_value=empty_response)
    tools = {t.definition.name: t.handler for t in zephyrus.get_tools()}

    with pytest.raises(ValueError, match="Could not find location"):
        await tools["zephyrus.get_current_weather"]({"location": "Nowhereville"})


@pytest.mark.asyncio
async def test_module_metadata(zephyrus):
    assert zephyrus.slug == "zephyrus"
    assert zephyrus.display_name == "Zephyrus"
    assert len(zephyrus.get_tools()) == 2


@pytest.mark.asyncio
async def test_imperial_units():
    module = ZephyrusModule()
    await module.setup({"default_location": "Austin", "units": "imperial"})
    geocode_response = _mock_response(
        {"results": [{"name": "Austin", "latitude": 30.0, "longitude": -97.0, "country": "US"}]}
    )
    forecast_response = _mock_response(
        {"current": {"temperature_2m": 85.0, "relative_humidity_2m": 50, "weather_code": 0, "wind_speed_10m": 5, "time": "t"}}
    )

    async def mock_get(url, params=None):
        if "geocoding" in str(url):
            return geocode_response
        assert params.get("temperature_unit") == "fahrenheit"
        return forecast_response

    module._client.get = AsyncMock(side_effect=mock_get)
    tools = {t.definition.name: t.handler for t in module.get_tools()}
    result = await tools["zephyrus.get_current_weather"]({"location": "Austin"})
    data = json.loads(result)
    assert "°F" in data["temperature"]
    await module.teardown()

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from hestia.core.tools.models import ToolDefinition
from hestia.modules.base import RegisteredTool

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class ZephyrusModule:
    slug = "zephyrus"
    display_name = "Zephyrus"
    domain = "Weather and forecasts"

    def __init__(self) -> None:
        self._default_location = "San Francisco"
        self._units = "metric"
        self._client: httpx.AsyncClient | None = None

    async def setup(self, config: dict[str, Any]) -> None:
        self._default_location = config.get("default_location", self._default_location)
        self._units = config.get("units", self._units)
        self._client = httpx.AsyncClient(timeout=30.0)

    async def teardown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def get_tools(self) -> list[RegisteredTool]:
        return [
            RegisteredTool(
                definition=ToolDefinition(
                    name="zephyrus.get_current_weather",
                    description="Get current weather for a location (city name or coordinates).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name, e.g. 'London' or 'San Francisco'",
                            },
                        },
                        "required": ["location"],
                    },
                ),
                handler=self._get_current_weather,
            ),
            RegisteredTool(
                definition=ToolDefinition(
                    name="zephyrus.get_forecast",
                    description="Get a multi-day weather forecast for a location.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name, e.g. 'London'",
                            },
                            "days": {
                                "type": "integer",
                                "description": "Number of forecast days (1-7)",
                                "minimum": 1,
                                "maximum": 7,
                            },
                        },
                        "required": ["location"],
                    },
                ),
                handler=self._get_forecast,
            ),
        ]

    async def _geocode(self, location: str) -> tuple[float, float, str]:
        assert self._client is not None
        response = await self._client.get(
            GEOCODING_URL,
            params={"name": location, "count": 1, "language": "en", "format": "json"},
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results") or []
        if not results:
            raise ValueError(f"Could not find location: {location}")
        place = results[0]
        name = place.get("name", location)
        admin = place.get("admin1", "")
        country = place.get("country", "")
        label = ", ".join(p for p in [name, admin, country] if p)
        return place["latitude"], place["longitude"], label

    def _unit_params(self) -> dict[str, str]:
        if self._units == "imperial":
            return {
                "temperature_unit": "fahrenheit",
                "windspeed_unit": "mph",
                "precipitation_unit": "inch",
            }
        return {
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        }

    async def _get_current_weather(self, args: dict[str, Any]) -> str:
        location = args.get("location") or self._default_location
        lat, lon, label = await self._geocode(location)
        assert self._client is not None
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            **self._unit_params(),
        }
        response = await self._client.get(FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()
        current = data.get("current", {})
        temp_unit = "°F" if self._units == "imperial" else "°C"
        result = {
            "location": label,
            "temperature": f"{current.get('temperature_2m')}{temp_unit}",
            "humidity": f"{current.get('relative_humidity_2m')}%",
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "time": current.get("time"),
        }
        return json.dumps(result)

    async def _get_forecast(self, args: dict[str, Any]) -> str:
        location = args.get("location") or self._default_location
        days = min(max(int(args.get("days", 3)), 1), 7)
        lat, lon, label = await self._geocode(location)
        assert self._client is not None
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
            "forecast_days": days,
            **self._unit_params(),
        }
        response = await self._client.get(FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()
        daily = data.get("daily", {})
        temp_unit = "°F" if self._units == "imperial" else "°C"
        forecast_days = []
        dates = daily.get("time", [])
        for i, date in enumerate(dates):
            forecast_days.append(
                {
                    "date": date,
                    "high": f"{daily['temperature_2m_max'][i]}{temp_unit}",
                    "low": f"{daily['temperature_2m_min'][i]}{temp_unit}",
                    "precipitation": daily["precipitation_sum"][i],
                    "weather_code": daily["weather_code"][i],
                }
            )
        result = {"location": label, "forecast": forecast_days}
        return json.dumps(result)

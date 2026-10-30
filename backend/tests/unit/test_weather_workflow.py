"""The weather workflow, with the Open-Meteo HTTP calls stubbed out."""

from typing import Any

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.domain.models import Reply, Step
from app.workflows import weather
from app.workflows.fake_llm import FakeChatModel
from app.workflows.weather import WeatherWorkflow, get_forecast

GEO = {"results": [{"name": "Utrecht", "country": "Netherlands", "latitude": 52.1, "longitude": 5.1}]}
CURRENT = {
    "current": {
        "time": "2026-10-30T12:00",
        "temperature_2m": 14.0,
        "apparent_temperature": 12.5,
        "relative_humidity_2m": 70,
        "wind_speed_10m": 11.0,
        "weather_code": 3,
    }
}
DAILY = {
    "daily": {
        "time": ["2026-10-30", "2026-10-31"],
        "temperature_2m_min": [6.0, 7.0],
        "temperature_2m_max": [14.0, 12.0],
        "precipitation_probability_max": [10, 80],
        "weather_code": [3, 63],
    }
}


def stub_http(monkeypatch: pytest.MonkeyPatch, geo: dict[str, Any]) -> None:
    def fake_get(url: str, params: dict[str, Any], timeout: int) -> httpx.Response:
        if url == weather.GEOCODE_URL:
            body = geo
        else:
            body = DAILY if "daily" in params else CURRENT
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(weather.httpx, "get", fake_get)


def test_agent_calls_the_tool_and_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_http(monkeypatch, GEO)
    workflow = WeatherWorkflow(FakeChatModel(), InMemorySaver())
    *steps, reply = workflow.stream("w1", "Do I need an umbrella in Utrecht?")
    assert [s.text for s in steps if isinstance(s, Step)] == [
        "Calling `get_current_weather(city='Utrecht')`",
        "`get_current_weather` returned data",
    ]
    assert isinstance(reply, Reply)
    assert "overcast" in reply.text


def test_unknown_city_is_reported_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_http(monkeypatch, {"results": []})
    *steps, reply = WeatherWorkflow(FakeChatModel(), InMemorySaver()).stream("w2", "Weather in Paris?")
    assert "`get_current_weather` failed" in [s.text for s in steps if isinstance(s, Step)]
    assert isinstance(reply, Reply)
    assert "Could not find" in reply.text


def test_forecast_tool_maps_days(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_http(monkeypatch, GEO)
    result = get_forecast.invoke({"city": "Utrecht", "days": 2})
    assert result["location"] == "Utrecht, Netherlands"
    assert result["days"][1] == {
        "date": "2026-10-31",
        "min_c": 7.0,
        "max_c": 12.0,
        "rain_chance_pct": 80,
        "conditions": "rain",
    }

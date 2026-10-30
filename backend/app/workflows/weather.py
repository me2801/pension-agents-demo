"""Weather agent: a tool-calling chat agent.

LangChain supplies the building blocks (chat model, tools, messages);
LangGraph wires them into a stateful agent loop:

    START -> agent --(tool calls?)--> tools -> agent -> ... -> END

Weather data comes from Open-Meteo (free, no API key needed).
"""

from collections.abc import Iterator
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.domain.models import Reply, Step
from app.workflows.base import ChatWorkflow

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT_S = 10

# Subset of the WMO weather interpretation codes used by Open-Meteo.
WMO_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "light showers",
    81: "showers",
    82: "violent showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "severe thunderstorm with hail",
}

SYSTEM_PROMPT = (
    "You are a friendly weather assistant. Use the tools to look up real data; "
    "never guess the weather. Keep answers short and practical "
    "(e.g. whether to bring an umbrella or a jacket)."
)


def _geocode(city: str) -> dict[str, Any]:
    """Resolve a city name to coordinates. Raises ValueError if not found."""
    resp = httpx.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    results: list[dict[str, Any]] | None = resp.json().get("results")
    if not results:
        raise ValueError(f"Could not find a location named '{city}'.")
    return results[0]


def _fetch_forecast(loc: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Call the Open-Meteo forecast API for a geocoded location."""
    resp = httpx.get(
        FORECAST_URL,
        params={"latitude": loc["latitude"], "longitude": loc["longitude"], "timezone": "auto", **params},
        timeout=HTTP_TIMEOUT_S,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data


def _location_label(loc: dict[str, Any]) -> str:
    """Human-readable 'City, Country' label."""
    return f"{loc['name']}, {loc.get('country', '')}"


# Tools: the docstring + type hints become the tool schema the model sees, so write them for the model.


@tool
def get_current_weather(city: str) -> dict[str, Any]:
    """Get the current weather for a city (temperature in °C, wind in km/h)."""
    loc = _geocode(city)
    fields = "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
    current = _fetch_forecast(loc, {"current": fields})["current"]
    return {
        "location": _location_label(loc),
        "time": current["time"],
        "temperature_c": current["temperature_2m"],
        "feels_like_c": current["apparent_temperature"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_kmh": current["wind_speed_10m"],
        "conditions": WMO_CODES.get(current["weather_code"], "unknown"),
    }


@tool
def get_forecast(city: str, days: int = 3) -> dict[str, Any]:
    """Get a daily weather forecast for a city for the next 1-7 days."""
    loc = _geocode(city)
    fields = "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
    daily = _fetch_forecast(loc, {"daily": fields, "forecast_days": max(1, min(days, 7))})["daily"]
    return {
        "location": _location_label(loc),
        "days": [
            {
                "date": date,
                "min_c": daily["temperature_2m_min"][i],
                "max_c": daily["temperature_2m_max"][i],
                "rain_chance_pct": daily["precipitation_probability_max"][i],
                "conditions": WMO_CODES.get(daily["weather_code"][i], "unknown"),
            }
            for i, date in enumerate(daily["time"])
        ],
    }


TOOLS = [get_current_weather, get_forecast]


def _steps_for(message: BaseMessage) -> list[Step]:
    """Progress steps to show for a message produced by the graph."""
    if isinstance(message, AIMessage) and message.tool_calls:
        return [
            Step(text=f"Calling `{call['name']}({', '.join(f'{k}={v!r}' for k, v in call['args'].items())})`")
            for call in message.tool_calls
        ]
    if isinstance(message, ToolMessage):
        outcome = "failed" if message.status == "error" else "returned data"
        return [Step(text=f"`{message.name}` {outcome}")]
    return []


class WeatherWorkflow(ChatWorkflow):
    """Claude decides when to look up current weather or a forecast."""

    id = "weather"
    name = "Weather agent"
    description = (
        "A tool-calling agent: Claude decides when to look up current weather or a forecast. "
        "The simplest LangGraph loop (agent -> tools -> agent)."
    )
    input_hint = "Ask about the weather anywhere"
    examples = {
        "Umbrella in Utrecht?": "Do I need an umbrella in Utrecht tomorrow?",
        "Amsterdam vs Barcelona": "Compare the weather in Amsterdam and Barcelona right now.",
        "Weekend in Paris": "What's the forecast for Paris for the next 5 days?",
    }

    def __init__(self, llm: BaseChatModel, checkpointer: BaseCheckpointSaver[Any]):
        self._llm = llm.bind_tools(TOOLS)
        builder = StateGraph(MessagesState)
        builder.add_node("agent", self._call_model)
        # handle_tool_errors: a failing tool (e.g. unknown city) is reported back to the model.
        builder.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", tools_condition)  # -> "tools" if tool calls, else END
        builder.add_edge("tools", "agent")
        self._graph = builder.compile(checkpointer=checkpointer)

    def _call_model(self, state: MessagesState) -> dict[str, list[BaseMessage]]:
        """Agent node: let the model answer or decide which tools to call."""
        response = self._llm.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    def stream(self, thread_id: str, message: str) -> Iterator[Step | Reply]:
        """Run the agent loop for one user message, yielding tool activity as steps."""
        config = RunnableConfig(configurable={"thread_id": thread_id})
        answer = ""
        for update in self._graph.stream({"messages": [HumanMessage(message)]}, config, stream_mode="updates"):
            for payload in update.values():
                for msg in payload["messages"]:
                    yield from _steps_for(msg)
                    if isinstance(msg, AIMessage) and not msg.tool_calls:
                        answer = str(msg.text)
        yield Reply(text=answer)

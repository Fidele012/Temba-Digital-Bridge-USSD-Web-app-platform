"""
Temba Water AI Chatbot Service
Uses Mistral AI (mistral-small-latest) — free tier at console.mistral.ai, no credit card.
OpenAI-compatible API called directly via httpx.
"""
import json
import logging
import os
from typing import Any

import httpx

from .knowledge_base import SYSTEM_PROMPT, is_water_related

logger = logging.getLogger(__name__)

_tavily_available: bool = True

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# ─── Tool definitions (OpenAI / Mistral format) ───────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "find_water_providers",
            "description": (
                "Search registered water service providers on the Temba platform. "
                "Call this IMMEDIATELY whenever the user asks to find, list, or search for "
                "water providers — even if no district is specified (pass empty string to get all). "
                "Returns provider names, contacts, services, and district coverage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "Rwanda district name (e.g. 'Gasabo', 'Huye'). Leave empty to get all.",
                    },
                    "service_type": {
                        "type": "string",
                        "description": "Optional filter: e.g. 'water_supply', 'truck_delivery'",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_providers",
            "description": (
                "Search the web for water service providers or water-related information "
                "not available in the Temba database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'water service providers in Rubavu Rwanda'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_report_action",
            "description": (
                "Trigger the 'File a Report' form on the Temba platform for the user. "
                "Use when the user confirms they want to report a water issue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "description": "Type: 'contamination', 'no_supply', 'pipe_burst', 'low_pressure', 'meter_problem', 'billing', 'other'",
                    },
                    "suggested_priority": {
                        "type": "string",
                        "enum": ["P1", "P2", "P3"],
                        "description": "P1=emergency, P2=urgent, P3=standard",
                    },
                },
                "required": ["issue_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment_action",
            "description": "Trigger the 'Book Appointment' flow on the Temba platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider_id": {"type": "string", "description": "Provider ID if known"},
                    "provider_name": {"type": "string", "description": "Provider name"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_service_action",
            "description": "Trigger the 'Request Service' form on the Temba platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "description": "Service: 'new_connection', 'truck_delivery', 'tank_installation', 'meter_support', 'inspection', 'other'",
                    }
                },
                "required": ["service_type"],
            },
        },
    },
]


# ─── Mistral REST call ────────────────────────────────────────────────────────

async def _mistral_chat(messages: list[dict], api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "mistral-small-latest",
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": 700,
        "temperature": 0.5,
    }
    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.post(MISTRAL_URL, json=body, headers=headers)
        if not resp.is_success:
            logger.error("Mistral API error %s: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
        return resp.json()


# ─── Tool execution ───────────────────────────────────────────────────────────

async def _execute_find_providers(
    district: str = "",
    service_type: str = "",
    api_base: str = "",
) -> str:
    try:
        params: dict[str, Any] = {"size": 50}
        if district:
            params["district"] = district
        if service_type:
            params["service_type"] = service_type

        base = api_base or os.getenv("API_BASE_URL", "http://localhost:8000")
        url = f"{base}/api/v1/providers"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return f"Could not retrieve providers (status {resp.status_code})."
            data = resp.json()

        providers = data.get("items", data) if isinstance(data, dict) else data
        if not providers:
            return (
                "No providers found on the Temba platform"
                + (f" in {district}" if district else "")
                + ". Try web_search_providers for unlisted operators."
            )

        lines = [f"Found {len(providers)} registered provider(s) on Temba:"]
        for p in providers[:10]:
            name = p.get("name") or p.get("organization_name", "Unknown")
            phone = p.get("phone") or p.get("phone_number", "N/A")
            email = p.get("email", "N/A")
            districts = p.get("districts_served") or p.get("district", "")
            services = p.get("services_offered") or p.get("service_types", "")
            lines.append(
                f"- {name} | Phone: {phone} | Email: {email}"
                + (f" | Districts: {districts}" if districts else "")
                + (f" | Services: {services}" if services else "")
            )
        return "\n".join(lines)

    except Exception as exc:
        logger.warning("find_providers failed: %s", exc)
        return "Provider database lookup failed. Try web_search_providers."


async def _execute_web_search(query: str) -> str:
    global _tavily_available
    if not _tavily_available:
        return "Web search is unavailable."

    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        _tavily_available = False
        return "Web search is not configured."

    try:
        from tavily import AsyncTavilyClient  # type: ignore

        client = AsyncTavilyClient(api_key=tavily_key)
        result = await client.search(
            query=f"Rwanda water {query}",
            search_depth="basic",
            max_results=5,
            include_answer=True,
        )

        parts = []
        if result.get("answer"):
            parts.append(f"Summary: {result['answer']}")
        for r in result.get("results", [])[:4]:
            title = r.get("title", "")
            content = r.get("content", "")[:300]
            url = r.get("url", "")
            parts.append(f"• {title}: {content}... [{url}]")
        return "\n".join(parts) if parts else "No results found."

    except ImportError:
        _tavily_available = False
        return "Web search library not available."
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return f"Web search failed: {exc}"


def _execute_platform_action(tool_name: str, tool_input: dict) -> dict:
    action_map = {
        "file_report_action": "file_report",
        "book_appointment_action": "book_appointment",
        "request_service_action": "request_service",
    }
    return {"action": action_map.get(tool_name, tool_name), "params": tool_input}


# ─── Main chat function ───────────────────────────────────────────────────────

async def chat(
    message: str,
    history: list[dict[str, str]],
    api_base: str = "",
) -> dict[str, Any]:
    if len(message.strip()) > 8 and not is_water_related(message):
        lang = _detect_language(message)
        return {"reply": _off_topic_reply(lang), "action": None, "language": lang}

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable not set")

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-10:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    platform_action: dict | None = None

    for _ in range(5):
        result = await _mistral_chat(messages, api_key)
        choice = result["choices"][0]
        finish_reason = choice.get("finish_reason", "stop")
        msg = choice["message"]

        if finish_reason == "stop":
            return {
                "reply": msg.get("content") or "",
                "action": platform_action,
                "language": _detect_language(message),
            }

        if finish_reason == "tool_calls":
            tool_calls = msg.get("tool_calls") or []

            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_input = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    tool_input = {}

                if tool_name in ("file_report_action", "book_appointment_action", "request_service_action"):
                    platform_action = _execute_platform_action(tool_name, tool_input)
                    result_content = f"Platform action '{platform_action['action']}' will be triggered."

                elif tool_name == "find_water_providers":
                    result_content = await _execute_find_providers(
                        district=tool_input.get("district", ""),
                        service_type=tool_input.get("service_type", ""),
                        api_base=api_base,
                    )

                elif tool_name == "web_search_providers":
                    result_content = await _execute_web_search(query=tool_input.get("query", ""))

                else:
                    result_content = f"Unknown tool: {tool_name}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_content,
                })

            continue

        break

    try:
        final = result["choices"][0]["message"].get("content") or ""
    except Exception:
        final = ""
    return {
        "reply": final or "I'm having trouble right now. Please try again.",
        "action": platform_action,
        "language": _detect_language(message),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _detect_language(text: str) -> str:
    rw_tokens = {
        "amazi", "mazi", "umuyoboro", "ndi", "niki", "bite", "murakoze",
        "yego", "oya", "ndashaka", "nshaka", "nsaba", "nasaba", "gusaba",
        "ikibazo", "serivisi", "akarere", "intara", "ubusarabishe", "raporo",
        "randevu", "kohereza", "muraho", "mwaramutse", "amakuru", "gute",
        "nshobora", "gufasha", "batanga", "batoa", "umutoa", "abatoa",
        "urutonde", "gutuza", "kugenzura", "yanduye", "kunywa", "kubaza",
        "inkono", "tanki", "ipompe", "inzitizi", "imyuka", "ubushyuhe",
    }
    tokens = set(text.lower().split())
    return "rw" if tokens & rw_tokens else "en"


def _off_topic_reply(lang: str) -> str:
    if lang == "rw":
        return (
            "Ndi Umufasha w'Amazi wa Temba kandi nshobora gusa gufasha "
            "mu bibazo bijyanye n'amazi na serivisi z'amazi. Ku bibazo ibindi, "
            "nyamuneka watumanahire kuri:\n\n"
            "tembadigitalbridge@gmail.com"
        )
    return (
        "I'm Temba Water Assistant and I'm only able to help with water-related "
        "questions and services. For other enquiries, please contact our support team:\n\n"
        "tembadigitalbridge@gmail.com"
    )

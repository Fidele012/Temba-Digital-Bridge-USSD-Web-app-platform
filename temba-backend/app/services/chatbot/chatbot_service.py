"""
Temba Water AI Chatbot Service
Calls Google Gemini 1.5 Flash directly via REST API (httpx) — no SDK, no compat layer issues.
Free tier: 15 RPM, 1 500 req/day, 1M tokens/day. API key from aistudio.google.com.
"""
import json
import logging
import os
from typing import Any

import httpx

from .knowledge_base import SYSTEM_PROMPT, is_water_related

logger = logging.getLogger(__name__)

_tavily_available: bool = True

GEMINI_URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-1.5-flash:generateContent"
)

# ─── Tool definitions (Gemini function declaration format) ────────────────────

_FUNCTION_DECLARATIONS = [
    {
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
    {
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
    {
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
    {
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
    {
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
]

_GEMINI_TOOLS = [{"functionDeclarations": _FUNCTION_DECLARATIONS}]
_TOOL_CONFIG = {"functionCallingConfig": {"mode": "AUTO"}}


# ─── Gemini REST call ─────────────────────────────────────────────────────────

async def _gemini_generate(contents: list[dict], api_key: str) -> dict:
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "tools": _GEMINI_TOOLS,
        "toolConfig": _TOOL_CONFIG,
        "generationConfig": {"maxOutputTokens": 700, "temperature": 0.5},
    }
    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.post(GEMINI_URL, json=body, params={"key": api_key})
        if not resp.is_success:
            logger.error("Gemini API error %s: %s", resp.status_code, resp.text[:500])
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

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")

    # Build Gemini-format contents (role: "user" | "model")
    contents: list[dict] = []
    for turn in history[-10:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    platform_action: dict | None = None

    for _ in range(5):
        result = await _gemini_generate(contents, api_key)

        candidate = result["candidates"][0]
        resp_parts = candidate["content"]["parts"]

        # Separate text parts from function-call parts
        fn_calls = [p["functionCall"] for p in resp_parts if "functionCall" in p]
        text = " ".join(p.get("text", "") for p in resp_parts if "text" in p).strip()

        if not fn_calls:
            return {
                "reply": text or "I'm having trouble right now. Please try again.",
                "action": platform_action,
                "language": _detect_language(message),
            }

        # Append model turn (including the functionCall parts)
        contents.append({"role": "model", "parts": resp_parts})

        # Execute each tool and collect functionResponse parts
        response_parts = []
        for fc in fn_calls:
            fn_name = fc["name"]
            fn_args = dict(fc.get("args") or {})

            if fn_name in ("file_report_action", "book_appointment_action", "request_service_action"):
                platform_action = _execute_platform_action(fn_name, fn_args)
                fn_result = {"result": f"Platform action '{platform_action['action']}' will be triggered."}

            elif fn_name == "find_water_providers":
                text_out = await _execute_find_providers(
                    district=fn_args.get("district", ""),
                    service_type=fn_args.get("service_type", ""),
                    api_base=api_base,
                )
                fn_result = {"result": text_out}

            elif fn_name == "web_search_providers":
                text_out = await _execute_web_search(query=fn_args.get("query", ""))
                fn_result = {"result": text_out}

            else:
                fn_result = {"result": f"Unknown tool: {fn_name}"}

            response_parts.append({
                "functionResponse": {"name": fn_name, "response": fn_result}
            })

        # Tool results go back as a "user" turn in Gemini's protocol
        contents.append({"role": "user", "parts": response_parts})

    return {
        "reply": "I'm having trouble processing your request right now. Please try again.",
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

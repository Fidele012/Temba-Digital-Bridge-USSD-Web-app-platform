"""
Temba Water AI Chatbot Service
Uses Claude claude-sonnet-5 with tool calling for provider lookup, web search, and platform actions.
"""
import json
import logging
import os
from typing import Any

import anthropic
import httpx

from .knowledge_base import SYSTEM_PROMPT, is_water_related

logger = logging.getLogger(__name__)

# ─── Client singletons ───────────────────────────────────────────────────────

_anthropic_client: anthropic.AsyncAnthropic | None = None
_tavily_available: bool = True


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


# ─── Tool definitions for Claude ─────────────────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "find_water_providers",
        "description": (
            "Search registered water service providers on the Temba platform. "
            "Use when the user asks about providers in a specific district, city, or area. "
            "Returns provider names, contacts, services, and district coverage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "district": {
                    "type": "string",
                    "description": "Rwanda district name (e.g. 'Gasabo', 'Huye', 'Musanze'). "
                    "Leave empty to search all providers.",
                },
                "service_type": {
                    "type": "string",
                    "description": "Optional filter: e.g. 'water_supply', 'truck_delivery', "
                    "'tank_installation', 'plumbing', 'water_testing'",
                },
            },
            "required": [],
        },
    },
    {
        "name": "web_search_providers",
        "description": (
            "Search the web for water service providers, water companies, or water-related "
            "information not available in the Temba database. Use for providers that may not "
            "be registered on Temba but are known to operate in Rwanda."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'water service providers in Rubavu district Rwanda'",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "file_report_action",
        "description": (
            "Trigger the 'File a Report' form on the Temba platform for the user. "
            "Use when the user confirms they want to report a water issue (contamination, "
            "no supply, burst pipe, low pressure, meter problem, billing dispute)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_type": {
                    "type": "string",
                    "description": "Type of issue: 'contamination', 'no_supply', 'pipe_burst', "
                    "'low_pressure', 'meter_problem', 'billing', 'other'",
                },
                "suggested_priority": {
                    "type": "string",
                    "enum": ["P1", "P2", "P3"],
                    "description": "Suggested priority based on described urgency. "
                    "P1=emergency/contamination, P2=urgent, P3=standard",
                },
            },
            "required": ["issue_type"],
        },
    },
    {
        "name": "book_appointment_action",
        "description": (
            "Trigger the 'Book Appointment' flow on the Temba platform. "
            "Use when the user confirms they want to book an appointment with a water service provider."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "provider_id": {
                    "type": "string",
                    "description": "Temba provider ID if known, otherwise empty string",
                },
                "provider_name": {
                    "type": "string",
                    "description": "Provider name the user wants to book with",
                },
            },
            "required": [],
        },
    },
    {
        "name": "request_service_action",
        "description": (
            "Trigger the 'Request Service' form on the Temba platform. "
            "Use when the user confirms they want to request a water service such as "
            "new connection, truck delivery, tank installation, meter support, or inspection."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_type": {
                    "type": "string",
                    "description": "Service type: 'new_connection', 'truck_delivery', "
                    "'tank_installation', 'meter_support', 'inspection', 'other'",
                }
            },
            "required": ["service_type"],
        },
    },
]


# ─── Tool execution ───────────────────────────────────────────────────────────

async def _execute_find_providers(
    district: str = "",
    service_type: str = "",
    api_base: str = "",
) -> str:
    """Call the Temba providers API and return formatted results."""
    try:
        params: dict[str, str | int] = {"size": 50}
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
                f"No providers found on the Temba platform"
                + (f" in {district}" if district else "")
                + ". Try the web_search_providers tool for unlisted operators."
            )

        lines = [f"Found {len(providers)} registered provider(s) on Temba:"]
        for p in providers[:10]:  # Cap at 10 results
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
        return "Provider database lookup failed. Try web_search_providers for more information."


async def _execute_web_search(query: str) -> str:
    """Search the web via Tavily for water provider/topic information."""
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
            include_domains=["wasac.gov.rw", "rura.gov.rw", "mininfra.gov.rw"],
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

        return "\n".join(parts) if parts else "No results found for this query."

    except ImportError:
        _tavily_available = False
        return "Web search library not available."
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return f"Web search failed: {exc}"


def _execute_platform_action(tool_name: str, tool_input: dict) -> dict:
    """Return a structured action signal for platform actions."""
    action_map = {
        "file_report_action": "file_report",
        "book_appointment_action": "book_appointment",
        "request_service_action": "request_service",
    }
    return {
        "action": action_map.get(tool_name, tool_name),
        "params": tool_input,
    }


# ─── Main chat function ───────────────────────────────────────────────────────

async def chat(
    message: str,
    history: list[dict[str, str]],
    api_base: str = "",
) -> dict[str, Any]:
    """
    Process a user message and return AI response with optional platform actions.

    Returns:
        {
            "reply": str,          # Text to display to the user
            "action": dict | None, # Platform action to trigger (if any)
            "language": str,       # Detected language: "en" | "rw"
        }
    """
    # Fast off-topic pre-screen (keeps API calls down for obvious off-topic)
    if len(message.strip()) > 8 and not is_water_related(message):
        lang = _detect_language(message)
        return {
            "reply": _off_topic_reply(lang),
            "action": None,
            "language": lang,
        }

    # Build conversation messages for Claude
    messages: list[dict[str, Any]] = []
    for turn in history[-10:]:  # Keep last 10 turns
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    client = _get_anthropic()
    platform_action: dict | None = None

    # Agentic loop — handle tool calls
    max_iterations = 5
    for _ in range(max_iterations):
        response = await client.messages.create(
            model="claude-sonnet-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
        )

        # Check stop reason
        if response.stop_reason == "end_turn":
            # Extract text reply
            text = _extract_text(response)
            return {
                "reply": text,
                "action": platform_action,
                "language": _detect_language(message),
            }

        if response.stop_reason == "tool_use":
            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input or {}

                # Platform action tools — don't call externally, return action signal
                if tool_name in (
                    "file_report_action",
                    "book_appointment_action",
                    "request_service_action",
                ):
                    platform_action = _execute_platform_action(tool_name, tool_input)
                    result_content = (
                        f"Platform action '{platform_action['action']}' will be triggered "
                        "for the user. Confirm to the user and provide any guidance."
                    )

                elif tool_name == "find_water_providers":
                    result_content = await _execute_find_providers(
                        district=tool_input.get("district", ""),
                        service_type=tool_input.get("service_type", ""),
                        api_base=api_base,
                    )

                elif tool_name == "web_search_providers":
                    result_content = await _execute_web_search(
                        query=tool_input.get("query", "")
                    )

                else:
                    result_content = f"Unknown tool: {tool_name}"

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    }
                )

            # Add assistant turn + tool results to message history
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue  # Next iteration

        # Unexpected stop reason
        break

    # Fallback: extract any text collected so far
    text = _extract_text(response)
    return {
        "reply": text or "I'm having trouble processing your request right now. Please try again.",
        "action": platform_action,
        "language": _detect_language(message),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_text(response: anthropic.types.Message) -> str:
    parts = []
    for block in response.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts).strip()


def _detect_language(text: str) -> str:
    """Simple Kinyarwanda detection via common words."""
    rw_tokens = {
        "amazi", "umuyoboro", "ndi", "niki", "bite", "murakoze", "yego", "oya",
        "ndashaka", "nsaba", "ikibazo", "serivisi", "akarere", "intara",
        "ubusarabishe", "raporo", "randevu", "kohereza", "gusaba",
    }
    tokens = set(text.lower().split())
    return "rw" if tokens & rw_tokens else "en"


def _off_topic_reply(lang: str) -> str:
    if lang == "rw":
        return (
            "Ndi Umufasha w'Amazi wa Temba kandi nshobora gusa gufasha "
            "mu bibazo bijyanye n'amazi na serivisi z'amazi. Ku bibazo ibindi, "
            "nyamuneka watumanahire kuri:\n\n"
            "📧 tembadigitalbridge@gmail.com\n\n"
            "Bazakunsanga ubufasha bwose."
        )
    return (
        "I'm Temba Water Assistant and I'm only able to help with water-related "
        "questions and services. For other enquiries, please contact our support team:\n\n"
        "📧 tembadigitalbridge@gmail.com\n\n"
        "They'll be happy to assist you."
    )

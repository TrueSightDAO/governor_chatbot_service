"""OpenAI-compatible client for Kimi (Moonshot AI)."""
from __future__ import annotations

import json
from typing import Any

import httpx

from .config import settings


class KimiClientError(Exception):
    pass


class KimiClient:
    def __init__(self) -> None:
        if not settings.kimi_api_key:
            raise KimiClientError("KIMI_API_KEY is not set.")
        self.base_url = settings.kimi_base_url.rstrip("/")
        self.api_key = settings.kimi_api_key
        self.model = settings.kimi_model
        self.max_tokens = settings.kimi_max_tokens
        self.temperature = settings.kimi_temperature

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request to Kimi."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            raise KimiClientError(f"Kimi API error {exc.response.status_code}: {body}") from exc
        except httpx.RequestError as exc:
            raise KimiClientError(f"Kimi request failed: {exc}") from exc

    def extract_response_text(self, completion: dict[str, Any]) -> str:
        """Extract the assistant message text from a completion response."""
        choices = completion.get("choices", [])
        if not choices:
            return "(no response)"
        message = choices[0].get("message", {})
        return message.get("content", "") or "(empty response)"

    def extract_tool_calls(self, completion: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool_calls from a completion response."""
        choices = completion.get("choices", [])
        if not choices:
            return []
        message = choices[0].get("message", {})
        return message.get("tool_calls", []) or []


# Default tool schemas for Phase 2+
def get_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read_context_file",
                "description": "Read a file from the agentic_ai_context repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path inside agentic_ai_context, e.g. 'WORKSPACE_CONTEXT.md'",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_repo_file",
                "description": "Read a file from a GitHub repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {
                            "type": "string",
                            "description": "GitHub repo name under TrueSightDAO, e.g. 'tokenomics'",
                        },
                        "path": {"type": "string", "description": "File path in the repo."},
                        "ref": {
                            "type": "string",
                            "description": "Branch or commit. Default: main",
                            "default": "main",
                        },
                    },
                    "required": ["repo", "path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_dao_submission",
                "description": "Compile and submit a [CONTRIBUTION EVENT] to Edgar for AI agent work.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short one-line title."},
                        "body": {"type": "string", "description": "Multi-line description with what changed and why."},
                        "pr_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "At least one https://github.com/TrueSightDAO/.../pull/N URL.",
                        },
                        "contributors": {
                            "type": "string",
                            "description": "Display name. Defaults to EMAIL local-part.",
                        },
                        "amount": {"type": "string", "default": "0"},
                        "tdg_issued": {"type": "string", "default": "0"},
                    },
                    "required": ["title", "body", "pr_urls"],
                },
            },
        },
    ]

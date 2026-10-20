"""Bridge: route litellm.completion(model="claude-code/<alias>") through `claude -p` headless subprocess.

Lets PageIndex (and any other litellm-based tool) reuse the user's Claude Code OAuth
subscription instead of requiring an Anthropic API key. No API key is read or required.

Model name format: `claude-code/<alias>` where <alias> is haiku / sonnet / opus / a full model ID.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Any, Iterator

from litellm import CustomLLM
from litellm.types.utils import (
    Choices,
    Message,
    ModelResponse,
    Usage,
)

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
DEFAULT_TIMEOUT_SEC = int(os.environ.get("CLAUDE_CODE_TIMEOUT", "180"))
DEFAULT_SYSTEM_PROMPT = (
    "You are a precise document analysis assistant. "
    "Follow the user's instructions exactly. Do not add commentary."
)
# Cap simultaneous `claude -p` subprocesses (PageIndex fans out via asyncio.gather).
MAX_CONCURRENT = int(os.environ.get("CLAUDE_CODE_MAX_CONCURRENT", "4"))
_SUBPROCESS_SLOTS = threading.Semaphore(MAX_CONCURRENT)


def _messages_to_prompt(messages: list[dict]) -> tuple[str, str]:
    """Split messages into (system_prompt, stdin_payload).

    PageIndex always sends a single user turn with no chat_history (see utils.llm_completion),
    but we handle multi-turn defensively.
    """
    system_parts: list[str] = []
    convo_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            convo_parts.append(f"[Assistant]\n{content}")
        else:
            convo_parts.append(content if not convo_parts else f"[User]\n{content}")
    system_prompt = "\n\n".join(system_parts) if system_parts else DEFAULT_SYSTEM_PROMPT
    payload = "\n\n".join(convo_parts).strip() or "(empty user message)"
    return system_prompt, payload


def _strip_provider_prefix(model: str) -> str:
    return model.removeprefix("claude-code/").strip() or "haiku"


def _invoke_claude(model_alias: str, system_prompt: str, payload: str, timeout: int) -> dict:
    # Slim flags: PageIndex prompts are pure text completion — no tools, MCP servers,
    # hooks, or project-memory context needed. Without these, every call pays ~4s extra
    # startup and ~26k tokens of system-prompt overhead against the user's quota.
    # NOTE: do NOT use --bare here — it disables OAuth auth, which this bridge relies on.
    cmd = [
        CLAUDE_BIN,
        "-p",
        "--model",
        model_alias,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--tools",
        "",
        "--setting-sources",
        "",
        "--system-prompt",
        system_prompt,
    ]
    with _SUBPROCESS_SLOTS:
        completed = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            # Neutral cwd so headless runs never pick up project-level Claude Code config.
            cwd=tempfile.gettempdir(),
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {completed.returncode}): "
            f"stderr={completed.stderr.strip()!r} stdout={completed.stdout[:500]!r}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude CLI returned non-JSON output: {completed.stdout[:500]!r}"
        ) from exc


def _to_model_response(claude_json: dict, requested_model: str) -> ModelResponse:
    text = claude_json.get("result", "") or ""
    usage_in = claude_json.get("usage", {}) or {}
    prompt_tokens = (
        (usage_in.get("input_tokens") or 0)
        + (usage_in.get("cache_read_input_tokens") or 0)
        + (usage_in.get("cache_creation_input_tokens") or 0)
    )
    completion_tokens = usage_in.get("output_tokens") or 0
    return ModelResponse(
        id=f"claude-code-{claude_json.get('session_id', uuid.uuid4().hex[:12])}",
        choices=[
            Choices(
                finish_reason="stop"
                if claude_json.get("stop_reason") == "end_turn"
                else (claude_json.get("stop_reason") or "stop"),
                index=0,
                message=Message(content=text, role="assistant"),
            )
        ],
        created=int(time.time()),
        model=requested_model,
        object="chat.completion",
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


class ClaudeCodeLLM(CustomLLM):
    """litellm CustomLLM that shells out to `claude -p`."""

    def completion(self, *args, **kwargs) -> ModelResponse:
        model = kwargs.get("model") or (args[0] if args else "")
        messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
        timeout = int(kwargs.get("timeout") or DEFAULT_TIMEOUT_SEC)

        model_alias = _strip_provider_prefix(model)
        system_prompt, payload = _messages_to_prompt(messages)
        claude_json = _invoke_claude(model_alias, system_prompt, payload, timeout)
        return _to_model_response(claude_json, model)

    async def acompletion(self, *args, **kwargs) -> ModelResponse:
        # PageIndex fans out node summaries / title checks via asyncio.gather — running
        # the subprocess in a worker thread keeps the event loop free so those calls
        # actually parallelize (bounded by _SUBPROCESS_SLOTS).
        return await asyncio.to_thread(self.completion, *args, **kwargs)

    def streaming(self, *args, **kwargs) -> Iterator[Any]:
        raise NotImplementedError("claude-code provider does not support streaming")

    async def astreaming(self, *args, **kwargs) -> Iterator[Any]:
        raise NotImplementedError("claude-code provider does not support streaming")


_REGISTERED = False


def register_claude_code() -> None:
    """Idempotently install the claude-code provider into litellm's custom provider map."""
    global _REGISTERED
    if _REGISTERED:
        return
    import litellm

    handler = ClaudeCodeLLM()
    existing = list(getattr(litellm, "custom_provider_map", []) or [])
    existing = [p for p in existing if p.get("provider") != "claude-code"]
    existing.append({"provider": "claude-code", "custom_handler": handler})
    litellm.custom_provider_map = existing
    _REGISTERED = True


if __name__ == "__main__":
    # Standalone smoke test: python claude_code_provider.py
    import sys

    register_claude_code()
    import litellm  # noqa: E402

    response = litellm.completion(
        model="claude-code/haiku",
        messages=[{"role": "user", "content": "Reply with exactly: PAGEINDEX_BRIDGE_OK"}],
    )
    print(response.choices[0].message.content)
    sys.exit(0 if "PAGEINDEX_BRIDGE_OK" in response.choices[0].message.content else 1)

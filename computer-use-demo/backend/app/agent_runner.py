from __future__ import annotations

import asyncio
import json
import uuid
from asyncio import Queue
from dataclasses import dataclass
from typing import Any, Callable

from anthropic.types.beta import BetaContentBlockParam

from computer_use_demo.loop import (
    APIProvider,
    sampling_loop,
)
from computer_use_demo.tools import ToolResult, ToolVersion

from .db import upsert_message


@dataclass
class StreamEvent:
    event: str
    data: dict[str, Any]


class AgentSession:
    def __init__(
        self,
        session_id: str,
        model: str,
        tool_version: ToolVersion,
        api_key: str,
        system_prompt_suffix: str = "",
        provider: APIProvider = APIProvider.ANTHROPIC,
    ) -> None:
        self.session_id = session_id
        self.model = model
        self.tool_version = tool_version
        self.api_key = api_key
        self.system_prompt_suffix = system_prompt_suffix
        self.provider = provider
        self.messages: list[dict[str, Any]] = []
        self.queue: Queue[StreamEvent] = Queue()
        self.lock = asyncio.Lock()

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        await self.queue.put(StreamEvent(event=event, data=data))

    async def add_user_message(self, content: str) -> None:
        message_id = str(uuid.uuid4())
        msg = {
            "id": message_id,
            "role": "user",
            "content": [{"type": "text", "text": content}],
        }
        self.messages.append(msg)
        await upsert_message(message_id, self.session_id, "user", msg)
        await self._emit("message", msg)

    async def run_once(self) -> None:
        async with self.lock:
            async def on_output(block: BetaContentBlockParam) -> None:
                await self._emit("assistant_chunk", {"block": block})

            async def on_tool_output(result: ToolResult, tool_id: str) -> None:  # type: ignore[override]
                payload = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "output": result.output,
                    "error": result.error,
                    "has_image": bool(result.base64_image),
                }
                # persist as a tool message
                message_id = str(uuid.uuid4())
                tool_msg = {
                    "id": message_id,
                    "role": "tool",
                    "content": [payload],
                }
                await upsert_message(message_id, self.session_id, "tool", tool_msg)
                await self._emit("message", tool_msg)

            async def on_api_response(req, res, err):  # noqa: ANN001
                await self._emit(
                    "http_exchange",
                    {
                        "request": str(req),
                        "status": getattr(res, "status_code", None),
                        "error": str(err) if err else None,
                    },
                )

            # run a single assistant turn
            new_messages = await sampling_loop(
                system_prompt_suffix=self.system_prompt_suffix,
                model=self.model,
                provider=self.provider,
                messages=self.messages,
                output_callback=lambda block: asyncio.create_task(on_output(block)),
                tool_output_callback=lambda result, tool_id: asyncio.create_task(
                    on_tool_output(result, tool_id)
                ),
                api_response_callback=lambda req, res, err: asyncio.create_task(
                    on_api_response(req, res, err)
                ),
                api_key=self.api_key,
                tool_version=self.tool_version,
                max_tokens=4096,
            )

            # Persist the assistant message (the last message added by sampling_loop)
            if new_messages and new_messages[-1]["role"] == "assistant":
                assistant = new_messages[-1]
                message_id = str(uuid.uuid4())
                await upsert_message(message_id, self.session_id, "assistant", assistant)
                await self._emit("message", {"id": message_id, **assistant})
            self.messages = new_messages

    async def sse_iter(self):
        while True:
            event = await self.queue.get()
            payload = f"event: {event.event}\n" f"data: {json.dumps(event.data)}\n\n"
            yield payload



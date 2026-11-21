"""FinPilot LLM agent: streaming tool-use loop with PII redaction.

Events yielded to the UI:
  {"type": "mode", "mode": "live" | "offline"}
  {"type": "text", "text": "..."}                 streamed answer (PII restored)
  {"type": "tool", "name", "label", "input", "hisob"}   deterministic computation that backs the answer
  {"type": "action", "action": {...}}             a prepared action awaiting confirmation (or auto-executed)
  {"type": "error", "message": "..."}
  {"type": "done", "redacted_payload": [...]}
"""
import json
import logging
import uuid
from collections import OrderedDict

import anthropic

from app import db, services
from app.agent.offline import offline_answer
from app.agent.tools import TOOL_LABELS, TOOLS, ToolInputError, run_tool
from app.config import settings
from app.security.pii import Redactor, StreamRestorer

log = logging.getLogger("finpilot.agent")

SYSTEM_PROMPT = """You are FinPilot, an AI financial agent embedded in a bank's mobile app in Uzbekistan.
You help a customer (a person or a small business) save money, earn on idle cash and reduce debt cost.

Rules:
- Always answer in Uzbek (Latin script). Be concise and concrete: short paragraphs or "- " bullet lists, **bold** for key numbers.
- Every number you state (amounts, rates, dates, scores) must come from a tool result in this conversation. Never estimate or invent numbers. If a needed number is not available from tools, say so.
- Format money like "89 000 so'm" (space as thousands separator). Rates as "17%".
- To act, call prepare_action. You can only PREPARE actions; the user confirms them in the app, or the bank's autonomy policy executes them. Never say an action is done unless prepare_action returned status "executed".
- Personal data is replaced with tokens such as [ISM_1], [KARTA_1], [TEL_1], [EMAIL_1]. Use these tokens verbatim where needed (e.g. in letters); never try to guess the real values.
- Mention rule IDs (R1-R5) only briefly; explain in plain words what they mean for the user.
- When writing a letter, output only the letter text ready to copy (with subject line), no extra commentary before it.
"""

MAX_TURNS = 6


class Conversation:
    def __init__(self, pid: str):
        p = services.profile(pid)
        self.pid = pid
        self.messages: list[dict] = []
        self.redactor = Redactor(p["sensitive_names"])
        self.last_payload: list[dict] = []


_conversations: "OrderedDict[str, Conversation]" = OrderedDict()
last_payload_by_profile: dict[str, list[dict]] = {}


def get_conversation(conv_id: str | None, pid: str) -> tuple[str, Conversation]:
    if conv_id and conv_id in _conversations and _conversations[conv_id].pid == pid:
        _conversations.move_to_end(conv_id)
        return conv_id, _conversations[conv_id]
    conv_id = uuid.uuid4().hex[:12]
    _conversations[conv_id] = Conversation(pid)
    while len(_conversations) > 100:
        _conversations.popitem(last=False)
    return conv_id, _conversations[conv_id]


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=120)


async def run_agent(pid: str, user_message: str, intent: str | None, conv_id: str | None, ctx: dict):
    conv_id, conv = get_conversation(conv_id, pid)
    ctx = {**ctx, "today": settings.today().isoformat()}
    db.audit(pid, "agent", "agent.query", {"conversation": conv_id, "intent": intent or "chat",
                                          "question": conv.redactor.redact(user_message)[:200]})

    if not settings.ai_enabled:
        yield {"type": "mode", "mode": "offline", "conversation_id": conv_id}
        async for ev in offline_answer(pid, user_message, intent, ctx, conv):
            yield ev
        return

    yield {"type": "mode", "mode": "live", "conversation_id": conv_id}
    snapshot = len(conv.messages)  # restore point if the API fails mid-turn
    redacted_question = conv.redactor.redact(user_message)
    conv.messages.append({"role": "user", "content": redacted_question})
    conv.last_payload = [{"role": "user", "content": redacted_question}]
    s = db.get_settings(pid)
    p = services.profile(pid)
    system = SYSTEM_PROMPT + (f"\nContext: profile type = {p['kind']} ({'person' if p['kind'] == 'personal' else 'pharmacy business'}); "
                              f"today = {ctx['today']}; autonomy level = {s['autonomy']}, auto limit = {s['auto_limit']} so'm.")
    client = _client()

    try:
        for _turn in range(MAX_TURNS):
            restorer = StreamRestorer(conv.redactor)
            json_retries = 0
            while True:
                try:
                    async with client.beta.messages.stream(
                        model=settings.claude_model,
                        max_tokens=8000,
                        system=system,
                        tools=TOOLS,
                        messages=conv.messages,
                        output_config={"effort": settings.claude_effort},
                        # If the model declines, the API retries on a fallback model inside the same call.
                        betas=["server-side-fallback-2026-07-01"],
                        fallbacks="default",
                    ) as stream:
                        async for event in stream:
                            if event.type == "text":
                                out = restorer.feed(event.text)
                                if out:
                                    yield {"type": "text", "text": out}
                        response = await stream.get_final_message()
                    break
                except ValueError:
                    # Tool input JSON the SDK could not parse at all: re-issue the turn (bounded)
                    json_retries += 1
                    if json_retries > 2:
                        raise
            tail = restorer.flush()
            if tail:
                yield {"type": "text", "text": tail}

            conv.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                yield {"type": "text", "text": "\n\nKechirasiz, bu so'rovga javob bera olmayman. Savolni boshqacha bering."}
                break
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "max_tokens":
                yield {"type": "text", "text": "\n\n(Javob juda uzun bo'lib ketdi — savolni toraytiring.)"}
                if tool_uses:
                    conv.messages.pop()  # don't keep a truncated tool call in history
                break
            if response.stop_reason == "pause_turn":
                continue
            if not tool_uses:
                break

            results = []
            for block in tool_uses:
                try:
                    out = await run_tool(block.name, block.input, pid, ctx)
                except ToolInputError as e:
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": f"Invalid input: {e}"})
                    continue
                yield {"type": "tool", "name": block.name, "label": TOOL_LABELS.get(block.name, block.name),
                       "input": block.input, "hisob": out["hisob"]}
                if out.get("action"):
                    yield {"type": "action", "action": out["action"]}
                payload = conv.redactor.redact(json.dumps(out["data"], ensure_ascii=False, default=str))
                conv.last_payload.append({"role": "tool", "name": block.name, "content": payload[:1500]})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": payload})
            conv.messages.append({"role": "user", "content": results})
        else:
            yield {"type": "text", "text": "\n\n(Juda ko'p qadam — to'xtatildi.)"}
    except anthropic.AuthenticationError:
        yield {"type": "error", "message": "AI kaliti noto'g'ri. Offline rejimga o'tilmoqda."}
        async for ev in _fallback_offline(pid, user_message, intent, ctx, conv, conv_id, snapshot):
            yield ev
        return
    except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
        log.warning("AI unavailable: %s", e)
        yield {"type": "error", "message": "AI xizmati hozir javob bermayapti. Offline demo rejimiga o'tildi."}
        async for ev in _fallback_offline(pid, user_message, intent, ctx, conv, conv_id, snapshot):
            yield ev
        return
    except anthropic.APIStatusError as e:
        log.error("AI error %s: %s", e.status_code, e.message)
        yield {"type": "error", "message": f"AI xatosi ({e.status_code}). Offline demo rejimiga o'tildi."}
        async for ev in _fallback_offline(pid, user_message, intent, ctx, conv, conv_id, snapshot):
            yield ev
        return

    last_payload_by_profile[pid] = conv.last_payload
    yield {"type": "done", "redacted_payload": conv.last_payload}


async def _fallback_offline(pid, user_message, intent, ctx, conv, conv_id, snapshot):
    # Roll back this turn so the live history stays valid if the API comes back
    del conv.messages[snapshot:]
    yield {"type": "mode", "mode": "offline", "conversation_id": conv_id}
    async for ev in offline_answer(pid, user_message, intent, ctx, conv):
        yield ev

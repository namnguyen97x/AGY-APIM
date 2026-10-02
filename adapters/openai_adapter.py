import json
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple

def parse_openai_messages(messages: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses OpenAI messages into systemInstruction and contents list.
    """
    system_text_parts = []
    contents = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            if isinstance(content, str):
                system_text_parts.append(content)
            elif isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        system_text_parts.append(p.get("text", ""))
        elif role == "user":
            parts = []
            if isinstance(content, str):
                parts.append({"text": content})
            elif isinstance(content, list):
                for p in content:
                    if isinstance(p, dict):
                        if p.get("type") == "text":
                            parts.append({"text": p.get("text", "")})
                        elif p.get("type") == "image_url":
                            url_obj = p.get("image_url", {})
                            url_str = url_obj.get("url", "")
                            if url_str.startswith("data:"):
                                # Parse base64
                                try:
                                    mime_and_data = url_str.split(",", 1)
                                    mime_part = mime_and_data[0].split(";")[0].replace("data:", "")
                                    b64_data = mime_and_data[1]
                                    parts.append({
                                        "inlineData": {
                                            "mimeType": mime_part,
                                            "data": b64_data
                                        }
                                    })
                                except Exception:
                                    pass
            if parts:
                contents.append({"role": "user", "parts": parts})
        elif role == "assistant":
            parts = []
            if content:
                if isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, list):
                    for p in content:
                        if isinstance(p, dict) and p.get("type") == "text":
                            parts.append({"text": p.get("text", "")})

            # Check tool_calls
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"raw_args": args}
                parts.append({
                    "functionCall": {
                        "name": fn.get("name", ""),
                        "args": args
                    }
                })

            if parts:
                contents.append({"role": "model", "parts": parts})

        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            response_content = content
            if isinstance(response_content, str):
                try:
                    response_content = json.loads(response_content)
                except Exception:
                    response_content = {"result": response_content}
            parts = [{
                "functionResponse": {
                    "name": msg.get("name", "tool_result"),
                    "response": response_content
                }
            }]
            contents.append({"role": "user", "parts": parts})

    system_instruction = None
    if system_text_parts:
        system_instruction = {
            "role": "user",
            "parts": [{"text": "\n\n".join(system_text_parts)}]
        }

    return system_instruction, contents

def build_cloudcode_request(openai_req: Dict[str, Any]) -> Dict[str, Any]:
    """Converts OpenAI /v1/chat/completions payload to Antigravity CloudCode request."""
    messages = openai_req.get("messages", [])
    system_inst, contents = parse_openai_messages(messages)

    gen_config: Dict[str, Any] = {
        "maxOutputTokens": openai_req.get("max_tokens") or openai_req.get("max_completion_tokens") or 8192
    }
    if "temperature" in openai_req:
        gen_config["temperature"] = openai_req["temperature"]
    if "top_p" in openai_req:
        gen_config["topP"] = openai_req["top_p"]

    # Thinking Config (Gemini / Claude reasoning)
    thinking_budget = openai_req.get("thinking_budget")
    if openai_req.get("reasoning_effort") or thinking_budget or "thinking" in openai_req.get("model", "").lower():
        budget = thinking_budget or 10000
        gen_config["thinkingConfig"] = {
            "includeThoughts": True,
            "thinkingBudget": budget
        }

    cloudcode_req: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": gen_config
    }
    if system_inst:
        cloudcode_req["systemInstruction"] = system_inst

    # Convert tools
    tools = openai_req.get("tools")
    if tools:
        declarations = []
        for t in tools:
            if t.get("type") == "function":
                fn = t.get("function", {})
                decl = {
                    "name": fn.get("name"),
                    "description": fn.get("description", "")
                }
                if "parameters" in fn:
                    decl["parameters"] = fn["parameters"]
                declarations.append(decl)
        if declarations:
            cloudcode_req["tools"] = [{"functionDeclarations": declarations}]

    return cloudcode_req

def format_openai_response(
    result: Dict[str, Any],
    original_model: str,
    account_email: str
) -> Dict[str, Any]:
    """Formats non-streaming result into OpenAI chat completion response."""
    msg: Dict[str, Any] = {
        "role": "assistant",
        "content": result.get("text", "")
    }
    tool_calls = result.get("tool_calls", [])
    if tool_calls:
        openai_tcs = []
        for i, tc in enumerate(tool_calls):
            openai_tcs.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": tc.get("name"),
                    "arguments": json.dumps(tc.get("args", {}))
                }
            })
        msg["tool_calls"] = openai_tcs

    usage = result.get("usage", {})
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": original_model,
        "system_fingerprint": f"ag-{account_email.split('@')[0]}",
        "choices": [
            {
                "index": 0,
                "message": msg,
                "finish_reason": "tool_calls" if tool_calls else "stop"
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0)
        }
    }

def format_openai_stream_chunk(
    chunk_text: str,
    cmpl_id: str,
    model_name: str,
    finish_reason: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Formats SSE chunk in standard OpenAI streaming format."""
    delta: Dict[str, Any] = {}
    if chunk_text:
        delta["content"] = chunk_text
    if tool_calls:
        delta["tool_calls"] = tool_calls

    payload = {
        "id": cmpl_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason
            }
        ]
    }
    return f"data: {json.dumps(payload)}\n\n"

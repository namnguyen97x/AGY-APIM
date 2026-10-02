import json
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple

def parse_anthropic_messages(system: Any, messages: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parses Anthropic messages into systemInstruction and contents list."""
    system_text = ""
    if isinstance(system, str):
        system_text = system
    elif isinstance(system, list):
        for item in system:
            if isinstance(item, dict) and item.get("type") == "text":
                system_text += item.get("text", "") + "\n\n"

    system_instruction = None
    if system_text.strip():
        system_instruction = {
            "role": "user",
            "parts": [{"text": system_text.strip()}]
        }

    contents = []
    for msg in messages:
        role = msg.get("role")
        role_mapped = "model" if role == "assistant" else "user"
        content = msg.get("content")

        parts = []
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    b_type = block.get("type")
                    if b_type == "text":
                        parts.append({"text": block.get("text", "")})
                    elif b_type == "tool_use":
                        parts.append({
                            "functionCall": {
                                "name": block.get("name"),
                                "args": block.get("input", {})
                            }
                        })
                    elif b_type == "tool_result":
                        res_content = block.get("content", "")
                        if isinstance(res_content, list):
                            res_content = "\n".join(b.get("text", "") for b in res_content if isinstance(b, dict))
                        parts.append({
                            "functionResponse": {
                                "name": block.get("tool_use_id", "tool"),
                                "response": {"result": res_content}
                            }
                        })
        if parts:
            contents.append({"role": role_mapped, "parts": parts})

    return system_instruction, contents

def build_anthropic_cloudcode_request(anthropic_req: Dict[str, Any]) -> Dict[str, Any]:
    """Converts Anthropic /v1/messages request to Antigravity CloudCode request."""
    system_inst, contents = parse_anthropic_messages(
        anthropic_req.get("system"),
        anthropic_req.get("messages", [])
    )

    gen_config: Dict[str, Any] = {
        "maxOutputTokens": anthropic_req.get("max_tokens", 4096)
    }
    if "temperature" in anthropic_req:
        gen_config["temperature"] = anthropic_req["temperature"]
    if "top_p" in anthropic_req:
        gen_config["topP"] = anthropic_req["top_p"]

    # Thinking
    thinking = anthropic_req.get("thinking")
    if thinking and isinstance(thinking, dict):
        if thinking.get("type") == "enabled":
            budget = thinking.get("budget_tokens", 16000)
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

    # Tools
    tools = anthropic_req.get("tools")
    if tools:
        declarations = []
        for t in tools:
            decl = {
                "name": t.get("name"),
                "description": t.get("description", "")
            }
            if "input_schema" in t:
                decl["parameters"] = t["input_schema"]
            declarations.append(decl)
        if declarations:
            cloudcode_req["tools"] = [{"functionDeclarations": declarations}]

    return cloudcode_req

def format_anthropic_response(result: Dict[str, Any], original_model: str) -> Dict[str, Any]:
    """Formats non-streaming response into Anthropic format."""
    content_blocks = []
    text = result.get("text", "")
    if text:
        content_blocks.append({
            "type": "text",
            "text": text
        })

    tool_calls = result.get("tool_calls", [])
    for tc in tool_calls:
        content_blocks.append({
            "type": "tool_use",
            "id": f"toolu_{uuid.uuid4().hex[:12]}",
            "name": tc.get("name"),
            "input": tc.get("args", {})
        })

    usage = result.get("usage", {})
    return {
        "id": f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": original_model,
        "content": content_blocks,
        "stop_reason": "tool_use" if tool_calls else "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0)
        }
    }

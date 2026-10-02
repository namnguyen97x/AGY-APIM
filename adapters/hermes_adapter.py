from typing import Dict, Any

def build_hermes_cloudcode_request(hermes_req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapts direct Hermes Agent or IDE requests to Google CloudCode format.
    """
    cloudcode_req: Dict[str, Any] = {}

    # 1. System instruction
    instructions = hermes_req.get("instructions")
    if instructions:
        cloudcode_req["systemInstruction"] = {
            "role": "user",
            "parts": [{"text": instructions}]
        }
    elif "systemInstruction" in hermes_req:
        cloudcode_req["systemInstruction"] = hermes_req["systemInstruction"]

    # 2. Contents
    cloudcode_req["contents"] = hermes_req.get("contents", [])

    # 3. Generation Config
    gen_config = hermes_req.get("generationConfig", {}).copy()
    reasoning = hermes_req.get("reasoning", {})
    if reasoning or "thinkingConfig" in hermes_req:
        thinking_budget = 10000
        if reasoning.get("effort") == "high":
            thinking_budget = 16000
        elif reasoning.get("effort") == "low":
            thinking_budget = 2000
        gen_config["thinkingConfig"] = {
            "includeThoughts": True,
            "thinkingBudget": thinking_budget
        }
    if not gen_config.get("maxOutputTokens"):
        gen_config["maxOutputTokens"] = 42768
    if not gen_config.get("topP"):
        gen_config["topP"] = 1.0

    cloudcode_req["generationConfig"] = gen_config

    # 4. Tools
    if "tools" in hermes_req:
        cloudcode_req["tools"] = hermes_req["tools"]

    return cloudcode_req

import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from httpx import AsyncClient, ASGITransport
from main import app

async def test_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== Test 1: GET /v1/models ===")
        res = await client.get("/v1/models")
        assert res.status_code == 200, f"Failed: {res.text}"
        models = res.json()["data"]
        print(f"Total models returned: {len(models)}")
        assert any(m["id"] == "gemini-3.8-flash-high" for m in models)
        assert any(m["id"] == "claude-sonnet-4-6" for m in models)
        print("Models endpoint verified!")

        print("\n=== Test 2: POST /v1/chat/completions (Non-Streaming) ===")
        payload = {
            "model": "gpt-4o",  # Should map to gemini-3.8-flash-high
            "messages": [
                {"role": "system", "content": "You are a test bot."},
                {"role": "user", "content": "What is 2+2? Answer in one digit."}
            ],
            "stream": False
        }
        res = await client.post("/v1/chat/completions", json=payload)
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()
        print("Status: 200 OK")
        print("Model used:", data.get("model"))
        print("Reply:", data["choices"][0]["message"]["content"].strip())
        print("Usage:", data.get("usage"))
        assert "4" in data["choices"][0]["message"]["content"]

        print("\n=== Test 3: POST /v1/chat/completions (Streaming SSE) ===")
        payload["stream"] = True
        payload["messages"] = [{"role": "user", "content": "Say 'STREAM_OK'."}]
        
        async with client.stream("POST", "/v1/chat/completions", json=payload) as stream_resp:
            assert stream_resp.status_code == 200
            full_chunks = []
            async for line in stream_resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk_json = json.loads(line[6:])
                    delta = chunk_json["choices"][0]["delta"].get("content", "")
                    if delta:
                        full_chunks.append(delta)
            stream_result = "".join(full_chunks)
            print("Stream Output:", stream_result.strip())
            assert len(stream_result) > 0

        print("\n=== Test 4: POST /v1/messages (Anthropic format) ===")
        anthropic_payload = {
            "model": "claude-3-7-sonnet",
            "messages": [
                {"role": "user", "content": "Say 'ANTHROPIC_SUCCESS'"}
            ],
            "max_tokens": 50
        }
        res = await client.post("/v1/messages", json=anthropic_payload)
        assert res.status_code == 200, f"Anthropic error: {res.text}"
        ant_data = res.json()
        print("Anthropic Response:", ant_data["content"][0]["text"].strip())

    print("\nAll API Endpoint integration tests passed with 100% success!")

if __name__ == "__main__":
    asyncio.run(test_endpoints())

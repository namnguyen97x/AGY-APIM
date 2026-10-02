import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional, Tuple
import httpx

logger = logging.getLogger("upstream_client")

CLOUDCODE_API_URL = "https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"

class QuotaExceededException(Exception):
    def __init__(self, message: str, reset_time: Optional[str] = None, account_id: Optional[str] = None):
        super().__init__(message)
        self.reset_time = reset_time
        self.account_id = account_id

class UpstreamException(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(f"Upstream error {status_code}: {message}")
        self.status_code = status_code
        self.message = message

class UpstreamClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=180.0)

    async def close(self):
        await self.client.aclose()

    async def execute_stream(
        self,
        access_token: str,
        project_id: str,
        model_name: str,
        request_body: Dict[str, Any],
        account_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes streamGenerateContent on Google CloudCode backend.
        Yields parsed response dicts from SSE data packets.
        Raises QuotaExceededException on 429/ResourceExhausted.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Antigravity/4.3.0 (Windows NT 10.0; Win64; x64) Chrome/132.0.6834.160 Electron/39.2.3",
            "x-client-name": "antigravity",
            "x-client-version": "4.3.0"
        }
        if "claude" in model_name.lower():
            headers["anthropic-beta"] = "claude-code-20250219"

        payload = {
            "project": project_id or "aicode-consumers",
            "model": model_name,
            "request": request_body
        }

        req = self.client.build_request(
            "POST",
            CLOUDCODE_API_URL,
            headers=headers,
            json=payload
        )

        resp = await self.client.send(req, stream=True)

        if resp.status_code == 429:
            err_text = await resp.aread()
            await resp.aclose()
            logger.warning(f"Upstream returned 429 Quota Exceeded on account {account_id}: {err_text.decode(errors='ignore')}")
            raise QuotaExceededException("Quota limit exceeded (HTTP 429)", account_id=account_id)

        if resp.status_code == 403:
            err_text = await resp.aread()
            await resp.aclose()
            decoded = err_text.decode(errors='ignore')
            if "RESOURCE_EXHAUSTED" in decoded or "quota" in decoded.lower() or "limit" in decoded.lower():
                logger.warning(f"Upstream returned 403 Quota Exceeded on account {account_id}: {decoded}")
                raise QuotaExceededException(f"Quota exceeded: {decoded}", account_id=account_id)
            raise UpstreamException(403, decoded)

        if resp.status_code >= 400:
            err_text = await resp.aread()
            await resp.aclose()
            decoded = err_text.decode(errors='ignore')
            if "RESOURCE_EXHAUSTED" in decoded:
                raise QuotaExceededException(f"Resource exhausted: {decoded}", account_id=account_id)
            raise UpstreamException(resp.status_code, decoded)

        try:
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data: "):
                    raw_json = line[6:].strip()
                    if raw_json == "[DONE]":
                        continue
                    try:
                        parsed = json.loads(raw_json)
                        if "error" in parsed:
                            err = parsed["error"]
                            if err.get("code") == 429 or "RESOURCE_EXHAUSTED" in str(err):
                                raise QuotaExceededException(f"Quota error in stream: {err}", account_id=account_id)
                        yield parsed
                    except json.JSONDecodeError:
                        pass
        finally:
            await resp.aclose()

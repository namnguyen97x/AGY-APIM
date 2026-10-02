import asyncio
import json
import logging
import os
import sys
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional

import uvicorn
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import load_config, save_config, AppConfig, DEFAULT_MODEL_MAPPING, CLIENT_ID, CLIENT_SECRET
from account_manager import AccountManager, Account
from upstream_client import UpstreamClient, UpstreamException, QuotaExceededException
from router import SmartRotator
from adapters.openai_adapter import build_cloudcode_request, format_openai_response, format_openai_stream_chunk
from adapters.anthropic_adapter import build_anthropic_cloudcode_request, format_anthropic_response
from adapters.hermes_adapter import build_hermes_cloudcode_request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("antigravity_hub")

# Initialize app and state
config = load_config()
account_mgr = AccountManager()
upstream_client = UpstreamClient()
rotator = SmartRotator(account_mgr, upstream_client, config)

app = FastAPI(title="Antigravity Multi-Account Hub & Smart Rotator", version="1.1.0")

# Enable CORS for external web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Auth verification helper
def verify_api_key(authorization: Optional[str] = Header(None)):
    if config.api_key:
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization Header")
        token = authorization.replace("Bearer ", "").strip()
        if token != config.api_key:
            raise HTTPException(status_code=403, detail="Invalid API Key")

# Background periodic quota poller
async def quota_poller_task():
    while True:
        try:
            logger.info("Running background quota check...")
            await account_mgr.refresh_all_quotas()
        except Exception as e:
            logger.error(f"Error in background quota check: {e}")
        await asyncio.sleep(600)  # Check every 10 minutes

@app.on_event("startup")
async def on_startup():
    logger.info("Antigravity Hub starting up...")
    account_mgr.auto_discover_accounts()
    asyncio.create_task(account_mgr.refresh_all_quotas())
    asyncio.create_task(quota_poller_task())

@app.on_event("shutdown")
async def on_shutdown():
    await upstream_client.close()

# ==========================================================
# Web UI & Management Endpoints
# ==========================================================
@app.get("/")
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Antigravity API Hub is running"}

@app.get("/api/status")
async def get_status():
    return {
        "accounts": [acc.model_dump() for acc in account_mgr.accounts.values()],
        "active_ide_account_id": account_mgr.active_ide_account_id,
        "config": config.model_dump(),
        "rotations": rotator.rotation_history
    }

@app.post("/api/accounts/discover")
async def trigger_discover():
    count = account_mgr.auto_discover_accounts()
    asyncio.create_task(account_mgr.refresh_all_quotas())
    return {"success": True, "imported_count": count}

# Google OAuth Login Flow
@app.get("/api/oauth/login")
async def oauth_login():
    """Generates Google OAuth URL to easily add an account via browser."""
    redirect_uri = f"http://localhost:{config.port}/oauth/callback"
    scopes = [
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
    scope_str = "%20".join(scopes)
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope_str}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return {"auth_url": auth_url}

@app.get("/oauth/callback")
async def oauth_callback(code: str):
    """Handles Google OAuth authorization code callback."""
    redirect_uri = f"http://localhost:{config.port}/oauth/callback"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                }
            )
            if token_resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_resp.text}")

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")

            # Get user info
            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_data = user_resp.json() if user_resp.status_code == 200 else {}
            email = user_data.get("email")
            name = user_data.get("name") or (email.split("@")[0] if email else "Google User")

            if not email or not refresh_token:
                raise HTTPException(status_code=400, detail="Missing email or refresh_token from Google response")

            # Find or create account
            existing = next((a for a in account_mgr.accounts.values() if a.email == email), None)
            if existing:
                existing.refresh_token = refresh_token
                existing.access_token = access_token
                existing.token_expiry = time.time() + token_data.get("expires_in", 3600)
                existing.name = name
                target_acc = existing
            else:
                target_acc = Account(
                    email=email,
                    name=name,
                    refresh_token=refresh_token,
                    access_token=access_token,
                    token_expiry=time.time() + token_data.get("expires_in", 3600),
                    priority=50
                )
                account_mgr.accounts[target_acc.id] = target_acc

            account_mgr.save()
            asyncio.create_task(account_mgr.refresh_account_quota(target_acc))

            # Redirect back to Web UI with success param
            return RedirectResponse(url="/?oauth_success=1")

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(url=f"/?oauth_error={str(e)}")

class AddAccountPayload(BaseModel):
    email: str
    name: Optional[str] = ""
    refresh_token: str
    priority: Optional[int] = 50
    plan_type: Optional[str] = "FREE"

@app.post("/api/accounts")
async def add_account(payload: AddAccountPayload):
    acc = Account(
        email=payload.email,
        name=payload.name or payload.email.split("@")[0],
        refresh_token=payload.refresh_token,
        priority=payload.priority or 50,
        plan_type=(payload.plan_type or "FREE").upper()
    )
    account_mgr.accounts[acc.id] = acc
    account_mgr.save()
    asyncio.create_task(account_mgr.refresh_account_quota(acc))
    return {"success": True, "account": acc.model_dump()}

class UpdateAccountPayload(BaseModel):
    name: Optional[str] = None
    priority: Optional[int] = None
    plan_type: Optional[str] = None

@app.put("/api/accounts/{acc_id}")
async def update_account(acc_id: str, payload: UpdateAccountPayload):
    acc = account_mgr.accounts.get(acc_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    if payload.name is not None:
        acc.name = payload.name
    if payload.priority is not None:
        acc.priority = payload.priority
    if payload.plan_type is not None:
        acc.plan_type = payload.plan_type.upper()
    account_mgr.save()
    return {"success": True, "account": acc.model_dump()}

@app.post("/api/accounts/{acc_id}/toggle_plan")
async def toggle_plan(acc_id: str):
    acc = account_mgr.accounts.get(acc_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    acc.plan_type = "PRO" if acc.plan_type == "FREE" else "FREE"
    account_mgr.save()
    return {"success": True, "plan_type": acc.plan_type}

@app.post("/api/accounts/{acc_id}/sync_ide")
async def sync_ide(acc_id: str):
    success = account_mgr.sync_to_antigravity_ide(acc_id)
    if success:
        return {"success": True}
    return {"success": False, "error": "Account not found or sync failed"}

@app.post("/api/accounts/{acc_id}/refresh_quota")
async def refresh_quota(acc_id: str):
    acc = account_mgr.accounts.get(acc_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    await account_mgr.refresh_account_quota(acc)
    return {"success": True, "account": acc.model_dump()}

@app.post("/api/accounts/{acc_id}/reset_cooldown")
async def reset_cooldown(acc_id: str):
    acc = account_mgr.accounts.get(acc_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    acc.cooldown_until = 0.0
    account_mgr.save()
    return {"success": True}

@app.post("/api/accounts/refresh_all_quotas")
async def refresh_all():
    await account_mgr.refresh_all_quotas()
    return {"success": True}

@app.post("/api/accounts/{acc_id}/toggle")
async def toggle_account(acc_id: str):
    acc = account_mgr.accounts.get(acc_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    acc.disabled = not acc.disabled
    account_mgr.save()
    return {"success": True, "disabled": acc.disabled}

@app.delete("/api/accounts/{acc_id}")
async def delete_account(acc_id: str):
    if acc_id in account_mgr.accounts:
        del account_mgr.accounts[acc_id]
        account_mgr.save()
        return {"success": True}
    raise HTTPException(status_code=404, detail="Account not found")

@app.post("/api/rotations/clear")
async def clear_rotations():
    rotator.rotation_history.clear()
    return {"success": True}

# ==========================================================
# 1-Click App Integrations (Hermes, Codex, Claude Code)
# ==========================================================
@app.get("/api/integrations/status")
async def get_integrations_status():
    hermes_path = Path.home() / "AppData" / "Local" / "hermes" / "config.yaml"
    hermes_installed = hermes_path.exists()
    hermes_connected = False
    if hermes_installed:
        try:
            content = hermes_path.read_text(encoding="utf-8")
            if f":{config.port}" in content:
                hermes_connected = True
        except Exception:
            pass

    codex_dir = Path.home() / ".codex"
    codex_bat = Path.home() / "Desktop" / "Chay_Codex_Voi_Antigravity_API.bat"
    claude_bat = Path.home() / "Desktop" / "Chay_Claude_Code_API.bat"

    return {
        "hermes": {
            "installed": hermes_installed,
            "connected": hermes_connected,
            "path": str(hermes_path)
        },
        "codex": {
            "installed": codex_dir.exists(),
            "connected": codex_bat.exists()
        },
        "claude_code": {
            "connected": claude_bat.exists()
        }
    }

@app.post("/api/integrations/hermes")
async def integrate_hermes():
    import re
    hermes_path = Path.home() / "AppData" / "Local" / "hermes" / "config.yaml"
    if not hermes_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình Hermes Agent tại AppData\\Local\\hermes\\config.yaml")

    try:
        # Backup
        bak_path = hermes_path.with_name("config.yaml.antigravity-hub.bak")
        content = hermes_path.read_text(encoding="utf-8")
        bak_path.write_text(content, encoding="utf-8")

        # Update base_url
        new_content = re.sub(
            r"(base_url:\s*)http[s]?://[^\r\n]+",
            rf"\g<1>http://127.0.0.1:{config.port}",
            content
        )
        hermes_path.write_text(new_content, encoding="utf-8")
        return {"success": True, "message": f"Đã cấu hình Hermes Agent trỏ về Antigravity Hub (Port {config.port})!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi cấu hình Hermes: {e}")

@app.post("/api/integrations/codex")
async def integrate_codex():
    scripts_dir = Path(__file__).parent / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    bat_path = scripts_dir / "Chay_Codex_Voi_Antigravity_API.bat"
    bat_content = f"""@echo off
title Codex CLI voi Antigravity API Hub
echo ========================================================
echo   KHOI DONG CODEX VOI ANTIGRAVITY API HUB (PORT {config.port})
echo ========================================================
echo.

set OPENAI_BASE_URL=http://127.0.0.1:{config.port}/v1
set OPENAI_API_KEY=sk-antigravity
set OPENAI_API_BASE=http://127.0.0.1:{config.port}/v1

echo Endpoint: %OPENAI_BASE_URL%
echo.
echo Dang khoi dong Codex CLI...
codex
pause
"""
    try:
        bat_path.write_text(bat_content, encoding="utf-8")
        return {"success": True, "message": "Đã lưu script 'scripts/Chay_Codex_Voi_Antigravity_API.bat'!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo file Codex: {e}")

@app.post("/api/integrations/claude_code")
async def integrate_claude_code():
    scripts_dir = Path(__file__).parent / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    bat_path = scripts_dir / "Chay_Claude_Code_API.bat"
    bat_content = f"""@echo off
title Claude Code voi Antigravity API Hub
echo ========================================================
echo   KHOI DONG CLAUDE CODE VOI ANTIGRAVITY API HUB (PORT {config.port})
echo ========================================================
echo.

set ANTHROPIC_BASE_URL=http://127.0.0.1:{config.port}
set ANTHROPIC_API_KEY=sk-antigravity

echo Endpoint: %ANTHROPIC_BASE_URL%
echo.
echo Dang khoi dong Claude Code CLI...
claude
pause
"""
    try:
        bat_path.write_text(bat_content, encoding="utf-8")
        return {"success": True, "message": "Đã lưu script 'scripts/Chay_Claude_Code_API.bat'!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo file Claude Code: {e}")

class UpdateConfigPayload(BaseModel):
    min_quota_threshold: Optional[float] = None
    rotation_strategy: Optional[str] = None
    api_key: Optional[str] = None
    cooldown_seconds_on_429: Optional[int] = None

@app.post("/api/config")
async def update_config(payload: UpdateConfigPayload):
    if payload.min_quota_threshold is not None:
        config.min_quota_threshold = payload.min_quota_threshold
    if payload.rotation_strategy is not None:
        config.rotation_strategy = payload.rotation_strategy
    if payload.api_key is not None:
        config.api_key = payload.api_key if payload.api_key.strip() else None
    if payload.cooldown_seconds_on_429 is not None:
        config.cooldown_seconds_on_429 = payload.cooldown_seconds_on_429
    save_config(config)
    return {"success": True, "config": config.model_dump()}

# ==========================================================
# OpenAI Compatible API Endpoints
# ==========================================================
@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
@app.get("/models", dependencies=[Depends(verify_api_key)])
async def list_models():
    """Returns OpenAI standard list of available models."""
    model_ids = set()
    for acc in account_mgr.accounts.values():
        for b in acc.quota_buckets.values():
            model_ids.add(b.bucket_id)

    defaults = [
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-medium",
        "gemini-3.8-flash-low",
        "gemini-3.7-flash-high",
        "gemini-3.6-flash-high",
        "gemini-3-flash",
        "gemini-2.5-pro",
        "gemini-3.1-pro-high",
        "claude-sonnet-4-6",
        "claude-opus-4-6-thinking",
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-7-sonnet"
    ]
    for m in defaults:
        model_ids.add(m)

    models_data = []
    for mid in sorted(model_ids):
        models_data.append({
            "id": mid,
            "object": "model",
            "created": 1720000000,
            "owned_by": "antigravity"
        })
    return {"object": "list", "data": models_data}

@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
@app.post("/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request):
    """
    OpenAI-compatible Chat Completions endpoint.
    Guarantees seamless zero-disruption rotation on 429 quota exhaustion.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    requested_model = body.get("model", "gemini-3.8-flash-high")
    stream = body.get("stream", False)

    cloudcode_req = build_cloudcode_request(body)

    if not stream:
        try:
            result, used_account = await rotator.execute_chat(
                requested_model=requested_model,
                cloudcode_request=cloudcode_req,
                stream=False
            )
            openai_resp = format_openai_response(
                result=result,
                original_model=requested_model,
                account_email=used_account.email
            )
            return JSONResponse(content=openai_resp)
        except UpstreamException as ue:
            return JSONResponse(status_code=ue.status_code, content={"error": {"message": ue.message, "type": "upstream_error"}})
        except Exception as e:
            logger.error(f"Unexpected error in chat completions: {e}")
            return JSONResponse(status_code=500, content={"error": {"message": str(e), "type": "server_error"}})

    else:
        try:
            stream_gen, initial_acc = await rotator.execute_chat(
                requested_model=requested_model,
                cloudcode_request=cloudcode_req,
                stream=True
            )

            cmpl_id = f"chatcmpl-{uuid.uuid4().hex}"

            async def sse_event_stream():
                try:
                    async for chunk, current_acc in stream_gen:
                        if "error" in chunk:
                            err_payload = json.dumps(chunk)
                            yield f"data: {err_payload}\n\n"
                            break

                        resp_obj = chunk.get("response", {})
                        candidates = resp_obj.get("candidates", [])
                        if candidates:
                            candidate = candidates[0]
                            parts = candidate.get("content", {}).get("parts", [])
                            for part in parts:
                                if "text" in part and part["text"]:
                                    yield format_openai_stream_chunk(
                                        chunk_text=part["text"],
                                        cmpl_id=cmpl_id,
                                        model_name=requested_model
                                    )
                                if "functionCall" in part:
                                    fn = part["functionCall"]
                                    tc = [{
                                        "index": 0,
                                        "id": f"call_{uuid.uuid4().hex[:8]}",
                                        "type": "function",
                                        "function": {
                                            "name": fn.get("name"),
                                            "arguments": json.dumps(fn.get("args", {}))
                                        }
                                    }]
                                    yield format_openai_stream_chunk(
                                        chunk_text="",
                                        cmpl_id=cmpl_id,
                                        model_name=requested_model,
                                        tool_calls=tc
                                    )

                    yield format_openai_stream_chunk(
                        chunk_text="",
                        cmpl_id=cmpl_id,
                        model_name=requested_model,
                        finish_reason="stop"
                    )
                    yield "data: [DONE]\n\n"
                except Exception as ex:
                    logger.error(f"Error yielding SSE stream: {ex}")
                    yield f"data: {json.dumps({'error': {'message': str(ex)}})}\n\n"

            return StreamingResponse(sse_event_stream(), media_type="text/event-stream")

        except Exception as e:
            logger.error(f"Failed to initiate stream: {e}")
            return JSONResponse(status_code=500, content={"error": {"message": str(e)}})

# ==========================================================
# Anthropic Compatible API Endpoints
# ==========================================================
@app.post("/v1/messages", dependencies=[Depends(verify_api_key)])
@app.post("/messages", dependencies=[Depends(verify_api_key)])
async def anthropic_messages(request: Request):
    """Anthropic-compatible endpoint for Claude Code CLI, Cline, Cursor, etc."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    requested_model = body.get("model", "claude-sonnet-4-6")
    stream = body.get("stream", False)

    cloudcode_req = build_anthropic_cloudcode_request(body)

    if not stream:
        try:
            result, used_account = await rotator.execute_chat(
                requested_model=requested_model,
                cloudcode_request=cloudcode_req,
                stream=False
            )
            anthropic_resp = format_anthropic_response(result, requested_model)
            return JSONResponse(content=anthropic_resp)
        except UpstreamException as ue:
            return JSONResponse(status_code=ue.status_code, content={"type": "error", "error": {"type": "api_error", "message": ue.message}})
        except Exception as e:
            return JSONResponse(status_code=500, content={"type": "error", "error": {"type": "server_error", "message": str(e)}})
    else:
        try:
            stream_gen, _ = await rotator.execute_chat(
                requested_model=requested_model,
                cloudcode_request=cloudcode_req,
                stream=True
            )
            msg_id = f"msg_{uuid.uuid4().hex}"

            async def anthropic_sse_stream():
                yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': requested_model, 'content': [], 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n"
                yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

                async for chunk, _ in stream_gen:
                    if "error" in chunk:
                        yield f"event: error\ndata: {json.dumps(chunk)}\n\n"
                        break
                    resp_obj = chunk.get("response", {})
                    candidates = resp_obj.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "text" in part and part["text"]:
                                yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': part['text']}})}\n\n"

                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
                yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 10}})}\n\n"
                yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

            return StreamingResponse(anthropic_sse_stream(), media_type="text/event-stream")
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

# ==========================================================
# Direct /responses API (Hermes Agent & IDE compatibility)
# ==========================================================
@app.post("/responses")
async def direct_responses(request: Request):
    """Direct /responses endpoint used by Hermes Agent or local tools."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    requested_model = body.get("model", "gemini-3.8-flash-high")
    cloudcode_req = build_hermes_cloudcode_request(body)

    try:
        stream_gen, used_acc = await rotator.execute_chat(
            requested_model=requested_model,
            cloudcode_request=cloudcode_req,
            stream=True
        )

        async def hermes_stream():
            async for chunk, _ in stream_gen:
                yield f"data: {json.dumps(chunk)}\n\n"

        return StreamingResponse(hermes_stream(), media_type="text/event-stream")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

def run_server():
    cfg = load_config()
    logger.info(f"Starting Antigravity API Hub on http://{cfg.host}:{cfg.port}")
    if "--open-browser" in sys.argv:
        try:
            webbrowser.open(f"http://{cfg.host}:{cfg.port}/")
        except Exception:
            pass
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")

if __name__ == "__main__":
    run_server()

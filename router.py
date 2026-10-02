import asyncio
import hashlib
import json
import logging
import time
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple

from account_manager import AccountManager, Account
from config import AppConfig
from upstream_client import UpstreamClient, QuotaExceededException, UpstreamException

logger = logging.getLogger("router")

class RotationEvent:
    def __init__(self, from_account: str, to_account: str, model: str, reason: str):
        self.timestamp = time.time()
        self.from_account = from_account
        self.to_account = to_account
        self.model = model
        self.reason = reason

class SmartRotator:
    def __init__(self, account_mgr: AccountManager, upstream: UpstreamClient, config: AppConfig):
        self.account_mgr = account_mgr
        self.upstream = upstream
        self.config = config
        self.rotation_history: List[Dict[str, Any]] = []
        self.current_api_account_id: Optional[str] = None
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

    def resolve_model(self, requested_model: str) -> str:
        """Maps user requested model name to actual Antigravity model name."""
        mapped = self.config.model_mappings.get(requested_model)
        if mapped:
            return mapped
        # Default fallback
        if "claude" in requested_model.lower():
            if "opus" in requested_model.lower():
                return "claude-opus-4-6-thinking"
            return "claude-sonnet-4-6"
        return requested_model

    def select_candidate_accounts(self, target_model: str) -> List[Account]:
        """
        Filters and ranks available accounts according to strategy
        and remaining quota.
        """
        all_accounts = list(self.account_mgr.accounts.values())
        if not all_accounts:
            return []

        now = time.time()
        # 1. Filter out permanently disabled accounts
        active = [a for a in all_accounts if not a.disabled]
        if not active:
            return []

        # 2. Separate into non-cooldown and cooldown
        ready = [a for a in active if a.cooldown_until <= now]

        # If all ready accounts are on cooldown, take the one that will exit cooldown soonest
        if not ready:
            sorted_by_cooldown = sorted(active, key=lambda a: a.cooldown_until)
            return sorted_by_cooldown

        # 3. Filter accounts with quota above threshold
        threshold = self.config.min_quota_threshold
        has_quota = [a for a in ready if a.get_remaining_quota(target_model) > threshold]

        candidates = has_quota if has_quota else ready

        # 4. Sort according to strategy
        strategy = self.config.rotation_strategy
        if strategy == "highest_quota":
            candidates.sort(key=lambda a: (a.get_remaining_quota(target_model), 1 if a.plan_type == "PRO" else 0, a.priority), reverse=True)
        elif strategy == "priority":
            candidates.sort(key=lambda a: (1 if a.plan_type == "PRO" else 0, a.priority, a.get_remaining_quota(target_model)), reverse=True)
        elif strategy == "round_robin":
            # Rotate round robin
            idx = self._round_robin_index % len(candidates)
            candidates = candidates[idx:] + candidates[:idx]
            self._round_robin_index = (self._round_robin_index + 1) % 10000

        return candidates

    def log_rotation(self, from_email: str, to_email: str, model: str, reason: str):
        event = {
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "from_account": from_email,
            "to_account": to_email,
            "model": model,
            "reason": reason
        }
        self.rotation_history.insert(0, event)
        if len(self.rotation_history) > 200:
            self.rotation_history.pop()
        logger.info(f"[ZERO-DISRUPTION ROTATE] From {from_email} -> {to_email} | Model: {model} | Reason: {reason}")

    async def execute_chat(
        self,
        requested_model: str,
        cloudcode_request: Dict[str, Any],
        stream: bool = False
    ) -> Tuple[Any, Account]:
        """
        Executes a chat generation turn.
        If the primary account encounters 429 Quota Exceeded, the rotator
        AUTOMATICALLY switches to the next account without failing or losing
        the conversation context!
        """
        target_model = self.resolve_model(requested_model)
        candidates = self.select_candidate_accounts(target_model)

        if not candidates:
            raise UpstreamException(503, "No available Antigravity accounts configured in system.")

        last_exception = None
        for i, account in enumerate(candidates):
            try:
                # Obtain valid OAuth token
                token = await self.account_mgr.get_valid_access_token(account)
                project = account.cloudaicompanion_project or "aicode-consumers"

                if not stream:
                    # Non-streaming mode
                    aggregated_response = None
                    full_text = ""
                    tool_calls = []
                    usage_metadata = {}

                    async for chunk in self.upstream.execute_stream(
                        access_token=token,
                        project_id=project,
                        model_name=target_model,
                        request_body=cloudcode_request,
                        account_id=account.id
                    ):
                        resp_obj = chunk.get("response", {})
                        if "usageMetadata" in resp_obj:
                            usage_metadata = resp_obj["usageMetadata"]

                        candidates_list = resp_obj.get("candidates", [])
                        if candidates_list:
                            candidate = candidates_list[0]
                            parts = candidate.get("content", {}).get("parts", [])
                            for part in parts:
                                if "text" in part:
                                    full_text += part["text"]
                                if "functionCall" in part:
                                    tool_calls.append(part["functionCall"])

                    account.last_used = time.time()
                    self.account_mgr.save()

                    # Return successful result
                    self.current_api_account_id = account.id
                    return {
                        "model": target_model,
                        "text": full_text,
                        "tool_calls": tool_calls,
                        "usage": usage_metadata,
                        "account_email": account.email
                    }, account

                else:
                    # Streaming mode with zero-disruption failover buffer
                    # We buffer until the first valid packet arrives or 429 occurs
                    self.current_api_account_id = account.id
                    generator = self._stream_with_failover(
                        target_model=target_model,
                        cloudcode_request=cloudcode_request,
                        initial_account=account,
                        remaining_candidates=candidates[i+1:]
                    )
                    return generator, account

            except QuotaExceededException as qe:
                # Mark account in cooldown
                self.account_mgr.mark_cooldown(
                    account.id,
                    duration_seconds=self.config.cooldown_seconds_on_429,
                    reset_time_str=qe.reset_time
                )
                next_acc = candidates[i+1] if i + 1 < len(candidates) else None
                if next_acc:
                    self.log_rotation(
                        from_email=account.email,
                        to_email=next_acc.email,
                        model=target_model,
                        reason="Quota Exceeded (429 / Resource Exhausted)"
                    )
                    try:
                        self.account_mgr.sync_to_antigravity(next_acc.id)
                    except Exception:
                        pass
                last_exception = qe
                continue
            except Exception as e:
                logger.error(f"Error on account {account.email}: {e}")
                last_exception = e
                continue

        # If all candidates exhausted
        if isinstance(last_exception, QuotaExceededException):
            raise UpstreamException(429, "All configured Antigravity accounts have exceeded their quota limits.")
        raise UpstreamException(500, f"All account attempts failed: {last_exception}")

    async def _stream_with_failover(
        self,
        target_model: str,
        cloudcode_request: Dict[str, Any],
        initial_account: Account,
        remaining_candidates: List[Account]
    ) -> AsyncGenerator[Tuple[Dict[str, Any], Account], None]:
        """
        Streams response chunks. If 429 occurs at stream initialization,
        silently fails over to next candidate without breaking client stream!
        """
        current_acc = initial_account
        account_queue = [initial_account] + remaining_candidates

        for account in account_queue:
            try:
                token = await self.account_mgr.get_valid_access_token(account)
                project = account.cloudaicompanion_project or "aicode-consumers"

                stream_gen = self.upstream.execute_stream(
                    access_token=token,
                    project_id=project,
                    model_name=target_model,
                    request_body=cloudcode_request,
                    account_id=account.id
                )

                # Iterate stream
                has_yielded = False
                async for chunk in stream_gen:
                    has_yielded = True
                    self.current_api_account_id = account.id
                    yield chunk, account

                # Successfully finished
                account.last_used = time.time()
                self.account_mgr.save()
                return

            except QuotaExceededException as qe:
                self.account_mgr.mark_cooldown(
                    account.id,
                    duration_seconds=self.config.cooldown_seconds_on_429,
                    reset_time_str=qe.reset_time
                )
                idx = account_queue.index(account)
                next_acc = account_queue[idx + 1] if idx + 1 < len(account_queue) else None
                if next_acc:
                    self.log_rotation(
                        from_email=account.email,
                        to_email=next_acc.email,
                        model=target_model,
                        reason="Stream Quota Exceeded (429)"
                    )
                    try:
                        self.account_mgr.sync_to_antigravity(next_acc.id)
                    except Exception:
                        pass
                continue
            except Exception as e:
                logger.error(f"Stream error on {account.email}: {e}")
                continue

        # If arrived here, all accounts failed
        yield {
            "error": {
                "message": "All Antigravity accounts in pool exceeded quota or failed.",
                "type": "quota_exceeded"
            }
        }, current_acc

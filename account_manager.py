import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from config import CLIENT_ID, CLIENT_SECRET, DEFAULT_DATA_DIR, LEGACY_ACCOUNTS_DIR, GEMINI_DIR

logger = logging.getLogger("account_manager")

class QuotaBucket(BaseModel):
    bucket_id: str
    display_name: str
    remaining_fraction: float
    reset_time: Optional[str] = None
    window: Optional[str] = None

class Account(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str = ""
    refresh_token: str
    access_token: Optional[str] = None
    token_expiry: float = 0.0  # Unix timestamp
    disabled: bool = False
    priority: int = 50
    cooldown_until: float = 0.0  # Unix timestamp
    last_used: float = 0.0
    cloudaicompanion_project: str = "aicode-consumers"
    plan_type: str = "FREE"  # "FREE" | "PRO"
    tier_name: str = "Free Tier"
    quota_buckets: Dict[str, QuotaBucket] = Field(default_factory=dict)
    last_quota_check: float = 0.0
    last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        if self.disabled:
            return False
        if time.time() < self.cooldown_until:
            return False
        return True

    def get_remaining_quota(self, model_name: str) -> float:
        """Returns quota fraction between 0.0 and 1.0 for the requested model."""
        if "claude" in model_name.lower():
            # Check 3p-5h or 3p-weekly
            b_5h = self.quota_buckets.get("3p-5h")
            b_wk = self.quota_buckets.get("3p-weekly")
            f_5h = b_5h.remaining_fraction if b_5h else 1.0
            f_wk = b_wk.remaining_fraction if b_wk else 1.0
            return min(f_5h, f_wk)
        else:
            # Check gemini-5h or gemini-weekly
            b_5h = self.quota_buckets.get("gemini-5h")
            b_wk = self.quota_buckets.get("gemini-weekly")
            f_5h = b_5h.remaining_fraction if b_5h else 1.0
            f_wk = b_wk.remaining_fraction if b_wk else 1.0
            return min(f_5h, f_wk)

class AccountManager:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        self.data_dir = data_dir
        self.accounts_file = self.data_dir / "accounts.json"
        self.accounts: Dict[str, Account] = {}
        self.active_ide_account_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self.load()

    def load(self):
        if self.accounts_file.exists():
            try:
                data = json.loads(self.accounts_file.read_text(encoding="utf-8"))
                for acc_dict in data.get("accounts", []):
                    acc = Account.model_validate(acc_dict)
                    self.accounts[acc.id] = acc
                self.active_ide_account_id = data.get("active_ide_account_id")
            except Exception as e:
                logger.error(f"Error loading accounts: {e}")

        # If empty, attempt auto-import from existing tools on disk
        if not self.accounts:
            self.auto_discover_accounts()

    def save(self):
        data = {
            "accounts": [acc.model_dump() for acc in self.accounts.values()],
            "active_ide_account_id": self.active_ide_account_id,
            "updated_at": time.time()
        }
        self.accounts_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def auto_discover_accounts(self) -> int:
        """Discovers existing accounts from ~/.antigravity_tools and ~/.gemini."""
        imported_count = 0
        # 1. Check legacy Antigravity Tools accounts
        if LEGACY_ACCOUNTS_DIR.exists():
            for f in LEGACY_ACCOUNTS_DIR.glob("*.json"):
                try:
                    raw = json.loads(f.read_text(encoding="utf-8"))
                    email = raw.get("email")
                    rf_token = raw.get("token", {}).get("refresh_token")
                    if email and rf_token:
                        # Check if already present
                        existing = next((a for a in self.accounts.values() if a.email == email), None)
                        if not existing:
                            acc = Account(
                                id=raw.get("id") or str(uuid.uuid4()),
                                email=email,
                                name=raw.get("name") or email.split("@")[0],
                                refresh_token=rf_token,
                                access_token=raw.get("token", {}).get("access_token"),
                                disabled=raw.get("disabled", False) or raw.get("proxy_disabled", False),
                                priority=raw.get("priority", 50)
                            )
                            self.accounts[acc.id] = acc
                            imported_count += 1
                except Exception as e:
                    logger.warning(f"Failed to parse legacy account file {f}: {e}")

        # 2. Check ~/.gemini/oauth_creds.json
        gemini_creds = GEMINI_DIR / "oauth_creds.json"
        if gemini_creds.exists():
            try:
                raw = json.loads(gemini_creds.read_text(encoding="utf-8"))
                rf_token = raw.get("refresh_token")
                # Try to extract email from id_token or google_accounts.json
                email = None
                acc_file = GEMINI_DIR / "google_accounts.json"
                if acc_file.exists():
                    acc_json = json.loads(acc_file.read_text(encoding="utf-8"))
                    email = acc_json.get("active")
                if not email and "id_token" in raw:
                    import base64
                    payload = raw["id_token"].split(".")[1]
                    payload += "=" * ((4 - len(payload) % 4) % 4)
                    jwt_data = json.loads(base64.urlsafe_b64decode(payload))
                    email = jwt_data.get("email")

                if email and rf_token:
                    existing = next((a for a in self.accounts.values() if a.email == email), None)
                    if not existing:
                        acc = Account(
                            email=email,
                            name=email.split("@")[0],
                            refresh_token=rf_token,
                            access_token=raw.get("access_token")
                        )
                        self.accounts[acc.id] = acc
                        self.active_ide_account_id = acc.id
                        imported_count += 1
            except Exception as e:
                logger.warning(f"Failed to parse Gemini oauth_creds: {e}")

        if imported_count > 0:
            logger.info(f"Auto-discovered and imported {imported_count} accounts.")
            self.save()
        return imported_count

    async def get_valid_access_token(self, account: Account) -> str:
        """Retrieves or refreshes Google OAuth access token."""
        # Check if current access token is valid (valid for at least another 60 seconds)
        now = time.time()
        if account.access_token and (account.token_expiry > now + 60):
            return account.access_token

        # Refresh token
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "refresh_token": account.refresh_token,
                    "grant_type": "refresh_token"
                }
            )
            if resp.status_code != 200:
                error_msg = f"Failed to refresh token for {account.email}: {resp.status_code} - {resp.text}"
                logger.error(error_msg)
                account.last_error = error_msg
                self.save()
                raise ValueError(error_msg)

            data = resp.json()
            account.access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            account.token_expiry = now + expires_in
            account.last_error = None
            self.save()
            return account.access_token

    async def refresh_account_quota(self, account: Account):
        """Fetches the latest quota summary and resolves project ID."""
        try:
            token = await self.get_valid_access_token(account)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "Antigravity/4.3.0"
            }

            async with httpx.AsyncClient(timeout=15) as client:
                # 1. Quota Summary
                q_resp = await client.post(
                    "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary",
                    headers=headers,
                    json={}
                )
                if q_resp.status_code == 200:
                    q_data = q_resp.json()
                    buckets_map = {}
                    for group in q_data.get("groups", []):
                        for b in group.get("buckets", []):
                            bid = b.get("bucketId")
                            if bid:
                                buckets_map[bid] = QuotaBucket(
                                    bucket_id=bid,
                                    display_name=b.get("displayName", bid),
                                    remaining_fraction=float(b.get("remainingFraction", 1.0)),
                                    reset_time=b.get("resetTime"),
                                    window=b.get("window")
                                )
                    account.quota_buckets = buckets_map
                    account.last_quota_check = time.time()

                # 2. Project ID & Tier resolution
                ca_resp = await client.post(
                    "https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
                    headers=headers,
                    json={}
                )
                if ca_resp.status_code == 200:
                    ca_data = ca_resp.json()
                    proj = ca_data.get("cloudaicompanionProject")
                    if proj:
                        account.cloudaicompanion_project = proj
                    
                    current_tier = ca_data.get("currentTier", {})
                    paid_tier = ca_data.get("paidTier", {})
                    t_id = current_tier.get("id", "")
                    t_name = current_tier.get("name", "")
                    if paid_tier and paid_tier.get("id"):
                        account.plan_type = "PRO"
                        account.tier_name = paid_tier.get("name", "Google AI Pro")
                    elif t_id and t_id != "free-tier":
                        account.plan_type = "PRO"
                        account.tier_name = t_name or "Google AI Pro"
                    elif t_name:
                        account.tier_name = t_name

                account.last_error = None
                self.save()
        except Exception as e:
            account.last_error = str(e)
            logger.warning(f"Error checking quota for {account.email}: {e}")

    async def refresh_all_quotas(self):
        tasks = [self.refresh_account_quota(acc) for acc in self.accounts.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    def mark_cooldown(self, account_id: str, duration_seconds: int = 900, reset_time_str: Optional[str] = None):
        """Marks an account into cooldown when hitting 429 quota limit."""
        acc = self.accounts.get(account_id)
        if not acc:
            return

        cooldown_target = time.time() + duration_seconds
        if reset_time_str:
            try:
                # Parse ISO timestamp e.g. 2026-10-02T05:27:01Z
                dt = datetime.fromisoformat(reset_time_str.replace("Z", "+00:00"))
                reset_ts = dt.timestamp()
                if reset_ts > time.time():
                    cooldown_target = reset_ts
            except Exception:
                pass

        acc.cooldown_until = cooldown_target
        logger.warning(f"Account {acc.email} marked in cooldown until {datetime.fromtimestamp(cooldown_target, timezone.utc).isoformat()}")
        self.save()

    def sync_to_antigravity_ide(self, account_id: str) -> bool:
        """
        Hot-swaps active account in Antigravity IDE and CLI without losing
        ongoing chats, tabs, or conversation databases.
        """
        acc = self.accounts.get(account_id)
        if not acc:
            return False

        try:
            # 1. Update ~/.gemini/google_accounts.json
            acc_file = GEMINI_DIR / "google_accounts.json"
            old_accounts = []
            if acc_file.exists():
                try:
                    curr_data = json.loads(acc_file.read_text(encoding="utf-8"))
                    curr_active = curr_data.get("active")
                    old_accounts = curr_data.get("old", [])
                    if curr_active and curr_active != acc.email and curr_active not in old_accounts:
                        old_accounts.append(curr_active)
                except Exception:
                    pass

            acc_file.write_text(json.dumps({
                "active": acc.email,
                "old": old_accounts
            }, indent=2), encoding="utf-8")

            # 2. Update ~/.gemini/oauth_creds.json
            creds_file = GEMINI_DIR / "oauth_creds.json"
            creds_data = {
                "access_token": acc.access_token or "",
                "refresh_token": acc.refresh_token,
                "token_type": "Bearer",
                "expiry_date": int(acc.token_expiry * 1000) if acc.token_expiry else int((time.time() + 3600) * 1000)
            }
            creds_file.write_text(json.dumps(creds_data, indent=2), encoding="utf-8")

            # 3. Update ~/.gemini/antigravity-cli/antigravity-oauth-token
            cli_token_file = GEMINI_DIR / "antigravity-cli" / "antigravity-oauth-token"
            if cli_token_file.parent.exists():
                cli_data = {
                    "token": {
                        "access_token": acc.access_token or "",
                        "refresh_token": acc.refresh_token,
                        "token_type": "Bearer",
                        "expiry": datetime.fromtimestamp(acc.token_expiry or (time.time() + 3600), timezone.utc).isoformat()
                    }
                }
                cli_token_file.write_text(json.dumps(cli_data, indent=2), encoding="utf-8")

            self.active_ide_account_id = acc.id
            self.save()
            logger.info(f"Successfully synchronized active account {acc.email} to Antigravity IDE and CLI.")
            return True
        except Exception as e:
            logger.error(f"Failed to sync account to Antigravity IDE: {e}")
            return False

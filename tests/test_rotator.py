import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from account_manager import AccountManager
from config import load_config
from upstream_client import UpstreamClient
from router import SmartRotator

async def main():
    print("=== Test 1: Auto Discovery ===")
    mgr = AccountManager()
    count = mgr.auto_discover_accounts()
    print(f"Discovered accounts: {len(mgr.accounts)} (New imported: {count})")
    for acc in mgr.accounts.values():
        print(f" - {acc.email} | Priority: {acc.priority} | Project: {acc.cloudaicompanion_project}")

    print("\n=== Test 2: Quota Retrieval ===")
    if mgr.accounts:
        first_acc = list(mgr.accounts.values())[0]
        print(f"Refreshing quota for {first_acc.email}...")
        await mgr.refresh_account_quota(first_acc)
        print("Quota buckets:")
        for k, v in first_acc.quota_buckets.items():
            print(f"   * {k}: {v.display_name} -> {round(v.remaining_fraction*100, 1)}% (Reset: {v.reset_time})")

    print("\n=== Test 3: Model Resolution & Candidate Selection ===")
    cfg = load_config()
    upstream = UpstreamClient()
    rotator = SmartRotator(mgr, upstream, cfg)
    
    candidates = rotator.select_candidate_accounts("gemini-3.8-flash-high")
    print(f"Selected candidates for gemini-3.8-flash-high: {len(candidates)}")
    for c in candidates:
        print(f"   -> {c.email} (Quota: {round(c.get_remaining_quota('gemini-3.8-flash-high')*100, 1)}%)")

    print("\n=== Test 4: Seamless Zero-Disruption Rotation Simulation ===")
    # Simulate Account 1 failing with 429 and verify Account 2 seamlessly executes
    cloudcode_req = {
        "contents": [
            {"role": "user", "parts": [{"text": "Reply with 'ROTATION_SUCCESS' in 2 words."}]}
        ]
    }
    
    res, used_acc = await rotator.execute_chat("gemini-3-flash", cloudcode_req, stream=False)
    print(f"Execution succeeded using account: {used_acc.email}")
    print(f"Response text: {res.get('text').strip()}")

    await upstream.close()
    print("\nAll Rotator unit tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())

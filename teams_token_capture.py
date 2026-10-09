"""
teams_token_capture.py
----------------------
ONE-TIME setup script.

Run this once as the SafeLensAI service account (safelens.alerts@prodisyn.com).
It authenticates via browser device code, then saves the MSAL token cache
to a local JSON file.

From that point forward, the production backend can silently acquire fresh
access tokens from the cache — no browser, no human, fully unattended.

Usage:
    python3 teams_token_capture.py

After running:
    - Saves token cache to the path in MS_TOKEN_CACHE_FILE (default: ms_token_cache.json)
    - Prints next steps including what to add to your .env
"""

import os
import sys
import json
import msal

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CLIENT_ID  = os.environ.get("MS_CLIENT_ID",  "2c6b365c-4865-4d1f-8453-f8e14a9e04b7")
TENANT_ID  = os.environ.get("MS_TENANT_ID",  "744972e2-6822-4037-90fb-cda70db56125")
AUTHORITY  = f"https://login.microsoftonline.com/{TENANT_ID}"

# Path where the token cache JSON will be stored.
# On EC2, use an absolute path like /etc/safelens/ms_token_cache.json
CACHE_FILE = os.environ.get("MS_TOKEN_CACHE_FILE", "ms_token_cache.json")

# offline_access is the scope that instructs Microsoft to issue a refresh token.
# Without it, only a short-lived access token is returned.
SCOPES = [
    "Chat.Create",
    "ChatMessage.Send",
    "User.Read",
    "User.ReadBasic.All",
    # Note: offline_access is added automatically by MSAL — do NOT include it here
]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
def load_cache(path):
    cache = msal.SerializableTokenCache()
    if os.path.exists(path):
        print(f"[CACHE] Loading existing token cache from: {path}")
        with open(path, "r") as f:
            cache.deserialize(f.read())
    return cache


def save_cache(cache, path):
    if cache.has_state_changed:
        with open(path, "w") as f:
            f.write(cache.serialize())
        os.chmod(path, 0o600)   # owner read/write only — keep it private
        print(f"[CACHE] ✅ Token cache saved to: {os.path.abspath(path)}")
    else:
        print(f"[CACHE] Token cache unchanged — no write needed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print()
    print("SafeLensAI — Teams Service Account Token Capture")
    print(f"  Client ID  : {CLIENT_ID}")
    print(f"  Tenant ID  : {TENANT_ID}")
    print(f"  Cache File : {os.path.abspath(CACHE_FILE)}")
    print()

    cache = load_cache(CACHE_FILE)

    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )

    # --- Attempt silent acquisition first (if cache already has an account) ---
    accounts = app.get_accounts()
    if accounts:
        print(f"[MSAL] Cached account found: {accounts[0]['username']}")
        print(f"[MSAL] Attempting silent token refresh...")
        result = app.acquire_token_silent(scopes=SCOPES, account=accounts[0])
        if result and "access_token" in result:
            print(f"[MSAL] ✅ Silent refresh succeeded — no re-login needed.")
            save_cache(cache, CACHE_FILE)
            print_summary(CACHE_FILE)
            return
        else:
            err = result.get("error_description", "unknown") if result else "no result"
            print(f"[MSAL] Silent refresh failed ({err}). Re-authenticating via device code...")

    # --- Interactive device code login ---
    print("[MSAL] Initiating Device Code Flow...")
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        print(f"[ERROR] Failed to create device flow:")
        print(json.dumps(flow, indent=2))
        sys.exit(1)

    print()
    print("=" * 65)
    print("  ACTION REQUIRED — Open this URL in your browser:")
    print(f"  URL  : {flow['verification_uri']}")
    print(f"  Code : {flow['user_code']}")
    print()
    print("  ⚠️  IMPORTANT: Sign in as the SERVICE ACCOUNT, not yourself.")
    print("      Email: safelens.alerts@prodisyn.com")
    print("      If your own account appears, click 'Use another account'.")
    print("=" * 65)
    print()
    print("[MSAL] Waiting for login completion...")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        print()
        print("[ERROR] Token acquisition failed.")
        print(f"        Error       : {result.get('error', 'unknown')}")
        print(f"        Description : {result.get('error_description', 'none')}")
        sys.exit(1)

    print(f"[MSAL] ✅ Token acquired for account: {result.get('id_token_claims', {}).get('preferred_username', 'unknown')}")

    save_cache(cache, CACHE_FILE)
    print_summary(CACHE_FILE)


def print_summary(cache_file):
    abs_path = os.path.abspath(cache_file)
    print()
    print("=" * 65)
    print("  ✅  SERVICE ACCOUNT TOKEN CAPTURE COMPLETE")
    print()
    print(f"  Token cache file: {abs_path}")
    print(f"  Permissions set : 600 (owner read/write only)")
    print()
    print("  ─── Next steps ───────────────────────────────────────")
    print()
    print("  1. Add this line to your .env (local) and EC2 .env:")
    print(f"     MS_TOKEN_CACHE_FILE={abs_path}")
    print()
    print("  2. On EC2, copy the cache file to a secure location:")
    print("     sudo cp ms_token_cache.json /etc/safelens/ms_token_cache.json")
    print("     sudo chmod 600 /etc/safelens/ms_token_cache.json")
    print("     sudo chown ec2-user /etc/safelens/ms_token_cache.json")
    print()
    print("  3. Update EC2 .env:")
    print("     MS_TOKEN_CACHE_FILE=/etc/safelens/ms_token_cache.json")
    print()
    print("  4. Tell your coding agent: token capture is complete.")
    print("     They will now build the production Graph helper in utils.py.")
    print()
    print("  Token auto-refreshes silently every ~1 hour.")
    print("  Refresh token is valid for up to 90 days (rolling).")
    print("=" * 65)
    print()


if __name__ == "__main__":
    main()

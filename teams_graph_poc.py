"""
teams_graph_poc.py
------------------
Standalone POC: Microsoft Graph Authentication via MSAL Device Code Flow.

Purpose:
    Prove that the SafeLensAI Entra app can acquire a valid delegated
    Graph token and call GET /me successfully.

    This script does NOT touch poll_events.py, utils.py, or any
    production code. It is a throw-away validation tool.

Usage:
    # Set env vars (or let defaults below handle the POC values)
    export MS_CLIENT_ID=2c6b365c-4865-4d1f-8453-f8e14a9e04b7
    export MS_TENANT_ID=744972e2-6822-4037-90fb-cda70db56125

    python teams_graph_poc.py

Stop: Ctrl+C at any time. Script exits after /me result is printed.
"""

import os
import sys
import json
import requests
import msal

# ---------------------------------------------------------------------------
# Configuration — reads from env, falls back to POC defaults
# ---------------------------------------------------------------------------
CLIENT_ID = os.environ.get("MS_CLIENT_ID", "2c6b365c-4865-4d1f-8453-f8e14a9e04b7")
TENANT_ID = os.environ.get("MS_TENANT_ID", "744972e2-6822-4037-90fb-cda70db56125")
AUTHORITY  = f"https://login.microsoftonline.com/{TENANT_ID}"

SCOPES = [
    "Chat.Create",
    "ChatMessage.Send",
    "User.Read",           # needed for /me
    "User.ReadBasic.All",  # needed for looking up other users
]

GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

# ---------------------------------------------------------------------------
# Step 1: Acquire token via Device Code Flow
# ---------------------------------------------------------------------------
def acquire_token_device_code():
    print("\n[MSAL] Initialising PublicClientApplication...")
    app = msal.PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
    )

    print("[MSAL] Initiating Device Code Flow...")
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        print(f"\n[ERROR] Failed to create device flow.")
        print(f"        Details: {json.dumps(flow, indent=2)}")
        sys.exit(1)

    # Print the instructions Microsoft returned
    print("\n" + "=" * 60)
    print("  ACTION REQUIRED — Open this URL in your browser:")
    print(f"  URL  : {flow['verification_uri']}")
    print(f"  Code : {flow['user_code']}")
    print("=" * 60)
    print("  Sign in with your company Microsoft/Teams account.")
    print("  Waiting for you to complete login...\n")

    # Blocks here until the user completes login or it times out
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        error        = result.get("error", "unknown_error")
        description  = result.get("error_description", "No description provided.")
        print(f"\n[ERROR] Token acquisition failed.")
        print(f"        Error       : {error}")
        print(f"        Description : {description}")
        sys.exit(1)

    print("[MSAL] ✅ Token acquired successfully.")
    return result["access_token"]


# ---------------------------------------------------------------------------
# Step 2: Call GET /me to verify the token works
# ---------------------------------------------------------------------------
def verify_me(access_token):
    print("\n[GRAPH] Calling GET /me ...")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    response = requests.get(GRAPH_ME_URL, headers=headers, timeout=15)

    print(f"[GRAPH] HTTP Status : {response.status_code}")

    if response.status_code == 200:
        me = response.json()
        print("\n[GRAPH] ✅ Authentication verified. Your identity:")
        print(f"        Display Name  : {me.get('displayName', 'N/A')}")
        print(f"        UPN / Email   : {me.get('userPrincipalName', 'N/A')}")
        print(f"        Entra User ID : {me.get('id', 'N/A')}")
        print(f"        Job Title     : {me.get('jobTitle', 'N/A')}")
        print("\n[POC] Auth step complete. Report this result before proceeding.")
    else:
        print(f"\n[ERROR] /me call failed.")
        print(f"        Status  : {response.status_code}")
        try:
            print(f"        Body    : {json.dumps(response.json(), indent=2)}")
        except Exception:
            print(f"        Raw     : {response.text[:500]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("SafeLensAI — Microsoft Graph POC")
    print(f"  Client ID : {CLIENT_ID}")
    print(f"  Tenant ID : {TENANT_ID}")
    print(f"  Scopes    : {', '.join(SCOPES)}")

    token = acquire_token_device_code()
    verify_me(token)

    # --- Step 3: Lookup target user ---
    target_email = os.environ.get("TARGET_TEAMS_EMAIL", "sivaelango.n@prodisyn.com")
    print(f"\n[GRAPH] Looking up user: {target_email} ...")
    url = f"https://graph.microsoft.com/v1.0/users/{target_email}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.get(url, headers=headers, timeout=15)
    print(f"[GRAPH] HTTP Status : {resp.status_code}")

    if resp.status_code == 200:
        user = resp.json()
        print(f"\n[GRAPH] ✅ User resolved:")
        print(f"        Display Name  : {user.get('displayName', 'N/A')}")
        print(f"        UPN / Email   : {user.get('userPrincipalName', 'N/A')}")
        print(f"        Entra User ID : {user.get('id', 'N/A')}")
        target_user_id = user.get('id')
        print(f"\n[POC] User lookup complete.")
    else:
        print(f"\n[ERROR] User lookup failed.")
        try:
            print(f"        Body : {json.dumps(resp.json(), indent=2)}")
        except Exception:
            print(f"        Raw  : {resp.text[:500]}")
        print("\n[HINT] If 403 — add 'User.ReadBasic.All' delegated permission in Entra portal + re-consent.")
        sys.exit(1)

    # --- Step 4: Create 1:1 chat ---
    # Get signed-in user's ID from /me (we already called it)
    me_resp = requests.get(GRAPH_ME_URL, headers=headers, timeout=15)
    signed_in_user_id = me_resp.json().get('id') if me_resp.status_code == 200 else None

    if signed_in_user_id == target_user_id:
        print(f"\n[WARN] Signed-in user and target user are the SAME person.")
        print(f"       1:1 chat with yourself may not work in Graph.")
        print(f"       To test with a different target, run:")
        print(f"       TARGET_TEAMS_EMAIL=other.person@prodisyn.com python3 teams_graph_poc.py")
        print(f"\n       Attempting anyway...\n")

    print(f"[GRAPH] Creating 1:1 chat between:")
    print(f"        Signed-in user : {signed_in_user_id}")
    print(f"        Target user    : {target_user_id}")

    chat_payload = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{signed_in_user_id}')"
            },
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{target_user_id}')"
            }
        ]
    }

    chat_resp = requests.post(
        "https://graph.microsoft.com/v1.0/chats",
        headers=headers,
        json=chat_payload,
        timeout=15
    )
    print(f"[GRAPH] HTTP Status : {chat_resp.status_code}")

    if chat_resp.status_code in (200, 201):
        chat = chat_resp.json()
        chat_id = chat.get('id')
        print(f"\n[GRAPH] ✅ 1:1 Chat ready:")
        print(f"        Chat ID : {chat_id}")
        print(f"        Type    : {chat.get('chatType', 'N/A')}")
    else:
        print(f"\n[ERROR] Chat creation failed.")
        try:
            print(f"        Body : {json.dumps(chat_resp.json(), indent=2)}")
        except Exception:
            print(f"        Raw  : {chat_resp.text[:500]}")
        print("\n[HINT] If 403 — check Chat.Create permission is granted + admin consent done.")
        sys.exit(1)

    # --- Step 5: Send test message ---
    print(f"\n[GRAPH] Sending test message to chat {chat_id[:30]}...")

    msg_payload = {
        "body": {
            "contentType": "html",
            "content": (
                "<b>🚨 SafeLensAI Test Alert</b><br><br>"
                "<b>Incident ID:</b> POC-001<br>"
                "<b>Date:</b> 2026-08-24 18:00:00<br>"
                "<b>Location:</b> Test Location<br>"
                "<b>Incident Type:</b> POC Test Message<br><br>"
                "<i>If you see this in your Teams chat, the Graph 1:1 path works! ✅</i>"
            )
        }
    }

    msg_resp = requests.post(
        f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
        headers=headers,
        json=msg_payload,
        timeout=15
    )
    print(f"[GRAPH] HTTP Status : {msg_resp.status_code}")

    if msg_resp.status_code in (200, 201):
        msg = msg_resp.json()
        print(f"\n[GRAPH] ✅ Message sent!")
        print(f"        Message ID : {msg.get('id', 'N/A')}")
        print(f"        Created    : {msg.get('createdDateTime', 'N/A')}")
        print(f"\n🎉 [POC COMPLETE] Check your Teams app — you should see the message in a 1:1 chat!")
    else:
        print(f"\n[ERROR] Message send failed.")
        try:
            print(f"        Body : {json.dumps(msg_resp.json(), indent=2)}")
        except Exception:
            print(f"        Raw  : {msg_resp.text[:500]}")
        print("\n[HINT] If 403 — check ChatMessage.Send permission is granted + admin consent done.")

import os
from twilio.rest import Client

sid = 'AC030dba48daaf129291fdbac9d430a5b7'
token = '7edf123757105830d7d24900de3c3431'
from_num = '+12186308968'
to_num = '+919640064349' # Placeholder, user needs to change this

print(f"Testing Twilio with SID: {sid}")
try:
    client = Client(sid, token)
    # Just checking account info to see if creds are valid
    account = client.api.accounts(sid).fetch()
    print(f"Twilio Account Status: {account.status}")
    print("Credentials are VALID.")
except Exception as e:
    print(f"Twilio API Error: {e}")

import os
import django
import sys
import argparse
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'safelensai.settings')
django.setup()

from apps.api.utils import send_aws_email, send_aws_sms, send_aws_whatsapp

def main():
    parser = argparse.ArgumentParser(description='Test AWS Notification Integration (SafeLens AI)')
    parser.add_argument('--email', help='Recipient email address')
    parser.add_argument('--phone', help='Recipient phone number in E.164 format (e.g. +919876543210)')
    parser.add_argument('--all', action='store_true', help='Test all channels (requires email and phone)')
    
    args = parser.parse_args()

    if not args.email and not args.phone:
        parser.print_help()
        return

    print("🚀 Starting SafeLens AI AWS Notification Test...")

    if args.email or args.all:
        if not args.email:
            print("❌ Error: --email required for email test")
        else:
            print(f"📧 Testing SES Email to: {args.email}...")
            res = send_aws_email(
                subject="SafeLens AI - AWS Test Alert 🚨",
                body="This is a test notification from the SafeLens AI AWS SES integration.",
                recipients=[args.email]
            )
            if res:
                print(f"✅ Email Sent! (ID: {res.get('MessageId')})")
            else:
                print("❌ Email Failed. Check logs or .env")

    if args.phone or args.all:
        if not args.phone:
            print("❌ Error: --phone required for SMS/WhatsApp test")
        else:
            # 1. SMS
            print(f"💬 Testing SNS SMS to: {args.phone}...")
            res_sms = send_aws_sms(args.phone, "SafeLens AI AWS SNS Test: Alert Simulation 🚨")
            if res_sms:
                print(f"✅ SMS Sent! (ID: {res_sms.get('MessageId')})")
            else:
                print("❌ SMS Failed. Check logs or .env")

            # 2. WhatsApp
            print(f"📱 Testing AWS WhatsApp to: {args.phone}...")
            res_wa = send_aws_whatsapp(args.phone, "SafeLens AI AWS WhatsApp Test: Alert Simulation 🚨")
            if res_wa:
                print(f"✅ WhatsApp Sent! (ID: {res_wa.get('messageId')})")
            else:
                print("❌ WhatsApp Failed. Check logs or .env")

    print("\n🏁 Test completed. If you didn't receive messages, verify:")
    print("1. Your SES Identity is verified in AWS console.")
    print("2. Your SNS is out of Sandbox OR the recipient number is verified.")
    print("3. AWS_WHATSAPP_PHONE_NUMBER_ID is set in .env.")

if __name__ == "__main__":
    main()

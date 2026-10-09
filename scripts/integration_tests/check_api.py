
import requests
import json

BASE_URL = "http://192.168.1.59:8000/api/overview"

def check_endpoint(name, url):
    print(f"\n--- Checking {name} ---")
    print(f"URL: {url}")
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                print(f"Result count: {len(data)}")
                if data:
                    print("Sample item:", json.dumps(data[0], indent=2))
            else:
                print("Result:", json.dumps(data, indent=2))
        else:
            print("Error:", response.text)
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    print("Verifying Worker Safety API Overview Endpoints...")
    
    # 1. Events List (Today)
    check_endpoint("Events (Today)", f"{BASE_URL}/events/?date=2026-02-09")

    # 2. Summary Stats
    check_endpoint("Summary Stats", f"{BASE_URL}/summary/")

    # 3. Graph Data (Today)
    check_endpoint("Graph Data (Today)", f"{BASE_URL}/graph/?time_range=today")

    # 4. Graph Data (Week)
    check_endpoint("Graph Data (Week)", f"{BASE_URL}/graph/?time_range=week")

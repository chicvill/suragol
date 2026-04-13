import urllib.request
import sys

headers = {'User-Agent': 'Mozilla/5.0'}

ports = [8899, 10000]
success = False

for port in ports:
    url = f"http://127.0.0.1:{port}/api/internal/seed-demo"
    print(f"Trying {url}...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"Success on port {port}: {response.read().decode()}")
            success = True
            break
    except Exception as e:
        print(f"Failed on port {port}: {e}")

if not success:
    sys.exit(1)

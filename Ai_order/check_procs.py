import psutil

with open("process_dump.txt", "w", encoding="utf-8") as f:
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if "cloudflared" in proc.info['name'].lower() or ("python" in proc.info['name'].lower() and "run_domain" in " ".join(proc.info['cmdline'] or [])):
                f.write(f"PID: {proc.info['pid']}, Name: {proc.info['name']}, Cmd: {proc.info['cmdline']}\n")
        except:
            pass
    f.write("Done.\n")

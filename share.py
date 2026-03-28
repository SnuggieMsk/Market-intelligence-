"""
Share your Market Intelligence dashboard on the internet.
Your friend just opens the link -- no API keys needed on their end.

Usage:
    python share.py                          # Read-only (safe, API keys protected)
    python share.py --full                   # Full access (uses your API keys!)
    python share.py --setup                  # First-time setup (ngrok auth token)

Tunnel options (tries in order):
    1. ngrok   (free account at ngrok.com -- most reliable)
    2. localhost.run (SSH tunnel, no signup -- may be slow/unreliable)
"""

import os
import sys
import subprocess
import time

# ── Config ────────────────────────────────────────────────────────────────────
PORT = 8501
READ_ONLY_ENV = "SHARE_READ_ONLY"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def setup_ngrok():
    """Guide user through one-time ngrok setup."""
    print()
    print("=" * 60)
    print("  NGROK SETUP (one-time, takes 2 minutes)")
    print("=" * 60)
    print()
    print("  Step 1: Sign up for free at https://dashboard.ngrok.com/signup")
    print("  Step 2: Copy your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken")
    print()

    token = input("  Paste your ngrok authtoken here: ").strip()
    if not token:
        print("  No token entered. Aborting.")
        return False

    try:
        from pyngrok import ngrok
        ngrok.set_auth_token(token)
        print()
        print("  Authtoken saved! You can now run: python share.py")
        print()
        return True
    except ImportError:
        print("  Installing pyngrok...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyngrok", "-q"])
        from pyngrok import ngrok
        ngrok.set_auth_token(token)
        print()
        print("  Authtoken saved! You can now run: python share.py")
        print()
        return True


def kill_existing_streamlit():
    """Kill any existing Streamlit on our port."""
    try:
        if sys.platform == "win32":
            # Find PID using port
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                if f":{PORT}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True)
                    print(f"  Killed old process on port {PORT} (PID {pid})")
                    time.sleep(2)
                    break
        else:
            subprocess.run(f"lsof -ti:{PORT} | xargs kill -9 2>/dev/null",
                           shell=True, capture_output=True)
    except Exception:
        pass


def start_streamlit(read_only: bool = True):
    """Start Streamlit in a subprocess."""
    kill_existing_streamlit()

    env = os.environ.copy()
    if read_only:
        env[READ_ONLY_ENV] = "1"

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        os.path.join("dashboard", "app.py"),
        "--server.port", str(PORT),
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
        "--browser.gatherUsageStats", "false",
    ]
    proc = subprocess.Popen(cmd, env=env, cwd=PROJECT_DIR)
    return proc


def wait_for_streamlit():
    """Wait until Streamlit health endpoint responds."""
    import urllib.request
    print("  Waiting for dashboard to start", end="", flush=True)
    for _ in range(30):
        time.sleep(1)
        print(".", end="", flush=True)
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2)
            print(" Ready!")
            return True
        except Exception:
            continue
    print(" Timeout!")
    return False


def try_ngrok(port: int):
    """Try ngrok tunnel."""
    try:
        from pyngrok import ngrok
        tunnel = ngrok.connect(port, "http")
        return tunnel.public_url, "ngrok", None
    except Exception as e:
        err = str(e)
        if "authtoken" in err.lower():
            print(f"  ngrok: No auth token. Run 'python share.py --setup' first.")
        else:
            print(f"  ngrok: {err[:100]}")
        return None, None, None


def try_localhost_run(port: int):
    """Try localhost.run SSH tunnel (no signup needed)."""
    try:
        proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             "-o", "ServerAliveInterval=60",
             "-R", f"80:localhost:{port}", "nokey@localhost.run"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        url = None
        for _ in range(30):
            line = proc.stdout.readline()
            if not line:
                break
            if "https://" in line:
                for word in line.split():
                    w = word.strip().rstrip(",").rstrip(".")
                    # Must be a real tunnel URL, not the admin/docs page
                    if w.startswith("https://") and "localhost.run" in w:
                        # Skip admin/docs URLs -- real tunnel URLs have random subdomains
                        if w in ("https://admin.localhost.run/", "https://localhost.run",
                                 "https://admin.localhost.run", "https://docs.localhost.run"):
                            continue
                        url = w
                        break
                if url:
                    break
        if url:
            return url, "localhost.run", proc
        proc.terminate()
        print("  localhost.run: Could not get tunnel URL (may be down or rate-limited)")
        return None, None, None
    except FileNotFoundError:
        print("  localhost.run: SSH not found")
        return None, None, None
    except Exception as e:
        print(f"  localhost.run: {e}")
        return None, None, None


def main():
    # Handle --setup
    if "--setup" in sys.argv:
        setup_ngrok()
        return

    full_access = "--full" in sys.argv
    read_only = not full_access

    print()
    print("=" * 60)
    print("  MARKET INTELLIGENCE - SHARE DASHBOARD")
    print("=" * 60)

    if read_only:
        print()
        print("  Mode: READ-ONLY (your API keys are safe)")
        print("  Your friend can browse all existing analyses,")
        print("  agent reports, quant predictions, and heatmaps.")
        print("  'Analyze Any Stock' is disabled.")
        print()
    else:
        print()
        print("  Mode: FULL ACCESS (careful -- uses your API keys!)")
        print("  Anyone with the link can trigger new analyses.")
        print()

    # Step 1: Start Streamlit
    print("  Starting dashboard...")
    st_proc = start_streamlit(read_only=read_only)

    if not wait_for_streamlit():
        print("  Failed to start Streamlit. Check for errors.")
        st_proc.terminate()
        return

    # Step 2: Create tunnel
    print()
    print("  Creating public URL...")
    url, tunnel_type, tunnel_proc = try_ngrok(PORT)

    if not url:
        print("  Trying fallback tunnel (localhost.run)...")
        url, tunnel_type, tunnel_proc = try_localhost_run(PORT)

    if not url:
        print()
        print("-" * 60)
        print("  Could not create a public tunnel automatically.")
        print()
        print("  OPTION 1: Set up ngrok (recommended, 2 min)")
        print("    python share.py --setup")
        print()
        print("  OPTION 2: Manual SSH tunnel")
        print(f"    ssh -R 80:localhost:{PORT} nokey@localhost.run")
        print()
        print(f"  Meanwhile, dashboard is running at:")
        print(f"    http://localhost:{PORT}")
        print()
        print("  Press ENTER to stop.")
        print("-" * 60)

        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
        st_proc.terminate()
        return

    # Success!
    print()
    print("=" * 60)
    print()
    print(f"  PUBLIC URL:  {url}")
    print(f"  Tunnel:      {tunnel_type}")
    print(f"  Mode:        {'Read-only' if read_only else 'Full access'}")
    print()
    print("  ---- Copy this for WhatsApp ----")
    print()
    print(f"  Check out my AI-powered Stock Analysis Dashboard!")
    print(f"  {url}")
    print(f"  ")
    print(f"  47 AI agents + quant models analyzed Indian")
    print(f"  stocks (NSE/BSE) -- verdicts, risks, fair values")
    print(f"  and more. Built with Gemini + Groq.")
    print()
    print("  --------------------------------")
    print()
    print(f"  Local: http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop sharing.")
    print()
    print("=" * 60)

    def cleanup():
        print("\n  Shutting down...")
        st_proc.terminate()
        if tunnel_proc:
            tunnel_proc.terminate()
        try:
            from pyngrok import ngrok
            ngrok.kill()
        except Exception:
            pass
        print("  Done. Link is no longer active.")

    try:
        # Block until user presses Enter or Ctrl+C
        # (don't rely on st_proc.wait() which can exit early)
        input("\n  >>> Press ENTER to stop sharing <<<\n")
        cleanup()
    except (KeyboardInterrupt, EOFError):
        cleanup()


if __name__ == "__main__":
    main()

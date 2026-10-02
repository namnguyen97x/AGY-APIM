"""
Antigravity Multi-Account API Hub - Windows System Tray Runner
Runs the Gateway silently in the background and places a management icon
in the Windows System Tray (Taskbar Notification Area).
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure pythonw has valid stdout and stderr streams (critical for Windows pythonw!)
if sys.stdout is None:
    try:
        sys.stdout = open(PROJECT_ROOT / "daemon.log", "a", encoding="utf-8")
    except Exception:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")

if sys.stderr is None:
    try:
        sys.stderr = open(PROJECT_ROOT / "daemon.log", "a", encoding="utf-8")
    except Exception:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

import threading
import time
import webbrowser
import subprocess
from PIL import Image, ImageDraw
import pystray
import uvicorn
import httpx

from main import app, account_mgr
from config import load_config

cfg = load_config()
PORT = cfg.port
HOST = cfg.host

STARTUP_DIR = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_FILE = STARTUP_DIR / "Antigravity_Hub_Tray.vbs"

class UvicornServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.config = uvicorn.Config(app=app, host=HOST, port=PORT, log_level="warning")
        self.server = uvicorn.Server(config=self.config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def get_or_create_icon():
    ico_path = PROJECT_ROOT / "static" / "app.ico"
    if ico_path.exists():
        try:
            return Image.open(ico_path)
        except Exception:
            pass

    icon_path = PROJECT_ROOT / "static" / "icon.png"
    if icon_path.exists():
        try:
            return Image.open(icon_path)
        except Exception:
            pass

    # Fallback procedural generation
    width, height = 64, 64
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(img)
    dc.ellipse([2, 2, width - 2, height - 2], fill=(15, 23, 42, 255), outline=(56, 189, 248, 255), width=3)
    dc.ellipse([10, 10, width - 10, height - 10], outline=(245, 158, 11, 200), width=2)
    dc.line([(32, 14), (18, 50)], fill=(56, 189, 248, 255), width=4)
    dc.line([(32, 14), (46, 50)], fill=(56, 189, 248, 255), width=4)
    dc.line([(23, 38), (41, 38)], fill=(245, 158, 11, 255), width=3)
    return img

def safe_notify(icon, message, title="Antigravity Hub"):
    try:
        if icon:
            icon.notify(message, title)
    except Exception:
        pass

def open_dashboard(icon=None, item=None):
    webbrowser.open(f"http://127.0.0.1:{PORT}/")

def refresh_quotas_action(icon=None, item=None):
    def _refresh():
        try:
            with httpx.Client(timeout=30) as client:
                client.post(f"http://127.0.0.1:{PORT}/api/accounts/refresh_all_quotas")
            safe_notify(icon, "Đã làm mới Quota cho tất cả tài khoản Google!", "Antigravity Hub")
        except Exception as e:
            safe_notify(icon, f"Lỗi làm mới Quota: {e}", "Antigravity Hub")
    threading.Thread(target=_refresh, daemon=True).start()

def run_hermes_action(icon=None, item=None):
    subprocess.Popen(["cmd.exe", "/c", "start", "hermes"], cwd=str(PROJECT_ROOT))

def run_codex_action(icon=None, item=None):
    codex_bat = PROJECT_ROOT / "scripts" / "Chay_Codex_Voi_Antigravity_API.bat"
    if codex_bat.exists():
        subprocess.Popen(["cmd.exe", "/c", "start", str(codex_bat)], cwd=str(PROJECT_ROOT))
    else:
        subprocess.Popen(["cmd.exe", "/c", "start", "codex"], cwd=str(PROJECT_ROOT))

def run_claude_action(icon=None, item=None):
    claude_bat = PROJECT_ROOT / "scripts" / "Chay_Claude_Code_API.bat"
    if claude_bat.exists():
        subprocess.Popen(["cmd.exe", "/c", "start", str(claude_bat)], cwd=str(PROJECT_ROOT))
    else:
        subprocess.Popen(["cmd.exe", "/c", "start", "claude"], cwd=str(PROJECT_ROOT))

def is_startup_enabled(item=None):
    return STARTUP_FILE.exists()

def toggle_startup(icon=None, item=None):
    if STARTUP_FILE.exists():
        try:
            STARTUP_FILE.unlink()
            safe_notify(icon, "Đã tắt tự khởi động cùng Windows.", "Antigravity Hub")
        except Exception as e:
            safe_notify(icon, f"Lỗi: {e}", "Antigravity Hub")
    else:
        try:
            STARTUP_DIR.mkdir(parents=True, exist_ok=True)
            vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{PROJECT_ROOT}"
WshShell.Run "pythonw.exe ""{PROJECT_ROOT / 'tray_app.py'}""", 0, False
'''
            STARTUP_FILE.write_text(vbs_content, encoding="utf-8")
            safe_notify(icon, "Đã bật tự khởi động cùng Windows!", "Antigravity Hub")
        except Exception as e:
            safe_notify(icon, f"Lỗi tạo startup: {e}", "Antigravity Hub")

def get_status_text(item=None):
    total = len(account_mgr.accounts)
    pro = sum(1 for a in account_mgr.accounts.values() if a.plan_type == "PRO")
    return f"📊 Trạng thái: {total} Accs ({pro} Pro)"

def exit_action(icon, item=None):
    icon.stop()

def main():
    # 1. Start Uvicorn in background thread
    server_thread = UvicornServerThread()
    server_thread.start()

    # Give server a moment to bind port
    time.sleep(1)

    # 2. Build Tray Menu
    menu = pystray.Menu(
        pystray.MenuItem("🌐 Mở Web Dashboard", open_dashboard, default=True),
        pystray.MenuItem("🔄 Làm Mới Quota Toàn Bộ", refresh_quotas_action),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(get_status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("⚡ Chạy Ứng Dụng", pystray.Menu(
            pystray.MenuItem("Hermes Agent", run_hermes_action),
            pystray.MenuItem("OpenAI Codex", run_codex_action),
            pystray.MenuItem("Claude Code", run_claude_action),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "🚀 Khởi Động Cùng Windows",
            toggle_startup,
            checked=is_startup_enabled
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ Thoát Hoàn Toàn", exit_action)
    )

    image = get_or_create_icon()
    icon = pystray.Icon(
        "AntigravityHub",
        image,
        f"Antigravity API Hub (Port {PORT})",
        menu=menu
    )

    # Safely notify on first launch
    def on_ready(i):
        safe_notify(
            i,
            f"Gateway đang chạy ngầm trên cổng {PORT}.\nNhấp đúp chuột vào icon để mở Web Dashboard.",
            "Antigravity API Hub Sẵn Sàng"
        )

    icon.run(setup=on_ready)

    # On exit
    server_thread.stop()
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        with open(PROJECT_ROOT / "crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- CRASH AT {time.ctime()} ---\n")
            traceback.print_exc(file=f)


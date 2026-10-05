"""Start Technician AI on this computer (run by start.bat in the Windows package).

First run asks for an API key (Gemini, Claude or OpenAI — detected from the key)
and writes .env; every run opens the browser already logged in to the local workspace.
"""
import io
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
# Messages are bilingual; without this, Windows output redirected to a file or
# pipe uses the legacy code page and crashes on the Chinese text.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
BUNDLED_KEY_FILE = ROOT / "gemini_key.txt"  # written by packaging/build_windows.ps1 -GeminiKey
PORT = int(os.environ.get("PORT", "8000"))


# Provider settings written to .env. Claude has no embeddings API, so with a
# Claude key retrieval falls back to keyword search.
PROVIDERS = {
    "google": ("Google Gemini", [
        "LLM_PROVIDER=google",
        "GOOGLE_API_KEY={key}",
        "TECHNICIAN_AI_MODEL=gemini-3.1-flash-lite",
        "EMBED_PROVIDER=google",
        "EMBED_DIM=512",
    ]),
    "anthropic": ("Anthropic Claude", [
        "LLM_PROVIDER=anthropic",
        "ANTHROPIC_API_KEY={key}",
        "TECHNICIAN_AI_MODEL=claude-sonnet-5-5",
    ]),
    "openai": ("OpenAI", [
        "LLM_PROVIDER=openai",
        "OPENAI_API_KEY={key}",
        "TECHNICIAN_AI_MODEL=gpt-6.1-sol",
        "EMBED_PROVIDER=openai",
        "EMBED_DIM=512",
    ]),
}
COMMON_SETTINGS = [
    "USE_LLM_TAGGER=false",
    "USE_VISION_INGEST=true",
    "VISION_ALL_PAGES=true",
    "VISION_PAGE_RANGE=1-30",
]


def detect_provider(key: str) -> str | None:
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("sk-"):
        return "openai"
    if key.startswith(("AIza", "AQ.")):
        return "google"
    return None


def ask_provider() -> str:
    print("无法识别这个 key 属于哪一家，请选择 / Which provider is this key from?")
    print("  1) Google Gemini   2) Anthropic Claude   3) OpenAI")
    choices = {"1": "google", "2": "anthropic", "3": "openai"}
    choice = ""
    while choice not in choices:
        choice = input("输入 1、2 或 3 后按回车 / Enter 1, 2 or 3: ").strip()
    return choices[choice]


def first_run_setup() -> None:
    if BUNDLED_KEY_FILE.exists():
        key = BUNDLED_KEY_FILE.read_text(encoding="utf-8").strip()
    else:
        print("=" * 60)
        print(" 首次使用设置 / First-time setup")
        print("=" * 60)
        print("需要一个 AI 的 API key，Gemini、Claude 或 OpenAI 任意一家都可以。")
        print("You need an API key from Gemini, Claude, or OpenAI.")
        print("没有的话，可以免费申请 Gemini key / No key? Get a free Gemini key:")
        print("  https://aistudio.google.com/apikey")
        print()
        key = ""
        while not key:
            key = input("粘贴 API key 后按回车 / Paste the key and press Enter: ").strip()
    provider = detect_provider(key) or ask_provider()
    name, settings = PROVIDERS[provider]
    lines = [s.format(key=key) for s in settings] + COMMON_SETTINGS
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已保存，使用 {name} / Saved, using {name}.")
    print("(要更换 key，删除 .env 文件和 data 文件夹后重新运行 / to change it, delete .env and the data folder)")
    print()


if not ENV_FILE.exists():
    first_run_setup()

from technician_ai import workspaces  # noqa: E402

if not workspaces.list_all():
    workspaces.create("Local", use_existing_data=True)
code = next(iter(workspaces.list_all()))
url = f"http://localhost:{PORT}/?code={code}"


def lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packets sent; just picks the outbound interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


print("Technician AI 已启动 / is running:")
print(f"  本机 / This computer:  {url}")
ip = lan_ip()
if ip:
    # The access code in the link lets phones on the same WiFi log straight in.
    lan_url = f"http://{ip}:{PORT}/?code={code}"
    print(f"  手机 / Phone (same WiFi):  {lan_url}")
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(lan_url)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        sys.stdout.flush()
        sys.stdout.buffer.write(("\n" + buf.getvalue() + "  用手机扫码 / Scan with your phone\n").encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        pass
print("关闭此窗口即停止 / Close this window to stop.")
threading.Timer(3, webbrowser.open, args=[url]).start()

import uvicorn  # noqa: E402

uvicorn.run("technician_ai.api:app", host="0.0.0.0", port=PORT)

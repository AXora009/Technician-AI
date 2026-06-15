"""Local development entrypoint for the Technician AI API."""

import os

from technician_ai.api import app  # noqa: F401  re-exported for uvicorn

if __name__ == "__main__":
    import io
    import socket
    import sys
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "127.0.0.1"

    url = f"http://{lan_ip}:{port}"

    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        qr_text = buf.getvalue()
        separator = "-" * 44
        output = f"\n{separator}\n  Technician AI  --  {url}\n{separator}\n{qr_text}  Scan with your phone (same WiFi)\n{separator}\n"
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        print(f"\n  Technician AI running at: {url}\n")

    uvicorn.run("technician_ai.api:app", host="0.0.0.0", port=port, reload=True)

import os
import asyncio
import threading
import dns.resolver
from pyrogram import Client, idle
from http.server import BaseHTTPRequestHandler, HTTPServer
from database import setup_db, delete_worker
# Tambahkan ini di bagian paling atas file main.py
from database import get_my_admin_groups, update_config, get_config

# ── Fix DNS Termux ─────────────────────────────────────────────────────────────
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['223.5.5.5', '223.6.6.6']

# ── Env ────────────────────────────────────────────────────────────────────────
API_ID    = int(os.environ.get("API_ID", 0))
API_HASH  = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ── Pyrogram Client ────────────────────────────────────────────────────────────
app = Client(
    "antispam_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins"),
)


# ── Health Check ───────────────────────────────────────────────────────────────
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Antispam is Online 2026")

    def log_message(self, *args):   # Matikan log bawaan HTTPServer (hemat I/O)
        pass


def run_health_check():
    try:
        port = int(os.environ.get("PORT", 8000))
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[HealthCheck] Error: {e}")


# ── Entry Point ────────────────────────────────────────────────────────────────
async def main():
    threading.Thread(target=run_health_check, daemon=True).start()
    await setup_db()
    asyncio.create_task(delete_worker(app))

    while True:
        try:
            await app.start()
            print("🚀 Bot Antispam aktif!")
            await idle()
            break
        except Exception as e:
            print(f"⚠️  Koneksi error: {e} — rekonek 5 detik...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot dihentikan.")
    finally:
        try:
            # Kita coba hentikan paksa tanpa mengecek status
            loop.run_until_complete(app.stop())
        except Exception:
            pass # Abaikan jika sudah tertutup

        loop.close()
        print("\n🛑 Bot berhasil dimatikan dengan bersih.")

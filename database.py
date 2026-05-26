import os
import time
import asyncio
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.enums import ChatMemberStatus
from dotenv import load_dotenv

load_dotenv()

# ── Konfigurasi Database ──────────────────────────────────────────────────────
MONGO_URL        = os.environ.get("MONGO_URL", "")
mongo_client     = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
db               = mongo_client["antispam"]
config_db        = db["status"]
messages_db      = db["seen_messages"]
regex_db         = db["regex_list"]

# ── Konstanta ─────────────────────────────────────────────────────────────────
GLOBAL_EXPIRY        = 15
DEFAULT_LOCAL_EXPIRY = 3600
TZ_WIB               = timezone(timedelta(hours=7))

# ── Cache ringan (in-memory) ──────────────────────────────────────────────────
_config_cache: dict[int, tuple[dict, float]] = {}   # {chat_id: (cfg, ts)}
_admin_cache:  dict[tuple, tuple[bool, float]] = {}  # {(chat,user): (bool, ts)}
CONFIG_TTL = 60   # detik sebelum cache config expired
ADMIN_TTL  = 120  # detik sebelum cache admin expired

# ── Queue hapus pesan (batch) ─────────────────────────────────────────────────
delete_queue: asyncio.Queue = asyncio.Queue()

# ── FSM State: menunggu input ID dari admin ───────────────────────────────────
# Format: {user_id: {"action": "wl"|"unwl", "chat_id": int, "msg_id": int}}
pending_wl_state: dict[int, dict] = {}


# ── Setup DB ──────────────────────────────────────────────────────────────────
async def setup_db():
    await messages_db.create_index("createdAt", expireAfterSeconds=86400)
    print("✅ Database & TTL Index (24 Jam) Aktif.")


# ── Config ────────────────────────────────────────────────────────────────────
async def get_config(chat_id: int) -> dict:
    now = time.monotonic()
    cached = _config_cache.get(chat_id)
    if cached and (now - cached[1]) < CONFIG_TTL:
        return cached[0]

    cfg = await config_db.find_one({"chat_id": chat_id})
    if not cfg:
        cfg = {
            "local":     True,
            "global":    True,
            "expiry":    DEFAULT_LOCAL_EXPIRY,
            "bio_check": False,
        }
    _config_cache[chat_id] = (cfg, now)
    return cfg


async def update_config(chat_id: int, key: str, value) -> None:
    await config_db.update_one(
        {"chat_id": chat_id}, {"$set": {key: value}}, upsert=True
    )
    # Invalidate cache agar nilai baru langsung berlaku
    _config_cache.pop(chat_id, None)


# ── Admin check ───────────────────────────────────────────────────────────────
async def is_admin(client, chat_id: int, user_id) -> bool:
    if not user_id:
        return False
    now = time.monotonic()
    key = (chat_id, user_id)
    cached = _admin_cache.get(key)
    if cached and (now - cached[1]) < ADMIN_TTL:
        return cached[0]

    try:
        member = await client.get_chat_member(chat_id, user_id)
        result = member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        result = False

    _admin_cache[key] = (result, now)
    return result


# ── Auto-delete helper ────────────────────────────────────────────────────────
async def auto_delete_reply(messages: list, delay: int = 5) -> None:
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass


# ── Delete worker (batch per chat_id) ────────────────────────────────────────
async def delete_worker(client) -> None:
    """
    Mengumpulkan semua permintaan hapus dalam 0.3 detik lalu
    mengirim satu panggilan delete_messages per chat_id (hemat API call).
    """
    pending: dict[int, list[int]] = {}

    async def flush():
        for cid, mids in list(pending.items()):
            if mids:
                try:
                    await client.delete_messages(cid, mids)
                except Exception:
                    pass
        pending.clear()

    while True:
        try:
            # Tunggu item pertama
            cid, mids = await asyncio.wait_for(delete_queue.get(), timeout=0.3)
            pending.setdefault(cid, []).extend(mids)
            delete_queue.task_done()

            # Kuras sisa queue tanpa blocking
            while not delete_queue.empty():
                try:
                    cid2, mids2 = delete_queue.get_nowait()
                    pending.setdefault(cid2, []).extend(mids2)
                    delete_queue.task_done()
                except asyncio.QueueEmpty:
                    break

            await flush()

        except asyncio.TimeoutError:
            # Tidak ada item — flush jika ada sisa
            if pending:
                await flush()


# ── Ambil grup yang user jadi admin ──────────────────────────────────────────
async def get_my_admin_groups(client, user_id: int):
    admin_groups = []
    cursor = config_db.find({})
    async for doc in cursor:
        chat_id = doc.get("chat_id")
        if not chat_id:
            continue
        if await is_admin(client, chat_id, user_id):
            try:
                chat = await client.get_chat(chat_id)
                admin_groups.append({"id": chat_id, "title": chat.title})
            except Exception:
                continue
    return admin_groups

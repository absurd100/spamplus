import httpx
import asyncio
from database import db, auto_delete_reply, is_admin, delete_queue, update_config
from pyrogram import Client, filters
from pyrogram.types import Message

DELAY_NOTIF   = 10
whitelist_col = db["whitelist_per_group"]


# ── CAS API ───────────────────────────────────────────────────────────────────
async def is_cas_banned(user_id: int) -> bool:
    url = f"https://api.cas.chat/check?user_id={user_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(url)
            return r.status_code == 200 and r.json().get("ok", False)
    except Exception:
        return False


# ── /wl ───────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("wl") & filters.group)
async def add_whitelist(client: Client, message: Message):
    cid = message.chat.id
    if not await is_admin(client, cid, message.from_user.id if message.from_user else None):
        return

    target_id = _resolve_target(message)
    if target_id is None:
        res = await message.reply_text("❌ **ID tidak ditemukan.** Reply ke user atau kirim `/wl <ID>`.")
        return await auto_delete_reply([res, message], delay=DELAY_NOTIF)

    await whitelist_col.update_one(
        {"user_id": target_id, "chat_id": cid},
        {"$set": {"status": "whitelisted"}},
        upsert=True,
    )
    res = await message.reply_text(f"✅ **Whitelisted:** `{target_id}`")
    await auto_delete_reply([res, message], delay=DELAY_NOTIF)


# ── /unwl ─────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("unwl") & filters.group)
async def remove_whitelist(client: Client, message: Message):
    cid = message.chat.id
    if not await is_admin(client, cid, message.from_user.id if message.from_user else None):
        return

    target_id = _resolve_target(message)
    if target_id is None:
        res = await message.reply_text("❌ **ID tidak ditemukan.** Reply ke user atau kirim `/unwl <ID>`.")
        return await auto_delete_reply([res, message], delay=DELAY_NOTIF)

    result = await whitelist_col.delete_one({"user_id": target_id, "chat_id": cid})
    text = (f"🗑️ **Unwhitelisted:** `{target_id}`"
            if result.deleted_count else "❌ ID **tidak ditemukan** di whitelist.")
    res = await message.reply_text(text)
    await auto_delete_reply([res, message], delay=DELAY_NOTIF)


# ── CAS Auto-Mod ──────────────────────────────────────────────────────────────
@Client.on_message(filters.group & ~filters.service, group=-1)
async def cas_auto_mod(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    uid     = message.from_user.id
    chat_id = message.chat.id

    if await whitelist_col.find_one({"user_id": uid, "chat_id": chat_id}):
        return
    if await is_admin(client, chat_id, uid):
        return

    if await is_cas_banned(uid):
        try:
            await client.ban_chat_member(chat_id, uid)
            await delete_queue.put((chat_id, [message.id]))
            alert = await client.send_message(
                chat_id,
                f"🛡️ **CAS Anti-Spam**\n"
                f"├ **User:** {message.from_user.mention}\n"
                f"└ **Alasan:** Terdeteksi di database global spammer.",
            )
            await auto_delete_reply([alert], delay=DELAY_NOTIF)
        except Exception as e:
            print(f"⚠️  CAS-Error [chat={chat_id}]: {e}")

@Client.on_message(filters.service)
async def handle_service_messages(client, message):
    # Cek jika bot diundang ke grup
    if message.new_chat_members:
        for member in message.new_chat_members:
            if member.id == (await client.get_me()).id:
                # Simpan ke database saat bot masuk
                await update_config(message.chat.id, "local", True)
                await message.reply("✅ Bot berhasil aktif! Proteksi otomatis dimulai.")

# ── Helper ────────────────────────────────────────────────────────────────────
def _resolve_target(message: Message):
    """Ambil target user_id dari reply atau argumen command."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    if len(message.command) > 1:
        try:
            return int(message.command[1])
        except ValueError:
            pass
    return None

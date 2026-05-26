import re
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.raw import functions
from database import auto_delete_reply, is_admin, delete_queue, get_config, update_config

# Pattern link / username di Bio
LINK_PATTERN = re.compile(
    r"(@\S+|https?://\S+|t\.me/\S+|bit\.ly/\S+|linktr\.ee/\S+)",
    re.IGNORECASE,
)


# ── /biocheck on|off ──────────────────────────────────────────────────────────
@Client.on_message(filters.command("biocheck") & filters.group)
async def toggle_bio_check(client: Client, message: Message):
    cid = message.chat.id
    uid = message.from_user.id if message.from_user else None

    if not await is_admin(client, cid, uid):
        return

    if len(message.command) < 2:
        res = await message.reply_text(
            "⚠️ **Format:** `/biocheck on` atau `/biocheck off`"
        )
        return await auto_delete_reply([res, message], delay=5)

    arg = message.command[1].lower()
    if arg == "on":
        await update_config(cid, "bio_check", True)
        res = await message.reply_text(
            "✅ **Bio Link Detector AKTIF**\n"
            "└ Pesan member (non-admin) dengan link di bio akan dihapus."
        )
    elif arg == "off":
        await update_config(cid, "bio_check", False)
        res = await message.reply_text("🔕 **Bio Link Detector NONAKTIF.**")
    else:
        res = await message.reply_text("❓ Gunakan argumen `on` atau `off`.")

    await auto_delete_reply([res, message], delay=5)


# ── Core filter: scan bio setiap pesan ───────────────────────────────────────
@Client.on_message(filters.group & ~filters.service, group=1)
async def main_bio_filter(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    cid = message.chat.id
    uid = message.from_user.id

    cfg = await get_config(cid)
    if not cfg.get("bio_check", False):
        return

    if await is_admin(client, cid, uid):
        return

    try:
        full_user = await client.invoke(
            functions.users.GetFullUser(id=await client.resolve_peer(uid))
        )
        bio = full_user.full_user.about or ""
        if LINK_PATTERN.search(bio):
            await delete_queue.put((cid, [message.id]))
            print(f"🛡️ Bio-Hit: uid={uid} chat={cid} bio={bio[:30]}...")
    except Exception as e:
        print(f"⚠️  Bio-Error [chat={cid}]: {e}")

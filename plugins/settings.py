import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_config, update_config, is_admin, auto_delete_reply, DEFAULT_LOCAL_EXPIRY


@Client.on_message(
    filters.command(["setlocal", "setglobal", "setwaktu", "status", "setbio", "antigcast"])
    & filters.group
)
async def admin_handlers(client, message):
    if not message.from_user:
        return

    cid = message.chat.id
    cmd = message.command[0].lower()

    # ── /antigcast — bisa dilihat semua member ────────────────────────────────
    if cmd == "antigcast":
        me = await client.get_me()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👀 Lihat Detail Bot", url=f"t.me/{me.username}?start=help")
        ]])
        res = await message.reply(
            "🛡️ **Grup ini dilindungi Sistem Antispam**\n"
            "└ Spam & konten berbahaya diblokir secara otomatis.",
            reply_markup=keyboard,
        )
        return asyncio.create_task(auto_delete_reply([message, res], 5))

    # ── Perintah lain: khusus admin ───────────────────────────────────────────
    if not await is_admin(client, cid, message.from_user.id):
        return

    cfg = await get_config(cid)
    res = None

    # ── /status ───────────────────────────────────────────────────────────────
    if cmd == "status":
        def _flag(val): return "🟢 AKTIF" if val else "🔴 OFF"
        expiry_min = cfg.get("expiry", DEFAULT_LOCAL_EXPIRY) // 60
        res = await message.reply(
            "╔══════════════════════════╗\n"
            "║  🖥️  DASHBOARD KEAMANAN  ║\n"
            "╚══════════════════════════╝\n"
            f"├ 📡 Proteksi Lokal   : `{_flag(cfg.get('local', True))}`\n"
            f"├ 🌐 Proteksi Global  : `{_flag(cfg.get('global', True))}`\n"
            f"├ 🔍 Bio Link Detector: `{_flag(cfg.get('bio_check', False))}`\n"
            f"└ ⏱️  Jendela Deteksi  : `{expiry_min} menit`"
        )

    # ── /setwaktu ─────────────────────────────────────────────────────────────
    elif cmd == "setwaktu":
        if len(message.command) > 1 and message.command[1].isdigit():
            m = int(message.command[1])
            await update_config(cid, "expiry", m * 60)
            res = await message.reply(f"✅ Jendela deteksi lokal: `{m} menit`.")
        else:
            res = await message.reply("⚠️ **Format:** `/setwaktu <menit>`")

    # ── /setlocal | /setglobal | /setbio ─────────────────────────────────────
    elif cmd in ("setlocal", "setglobal", "setbio"):
        if len(message.command) > 1:
            mode = message.command[1].lower() == "on"
            key_map = {"setlocal": "local", "setglobal": "global", "setbio": "bio_check"}
            key = key_map[cmd]
            await update_config(cid, key, mode)
            label = "ON ✅" if mode else "OFF 🔴"
            res = await message.reply(f"✅ `{key.upper()}` → `{label}`")
        else:
            res = await message.reply(f"⚠️ **Format:** `/{cmd} on` atau `/{cmd} off`")

    if res:
        asyncio.create_task(auto_delete_reply([message, res], 10))

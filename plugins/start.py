import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.enums import ParseMode
from database import (
    get_my_admin_groups, update_config, get_config,
    db, pending_wl_state, is_admin
)

whitelist_col = db["whitelist_per_group"]

WAIT_TIMEOUT = 30  # detik tunggu admin kirim ID


# ── /start di private ─────────────────────────────────────────────────────────
@Client.on_message(filters.command("start") & filters.private)
async def start_private(client, message: Message):
    me = await client.get_me()
    add_url = f"t.me/{me.username}?startgroup=true&admin=delete_messages"

    text = (
        "<b>╔══════════════════════════╗</b>\n"
        "<b>║      🛡️ BOT ANTISPAM      ║</b>\n"
        "<b>╚══════════════════════════╝</b>\n\n"
        "Sistem mitigasi spam massal lintas grup secara <b>real-time</b>.\n\n"
        "<b>📖 CARA PENGGUNAAN:</b>\n"
        "① Klik tombol di bawah → tambahkan ke grup.\n"
        "② Berikan izin <b>Administrator + Hapus Pesan</b>. Untuk mengaktifkan CAS, berikan ijin blokir pengguna pada bot jika diperlukan.\n"
        "③ Bot langsung aktif memantau secara otomatis."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Aktifkan Proteksi di Grup", url=add_url)],
        [InlineKeyboardButton("⚙️ Admin Group Menu", callback_data="admin_menu")]
    ])

    await message.reply(text=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


# ── Kembali ke start ──────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex("^start$"))
async def back_to_start(client, callback: CallbackQuery):
    me = await client.get_me()
    add_url = f"t.me/{me.username}?startgroup=true&admin=delete_messages"

    text = (
        "<b>╔══════════════════════════╗</b>\n"
        "<b>║      🛡️ BOT ANTISPAM      ║</b>\n"
        "<b>╚══════════════════════════╝</b>\n\n"
        "Sistem mitigasi spam massal lintas grup secara <b>real-time</b>.\n\n"
        "<b>📖 CARA PENGGUNAAN:</b>\n"
        "① Klik tombol di bawah → tambahkan ke grup.\n"
        "② Berikan izin <b>Administrator + Hapus Pesan</b>. Untuk mengaktifkan CAS, berikan ijin blokir pengguna pada bot jika diperlukan.\n"
        "③ Bot langsung aktif memantau secara otomatis."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Aktifkan Proteksi di Grup", url=add_url)],
        [InlineKeyboardButton("⚙️ Admin Group Menu", callback_data="admin_menu")]
    ])

    await callback.message.edit(text=text, reply_markup=keyboard)


# ── Admin Menu ────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex("^admin_menu$"))
async def admin_menu_handler(client, callback: CallbackQuery):
    await callback.answer("Memuat daftar grup...")
    groups = await get_my_admin_groups(client, callback.from_user.id)

    if not groups:
        await callback.message.edit(
            "❌ Tidak ditemukan grup dimana Anda adalah admin.\n"
            "<i>Pastikan Anda admin di grup tersebut.</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_menu")],
                [InlineKeyboardButton("🔙 Kembali", callback_data="start")]
            ])
        )
        return

    buttons = [
        [InlineKeyboardButton(g["title"], callback_data=f"manage_{g['id']}")]
        for g in groups
    ]
    buttons.append([InlineKeyboardButton("🔄 Refresh Daftar", callback_data="admin_menu")])
    buttons.append([InlineKeyboardButton("🔙 Kembali", callback_data="start")])

    await callback.message.edit(
        "<b>Pilih grup untuk diatur:</b>",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ── Pengaturan per grup ───────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^manage_(-?\d+)$"))
async def manage_group_settings(client, callback: CallbackQuery):
    chat_id = int(callback.data.split("_", 1)[1])
    cfg = await get_config(chat_id)

    local_txt  = "✅ ON" if cfg.get("local", True) else "❌ OFF"
    global_txt = "✅ ON" if cfg.get("global", True) else "❌ OFF"
    bio_txt    = "✅ ON" if cfg.get("bio_check", False) else "❌ OFF"
    waktu      = cfg.get("expiry", 3600) // 60

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🔁 Local: {local_txt}", callback_data=f"toggle_local_{chat_id}"),
        ],
        [
            InlineKeyboardButton(f"🔁 Global: {global_txt}", callback_data=f"toggle_global_{chat_id}"),
        ],
        [
            InlineKeyboardButton(f"🔁 Bio Check: {bio_txt}", callback_data=f"toggle_bio_check_{chat_id}"),
        ],
        [
            InlineKeyboardButton(f"⏱ Waktu: {waktu}m", callback_data="none"),
            InlineKeyboardButton("➖", callback_data=f"time_dec_{chat_id}"),
            InlineKeyboardButton("➕", callback_data=f"time_inc_{chat_id}"),
        ],
        [
            InlineKeyboardButton("✅ Whitelist CAS", callback_data=f"wl_cas_{chat_id}"),
            InlineKeyboardButton("❌ Un-Whitelist CAS", callback_data=f"unwl_cas_{chat_id}"),
        ],
        [InlineKeyboardButton("🔙 Kembali ke Daftar Grup", callback_data="admin_menu")]
    ])

    await callback.message.edit(
        f"<b>⚙️ Pengaturan Grup</b>\n"
        f"<b>ID:</b> <code>{chat_id}</code>",
        reply_markup=keyboard
    )


# ── Toggle local / global / bio_check ────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^toggle_(local|global|bio_check)_(-?\d+)$"))
async def handle_toggle(client, callback: CallbackQuery):
    parts   = callback.data.split("_", 2)
    # parts: ['toggle', 'local'|'global'|'bio', 'check_CHATID' atau 'CHATID']
    # Lebih aman pakai regex match
    import re
    m = re.match(r"^toggle_(local|global|bio_check)_(-?\d+)$", callback.data)
    key     = m.group(1)
    chat_id = int(m.group(2))

    cfg     = await get_config(chat_id)
    new_val = not cfg.get(key, True)
    await update_config(chat_id, key, new_val)

    callback.data = f"manage_{chat_id}"
    await manage_group_settings(client, callback)


# ── Atur waktu ────────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^time_(inc|dec)_(-?\d+)$"))
async def handle_time(client, callback: CallbackQuery):
    import re
    m      = re.match(r"^time_(inc|dec)_(-?\d+)$", callback.data)
    action = m.group(1)
    chat_id = int(m.group(2))

    cfg            = await get_config(chat_id)
    current_expiry = cfg.get("expiry", 3600)
    new_expiry     = (current_expiry + 3600) if action == "inc" else max(3600, current_expiry - 3600)

    await update_config(chat_id, "expiry", new_expiry)

    callback.data = f"manage_{chat_id}"
    await manage_group_settings(client, callback)


# ── FSM: Whitelist / Un-Whitelist CAS via inline ──────────────────────────────
@Client.on_callback_query(filters.regex(r"^(wl|unwl)_cas_(-?\d+)$"))
async def handle_wl_request(client, callback: CallbackQuery):
    import re
    m       = re.match(r"^(wl|unwl)_cas_(-?\d+)$", callback.data)
    action  = m.group(1)   # "wl" atau "unwl"
    chat_id = int(m.group(2))

    user_id = callback.from_user.id
    label   = "Whitelist" if action == "wl" else "Un-Whitelist"

    # Simpan state FSM
    pending_wl_state[user_id] = {
        "action":  action,
        "chat_id": chat_id,
        "msg_id":  callback.message.id,
    }

    await callback.message.edit(
        f"⏳ <b>Mode Tunggu — {label} CAS</b>\n\n"
        f"Kirim <b>ID User</b> (angka) dalam <b>30 detik</b>.\n"
        f"Contoh: <code>123456789</code>\n\n"
        f"<i>Ketik /batal untuk membatalkan.</i>"
    )

    # Auto-cancel setelah 30 detik jika tidak ada input
    await asyncio.sleep(30)
    if user_id in pending_wl_state:
        pending_wl_state.pop(user_id, None)
        try:
            await callback.message.edit(
                "⌛ <b>Waktu habis.</b> Tidak ada ID yang dikirim.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali", callback_data=f"manage_{chat_id}")]
                ])
            )
        except Exception:
            pass


# ── Handler pesan private: tangkap ID dari FSM ────────────────────────────────
@Client.on_message(filters.private & filters.text & ~filters.command(["start", "batal"]))
async def handle_wl_input(client, message: Message):
    user_id = message.from_user.id
    state   = pending_wl_state.get(user_id)

    if not state:
        return  # tidak ada state aktif, abaikan

    # Validasi input: harus angka
    raw = message.text.strip()
    if not raw.lstrip("-").isdigit():
        err = await message.reply("❌ ID tidak valid. Kirim angka saja, contoh: <code>123456789</code>")
        await asyncio.sleep(5)
        try:
            await err.delete()
            await message.delete()
        except Exception:
            pass
        return

    target_id = int(raw)
    action    = state["action"]
    chat_id   = state["chat_id"]

    # Hapus state
    pending_wl_state.pop(user_id, None)

    # Lakukan aksi whitelist / unwhitelist
    if action == "wl":
        await whitelist_col.update_one(
            {"user_id": target_id, "chat_id": chat_id},
            {"$set": {"status": "whitelisted"}},
            upsert=True,
        )
        result_text = f"✅ <b>Whitelisted:</b> <code>{target_id}</code>"
    else:
        result = await whitelist_col.delete_one({"user_id": target_id, "chat_id": chat_id})
        if result.deleted_count:
            result_text = f"🗑️ <b>Un-Whitelisted:</b> <code>{target_id}</code>"
        else:
            result_text = f"❌ ID <code>{target_id}</code> <b>tidak ditemukan</b> di whitelist."

    # Ambil daftar whitelist terbaru untuk grup ini
    wl_list = await _get_whitelist_text(chat_id)

    # Edit pesan sebelumnya (mode tunggu) + tambahkan daftar whitelist
    try:
        from pyrogram.types import InputMediaPhoto  # noqa
        await client.edit_message_text(
            chat_id=message.chat.id,
            message_id=state["msg_id"],
            text=f"{result_text}\n\n{wl_list}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Kembali ke Pengaturan", callback_data=f"manage_{chat_id}")]
            ])
        )
    except Exception:
        pass

    # Hapus pesan ID yang dikirim admin
    try:
        await message.delete()
    except Exception:
        pass


# ── /batal — batalkan FSM ─────────────────────────────────────────────────────
@Client.on_message(filters.command("batal") & filters.private)
async def cancel_wl(client, message: Message):
    user_id = message.from_user.id
    if pending_wl_state.pop(user_id, None):
        res = await message.reply("✅ Dibatalkan.")
    else:
        res = await message.reply("Tidak ada proses yang aktif.")
    await asyncio.sleep(3)
    try:
        await res.delete()
        await message.delete()
    except Exception:
        pass


# ── Helper: format daftar whitelist ──────────────────────────────────────────
async def _get_whitelist_text(chat_id: int) -> str:
    docs = whitelist_col.find({"chat_id": chat_id})
    ids  = [str(doc["user_id"]) async for doc in docs]
    if not ids:
        return "📋 <b>Whitelist CAS:</b> <i>Kosong</i>"
    lines = "\n".join(f"  • <code>{uid}</code>" for uid in ids)
    return f"📋 <b>Whitelist CAS ({len(ids)} user):</b>\n{lines}"

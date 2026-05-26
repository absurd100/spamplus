import os
import re
from pyrogram import Client, filters
from database import regex_db

OWNER_ID = int(os.environ.get("OWNER_ID", 0))


@Client.on_message(
    filters.command(["addregex", "delregex", "infobot"]) & filters.user(OWNER_ID)
)
async def owner_management(client, message):
    cmd = message.command[0].lower()

    # ── /addregex ─────────────────────────────────────────────────────────────
    if cmd == "addregex":
        if len(message.command) < 2:
            return await message.reply("⚠️ **Format:** `/addregex pola_regex`")
        pattern = " ".join(message.command[1:])
        try:
            re.compile(pattern)
        except re.error:
            return await message.reply("❌ Pattern regex **tidak valid**.")
        await regex_db.update_one(
            {"pattern": pattern}, {"$set": {"pattern": pattern}}, upsert=True
        )
        await message.reply(f"✅ Regex disimpan:\n`{pattern}`")

    # ── /delregex ─────────────────────────────────────────────────────────────
    elif cmd == "delregex":
        if len(message.command) < 2:
            return await message.reply("⚠️ **Format:** `/delregex pola_regex`")
        pattern = " ".join(message.command[1:])
        result = await regex_db.delete_one({"pattern": pattern})
        if result.deleted_count:
            await message.reply(f"🗑️ Regex dihapus:\n`{pattern}`")
        else:
            await message.reply("❌ Pattern **tidak ditemukan** di database.")

    # ── /infobot ──────────────────────────────────────────────────────────────
    elif cmd == "infobot":
        patterns = [doc["pattern"] async for doc in regex_db.find({})]
        if patterns:
            lines = "\n".join(f"• `{p}`" for p in patterns)
            text  = f"📋 **Daftar Regex Blacklist** ({len(patterns)} pattern):\n\n{lines}"
        else:
            text = "📋 **Daftar Regex Blacklist:** _Kosong._"
        await message.reply(text)

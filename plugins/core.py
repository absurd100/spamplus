import re
import time
import hashlib
import asyncio
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters
from rapidfuzz import fuzz
from database import (
    messages_db, regex_db, get_config, is_admin,
    delete_queue, GLOBAL_EXPIRY, DEFAULT_LOCAL_EXPIRY, TZ_WIB,
)

# ── Cache Regex (refresh tiap 5 menit, hemat query Mongo) ─────────────────────
_regex_cache:      list[re.Pattern] = []
_regex_cache_ts:   float = 0.0
REGEX_CACHE_TTL  = 300   # detik


async def _get_regex_patterns() -> list[re.Pattern]:
    global _regex_cache, _regex_cache_ts
    now = time.monotonic()
    if now - _regex_cache_ts < REGEX_CACHE_TTL:
        return _regex_cache
    _regex_cache = [
        re.compile(doc["pattern"], re.IGNORECASE)
        async for doc in regex_db.find({})
    ]
    _regex_cache_ts = now
    return _regex_cache


def simplify_text(text: str) -> str:
    """Normalisasi: angka→huruf mirip, huruf berulang, hanya a-z."""
    if not text:
        return ""
    text = text.lower()
    for ch, rep in {'1':'i','0':'o','3':'e','4':'a','5':'s','8':'b'}.items():
        text = text.replace(ch, rep)
    text = re.sub(r'(.)\1+', r'\1', text)   # hapus huruf berulang
    return re.sub(r'[^a-z]', '', text)


@Client.on_message(filters.group & ~filters.service, group=2)
async def main_core_filter(client, message):
    if not message.from_user:
        return

    cid, uid, mid = message.chat.id, message.from_user.id, message.id

    # ── Early exit: admin dilewati ────────────────────────────────────────────
    if await is_admin(client, cid, uid):
        return

    content = (message.text or message.caption or "").strip()
    if not content or content.startswith("/"):
        return

    cfg = await get_config(cid)

    # ── 1. Regex Blacklist ────────────────────────────────────────────────────
    for pattern in await _get_regex_patterns():
        if pattern.search(content):
            await delete_queue.put((cid, [mid]))
            return

    now_ts  = time.time()
    now_dt  = datetime.now(TZ_WIB)
    norm    = simplify_text(content)

    # ── 2. Anti Duplikasi Lokal ───────────────────────────────────────────────
    is_duplicate = False
    if cfg.get("local", True):
        cursor = messages_db.find(
            {"chat_id": cid, "user_id": uid, "type": "local_track"}
        ).sort("time", -1).limit(5)

        async for old in cursor:
            old_norm = old.get("norm_txt", "")
            if not old_norm:
                continue
            if fuzz.ratio(norm, old_norm) >= 90:
                if (now_ts - old["time"]) < cfg.get("expiry", DEFAULT_LOCAL_EXPIRY):
                    await delete_queue.put((cid, [old["msg_id"], mid]))
                    is_duplicate = True
                    break

    if is_duplicate:
        return

    # Simpan jejak lokal
    local_key = f"loc_{cid}_{uid}_{hashlib.md5(content.encode()).hexdigest()}"
    await messages_db.update_one(
        {"_id": local_key},
        {"$set": {
            "time":      now_ts,
            "msg_id":    mid,
            "chat_id":   cid,
            "user_id":   uid,
            "norm_txt":  norm,
            "type":      "local_track",
            "createdAt": now_dt,
        }},
        upsert=True,
    )

    # ── 3. Anti Duplikasi Global ──────────────────────────────────────────────
    # (Pesan ini tetap dicatat ke database sebagai pemicu,
    # meskipun grup ini mungkin memiliki fitur Global Spam = False)

    content_hash = hashlib.md5(content.encode()).hexdigest()
    global_key   = f"glob_{uid}_{content_hash}"
    existing     = await messages_db.find_one({"_id": global_key})

    if existing:
        if (now_ts - existing["time"]) < GLOBAL_EXPIRY:
            locs = existing.get("locations", [])
            # Tambahkan lokasi baru ke record agar tercatat sebagai pemicu
            if [cid, mid] not in locs:
                locs.append([cid, mid])
                await messages_db.update_one(
                    {"_id": global_key},
                    {"$set": {"locations": locs, "createdAt": now_dt}},
                )

            # Hapus hanya jika grup tersebut mengaktifkan fitur Global
            for loc_cid, loc_mid in locs:
                t_cfg = await get_config(loc_cid)
                # Hanya hapus jika grup tersebut mengaktifkan fitur Global
                if t_cfg.get("global", True):
                    await delete_queue.put((loc_cid, [loc_mid]))
        else:
            # Update waktu jika sudah expired
            await messages_db.update_one(
                {"_id": global_key},
                {"$set": {"time": now_ts, "createdAt": now_dt, "locations": [[cid, mid]]}},
            )
    else:
        # Rekam pertama kali
        await messages_db.insert_one({
            "_id":       global_key,
            "time":      now_ts,
            "createdAt": now_dt,
            "locations": [[cid, mid]],
        })

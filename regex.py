import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# ==========================================
# ⚙️ KONFIGURASI KREDENSIAL (ISI BAGIAN INI)
# ==========================================
API_ID = 12345678  # Ganti dengan API ID Mbah
API_HASH = "string_api_hash_mbah" # Ganti dengan API Hash Mbah
BOT_TOKEN = "123456:string_bot_token" # Ganti dengan Token Bot dari BotFather
MONGO_URI = "mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority" # Ganti dengan URI Mongo Mbah

# ==========================================
# 🚀 INISIALISASI BOT & DATABASE
# ==========================================
app = Client("bot_antispam_mbah", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["bot_anti_spam"]
koleksi_grup = db["grup_settings"]

# Penyimpanan State Admin sementara di RAM (Batal otomatis saat restart)
admin_states = {} # Format: {user_id: {"state": "waiting_...", "chat_id": -100...}}

print("🟢 [LOG ADMIN] Menjalankan Bot Mbah Bodho...")

# ==========================================
# 🧠 FUNGSI PARSER REGEX CUSTOM
# ==========================================
def bersihkan_teks(teks):
    """Menghapus simbol pengganggu (Anti-Bypass Obfuscation)"""
    if not teks: return ""
    teks_bersih = teks.lower()
    teks_bersih = re.sub(r"[.,_\-\*\/\\@\[\]\(\)\"\'\?\!\:\;\#\$\%\^\&\+] ", " ", teks_bersih)
    teks_bersih = re.sub(r"[.,_\-\*\/\\@\[\]\(\)\"\'\?\!\:\;\#\$\%\^\&]", "", teks_bersih)
    return teks_bersih

def cek_kata_terlarang(pesan_teks, aturan_custom):
    """Logika * + && dan ||"""
    teks_target = bersihkan_teks(pesan_teks)
    bagian_and = [bagian.strip() for bagian in aturan_custom.split('&&')]
    
    for bagian in bagian_and:
        pola_siap = re.escape(bagian).replace(r"\|\|", "|")
        pola_siap = pola_siap.replace(r"\*", ".*").replace(r"\+", ".+")
        
        if not re.search(pola_siap, teks_target):
            return False 
    return True

# ==========================================
# 🛠️ 1. PEMICU MENU PENGATURAN (DI GRUP)
# ==========================================
@app.on_message(filters.command("setting") & filters.group)
async def buka_menu_setting(client, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_title = message.chat.title
    
    # Cek apakah yang mengetik adalah Admin
    member = await client.get_chat_member(chat_id, user_id)
    if member.status not in ["administrator", "creator"]:
        return

    # Daftarkan / Update data grup ke MongoDB
    await koleksi_grup.update_one(
        {"_id": chat_id}, 
        {"$set": {"nama_grup": chat_title}}, 
        upsert=True
    )
    
    # Kirim Menu ke DM Admin
    teks_menu = (
        f"🔧 **Pengaturan Kata Terlarang**\n"
        f"Grup: **{chat_title}**\n\n"
        f"Silakan pilih menu manajemen di bawah ini:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Tambah Kata", callback_data=f"tambah_{chat_id}"),
         InlineKeyboardButton("➖ Hapus Kata", callback_data=f"hapus_{chat_id}")],
        [InlineKeyboardButton("📜 Daftar Kata", callback_data=f"daftar_{chat_id}"),
         InlineKeyboardButton("🧪 Sandbox", callback_data=f"sandbox_{chat_id}")],
        [InlineKeyboardButton("❌ Tutup", callback_data="tutup_menu")]
    ])
    
    try:
        await client.send_message(user_id, teks_menu, reply_markup=keyboard)
        await message.reply("✅ Menu pengaturan telah dikirim ke DM Anda, Mbah!")
        print(f"🔵 [LOG ADMIN] {message.from_user.first_name} membuka setting untuk grup {chat_title}")
    except Exception:
        await message.reply("❌ Saya tidak bisa mengirim DM. Tolong mulai chat DM (Start) dengan saya dulu ya.")

# ==========================================
# 🎛️ 2. HANDLER TOMBOL INLINE (DI DM)
# ==========================================
@app.on_callback_query()
async def tangani_tombol(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "tutup_menu":
        if user_id in admin_states: del admin_states[user_id]
        await callback_query.message.delete()
        return

    # Ekstrak aksi dan ID grup dari callback data
    aksi, chat_id = data.split("_", 1)
    chat_id = int(chat_id)
    grup_data = await koleksi_grup.find_one({"_id": chat_id})
    nama_grup = grup_data.get("nama_grup", "Grup") if grup_data else "Grup"
    
    # Tombol Kembali ke Menu Utama
    tombol_kembali = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_{chat_id}")]])

    if aksi == "menu":
        if user_id in admin_states: del admin_states[user_id]
        teks_menu = f"🔧 **Pengaturan Kata Terlarang**\nGrup: **{nama_grup}**\n\nSilakan pilih menu:"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Tambah", callback_data=f"tambah_{chat_id}"),
             InlineKeyboardButton("➖ Hapus", callback_data=f"hapus_{chat_id}")],
            [InlineKeyboardButton("📜 Daftar", callback_data=f"daftar_{chat_id}"),
             InlineKeyboardButton("🧪 Sandbox", callback_data=f"sandbox_{chat_id}")],
            [InlineKeyboardButton("❌ Tutup", callback_data="tutup_menu")]
        ])
        await callback_query.message.edit_text(teks_menu, reply_markup=keyboard)

    elif aksi == "tambah":
        admin_states[user_id] = {"state": "waiting_add", "chat_id": chat_id}
        teks = (
            f"➕ **Tambah Kata Terlarang ({nama_grup})**\n\n"
            "Kirimkan kata yang ingin diblokir. Anda bisa menggunakan:\n"
            "`*` = 0/lebih karakter (contoh: `j*udi`)\n"
            "`+` = 1/lebih karakter (contoh: `slot+`)\n"
            "`&&` = Harus ada semua (contoh: `link && video`)\n"
            "`||` = Salah satu ada (contoh: `judi || slot`)\n\n"
            "👇 _Ketik dan kirim aturannya sekarang..._"
        )
        await callback_query.message.edit_text(teks, reply_markup=tombol_kembali)

    elif aksi == "hapus":
        admin_states[user_id] = {"state": "waiting_remove", "chat_id": chat_id}
        await callback_query.message.edit_text(
            f"➖ **Hapus Kata Terlarang ({nama_grup})**\n\nSilakan kirimkan (copy-paste) aturan persis yang ingin dihapus dari database.", 
            reply_markup=tombol_kembali
        )

    elif aksi == "sandbox":
        admin_states[user_id] = {"state": "waiting_sandbox", "chat_id": chat_id}
        await callback_query.message.edit_text(
            f"🧪 **Sandbox / Uji Coba ({nama_grup})**\n\nKirimkan teks pancingan (dummy text). Saya akan memeriksa apakah teks tersebut akan terhapus di grup.",
            reply_markup=tombol_kembali
        )

    elif aksi == "daftar":
        aturan = grup_data.get("kata_terlarang", []) if grup_data else []
        if not aturan:
            teks = f"📜 **Daftar Kata Terlarang ({nama_grup})**\n\n_Belum ada aturan yang dibuat._"
        else:
            teks = f"📜 **Daftar Kata Terlarang ({nama_grup})**\n\n" + "\n".join([f"• `{rule}`" for rule in aturan])
        await callback_query.message.edit_text(teks, reply_markup=tombol_kembali)

# ==========================================
# 📥 3. MENANGKAP INPUT DI DM (MODE TUNGGU)
# ==========================================
@app.on_message(filters.private & ~filters.command(["start", "help", "setting"]))
async def tangkap_input_dm(client, message):
    user_id = message.from_user.id
    if user_id not in admin_states:
        return

    state_data = admin_states[user_id]
    state = state_data["state"]
    chat_id = state_data["chat_id"]
    teks_input = message.text

    tombol_kembali = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali ke Menu", callback_data=f"menu_{chat_id}")]])

    if state == "waiting_add":
        # Masukkan ke MongoDB (Push ke array)
        await koleksi_grup.update_one({"_id": chat_id}, {"$addToSet": {"kata_terlarang": teks_input}})
        del admin_states[user_id]
        print(f"🟢 [LOG ADMIN] Aturan ditambahkan: {teks_input} (Grup: {chat_id})")
        await message.reply(f"✅ Aturan `{teks_input}` berhasil ditambahkan!", reply_markup=tombol_kembali)

    elif state == "waiting_remove":
        # Hapus dari MongoDB (Pull dari array)
        hasil = await koleksi_grup.update_one({"_id": chat_id}, {"$pull": {"kata_terlarang": teks_input}})
        del admin_states[user_id]
        if hasil.modified_count > 0:
            print(f"🔴 [LOG ADMIN] Aturan dihapus: {teks_input} (Grup: {chat_id})")
            await message.reply(f"✅ Aturan `{teks_input}` berhasil dihapus!", reply_markup=tombol_kembali)
        else:
            await message.reply(f"❌ Aturan `{teks_input}` tidak ditemukan di database.", reply_markup=tombol_kembali)

    elif state == "waiting_sandbox":
        grup_data = await koleksi_grup.find_one({"_id": chat_id})
        daftar_rule = grup_data.get("kata_terlarang", []) if grup_data else []
        terdeteksi = False
        aturan_pemicu = ""
        
        for rule in daftar_rule:
            if cek_kata_terlarang(teks_input, rule):
                terdeteksi = True
                aturan_pemicu = rule
                break
        
        if terdeteksi:
            respon = f"🚨 **HASIL: TERDETEKSI SPAM!**\n💥 **Pemicu:** `{aturan_pemicu}`"
        else:
            respon = "✅ **HASIL: AMAN** (Tidak ada aturan yang cocok)"
            
        await message.reply(respon, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Uji Lagi", callback_data=f"sandbox_{chat_id}")],
            [InlineKeyboardButton("🔙 Menu", callback_data=f"menu_{chat_id}")]
        ]))
        del admin_states[user_id]

# ==========================================
# 🛡️ 4. PENYARINGAN PESAN AKTIF DI GRUP
# ==========================================
@app.on_message(filters.group & ~filters.service)
async def saring_pesan_grup(client, message):
    chat_id = message.chat.id
    
    # Abaikan pesan tanpa teks (misal: stiker murni)
    teks_pesan = message.text or message.caption
    if not teks_pesan:
        return

    # Ambil aturan dari MongoDB
    grup_data = await koleksi_grup.find_one({"_id": chat_id})
    if not grup_data or not grup_data.get("kata_terlarang"):
        return
        
    daftar_rule = grup_data.get("kata_terlarang", [])
    
    # Bypass Admin (Admin bebas ngechat apa saja)
    try:
        member = await client.get_chat_member(chat_id, message.from_user.id)
        if member.status in ["administrator", "creator"]:
            return
    except Exception:
        pass # Handle jika user hidden admin / anonim
    
    # Loop pengecekan
    for rule in daftar_rule:
        if cek_kata_terlarang(teks_pesan, rule):
            try:
                await message.delete()
                print(f"🗑️ [LOG ADMIN] Pesan dihapus di Grup {chat_id}. Pemicu: {rule}. Pelaku: {message.from_user.id}")
                break
            except Exception as e:
                print(f"⚠️ [LOG ADMIN] Gagal menghapus pesan: {e} (Mungkin bot belum jadi admin)")

# Jalankan Bot
if __name__ == "__main__":
    app.run()

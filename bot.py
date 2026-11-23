import html
import io
import logging
import re
import urllib.parse
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image

import config
from sheets_helper import sheets
import ai_extractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN)


def is_authorized(message_or_call) -> bool:
    """Memvalidasi apakah pengirim pesan adalah akun admin yang berhak."""
    user_id = str(message_or_call.from_user.id)
    allowed_id = str(config.TELEGRAM_ALLOWED_CHAT_ID).strip()
    if not allowed_id or allowed_id == "123456789":
        # Jika belum diatur, izinkan untuk testing pertama
        return True
    return user_id == allowed_id


def send_telegram_alert(text: str, parse_mode: str = "HTML"):
    """Mengirim pesan notifikasi / laporan ke akun Telegram admin."""
    chat_id = config.TELEGRAM_ALLOWED_CHAT_ID
    if not chat_id:
        return
    try:
        bot.send_message(chat_id, text, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"Gagal mengirim notifikasi Telegram: {e}")


@bot.message_handler(commands=["start"])
def handle_start(message):
    if not is_authorized(message):
        return
    text = (
        "🤖 <b>Selamat Datang di Sales Command Center!</b>\n\n"
        "Bot ini adalah pusat kendali otomatisasi prospek, integrasi Google Sheets, dan email outreach Anda.\n\n"
        "💡 <b>Cara Cepat Memulai:</b>\n"
        "1. <b>Input Lead:</b> Langsung kirim <b>teks obrolan, link medsos, atau screenshot gambar</b> ke chat ini.\n"
        "2. <b>Lihat Panduan Lengkap:</b> Ketik <code>/help</code> untuk melihat seluruh perintah pengendali pipeline."
    )
    bot.reply_to(message, text, parse_mode="HTML")


@bot.message_handler(commands=["help"])
def handle_help(message):
    if not is_authorized(message):
        return
    text = (
        "📖 <b>PANDUAN LENGKAP SALES COMMAND CENTER BOT</b>\n\n"
        "📥 <b>1. Cara Input Prospek Baru:</b>\n"
        "Cukup kirimkan teks postingan, link sosmed, atau screenshot gambar ke bot ini. AI Gemini akan otomatis mengekstrak nama, email, tipe project, dan kebutuhan usaha, lalu menampilkan kartu verifikasi.\n\n"
        "🎮 <b>2. Daftar Perintah Pengendali Pipeline:</b>\n"
        "• <code>/status</code> ➔ Melihat ringkasan jumlah prospek di setiap status pipeline secara live dari Google Sheets.\n"
        "• <code>/find &lt;kata_kunci&gt;</code> ➔ Mencari ID prospek (LD-xxxx), status, dan kontak berdasarkan nama/email.\n"
        "• <code>/replied &lt;email/id&gt;</code> ➔ Menandai prospek telah membalas email/chat (mematikan follow-up otomatis).\n"
        "• <code>/scheduled &lt;email/id&gt;</code> ➔ Menandai meeting terjadwal secara manual jika klien sepakat meeting di WA tanpa lewat link Calendly.\n"
        "• <code>/deal &lt;email/id&gt;</code> ➔ Menandai prospek resmi closing/membayar proyek 🎉\n"
        "• <code>/nodeal &lt;email/id&gt;</code> ➔ Menandai batal closing setelah sesi meeting/diskusi.\n"
        "• <code>/cleardraft</code> ➔ Menghapus antrean draft prospek di tab Leads_Draft jika ingin reset antrean.\n\n"
        "🔄 <b>3. Siklus Status Prospek di Database:</b>\n"
        "• <b>Baru:</b> Siap dikirimi email penawaran pertama oleh cron blaster.\n"
        "• <b>WA_Manual:</b> Prospek tanpa email (hanya no WA/sosmed), wajib japri manual.\n"
        "• <b>Penawaran Terkirim:</b> Email 1 terkirim, jeda 3 hari.\n"
        "• <b>Follow Up 1:</b> Email FU1 terkirim, jeda 4 hari.\n"
        "• <b>Follow Up 2:</b> Email pamungkas terkirim, outreach selesai.\n"
        "• <b>Meeting Scheduled:</b> Jadwal meeting disepakati (Follow-up mati).\n"
        "• <b>Replied:</b> Prospek membalas (Follow-up mati).\n"
        "• <b>Deal / No Deal:</b> Hasil akhir negosiasi."
    )
    bot.reply_to(message, text, parse_mode="HTML")


@bot.message_handler(commands=["find", "cekid", "search"])
def handle_find(message):
    if not is_authorized(message):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(
            message,
            "Format: <code>/find &lt;nama_atau_email_atau_id&gt;</code>\n"
            "Contoh: <code>/find hendra</code> atau <code>/find maya</code>",
            parse_mode="HTML",
        )
        return

    keyword = args[1].strip().lower()
    try:
        leads = sheets.get_leads()
        matches = []
        for l in reversed(leads):
            nama = str(l.get("nama", "")).lower()
            email = str(l.get("email", "")).lower()
            lead_id = str(l.get("lead_id", "")).lower()
            kontak = str(l.get("kontak_lain", "")).lower()
            if keyword in nama or keyword in email or keyword in lead_id or keyword in kontak:
                matches.append(l)

        if not matches:
            bot.reply_to(
                message,
                f"❌ Tidak ditemukan prospek dengan kata kunci: <code>{html.escape(keyword)}</code>",
                parse_mode="HTML",
            )
            return

        total_match = len(matches)
        display_matches = matches[:5]
        res_text = f"🔍 <b>Hasil Pencarian Prospek:</b> (Ditemukan {total_match})\n\n"

        for idx, item in enumerate(display_matches):
            l_id = html.escape(str(item.get("lead_id") or "-"))
            l_nama = html.escape(str(item.get("nama") or "-"))
            l_email = html.escape(str(item.get("email") or "-"))
            l_kontak = html.escape(str(item.get("kontak_lain") or "-"))
            l_prod = html.escape(str(item.get("nama_produk_atau_jasa") or "-"))
            l_status = html.escape(str(item.get("status") or "-"))

            res_text += (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🆔 <b>ID:</b> <code>{l_id}</code>\n"
                f"👤 <b>Nama:</b> {l_nama}\n"
                f"✉️ <b>Email:</b> {l_email}\n"
                f"📞 <b>Kontak:</b> {l_kontak}\n"
                f"🏷️ <b>Produk:</b> {l_prod}\n"
                f"📌 <b>Status:</b> <b>{l_status}</b>\n"
                f"💡 <i>Gunakan ID untuk aksi:</i>\n"
                f"<code>/deal {l_id}</code> | <code>/nodeal {l_id}</code> | <code>/replied {l_id}</code>\n"
            )

        if total_match > 5:
            res_text += f"\n<i>(Menampilkan 5 data terbaru dari {total_match} hasil)</i>"

        bot.reply_to(message, res_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error command /find: {e}")
        bot.reply_to(message, f"❌ Gagal mencari data prospek: {e}")


@bot.message_handler(commands=["cleardraft"])
def handle_cleardraft(message):
    if not is_authorized(message):
        return
    sheets.clear_draft()
    bot.reply_to(message, "🧹 Antrean draft yang tertunda berhasil dibersihkan.")


@bot.message_handler(commands=["status"])
def handle_status(message):
    if not is_authorized(message):
        return
    try:
        summary, total = sheets.get_pipeline_summary()
        msg = (
            f"📊 <b>Rekap Status Pipeline Leads</b>\n"
            f"Total: <b>{total}</b> prospek\n\n"
            f"🆕 Baru: {summary.get('Baru', 0)}\n"
            f"📤 Penawaran Terkirim: {summary.get('Penawaran Terkirim', 0)}\n"
            f"🔁 Follow Up 1: {summary.get('Follow Up 1', 0)}\n"
            f"🔁 Follow Up 2: {summary.get('Follow Up 2', 0)}\n"
            f"📅 Meeting Scheduled: {summary.get('Meeting Scheduled', 0)}\n"
            f"💬 Replied: {summary.get('Replied', 0)}\n"
            f"📱 WA Manual (Japri): {summary.get('WA_Manual', 0)}\n"
            f"🎉 Deal: {summary.get('Deal', 0)}\n"
            f"❌ No Deal: {summary.get('No Deal', 0)}\n"
        )
        bot.reply_to(message, msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error status command: {e}")
        bot.reply_to(message, f"❌ Gagal mengambil status dari Sheets: {e}")


def _update_status_by_query(message, new_status: str, notes: str):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        cmd = args[0]
        bot.reply_to(
            message,
            f"Format salah. Gunakan: <code>{cmd} &lt;email_atau_id&gt;</code>\n"
            f"Contoh: <code>{cmd} budi@gmail.com</code> atau <code>{cmd} LD-1234</code>",
            parse_mode="HTML",
        )
        return

    query = args[1].strip()
    try:
        leads = sheets.get_leads()
        target = None
        for l in reversed(leads):
            if (
                l.get("email", "").lower() == query.lower()
                or l.get("lead_id", "").lower() == query.lower()
            ):
                target = l
                break

        if not target:
            bot.reply_to(message, f"❌ Prospek '{query}' tidak ditemukan di Google Sheets.")
            return

        sheets.update_lead_status(
            target["row_number"],
            new_status=new_status,
            notes=notes,
        )
        nama = html.escape(str(target.get("nama") or "-"))
        kontak = target.get("email") or target.get("lead_id")
        bot.reply_to(
            message,
            f"✅ Status untuk <b>{nama}</b> (<code>{kontak}</code>) "
            f"berhasil diubah ke: <b>{new_status}</b>.\n"
            f"Catatan: <i>{notes}</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error update status via command: {e}")
        bot.reply_to(message, f"❌ Gagal update status: {e}")


@bot.message_handler(commands=["replied", "pause"])
def handle_manual_replied(message):
    if not is_authorized(message):
        return
    _update_status_by_query(
        message,
        new_status="Replied",
        notes="Ditandai Replied manual via Telegram (Follow-up mati)",
    )


@bot.message_handler(commands=["scheduled"])
def handle_manual_scheduled(message):
    if not is_authorized(message):
        return
    _update_status_by_query(
        message,
        new_status="Meeting Scheduled",
        notes="Meeting terjadwal manual via Telegram (Follow-up mati)",
    )


@bot.message_handler(commands=["deal"])
def handle_deal(message):
    if not is_authorized(message):
        return
    _update_status_by_query(
        message,
        new_status="Deal",
        notes="Closing penjualan berhasil! 🎉",
    )


@bot.message_handler(commands=["nodeal"])
def handle_nodeal(message):
    if not is_authorized(message):
        return
    _update_status_by_query(
        message,
        new_status="No Deal",
        notes="Batal closing setelah sesi diskusi/meeting",
    )


@bot.message_handler(content_types=["text"])
def handle_text_lead(message):
    if not is_authorized(message):
        return

    text = message.text.strip()
    if text.startswith("/"):
        return

    # 1. Cek proteksi apakah masih ada draft tertunda
    try:
        existing_draft = sheets.get_active_draft()
        if existing_draft:
            nama_draft = html.escape(str(existing_draft.get('nama') or '-'))
            bot.reply_to(
                message,
                f"⚠️ <b>Masih Ada Draft Tertunda!</b>\n\n"
                f"Prospek sebelumnya: <b>{nama_draft}</b> belum disimpan atau dibatalkan.\n"
                f"Ketik /cleardraft jika ingin mengabaikannya dan mulai baru.",
                parse_mode="HTML",
            )
            return
    except Exception as e:
        logger.warning(f"Gagal cek draft: {e}")

    wait_msg = bot.reply_to(message, "⏳ *Menganalisis prospek dengan Gemini AI...*", parse_mode="Markdown")

    try:
        lead_data = ai_extractor.extract_lead_from_text(text)
        sheets.save_draft(lead_data)
        _send_preview(message.chat.id, lead_data)
        bot.delete_message(message.chat.id, wait_msg.message_id)
    except Exception as e:
        logger.error(f"Error ekstraksi teks: {e}")
        bot.edit_message_text(
            f"❌ Gagal mengekstrak data prospek: {e}",
            chat_id=message.chat.id,
            message_id=wait_msg.message_id,
        )


@bot.message_handler(content_types=["photo"])
def handle_photo_lead(message):
    if not is_authorized(message):
        return

    # Cek proteksi draft
    try:
        existing_draft = sheets.get_active_draft()
        if existing_draft:
            nama_draft = html.escape(str(existing_draft.get('nama') or '-'))
            bot.reply_to(
                message,
                f"⚠️ <b>Masih Ada Draft Tertunda!</b>\n\n"
                f"Prospek sebelumnya: <b>{nama_draft}</b> belum dikonfirmasi.\n"
                f"Ketik /cleardraft jika ingin mengabaikannya dan mulai baru.",
                parse_mode="HTML",
            )
            return
    except Exception as e:
        logger.warning(f"Gagal cek draft: {e}")

    wait_msg = bot.reply_to(message, "⏳ *Membaca gambar screenshot dengan Gemini Vision...*", parse_mode="Markdown")

    try:
        # Download gambar kualitas tertinggi
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(downloaded))

        caption = message.caption or ""
        lead_data = ai_extractor.extract_lead_from_image(image, caption=caption)
        sheets.save_draft(lead_data)
        _send_preview(message.chat.id, lead_data)
        bot.delete_message(message.chat.id, wait_msg.message_id)
    except Exception as e:
        logger.error(f"Error ekstraksi gambar: {e}")
        bot.edit_message_text(
            f"❌ Gagal membaca screenshot: {e}",
            chat_id=message.chat.id,
            message_id=wait_msg.message_id,
        )


def _extract_clean_phone(raw_str: str) -> str:
    """Mencari digit nomor telepon dan mengubah ke format internasional 628xxx."""
    if not raw_str:
        return ""
    match = re.search(r"(?:\+?62|0)8[0-9\s\-]{7,14}", str(raw_str))
    if match:
        digits = re.sub(r"\D", "", match.group(0))
        if digits.startswith("0"):
            digits = "62" + digits[1:]
        elif digits.startswith("8"):
            digits = "628" + digits[1:]
        return digits
    return ""


def _build_wa_pitch_message(lead: dict) -> str:
    """Menyusun draf pesan WhatsApp business casual yang sopan dan relevan."""
    nama = str(lead.get("nama") or "Kak/Admin").strip()
    kebutuhan = str(lead.get("ringkasan_kebutuhan") or "operasional usaha").strip()
    poin = str(lead.get("poin_unggulan") or "solusi sistem siap pakai").strip()
    sender = config.GMAIL_SENDER_NAME.split()[0] if config.GMAIL_SENDER_NAME else "Rizki"

    msg = (
        f"Halo Kak/Admin {nama}, salam kenal ya Kak 🙏\n\n"
        f"Saya {sender}, kebetulan perhatikan usaha {nama} makin berkembang.\n\n"
        f"Biasanya di fase seperti saat ini, {kebutuhan} cukup menyita waktu jika masih dikelola manual. "
        f"Kebetulan kami biasa buatkan solusi sistem/web yang siap pakai dan disesuaikan khusus untuk alur bisnis seperti {nama} ({poin}).\n\n"
        f"Kira-kira apakah berkenan kalau saya bagikan gambaran singkat/contoh demonya lewat chat sini Kak? "
        f"Santai saja Kak, barangkali bisa bermanfaat untuk {nama}.\n\n"
        f"Terima kasih banyak atas waktunya Kak!"
    )
    return msg


def _send_preview(chat_id: int, lead: dict):
    """Mengirim pesan preview ke Telegram lengkap dengan tombol simpan & WhatsApp."""
    markup = InlineKeyboardMarkup()
    btn_save = InlineKeyboardButton("✅ Simpan ke Leads", callback_data="save_draft")
    btn_cancel = InlineKeyboardButton("❌ Batalkan", callback_data="cancel_draft")
    markup.row(btn_save, btn_cancel)

    clean_phone = _extract_clean_phone(lead.get("kontak_lain") or "")
    is_wa_manual = lead.get("status") == "WA_Manual" or not lead.get("email")

    if is_wa_manual and clean_phone:
        pitch = _build_wa_pitch_message(lead)
        encoded_pitch = urllib.parse.quote(pitch)
        btn_wa = InlineKeyboardButton("📲 Buka WhatsApp Sekarang", url=f"https://wa.me/{clean_phone}?text={encoded_pitch}")
        markup.row(btn_wa)

    lead_id = html.escape(str(lead.get("lead_id") or "-"))
    nama = html.escape(str(lead.get("nama") or "-"))
    email_val = lead.get("email")
    if email_val:
        email_text = f"<code>{html.escape(str(email_val))}</code>"
    else:
        email_text = "<i>(Tidak ada email - Wajib Japri Manual)</i>"

    kontak = html.escape(str(lead.get("kontak_lain") or "-"))
    tipe_proj = html.escape(str(lead.get("tipe_project") or "-"))
    produk = html.escape(str(lead.get("nama_produk_atau_jasa") or "-"))
    unggulan = html.escape(str(lead.get("poin_unggulan") or "-"))
    kebutuhan = html.escape(str(lead.get("ringkasan_kebutuhan") or "-"))
    status = html.escape(str(lead.get("status") or "-"))

    text = (
        f"📋 <b>Preview Prospek Baru:</b>\n\n"
        f"🆔 <b>ID:</b> <code>{lead_id}</code>\n"
        f"👤 <b>Nama:</b> {nama}\n"
        f"✉️ <b>Email:</b> {email_text}\n"
        f"📞 <b>Kontak Lain:</b> {kontak}\n"
        f"🏷️ <b>Tipe:</b> {tipe_proj} ({produk})\n"
        f"💡 <b>Unggulan:</b> {unggulan}\n"
        f"📝 <b>Kebutuhan:</b> {kebutuhan}\n"
        f"📌 <b>Target Status:</b> <b>{status}</b>\n\n"
    )

    if is_wa_manual and clean_phone:
        text += (
            f"💬 <b>Draf Pesan WhatsApp Siap Kirim:</b>\n"
            f"<pre>{html.escape(_build_wa_pitch_message(lead))}</pre>\n\n"
        )

    text += "Simpan prospek ini ke spreadsheet?"
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "Unauthorized.")
        return

    if call.data == "save_draft":
        try:
            saved = sheets.commit_draft()
            if saved:
                bot.answer_callback_query(call.id, "✅ Tersimpan!")
                nama = html.escape(str(saved.get("nama") or "-"))
                produk = html.escape(str(saved.get("nama_produk_atau_jasa") or "-"))
                status = html.escape(str(saved.get("status") or "-"))
                feedback = (
                    f"✅ <b>Prospek Berhasil Disimpan ke Leads!</b>\n\n"
                    f"👤 Nama: <b>{nama}</b>\n"
                    f"🏷️ Produk: <b>{produk}</b>\n"
                    f"📌 Status: <b>{status}</b>\n"
                )
                wa_markup = None
                if saved.get("status") == "WA_Manual":
                    kontak = html.escape(str(saved.get("kontak_lain") or "-"))
                    clean_phone = _extract_clean_phone(saved.get("kontak_lain") or "")
                    feedback += (
                        f"\n⚠️ <i>Perhatian:</i> Prospek ini tidak punya email.\n"
                        f"Silakan langsung japri manual ke kontak: <code>{kontak}</code>.\n"
                    )
                    if clean_phone:
                        pitch = _build_wa_pitch_message(saved)
                        encoded_pitch = urllib.parse.quote(pitch)
                        wa_markup = InlineKeyboardMarkup()
                        wa_markup.row(InlineKeyboardButton("📲 Buka WhatsApp Sekarang", url=f"https://wa.me/{clean_phone}?text={encoded_pitch}"))
                        feedback += (
                            f"\n💬 <b>Draf Pesan WhatsApp:</b>\n"
                            f"<pre>{html.escape(pitch)}</pre>\n"
                            f"👉 <i>Klik tombol di bawah untuk langsung membuka WhatsApp dengan pesan ini!</i>"
                        )

                bot.edit_message_text(
                    feedback,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=wa_markup,
                    parse_mode="HTML",
                )
            else:
                bot.answer_callback_query(call.id, "Draft sudah tidak ada / kosong.")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Gagal simpan: {e}")

    elif call.data == "cancel_draft":
        try:
            sheets.clear_draft()
            bot.answer_callback_query(call.id, "Draft dibatalkan.")
            bot.edit_message_text(
                "❌ <b>Draft dibatalkan.</b> Antrean telah dikosongkan.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
            )
        except Exception as e:
            bot.answer_callback_query(call.id, f"Error: {e}")


if __name__ == "__main__":
    print("🤖 Bot Telegram berjalan dalam mode Long-Polling (Uji Coba Lokal)...")
    bot.infinity_polling()

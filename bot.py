import io
import logging
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


@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    if not is_authorized(message):
        return
    text = (
        "🤖 **Sales Command Center Bot Siap!**\n\n"
        "Cara pakai:\n"
        "1. **Input Lead Baru:** Langsung kirim teks deskripsi, link prospek, atau foto screenshot ke chat ini.\n"
        "2. **Cek Status Pipeline:** Ketik /status\n"
        "3. **Tandai Klien Balas Manual:** Ketik `/replied <email_atau_id>`\n"
    )
    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=["status"])
def handle_status(message):
    if not is_authorized(message):
        return
    try:
        summary, total = sheets.get_pipeline_summary()
        msg = f"📊 **Rekap Status Pipeline Leads**\nTotal: {total} prospek\n\n"
        msg += f"🆕 Baru: {summary.get('Baru', 0)}\n"
        msg += f"📤 Penawaran Terkirim: {summary.get('Penawaran Terkirim', 0)}\n"
        msg += f"🔁 Follow Up 1: {summary.get('Follow Up 1', 0)}\n"
        msg += f"🔁 Follow Up 2: {summary.get('Follow Up 2', 0)}\n"
        msg += f"📅 Meeting Scheduled: {summary.get('Meeting Scheduled', 0)}\n"
        msg += f"💬 Replied: {summary.get('Replied', 0)}\n"
        msg += f"📱 WA Manual (Japri): {summary.get('WA_Manual', 0)}\n"
        msg += f"🎉 Deal: {summary.get('Deal', 0)}\n"
        msg += f"❌ No Deal: {summary.get('No Deal', 0)}\n"
        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error status command: {e}")
        bot.reply_to(message, f"❌ Gagal mengambil status dari Sheets: {e}")


@bot.message_handler(commands=["replied", "pause"])
def handle_manual_replied(message):
    if not is_authorized(message):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(
            message,
            "Gunakan format: `/replied <email_klien>` atau `/replied <lead_id>`",
            parse_mode="Markdown",
        )
        return

    query = args[1].strip()
    try:
        leads = sheets.get_leads()
        target = None
        for l in leads:
            if (
                l.get("email", "").lower() == query.lower()
                or l.get("lead_id", "").lower() == query.lower()
            ):
                target = l
                break

        if not target:
            bot.reply_to(message, f"❌ Prospek '{query}' tidak ditemukan di Sheet.")
            return

        sheets.update_lead_status(
            target["row_number"],
            new_status="Replied",
            notes="Ditandai manual via Telegram",
        )
        bot.reply_to(
            message,
            f"✅ Status untuk *{target.get('nama')}* ({target.get('email')}) berhasil diubah ke *Replied*. Follow-up email dihentikan.",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Gagal update status: {e}")


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
            bot.reply_to(
                message,
                f"⚠️ **Masih Ada Draft Tertunda!**\n\n"
                f"Prospek sebelumnya: *{existing_draft.get('nama')}* belum disimpan atau dibatalkan.\n"
                f"Silakan klik tombol pada preview sebelumnya sebelum memasukkan prospek baru.",
                parse_mode="Markdown",
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
            bot.reply_to(
                message,
                f"⚠️ **Masih Ada Draft Tertunda!**\n\n"
                f"Prospek sebelumnya: *{existing_draft.get('nama')}* belum dikonfirmasi.\n"
                f"Selesaikan draft sebelumnya terlebih dahulu.",
                parse_mode="Markdown",
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


def _send_preview(chat_id: int, lead: dict):
    """Mengirim pesan preview ke Telegram lengkap dengan 2 tombol Inline."""
    markup = InlineKeyboardMarkup()
    btn_save = InlineKeyboardButton("✅ Simpan ke Leads", callback_data="save_draft")
    btn_cancel = InlineKeyboardButton("❌ Batalkan", callback_data="cancel_draft")
    markup.row(btn_save, btn_cancel)

    email_text = lead.get("email") or "_(Tidak ada email - Wajib Japri Manual)_"
    text = (
        f"📋 **Preview Prospek Baru:**\n\n"
        f"🆔 **ID:** `{lead.get('lead_id')}`\n"
        f"👤 **Nama:** {lead.get('nama')}\n"
        f"✉️ **Email:** {email_text}\n"
        f"📞 **Kontak Lain:** {lead.get('kontak_lain') or '-'}\n"
        f"🏷️ **Tipe:** {lead.get('tipe_project')} ({lead.get('nama_produk_atau_jasa')})\n"
        f"💡 **Unggulan:** {lead.get('poin_unggulan')}\n"
        f"📝 **Kebutuhan:** {lead.get('ringkasan_kebutuhan')}\n"
        f"📌 **Target Status:** *{lead.get('status')}*\n\n"
        f"Simpan prospek ini ke spreadsheet?"
    )
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


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
                feedback = (
                    f"✅ **Prospek Berhasil Disimpan ke Leads!**\n\n"
                    f"👤 Nama: *{saved.get('nama')}*\n"
                    f"🏷️ Produk: *{saved.get('nama_produk_atau_jasa')}*\n"
                    f"📌 Status: *{saved.get('status')}*\n"
                )
                if saved.get("status") == "WA_Manual":
                    feedback += (
                        f"\n⚠️ *Perhatian:* Prospek ini tidak punya email. "
                        f"Silakan langsung japri manual ke kontak: `{saved.get('kontak_lain')}`."
                    )
                bot.edit_message_text(feedback, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "Draft sudah tidak ada / kosong.")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Gagal simpan: {e}")

    elif call.data == "cancel_draft":
        try:
            sheets.clear_draft()
            bot.answer_callback_query(call.id, "Draft dibatalkan.")
            bot.edit_message_text("❌ **Draft dibatalkan.** Antrean telah dikosongkan.", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Error: {e}")


if __name__ == "__main__":
    print("🤖 Bot Telegram berjalan dalam mode Long-Polling (Uji Coba Lokal)...")
    bot.infinity_polling()

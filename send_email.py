import html
import smtplib
import ssl
import time
import random
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid

import config
from sheets_helper import sheets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_telegram_alert(text: str, parse_mode: str = "HTML"):
    """Mengirim pesan notifikasi / laporan ke akun Telegram admin."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_ALLOWED_CHAT_ID:
        return
    import requests
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_ALLOWED_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Gagal kirim notif Telegram HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Gagal mengirim laporan Telegram: {e}")


def resolve_template(lead: dict, target_stage: str, templates: list) -> dict:
    """Mencari template email yang cocok berdasarkan hierarki fallback."""
    lead_type = str(lead.get("tipe_project", "")).strip().lower()
    lead_product = str(lead.get("nama_produk_atau_jasa", "")).strip().lower()
    target_stage_clean = target_stage.strip().lower()

    # 1. Exact Match: Tipe + Target Identifier + Tahap
    for t in templates:
        if (
            str(t.get("tipe_project", "")).strip().lower() == lead_type
            and str(t.get("target_identifier", "")).strip().lower() == lead_product
            and str(t.get("tahap", "")).strip().lower() == target_stage_clean
        ):
            return t

    # 2. Fallback Kategori: Tipe + 'general' + Tahap
    for t in templates:
        if (
            str(t.get("tipe_project", "")).strip().lower() == lead_type
            and str(t.get("target_identifier", "")).strip().lower() == "general"
            and str(t.get("tahap", "")).strip().lower() == target_stage_clean
        ):
            return t

    # 3. Fallback Global: 'all'
    for t in templates:
        if str(t.get("tipe_project", "")).strip().lower() == "all":
            return t

    return None


def render_email_content(lead: dict, template: dict) -> tuple[str, str]:
    """Mengganti variabel {{...}} di dalam subjek dan body email."""
    nama_lengkap = lead.get("nama", "Bapak/Ibu")
    nama_depan = nama_lengkap.split()[0] if nama_lengkap else "Bapak/Ibu"
    link_booking = lead.get("link_booking") or config.CALENDLY_BOOKING_LINK
    poin = lead.get("poin_unggulan") or "Solusi teknologi siap pakai dan efisien"
    kebutuhan = lead.get("ringkasan_kebutuhan") or "optimalisasi sistem operasional"
    produk = lead.get("nama_produk_atau_jasa") or ""

    subject = template.get("subject", "")
    body = template.get("body", "")

    for key, val in [
        ("{{nama}}", nama_lengkap),
        ("{{nama_depan}}", nama_depan),
        ("{{nama_produk_atau_jasa}}", produk),
        ("{{poin_unggulan}}", poin),
        ("{{ringkasan_kebutuhan}}", kebutuhan),
        ("{{link_booking}}", link_booking),
        ("{{sender_name}}", config.GMAIL_SENDER_NAME),
    ]:
        subject = subject.replace(key, val)
        body = body.replace(key, val)

    return subject, body


def send_smtp_email(to_email: str, subject: str, body: str):
    """Mengirim email melalui SMTP SSL Gmail dengan header standar RFC."""
    msg = MIMEMultipart()
    msg["From"] = f"{config.GMAIL_SENDER_NAME} <{config.GMAIL_SENDER_EMAIL}>"
    msg["To"] = to_email
    msg["Reply-To"] = config.GMAIL_SENDER_EMAIL
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="gmail.com")
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(config.GMAIL_SENDER_EMAIL, config.GMAIL_APP_PASSWORD)
        server.sendmail(config.GMAIL_SENDER_EMAIL, to_email, msg.as_string())


def run_blaster():
    logger.info("🚀 Memulai proses pengiriman email outreach (Cron Blaster)...")

    leads = sheets.get_leads()
    templates = sheets.get_templates()

    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")

    status_to_ignore = {
        "meeting scheduled",
        "replied",
        "deal",
        "no deal",
        "wa_manual",
    }

    candidates = []

    for lead in leads:
        email = str(lead.get("email", "")).strip()
        if not email or "@" not in email:
            continue

        status = str(lead.get("status", "Baru")).strip()
        if status.lower() in status_to_ignore:
            continue

        # Hitung selisih hari dari aksi terakhir
        last_action_str = str(lead.get("last_action_date", today_str)).strip()
        try:
            last_action_dt = datetime.strptime(last_action_str, "%Y-%m-%d")
        except Exception:
            last_action_dt = today_dt

        diff_days = (today_dt - last_action_dt).days

        eligible = False
        target_stage = ""
        new_status = ""

        if status == "Baru":
            eligible = True
            target_stage = "Baru"
            new_status = "Penawaran Terkirim"
        elif status == "Penawaran Terkirim" and diff_days >= 3:
            eligible = True
            target_stage = "Follow Up 1"
            new_status = "Follow Up 1"
        elif status == "Follow Up 1" and diff_days >= 4:
            eligible = True
            target_stage = "Follow Up 2"
            new_status = "Follow Up 2"

        if eligible:
            matched_template = resolve_template(lead, target_stage, templates)
            if matched_template:
                subject, body = render_email_content(lead, matched_template)
                candidates.append(
                    {
                        "lead": lead,
                        "new_status": new_status,
                        "subject": subject,
                        "body": body,
                        "target_stage": target_stage,
                    }
                )

        if len(candidates) >= config.DAILY_MAX_EMAILS:
            break

    total_candidates = len(candidates)
    logger.info(f"Ditemukan {total_candidates} prospek yang layak dikirimkan email hari ini.")

    if total_candidates == 0:
        logger.info("Tidak ada email yang perlu dikirim hari ini.")
        return

    sent_count = 0
    sent_details = []

    for idx, item in enumerate(candidates):
        lead = item["lead"]
        to_email = lead["email"]
        subject = item["subject"]
        body = item["body"]
        new_status = item["new_status"]
        row_num = lead["row_number"]

        try:
            logger.info(f"Mengirim email ({idx+1}/{total_candidates}) ke: {to_email}...")
            send_smtp_email(to_email, subject, body)

            # Update Google Sheets
            sheets.update_lead_status(
                row_number=row_num,
                new_status=new_status,
                last_action_date=today_str,
            )

            sent_count += 1
            nama_clean = html.escape(str(lead.get("nama") or "-"))
            produk_clean = html.escape(str(lead.get("nama_produk_atau_jasa") or "-"))
            sent_details.append(f"• <b>{nama_clean}</b> ({produk_clean}) ➔ <b>{new_status}</b>")

            # Jeda acak antar email (kecuali pada pengiriman terakhir)
            if idx < total_candidates - 1:
                delay_sec = random.randint(
                    config.EMAIL_DELAY_MIN_SEC, config.EMAIL_DELAY_MAX_SEC
                )
                logger.info(f"Menunggu {delay_sec} detik sebelum email berikutnya (Anti-Spam safety)...")
                time.sleep(delay_sec)

        except Exception as e:
            logger.error(f"Gagal mengirim email ke {to_email}: {e}")
            send_telegram_alert(f"🚨 *Gagal Kirim Email ke:* `{to_email}`\nError: `{e}`")

    # Kirim laporan rekap ke Telegram
    report_msg = (
        f"📬 <b>Laporan Email Blaster Hari Ini ({today_str})</b>\n\n"
        f"Total Terkirim: <b>{sent_count} email</b>\n"
        + "\n".join(sent_details)
        + "\n\nStatus di Google Sheets telah diperbarui."
    )
    send_telegram_alert(report_msg, parse_mode="HTML")
    logger.info("Pengiriman email hari ini selesai.")


if __name__ == "__main__":
    run_blaster()

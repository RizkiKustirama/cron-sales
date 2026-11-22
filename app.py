import html
import logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
import telebot

import config
from bot import bot, send_telegram_alert
from sheets_helper import sheets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sales Bot Webhook Server")


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Sales Bot & Outreach Command Center"}


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Menerima webhook dari Telegram saat berjalan di VPS production."""
    try:
        json_data = await request.json()
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error memproses update Telegram: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/webhook/calendly")
async def calendly_webhook(request: Request):
    """Menerima webhook dari Calendly saat prospek berhasil booking meeting."""
    try:
        payload = await request.json()
        event_type = payload.get("event")

        # Calendly menyematkan data invitee di dalam payload
        event_payload = payload.get("payload", {})
        invitee_email = event_payload.get("email", "").strip().lower()
        invitee_name = event_payload.get("name", "Prospek")
        start_time = (
            event_payload.get("scheduled_event", {}).get("start_time", "")
        )

        logger.info(f"Menerima event Calendly: {event_type} untuk {invitee_email}")

        if event_type == "invitee.created" and invitee_email:
            matched_lead = sheets.find_lead_by_email(invitee_email)

            today_str = datetime.now().strftime("%Y-%m-%d")

            if matched_lead:
                old_status = matched_lead.get("status", "Baru")
                row_num = matched_lead["row_number"]
                was_no_deal = old_status == "No Deal"

                sheets.update_lead_status(
                    row_number=row_num,
                    new_status="Meeting Scheduled",
                    last_action_date=today_str,
                    notes=f"Booking via Calendly ({start_time})",
                )

                revived_text = " <b>(🎉 PROSPEK BANGKIT DARI NO DEAL!)</b>" if was_no_deal else ""
                alert_msg = (
                    f"🔥 <b>PROSPEK BOOKING MEETING!</b>{revived_text}\n\n"
                    f"👤 Nama: <b>{html.escape(invitee_name)}</b>\n"
                    f"✉️ Email: <code>{html.escape(invitee_email)}</code>\n"
                    f"📌 Status Sebelumnya: <b>{html.escape(old_status)}</b>\n"
                    f"📅 Jadwal: <code>{html.escape(start_time)}</code>\n\n"
                    f"Status di Google Sheets otomatis diubah ke <b>Meeting Scheduled</b>. "
                    f"Follow-up email dihentikan!"
                )
                send_telegram_alert(alert_msg, parse_mode="HTML")
            else:
                logger.info(f"Email {invitee_email} booking di Calendly tapi tidak ditemukan di tab Leads.")

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Error memproses webhook Calendly: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.HOST, port=config.PORT, reload=True)

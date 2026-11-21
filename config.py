import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Google Sheets
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE", str(BASE_DIR / "google_credentials.json")
)

# Gmail Outbound
GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
GMAIL_SENDER_NAME = os.getenv("GMAIL_SENDER_NAME", "Sales Representative")

# Outreach settings
CALENDLY_BOOKING_LINK = os.getenv(
    "CALENDLY_BOOKING_LINK", "https://calendly.com"
)
DAILY_MAX_EMAILS = int(os.getenv("DAILY_MAX_EMAILS", "7"))
EMAIL_DELAY_MIN_SEC = int(os.getenv("EMAIL_DELAY_MIN_SEC", "90"))
EMAIL_DELAY_MAX_SEC = int(os.getenv("EMAIL_DELAY_MAX_SEC", "180"))

# Server
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
PUBLIC_WEBHOOK_BASE_URL = os.getenv("PUBLIC_WEBHOOK_BASE_URL", "").rstrip("/")

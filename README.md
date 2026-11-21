# Sales Bot & Scheduled Email Outreach System

Sistem otomatisasi penangkapan prospek (AI Lead Extraction via Telegram Bot) dan pengiriman email follow-up terjadwal (Linux Crontab) yang terhubung ke Google Sheets & Calendly.

---

## 📁 Struktur Direktori

```text
cron-sales/
├── .env.example             # Contoh template konfigurasi rahasia
├── .gitignore               # Menjaga file rahasia (.env & credentials) agar tidak ter-push ke GitHub
├── requirements.txt         # Daftar pustaka Python yang dibutuhkan
│
├── config.py                # Loader konfigurasi lingkungan
├── sheets_helper.py         # Modul integrasi Google Sheets (Leads, Templates, Leads_Draft)
├── ai_extractor.py          # Modul ekstraksi Gemini Flash (Teks, Link, & Screenshot)
├── bot.py                   # Telegram Bot Command Center (Polling lokal / Webhook)
├── send_email.py            # Mesin pengirim email terjadwal (Cron Blaster jam 09:00)
└── app.py                   # FastAPI Webhook Server untuk VPS (Calendly & Telegram)
```

---

## 🚀 Panduan Setup & Uji Coba di Laptop (Lokal)

### 1. Masuk ke Virtual Environment
Buka PowerShell atau Command Prompt di folder ini:
```powershell
# Aktifkan virtual environment yang sudah dibuat
.\.venv\Scripts\activate

# Install dependensi pustaka
pip install -r requirements.txt
```

### 2. Konfigurasi File Lingkungan (`.env`)
Salin file `.env.example` menjadi `.env`:
```powershell
copy .env.example .env
```
Buka `.env` dan lengkapi nilainya:
* `TELEGRAM_BOT_TOKEN`: Token dari `@BotFather`.
* `TELEGRAM_ALLOWED_CHAT_ID`: ID Telegram pribadi Anda dari `@userinfobot`.
* `GEMINI_API_KEY`: API Key dari [Google AI Studio](https://aistudio.google.com/).
* `GOOGLE_SHEET_ID`: ID dari URL Spreadsheet Anda.
* `GMAIL_SENDER_EMAIL`: Akun Gmail bot pengirim penawaran.
* `GMAIL_APP_PASSWORD`: Password aplikasi 16-huruf dari [Google Security](https://myaccount.google.com/apppasswords).
* `CALENDLY_BOOKING_LINK`: Link booking meeting Calendly Anda.

### 3. Letakkan File `google_credentials.json`
Letakkan file JSON kunci Service Account dari Google Cloud Console di dalam folder `cron-sales/` dengan nama: `google_credentials.json`.
*(Pastikan email Service Account sudah di-share ke Spreadsheet Anda dengan akses Editor).*

### 4. Uji Coba Bot Telegram di Laptop
Jalankan bot dalam mode Long-Polling (tidak butuh domain/SSL di laptop):
```powershell
python bot.py
```
* Buka Telegram di HP Anda, kirim pesan prospek (misal: *"Warung Bakso Solo, butuh POS kasir dan stok"* atau kirim foto screenshot).
* Bot akan membalas dengan ringkasan preview dan tombol `[✅ Simpan ke Leads]`.
* Klik tombol tersebut, lalu periksa tab `Leads` di Google Spreadsheet Anda!

### 5. Uji Coba Pengiriman Email Blaster Manual
Untuk menguji pengiriman email:
```powershell
python send_email.py
```
Script akan memeriksa baris `Baru`, merender template yang cocok, mengirim email penawaran via Gmail, memperbarui status di Sheet, dan mengirim laporan ringkas ke Telegram Anda!

---

## 🌐 Panduan Deployment ke VPS Linux (Production)

### 1. Clone Repository di VPS
```bash
cd /root
git clone https://github.com/RizkiKustirama/sales-bot.git sales-system
cd sales-system
```

### 2. Setup Virtual Environment di VPS
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Buat File `.env` dan `google_credentials.json` di VPS
```bash
nano .env
# Tempel konfigurasi rahasia Anda, lalu simpan (Ctrl+O, Enter, Ctrl+X)

nano google_credentials.json
# Tempel isi JSON service account Anda, lalu simpan
```

### 4. Setup Service Background (systemd) untuk `app.py`
Agar server webhook hidup 24 jam nonstop:
```bash
sudo nano /etc/systemd/system/sales-bot.service
```
Tempel konfigurasi berikut:
```ini
[Unit]
Description=Sales Bot Webhook Server
After=network.target

[Service]
User=root
WorkingDirectory=/root/sales-system
ExecStart=/root/sales-system/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```
Aktifkan service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sales-bot
sudo systemctl start sales-bot
```

### 5. Setup Nginx & SSL Let's Encrypt
```bash
sudo apt install nginx certbot python3-certbot-nginx -y
sudo nano /etc/nginx/sites-available/sales-bot
```
Isi konfigurasi Nginx:
```nginx
server {
    server_name api.domainanda.my.id;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Aktifkan dan pasang SSL gratis:
```bash
sudo ln -s /etc/nginx/sites-available/sales-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d api.domainanda.my.id
```

### 6. Daftarkan Webhook Telegram & Calendly
1. **Telegram:** Buka browser dan akses:
   `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://api.domainanda.my.id/webhook/telegram`
2. **Calendly:** Daftarkan URL `https://api.domainanda.my.id/webhook/calendly` pada menu Webhook di dashboard Calendly Anda (event: `invitee.created`).

### 7. Pasang Jadwal Crontab (Email Blaster Jam 09:00 WIB)
Ketik:
```bash
crontab -e
```
Tambahkan baris berikut di paling bawah (02:00 UTC = 09:00 WIB):
```text
0 2 * * 1-5 /root/sales-system/venv/bin/python3 /root/sales-system/send_email.py >> /root/sales-system/logs/cron_email.log 2>&1
```

🎉 **Sistem Anda kini berjalan otomatis 24/7 di VPS tanpa perlu membuka laptop lagi!**

import json
import random
import re
from datetime import datetime
from PIL import Image
import google.generativeai as genai
import config

# Inisialisasi Gemini API
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)

SYSTEM_PROMPT = """
Anda adalah asisten sales analis data B2B. Tugas Anda adalah mengekstrak data prospek dari teks chat, link sosmed, atau screenshot menjadi format JSON murni.

ATURAN UTAMA:
1. JANGAN mengarang data (no hallucination). Jika data kosong, isi null.
2. NAMA & NAMA DEPAN:
   - Ambil nama kontak/usaha.
   - Ambil 'nama_depan' (panggilan santai/profesional untuk sapaan email). Contoh: 'Budi Santoso' -> 'Budi', 'Bu Endang' -> 'Bu Endang', 'Drs. Hendra' -> 'Pak Hendra'.
3. EMAIL:
   - Cari alamat email valid. Jika tidak ada, isi null.
4. KONTAK LAIN:
   - Ambil nomor WhatsApp, @handle sosmed, atau link jika ada.
5. KLASIFIKASI TIPE PROJECT & PRODUK (STRICT ENUM):
   a. Jika usaha kuliner, cafe, resto, depot (contoh: Cwie Mie, resto, warung, kedai):
      - tipe_project: "saas_ready"
      - nama_produk_atau_jasa: "POS"
   b. Jika sekolah, SMK, LPK, akademi, kampus vokasi, lembaga kursus:
      - tipe_project: "saas_ready"
      - nama_produk_atau_jasa: "LMS_Vokasi"
   c. Jika membicarakan pembuatan web/mobile sistem khusus di luar di atas:
      - tipe_project: "custom_dev"
      - nama_produk_atau_jasa: Kategori konteks (pilih salah satu: "pencatatan", "inventaris", "pemesanan", "otomasi", "general")
6. POIN UNGGULAN: 1-2 nilai jual utama yang paling relevan.
7. RINGKASAN KEBUTUHAN: 1 kalimat singkat kebutuhan/peluang digitalisasi.
8. TARGET STATUS:
   - Jika 'email' ada -> "Baru"
   - Jika 'email' KOSONG (hanya ada no WA / sosmed) -> "WA_Manual"

OUTPUT WAJIB HANYA BERUPA JSON VALID TANPA MARKDOWN BACKTICKS ATAU PENJELASAN LAIN:
{
  "nama": "string",
  "nama_depan": "string",
  "email": "string or null",
  "kontak_lain": "string or null",
  "tipe_project": "saas_ready" | "custom_dev",
  "nama_produk_atau_jasa": "POS" | "LMS_Vokasi" | "string",
  "poin_unggulan": "string",
  "ringkasan_kebutuhan": "string",
  "target_status": "Baru" | "WA_Manual"
}
"""


def _clean_json_response(raw_text: str) -> dict:
    cleaned = re.sub(r"```json\s*", "", raw_text)
    cleaned = re.sub(r"```\s*", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Fallback parsing jika model menambahkan teks pengantar
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Gagal mem-parsing output JSON dari AI: {raw_text}")


def extract_lead_from_text(text: str) -> dict:
    """Mengekstrak data lead dari input teks atau link."""
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    response = model.generate_content(f"Ekstrak data prospek berikut:\n\n{text}")
    parsed = _clean_json_response(response.text)
    return _build_lead_object(parsed, raw_source=text)


def extract_lead_from_image(image: Image.Image, caption: str = "") -> dict:
    """Mengekstrak data lead dari gambar screenshot (Multimodal)."""
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    prompt = "Ekstrak informasi prospek bisnis dari screenshot berikut."
    if caption:
        prompt += f" Catatan tambahan pengirim: {caption}"

    response = model.generate_content([prompt, image])
    parsed = _clean_json_response(response.text)
    return _build_lead_object(parsed, raw_source=f"Screenshot + Caption: {caption}")


def _build_lead_object(parsed: dict, raw_source: str = "") -> dict:
    """Mengonversi hasil ekstraksi AI menjadi format baris Google Sheet."""
    today = datetime.now().strftime("%Y-%m-%d")
    random_num = random.randint(1000, 9999)
    lead_id = f"LD-{random_num}"

    has_email = bool(parsed.get("email") and "@" in str(parsed.get("email")))
    target_status = "Baru" if has_email else "WA_Manual"

    return {
        "lead_id": lead_id,
        "nama": parsed.get("nama") or "Lead Tanpa Nama",
        "email": parsed.get("email") or "",
        "kontak_lain": parsed.get("kontak_lain") or "",
        "tipe_project": parsed.get("tipe_project") or "custom_dev",
        "nama_produk_atau_jasa": parsed.get("nama_produk_atau_jasa") or "general",
        "poin_unggulan": parsed.get("poin_unggulan") or "Solusi digital terintegrasi",
        "ringkasan_kebutuhan": parsed.get("ringkasan_kebutuhan")
        or "Kebutuhan sistem usaha",
        "status": parsed.get("target_status") or target_status,
        "tanggal_input": today,
        "last_action_date": today,
        "link_booking": config.CALENDLY_BOOKING_LINK,
        "notes": f"Input via Telegram Bot ({raw_source[:60]})" if raw_source else "Input Telegram",
    }

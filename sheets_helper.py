import os
import json
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsHelper:
    def __init__(self):
        self.sheet_id = config.GOOGLE_SHEET_ID
        self.creds_file = config.GOOGLE_CREDENTIALS_FILE
        self._client = None
        self._doc = None

    def _get_doc(self):
        if self._doc is None:
            if not os.path.exists(self.creds_file):
                raise FileNotFoundError(
                    f"File credentials tidak ditemukan di: {self.creds_file}. "
                    f"Pastikan sudah meletakkan google_credentials.json di folder project."
                )
            creds = Credentials.from_service_account_file(
                self.creds_file, scopes=SCOPES
            )
            self._client = gspread.authorize(creds)
            self._doc = self._client.open_by_key(self.sheet_id)
        return self._doc

    def get_leads(self):
        """Mengambil semua baris dari tab Leads lengkap dengan nomor baris (row_number)."""
        doc = self._get_doc()
        ws = doc.worksheet("Leads")
        records = ws.get_all_records()
        leads = []
        for idx, row in enumerate(records):
            # Row di Google Sheets 1-indexed, header ada di row 1, maka record pertama di row 2
            row["row_number"] = idx + 2
            leads.append(row)
        return leads

    def get_templates(self):
        """Mengambil seluruh data template email dari tab Templates."""
        doc = self._get_doc()
        ws = doc.worksheet("Templates")
        return ws.get_all_records()

    def get_active_draft(self):
        """Mengecek apakah ada draft aktif yang tertunda di tab Leads_Draft."""
        doc = self._get_doc()
        ws = doc.worksheet("Leads_Draft")
        records = ws.get_all_records()
        if records and records[0].get("nama", "").strip():
            return records[0]
        return None

    def save_draft(self, draft_dict):
        """Menyimpan atau menimpa baris draft aktif di tab Leads_Draft."""
        doc = self._get_doc()
        ws = doc.worksheet("Leads_Draft")
        headers = ws.row_values(1)
        row_values = [draft_dict.get(h, "") for h in headers]

        # Bersihkan baris lama di row 2 jika ada, lalu isi data baru
        ws.batch_clear(["A2:Z2"])
        ws.append_row(row_values)
        return True

    def clear_draft(self):
        """Mengosongkan isi tab Leads_Draft (selain header)."""
        doc = self._get_doc()
        ws = doc.worksheet("Leads_Draft")
        ws.batch_clear(["A2:Z10"])
        return True

    def commit_draft(self):
        """Memindahkan data dari Leads_Draft ke tab Leads."""
        doc = self._get_doc()
        draft = self.get_active_draft()
        if not draft:
            return None

        ws_leads = doc.worksheet("Leads")
        headers = ws_leads.row_values(1)
        row_values = [draft.get(h, "") for h in headers]
        ws_leads.append_row(row_values)

        # Kosongkan draft setelah berhasil disimpan
        self.clear_draft()
        return draft

    def update_lead_status(
        self, row_number, new_status, last_action_date=None, notes=None
    ):
        """Memperbarui kolom status, last_action_date, dan notes di tab Leads."""
        doc = self._get_doc()
        ws = doc.worksheet("Leads")
        headers = ws.row_values(1)

        today_str = last_action_date or datetime.now().strftime("%Y-%m-%d")

        col_status = (
            headers.index("status") + 1 if "status" in headers else None
        )
        col_action = (
            headers.index("last_action_date") + 1
            if "last_action_date" in headers
            else None
        )
        col_notes = headers.index("notes") + 1 if "notes" in headers else None

        updates = []
        if col_status:
            updates.append(
                {"range": gspread.utils.rowcol_to_a1(row_number, col_status), "values": [[new_status]]}
            )
        if col_action:
            updates.append(
                {"range": gspread.utils.rowcol_to_a1(row_number, col_action), "values": [[today_str]]}
            )
        if notes and col_notes:
            # Ambil nilai notes lama jika ada
            old_notes = ws.cell(row_number, col_notes).value or ""
            combined_notes = f"{old_notes} | {notes}".strip(" |")
            updates.append(
                {"range": gspread.utils.rowcol_to_a1(row_number, col_notes), "values": [[combined_notes]]}
            )

        if updates:
            ws.batch_update(updates)
        return True

    def find_lead_by_email(self, email):
        """Mencari baris lead berdasarkan alamat email (memprioritaskan prospek aktif & paling baru)."""
        leads = self.get_leads()
        target = email.lower().strip()

        # 1. Prioritaskan baris terbaru yang statusnya masih aktif dalam siklus outreach
        active_statuses = {"baru", "penawaran terkirim", "follow up 1", "follow up 2"}
        for lead in reversed(leads):
            if lead.get("email", "").lower().strip() == target:
                if str(lead.get("status", "")).strip().lower() in active_statuses:
                    return lead

        # 2. Fallback: ambil baris paling terbaru (baris paling bawah)
        for lead in reversed(leads):
            if lead.get("email", "").lower().strip() == target:
                return lead

        return None

    def get_pipeline_summary(self):
        """Menghitung jumlah prospek per kategori status."""
        leads = self.get_leads()
        summary = {
            "Baru": 0,
            "Penawaran Terkirim": 0,
            "Follow Up 1": 0,
            "Follow Up 2": 0,
            "Meeting Scheduled": 0,
            "Replied": 0,
            "WA_Manual": 0,
            "Deal": 0,
            "No Deal": 0,
        }
        for lead in leads:
            st = lead.get("status", "Baru").strip()
            summary[st] = summary.get(st, 0) + 1
        return summary, len(leads)


# Singleton instance
sheets = SheetsHelper()

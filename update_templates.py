import csv
import os
from sheets_helper import sheets

def sync_templates():
    csv_path = os.path.join(os.path.dirname(__file__), "..", "Templates_Email.csv")
    if not os.path.exists(csv_path):
        csv_path = "Templates_Email.csv"

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    doc = sheets._get_doc()
    ws = doc.worksheet("Templates")
    ws.clear()
    ws.update(values=rows, range_name="A1")
    print(f"✅ Berhasil menyinkronkan {len(rows)-1} template baru ke tab Templates di Google Sheets!")

if __name__ == "__main__":
    sync_templates()

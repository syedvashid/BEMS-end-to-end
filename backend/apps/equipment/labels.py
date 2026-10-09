"""QR / Code 128 PNGs and the A4 3x8 label sheet (reportlab)."""
import io

import barcode
import qrcode
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

COLS, ROWS = 3, 8


def qr_png(value):
    buf = io.BytesIO()
    qrcode.make(value, box_size=8, border=2).save(buf, format="PNG")
    return buf.getvalue()


def barcode_png(value, with_text=True):
    buf = io.BytesIO()
    barcode.get("code128", value, writer=ImageWriter()).write(
        buf, options={"module_height": 10.0, "quiet_zone": 2.0, "write_text": with_text, "dpi": 300})
    return buf.getvalue()


def _short(text, limit=28):
    text = text or ""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def labels_pdf(items):
    """items: iterable of (asset_tag, name, qr_code_value). Fixed A4 layout, 3 columns x 8 rows."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    cell_w, cell_h = page_w / COLS, page_h / ROWS
    per_page = COLS * ROWS
    for i, (tag, name, qr_value) in enumerate(items):
        slot = i % per_page
        if i and slot == 0:
            c.showPage()
        col, row = slot % COLS, slot // COLS
        x, y = col * cell_w, page_h - (row + 1) * cell_h
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.rect(x + 1 * mm, y + 1 * mm, cell_w - 2 * mm, cell_h - 2 * mm)
        qr_size = 22 * mm
        c.drawImage(ImageReader(io.BytesIO(qr_png(qr_value))), x + 3 * mm, y + (cell_h - qr_size) / 2,
                    qr_size, qr_size)
        tx = x + 3 * mm + qr_size + 2 * mm
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(tx, y + cell_h - 9 * mm, tag)
        c.setFont("Helvetica", 7)
        c.drawString(tx, y + cell_h - 13 * mm, _short(name))
        bw = cell_w - (tx - x) - 3 * mm
        c.drawImage(ImageReader(io.BytesIO(barcode_png(tag, with_text=False))), tx, y + 5 * mm, bw, 12 * mm)
    c.showPage()
    c.save()
    return buf.getvalue()

"""Export helpers (xlsx / csv / pdf) and generic pagination."""
import csv
import io
from datetime import datetime
from decimal import Decimal

from fastapi import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .. import config


def make_xlsx(headers: list[str], rows: list[list], title="Sheet1") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    # Styles
    company_font = Font(name="Calibri", size=13, bold=True, color="1E3A8A")
    title_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    meta_font = Font(name="Calibri", size=9, italic=True, color="64748B")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10, color="0F172A")
    total_font = Font(name="Calibri", size=10, bold=True, color="0F172A")

    navy_fill = PatternFill(fill_type="solid", start_color="1E3A8A", end_color="1E3A8A")
    zebra_fill = PatternFill(fill_type="solid", start_color="F8FAFC", end_color="F8FAFC")
    total_fill = PatternFill(fill_type="solid", start_color="F1F5F9", end_color="F1F5F9")

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )
    total_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="0F172A"),
        bottom=Side(style="double", color="0F172A"),
    )

    # 1. Company Header Block
    ws.row_dimensions[1].height = 20
    c1 = ws.cell(row=1, column=1, value=config.APP_NAME)
    c1.font = company_font

    ws.row_dimensions[2].height = 18
    c2 = ws.cell(row=2, column=1, value=title.upper())
    c2.font = title_font

    ws.row_dimensions[3].height = 16
    c3 = ws.cell(row=3, column=1, value=f"Waktu Cetak: {datetime.now():%d-%m-%Y %H:%M:%S} | Total Data: {len(rows)} Baris")
    c3.font = meta_font

    ws.row_dimensions[4].height = 10  # Spacer

    # 2. Table Header Row (Row 5)
    header_row = 5
    ws.row_dimensions[header_row].height = 28
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=str(h))
        cell.font = header_font
        cell.fill = navy_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    # Keywords for column formatting
    qty_cols = {i for i, h in enumerate(headers, 1) if any(k in h.lower() for k in ["qty", "quantity", "variance", "erp", "physical", "total", "jumlah", "selisih"])}
    center_cols = {i for i, h in enumerate(headers, 1) if any(k in h.lower() for k in ["status", "round", "uom", "sheet", "code", "date", "time", "putaran", "satuan", "lembar", "waktu", "tanggal", "sumber"])}

    # 3. Data Rows (Row 6 onwards)
    start_data_row = 6
    last_data_row = start_data_row + len(rows) - 1

    for r_idx, r in enumerate(rows):
        cur_row = start_data_row + r_idx
        ws.row_dimensions[cur_row].height = 20
        is_even = (r_idx % 2 == 0)
        for col_idx, val in enumerate(r, 1):
            cell = ws.cell(row=cur_row, column=col_idx)
            cell.font = data_font
            cell.border = thin_border
            if not is_even:
                cell.fill = zebra_fill

            clean_val = _clean_cell(val)
            cell.value = clean_val

            if col_idx in qty_cols and isinstance(clean_val, (int, float, Decimal)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0.000" if isinstance(clean_val, float) and clean_val != int(clean_val) else "#,##0"
            elif col_idx in center_cols:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # 4. Summary / Total Row (if there are rows and quantity columns)
    if rows and qty_cols:
        total_row = last_data_row + 1
        ws.row_dimensions[total_row].height = 22
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=total_row, column=col_idx)
            cell.font = total_font
            cell.fill = total_fill
            cell.border = total_border
            col_letter = get_column_letter(col_idx)

            if col_idx == 1:
                cell.value = "TOTAL"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in qty_cols:
                cell.value = f"=SUM({col_letter}{start_data_row}:{col_letter}{last_data_row})"
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0"
            else:
                cell.value = ""

    # 5. Column Widths
    for col_idx, h in enumerate(headers, 1):
        max_len = len(str(h))
        for r in rows[:150]:
            if col_idx - 1 < len(r):
                max_len = max(max_len, len(str(r[col_idx - 1] or "")))
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 48)

    ws.freeze_panes = f"A{start_data_row}"
    if rows:
        last_col = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A{header_row}:{last_col}{last_data_row}"

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _clean_cell(v):
    if v is None:
        return ""
    if isinstance(v, (int, float, Decimal)):
        return v
    s = str(v)
    if s and (s[:1] in ("=", "+", "-", "@", "\t", "\r")) and not _isnum(s):
        return "'" + s
    return s


def _isnum(s):
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def make_csv(headers: list[str], rows: list[list]) -> bytes:
    sio = io.StringIO()
    w = csv.writer(sio)
    w.writerow(headers)
    for r in rows:
        w.writerow([_clean_cell(v) for v in r])
    # UTF-8 BOM so Excel opens with proper encoding
    return ("\ufeff" + sio.getvalue()).encode("utf-8")


def make_pdf(title: str, headers: list[str], rows: list[list]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    bio = io.BytesIO()
    page_w, page_h = landscape(A4)
    margin = 20
    usable_w = page_w - (margin * 2)  # ~801.89 pt

    doc = SimpleDocTemplate(
        bio,
        pagesize=(page_w, page_h),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=22,
        bottomMargin=22,
    )

    num_cols = len(headers)
    # Calculate column weights with Indonesian and English terms
    weights = []
    for h in headers:
        hl = h.lower()
        if any(k in hl for k in ["name", "nama"]):
            weights.append(3.0)
        elif any(k in hl for k in ["time", "date", "user", "alasan", "note", "waktu", "tanggal", "petugas", "catatan"]):
            weights.append(1.8)
        elif any(k in hl for k in ["item", "locator", "sto", "warehouse", "barang", "lokator", "gudang"]):
            weights.append(1.5)
        elif any(k in hl for k in ["status", "qty", "quantity", "variance", "jumlah", "selisih"]):
            weights.append(1.3)
        elif any(k in hl for k in ["round", "sheet", "uom", "putaran", "lembar", "satuan"]):
            weights.append(0.9)
        else:
            weights.append(1.2)

    total_weight = sum(weights)
    col_widths = [(w / total_weight) * usable_w for w in weights]

    st = getSampleStyleSheet()
    header_style = ParagraphStyle(
        "PDFHeader",
        parent=st["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8.5,
        textColor=colors.white,
        alignment=1,  # Center
    )
    cell_style = ParagraphStyle(
        "PDFCell",
        parent=st["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor("#0F172A"),
        alignment=0,  # Left
    )
    cell_right = ParagraphStyle(
        "PDFCellRight",
        parent=cell_style,
        alignment=2,  # Right
    )
    cell_center = ParagraphStyle(
        "PDFCellCenter",
        parent=cell_style,
        alignment=1,  # Center
    )

    qty_col_idxs = {i for i, h in enumerate(headers) if any(k in h.lower() for k in ["qty", "quantity", "variance", "erp", "physical", "total", "jumlah", "selisih"])}
    center_col_idxs = {i for i, h in enumerate(headers) if any(k in h.lower() for k in ["status", "round", "uom", "sheet", "date", "time", "putaran", "satuan", "lembar", "waktu", "tanggal", "sumber"])}

    from xml.sax.saxutils import escape as xml_escape

    # Build table data with Paragraphs to auto-wrap cleanly
    table_data = []
    # Header row
    table_data.append([Paragraph(xml_escape(str(h)), header_style) for h in headers])

    for r in rows[:1500]:
        row_cells = []
        for idx, val in enumerate(r):
            v_str = xml_escape(str(val if val is not None else "—"))
            if idx in qty_col_idxs:
                style = cell_right
            elif idx in center_col_idxs:
                style = cell_center
            else:
                style = cell_style
            row_cells.append(Paragraph(v_str, style))
        table_data.append(row_cells)

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))

    title_style = ParagraphStyle(
        "DocTitle",
        parent=st["Title"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        textColor=colors.HexColor("#0F172A"),
        alignment=0,
    )
    meta_style = ParagraphStyle(
        "DocMeta",
        parent=st["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748B"),
        alignment=0,
    )

    story = [
        Paragraph(f"<b>{config.APP_NAME}</b> — {title.upper()}", title_style),
        Spacer(1, 2),
        Paragraph(f"Generated: {datetime.now():%d-%m-%Y %H:%M:%S} | Total Baris: {len(rows)}", meta_style),
        Spacer(1, 8),
        t,
    ]

    doc.build(story)
    return bio.getvalue()


def respond(fmt: str, filename: str, title: str, headers: list[str], rows: list[list]) -> Response:
    fmt = (fmt or "xlsx").lower()
    if fmt == "csv":
        body, mt = make_csv(headers, rows), "text/csv; charset=utf-8"
    elif fmt == "pdf":
        body, mt = make_pdf(title, headers, rows), "application/pdf"
    else:
        fmt = "xlsx"
        body = make_xlsx(headers, rows, title)
        mt = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    clean_name = filename.strip().replace('"', '').replace("'", "").replace(" ", "_")
    if not clean_name.lower().endswith(f".{fmt}"):
        final_filename = f"{clean_name}.{fmt}"
    else:
        final_filename = clean_name

    return Response(
        content=body,
        media_type=mt,
        headers={
            "Content-Disposition": f'attachment; filename="{final_filename}"; filename*=UTF-8\'\'{final_filename}',
            "Content-Length": str(len(body)),
            "Content-Type": mt,
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


def page_params(page: int, size: int):
    page = max(1, page)
    size = min(max(1, size), 200)
    return (page - 1) * size, size

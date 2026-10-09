"""CSV / XLSX import of legacy equipment. Streaming/read-only parse, formulas never evaluated,
error messages never echo cell content."""
import csv
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from rest_framework.exceptions import ValidationError

from apps.core import audit
from apps.masters.models import Department, EquipmentModel, FundingSource, Location, Vendor

from . import services
from .errors import Conflict
from .models import Equipment, EquipmentCommissioning, EquipmentMovement, EquipmentStateHistory

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_ERRORS = 500
MAX_UNZIPPED = 100 * 1024 * 1024

FIELDS = [
    "manufacturer", "model_number", "serial_number", "name", "department_code", "location_code",
    "ownership_type", "owner_vendor_name", "funding_source_code", "supplier_name",
    "purchase_order_number", "purchase_order_date", "grn_number", "grn_date", "invoice_number", "invoice_date",
    "purchase_cost", "installation_date", "criticality", "legacy_asset_id", "operational_state", "notes",
]
REQUIRED = ("manufacturer", "model_number", "location_code")
OWNERSHIP = {"OWNED", "LEASED", "RENTAL", "LOAN_DEMO", "VENDOR_PLACED"}
CRITICALITY = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
IMPORT_STATES = {"IN_SERVICE", "OUT_OF_SERVICE"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def _bad_file():
    return ValidationError({"file": ["The file could not be read."]})


# ---------------------------------------------------------------- reading
def _cell(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return v.strip()
    return v


def _txt(v):
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()


def _read_csv(upload):
    upload.seek(0)
    data = upload.read()
    if b"\x00" in data[:4096]:
        raise _bad_file()
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        headers = next(reader, None)
        rows = []
        for r in reader:
            if not any(str(c).strip() for c in r):
                continue
            rows.append([_cell(c) for c in r])
            if len(rows) > MAX_ROWS:
                raise ValidationError({"file": [f"At most {MAX_ROWS} data rows are allowed."]})
    except (UnicodeDecodeError, csv.Error):
        raise _bad_file()
    if not headers:
        raise _bad_file()
    return [str(h).strip() for h in headers], rows


def _read_xlsx(upload):
    import openpyxl
    upload.seek(0)
    if not zipfile.is_zipfile(upload):
        raise _bad_file()
    upload.seek(0)
    try:
        with zipfile.ZipFile(upload) as z:
            if not any(n.startswith("xl/") for n in z.namelist()):
                raise _bad_file()
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                raise _bad_file()
        upload.seek(0)
        wb = openpyxl.load_workbook(upload, read_only=True, data_only=True)   # cached values, no formula evaluation
        try:
            ws = wb.worksheets[0]   # first sheet only
            it = ws.iter_rows(values_only=True)
            headers = next(it, None)
            if not headers:
                raise _bad_file()
            rows = []
            for r in it:
                cells = [_cell(c) for c in r]
                if not any(str(c).strip() for c in cells):
                    continue
                rows.append(cells)
                if len(rows) > MAX_ROWS:
                    raise ValidationError({"file": [f"At most {MAX_ROWS} data rows are allowed."]})
        finally:
            wb.close()
    except ValidationError:
        raise
    except Exception:
        raise _bad_file()
    return [str(h).strip() if h is not None else "" for h in headers], rows


def read_table(upload):
    if upload is None:
        raise ValidationError({"file": ["This field is required."]})
    if upload.size > MAX_BYTES:
        raise ValidationError({"file": ["The file is too large (5 MB maximum)."]})
    name = (upload.name or "").lower()
    if name.endswith(".csv"):
        return _read_csv(upload)
    if name.endswith(".xlsx"):
        return _read_xlsx(upload)
    raise ValidationError({"file": ["Only CSV or XLSX files are accepted."]})


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def parse_mapping(raw):
    if raw in (None, ""):
        return {}
    import json
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise ValidationError({"mapping": ["Invalid mapping."]})
    if not isinstance(data, dict) or any(
            k not in FIELDS or not (v is None or isinstance(v, str)) for k, v in data.items()):
        raise ValidationError({"mapping": ["Invalid mapping."]})
    return data


def _resolve(headers, mapping):
    by_norm = {}
    for i, h in enumerate(headers):
        by_norm.setdefault(_norm(h), i)
    colmap = {}
    for f in FIELDS:
        if f in mapping:
            header = mapping[f]
            if not header:
                continue
            if header not in headers:
                raise ValidationError({"mapping": ["Mapping refers to an unknown column."]})
            colmap[f] = headers.index(header)
        elif _norm(f) in by_norm:
            colmap[f] = by_norm[_norm(f)]
    return colmap


# ---------------------------------------------------------------- validation
def _parse_date(s):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return "bad"


def analyse(facility, upload, mapping_raw):
    """Returns (result_dict, parsed_rows). parsed_rows is only meaningful when there are no errors."""
    mapping = parse_mapping(mapping_raw)
    headers, raw = read_table(upload)
    colmap = _resolve(headers, mapping)
    mapped = {f: headers[i] for f, i in colmap.items()}
    absent = [f for f in REQUIRED if f not in colmap]
    if absent:
        return {"total_rows": len(raw), "valid_rows": 0, "errors": [], "errors_truncated": False,
                "missing_models": [], "headers": headers, "mapping": mapped, "missing_columns": absent}, []
    fid = facility.id

    models = {(m.manufacturer.name.strip().lower(), m.model_number.strip().lower()): m
              for m in EquipmentModel.objects.filter(facility_id=fid, is_active=True).select_related("manufacturer")}
    depts = {d.code.lower(): d for d in Department.objects.filter(facility_id=fid, is_active=True)}
    locs = {l.code.lower(): l for l in Location.objects.filter(facility_id=fid, is_active=True)}
    vendors = {v.name.strip().lower(): v for v in Vendor.objects.filter(facility_id=fid, is_active=True)}
    funds = {f.code.lower(): f for f in FundingSource.objects.filter(facility_id=fid, is_active=True)}

    errors, parsed, missing = [], [], {}
    seen_serial, seen_legacy = set(), set()
    for i, row in enumerate(raw, start=2):   # row numbers match the spreadsheet (header = row 1)
        errs_before = len(errors)

        def err(field, msg, _i=i):
            errors.append({"row": _i, "field": field, "message": msg})

        def val(f):
            idx = colmap.get(f)
            return row[idx] if idx is not None and idx < len(row) else ""

        def txt(f, maxlen):
            s = _txt(val(f))
            if len(s) > maxlen:
                err(f, "Value is too long.")
                return None
            return s or None

        def dt(f):
            s = _txt(val(f))
            if not s:
                return None
            d = _parse_date(s)
            if d == "bad":
                err(f, "Invalid date.")
                return None
            return d

        def lookup(f, table, label):
            s = _txt(val(f)).lower()
            if not s:
                return None
            obj = table.get(s)
            if obj is None:
                err(f, f"Unknown {label}.")
            return obj

        mfr, num = _txt(val("manufacturer")), _txt(val("model_number"))
        model = models.get((mfr.lower(), num.lower())) if mfr and num else None
        if not mfr or not num:
            err("manufacturer" if not mfr else "model_number", "Required.")
        elif model is None:
            err("equipment_model", "Equipment model not found.")
            entry = missing.setdefault((mfr[:100], num[:100]), [])
            if len(entry) < 50:
                entry.append(i)

        location = lookup("location_code", locs, "location code")
        if not _txt(val("location_code")):
            err("location_code", "Required.")
        department = lookup("department_code", depts, "department code")
        owner = lookup("owner_vendor_name", vendors, "vendor")
        supplier = lookup("supplier_name", vendors, "vendor")
        fund = lookup("funding_source_code", funds, "funding source code")

        serial = txt("serial_number", 100)
        legacy = txt("legacy_asset_id", 100)
        name = txt("name", 200)
        notes = txt("notes", 2000)
        po_no, grn_no, inv_no = txt("purchase_order_number", 100), txt("grn_number", 100), txt("invoice_number", 100)
        po_date, grn_date, inv_date, inst_date = dt("purchase_order_date"), dt("grn_date"), dt("invoice_date"), dt("installation_date")

        ownership = (_txt(val("ownership_type")) or "OWNED").upper()
        if ownership not in OWNERSHIP:
            err("ownership_type", "Invalid value.")
        elif ownership != "OWNED" and owner is None and _txt(val("owner_vendor_name")) == "":
            err("owner_vendor_name", "Required when ownership is not Owned.")
        crit = (_txt(val("criticality")) or "MEDIUM").upper()
        if crit not in CRITICALITY:
            err("criticality", "Invalid value.")
        state = (_txt(val("operational_state")) or "IN_SERVICE").upper()
        if state not in IMPORT_STATES:
            err("operational_state", "Invalid value.")

        cost = None
        cost_s = _txt(val("purchase_cost"))
        if cost_s:
            try:
                cost = Decimal(cost_s.replace(",", ""))
                if not cost.is_finite() or cost < 0 or cost >= Decimal(10) ** 12:
                    raise InvalidOperation
                cost = cost.quantize(Decimal("0.01"))
            except InvalidOperation:
                err("purchase_cost", "Invalid number.")
                cost = None

        skey = (model.pk, serial.lower()) if model is not None and serial else None
        if skey:
            if skey in seen_serial:
                err("serial_number", "Duplicate serial number in the file.")
            seen_serial.add(skey)
        if legacy:
            if legacy.lower() in seen_legacy:
                err("legacy_asset_id", "Duplicate legacy asset ID in the file.")
            seen_legacy.add(legacy.lower())

        if len(errors) == errs_before and model is not None:
            parsed.append({
                "row": i, "operational_state": state, "installation_date": inst_date, "skey": skey,
                "fields": {
                    "equipment_model": model, "name": name or model.model_name, "serial_number": serial,
                    "owning_department": department, "current_location": location, "criticality": crit,
                    "ownership_type": ownership, "owner_vendor": owner, "funding_source": fund,
                    "supplier_vendor": supplier, "purchase_order_number": po_no, "purchase_order_date": po_date,
                    "grn_number": grn_no, "grn_date": grn_date, "invoice_number": inv_no,
                    "invoice_date": inv_date, "purchase_cost": cost, "legacy_asset_id": legacy, "notes": notes,
                },
            })

    # clashes with existing data
    keys = {p["skey"] for p in parsed if p["skey"]}
    if keys:
        existing = set(
            Equipment.objects.filter(facility_id=fid, is_active=True,
                                     equipment_model_id__in={k[0] for k in keys}, serial_number__isnull=False)
            .annotate(ls=Lower("serial_number")).filter(ls__in={k[1] for k in keys})
            .values_list("equipment_model_id", "ls"))
        for p in parsed:
            if p["skey"] in existing:
                errors.append({"row": p["row"], "field": "serial_number", "message": "Serial number already exists."})
    legacies = {p["fields"]["legacy_asset_id"].lower() for p in parsed if p["fields"]["legacy_asset_id"]}
    if legacies:
        taken = set(Equipment.objects.filter(facility_id=fid, is_active=True, legacy_asset_id__isnull=False)
                    .annotate(ll=Lower("legacy_asset_id")).filter(ll__in=legacies).values_list("ll", flat=True))
        for p in parsed:
            lid = p["fields"]["legacy_asset_id"]
            if lid and lid.lower() in taken:
                errors.append({"row": p["row"], "field": "legacy_asset_id", "message": "Legacy asset ID already exists."})

    bad_rows = {e["row"] for e in errors}
    errors.sort(key=lambda e: e["row"])
    result = {
        "total_rows": len(raw),
        "valid_rows": len(raw) - len(bad_rows),
        "errors": errors[:MAX_ERRORS],
        "errors_truncated": len(errors) > MAX_ERRORS,
        "missing_models": [{"manufacturer": m, "model_number": n, "rows": rows}
                           for (m, n), rows in sorted(missing.items())],
        "headers": headers, "mapping": mapped, "missing_columns": [],
    }
    return result, parsed


# ---------------------------------------------------------------- commit
def commit(request, facility, parsed):
    """All-or-nothing creation of legacy entries at COMMISSIONED. One IMPORT audit event."""
    n = len(parsed)
    if n == 0:
        raise ValidationError({"file": ["The file has no data rows."]})
    uid = request.user.id
    try:
        with transaction.atomic():
            tags = services.generate_asset_tags(facility, n)
            objs = [
                Equipment(facility=facility, asset_tag=tag, qr_code_value=services.new_qr_code_value(),
                          lifecycle_stage="COMMISSIONED", operational_state=p["operational_state"],
                          is_legacy_entry=True, created_by=uid, updated_by=uid, **p["fields"])
                for tag, p in zip(tags, parsed)
            ]
            Equipment.objects.bulk_create(objs, batch_size=500)
            EquipmentCommissioning.objects.bulk_create([
                EquipmentCommissioning(
                    facility=facility, equipment=eq, installation_date=p["installation_date"],
                    commissioning_date=p["installation_date"],
                    handed_over_department=p["fields"]["owning_department"], created_by=uid, updated_by=uid)
                for eq, p in zip(objs, parsed)], batch_size=500)
            EquipmentMovement.objects.bulk_create([
                EquipmentMovement(
                    facility_id=facility.id, equipment=eq, from_location=None,
                    to_location=p["fields"]["current_location"], from_department=None,
                    to_department=p["fields"]["owning_department"], reason="Initial placement", created_by=uid)
                for eq, p in zip(objs, parsed)], batch_size=500)
            history = []
            for eq, p in zip(objs, parsed):
                history.append(EquipmentStateHistory(
                    facility_id=facility.id, equipment=eq, change_type="LIFECYCLE", from_value=None,
                    to_value="COMMISSIONED", reason="Legacy import", created_by=uid))
                history.append(EquipmentStateHistory(
                    facility_id=facility.id, equipment=eq, change_type="OPERATIONAL", from_value=None,
                    to_value=p["operational_state"], reason="Legacy import", created_by=uid))
            EquipmentStateHistory.objects.bulk_create(history, batch_size=500)
            audit.record(request=request, action="IMPORT", facility_id=facility.id, entity_type=services.ENTITY,
                         new={"count": n, "first_asset_tag": tags[0], "last_asset_tag": tags[-1]})
    except IntegrityError:
        raise Conflict("The import could not be completed. Run the dry-run again and retry.")
    return tags


def template_csv():
    return ",".join(FIELDS) + "\r\n"

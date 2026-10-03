import os
from dotenv import load_dotenv

_script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_script_dir, ".env"))
load_dotenv()

import re, io, json, time, hashlib, datetime, statistics, threading, secrets, getpass, subprocess, csv, warnings, traceback
from typing import List, Optional

warnings.filterwarnings("ignore", message=".*To copy construct from a tensor.*")
warnings.filterwarnings("ignore", message=".*Non compatible API.*")
warnings.filterwarnings("ignore", message=".*No ccache found.*")


def log_stage(stage: str, msg: str, elapsed: Optional[float] = None):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    elapsed_str = f" | elapsed={elapsed:.2f}s" if elapsed is not None else ""
    print(f"[{ts}] [{stage}] {msg}{elapsed_str}", flush=True)


def _secret(name, prompt=False):
    value = os.environ.get(name)
    if value:
        return value
    return getpass.getpass(f"{name}: ") if prompt else None


GEMINI_API_KEY  = _secret("GEMINI_API_KEY", prompt=True)
_tok            = _secret("API_TOKEN")
API_TOKEN       = _tok or secrets.token_urlsafe(32)
DATABASE_URL    = _secret("DATABASE_URL")
FRONTEND_ORIGIN = _secret("FRONTEND_ORIGIN") or "*"

# ---- confidence gate ------------------------------------------------------------------------------
# PaddleOCR scores are NOT calibrated probabilities - tune these on your own labelled prescriptions.
THRESH_OK    = 0.90    # critical field >= this and no validation issue  -> flag "ok"
THRESH_LOW   = 0.75    # below this -> flag "low" (UI should force the user to look at it)
CRITICAL_FIELDS = ("name", "strength", "frequency", "duration")   # a wrong value here can harm a patient

# ---- LLM ------------------------------------------------------------------------------------------------
MODEL_CANDIDATES = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-flash-latest"
]
SEND_IMAGE_TO_LLM = False   # True = Gemini also sees the image to double-check low-confidence lines
                            # (clearly better on handwriting; the image then leaves your server -> check privacy terms/consent)
USE_UNWARPING = False       # True for curved / photographed pages

# ---- upload limits ---------------------------------------------------------------------------------------
MAX_UPLOAD_MB = 10
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg", "image/pjpeg"}

# ---- database --------------------------------------------------------------------------------------------
import urllib.parse
from sqlalchemy.engine import make_url


def sanitize_database_url(raw_url: Optional[str]) -> str:
    """
    Sanitizes and normalizes the database URL for Supabase PostgreSQL.
    Properly encodes passwords containing special characters (e.g. '@', '#', '%', '!')
    without double-encoding existing percent-escapes.
    Normalizes 'postgres://' or 'postgresql://' to 'postgresql+psycopg2://'.
    """
    if not raw_url:
        return ""
    url = raw_url.strip()
    if url.startswith("sqlite"):
        return url

    # Normalize postgres:// -> postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    # Match proto://user:password@endpoint
    match = re.match(
        r'^(?P<proto>postgresql(?:\+[a-zA-Z0-9_]+)?)://(?P<user>[^:]+):(?P<password>.+)@(?P<endpoint>[^@]+)$',
        url
    )
    if match:
        proto = match.group("proto")
        if proto == "postgresql":
            proto = "postgresql+psycopg2"
        user = match.group("user")
        raw_pw = match.group("password")
        unquoted = urllib.parse.unquote(raw_pw)
        quoted_pw = urllib.parse.quote_plus(unquoted)
        endpoint = match.group("endpoint")
        return f"{proto}://{user}:{quoted_pw}@{endpoint}"

    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing or empty. Please configure your Supabase PostgreSQL connection string "
        "in model/.env (e.g., DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres "
        "or connection pooler: DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres). "
        "For offline local development, you may set DATABASE_URL=sqlite:///rx_local.db"
    )

CLEAN_DB_URL = sanitize_database_url(DATABASE_URL)

try:
    parsed_db_url = make_url(CLEAN_DB_URL)
    is_postgres = parsed_db_url.drivername.startswith("postgresql")
    masked_db_url = parsed_db_url.render_as_string(hide_password=True)
except Exception as e:
    raise RuntimeError(f"Invalid DATABASE_URL configuration: {e}")

print("DB      :", masked_db_url)
if not _tok:
    print("API key : (auto-generated for this session) ->", API_TOKEN)

"""## 3. Database
Tables: `raw_ocr` (raw OCR lines) - `extractions` (LLM draft + validation result) - `confirmed_prescriptions` (what the user confirmed) -
`observations` (numeric BP / sugar / weight rows for trends) - `medicine_master` (authenticated medicine data) - `audit_log`.

`medicine_master` is seeded with a **tiny starter list** so the pipeline works. Replace it with your authenticated database using
`import_medicine_csv("file.csv")` (columns: `name, generic, composition, uses, strengths_mg`).
"""

from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String, Text, Float,
                        select, insert, update, func)

_kw = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
} if is_postgres else {
    "connect_args": {"check_same_thread": False}
}

try:
    engine = create_engine(CLEAN_DB_URL, **_kw)
    with engine.connect() as test_conn:
        test_conn.execute(select(1))
except Exception as conn_err:
    raise RuntimeError(
        f"Could not connect to database ({masked_db_url}). Please verify network access, "
        f"Supabase project status, and credentials in model/.env. Error: {conn_err}"
    ) from conn_err

md_ = MetaData()

raw_ocr = Table("raw_ocr", md_,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("image_sha256", String(64), index=True),
    Column("patient_id", String(64), index=True),
    Column("filename", String(255)),
    Column("ocr_engine", String(64)),
    Column("image_w", Integer), Column("image_h", Integer),
    Column("avg_conf", Float),
    Column("lines_json", Text),
    Column("created_at", String(32)))

extractions = Table("extractions", md_,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("raw_ocr_id", Integer, index=True),
    Column("llm_model", String(64)),
    Column("analysis_json", Text),          # {record, gate, warnings}
    Column("status", String(32), index=True),   # PENDING_USER_CONFIRMATION | CONFIRMED | DISCARDED
    Column("created_at", String(32)))

confirmed_prescriptions = Table("confirmed_prescriptions", md_,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("extraction_id", Integer, unique=True),
    Column("patient_id", String(64), index=True),
    Column("rx_date", String(10), index=True),   # YYYY-MM-DD
    Column("hospital", String(255)), Column("doctor", String(255)), Column("doctor_reg_no", String(64)),
    Column("data_json", Text),                   # the final record the user confirmed
    Column("edits_json", Text),                  # what the user changed vs the machine output
    Column("confirmed_by", String(64)),
    Column("confirmed_at", String(32)))

observations = Table("observations", md_,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("patient_id", String(64), index=True),
    Column("prescription_id", Integer, index=True),
    Column("obs_date", String(10), index=True),
    Column("kind", String(24), index=True),      # bp | sugar_fasting | sugar_post_meal | sugar_random | hba1c | sugar_unspecified | pulse | temp | spo2 | weight
    Column("systolic", Float), Column("diastolic", Float), Column("value", Float),
    Column("unit", String(16)), Column("raw_text", String(120)),
    Column("created_at", String(32)))

medicine_master = Table("medicine_master", md_,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(120), unique=True),    # brand or generic name, lower case
    Column("generic", String(160)), Column("composition", Text), Column("uses", Text),
    Column("strengths_mg", String(200)),         # "250,500,850" (blank = unknown)
    Column("source", String(80)))

audit_log = Table("audit_log", md_,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String(32)), Column("event", String(40)),
    Column("extraction_id", Integer), Column("detail", Text))

md_.create_all(engine)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

def jd(o):
    return json.dumps(o, ensure_ascii=False, default=str)

def audit(conn, event, extraction_id=None, detail=None):
    conn.execute(insert(audit_log).values(ts=now_iso(), event=event, extraction_id=extraction_id,
                                          detail=jd(detail) if detail is not None else None))


# ---- medicine master -----------------------------------------------------------------------------
# STARTER ROWS ONLY - replace with your authenticated medicine database.
STARTER = [
    ("metformin", "metformin", "Metformin hydrochloride", "Type 2 diabetes (lowers blood glucose)", "250,500,850,1000"),
    ("atorvastatin", "atorvastatin", "Atorvastatin calcium", "High cholesterol; reduces cardiovascular risk", "5,10,20,40,80"),
    ("pantoprazole", "pantoprazole", "Pantoprazole sodium", "Acid reflux (GERD), peptic ulcer", "20,40"),
    ("pan", "pantoprazole", "Pantoprazole sodium", "Acid reflux (GERD), peptic ulcer", "20,40"),
    ("vitamin d3", "cholecalciferol", "Cholecalciferol (vitamin D3)", "Vitamin D deficiency", ""),
    ("cholecalciferol", "cholecalciferol", "Cholecalciferol (vitamin D3)", "Vitamin D deficiency", ""),
    ("paracetamol", "paracetamol", "Paracetamol", "Fever; mild to moderate pain", "250,500,650,1000"),
    ("pacimol", "paracetamol", "Paracetamol", "Fever; mild to moderate pain", ""),
    ("calpol", "paracetamol", "Paracetamol", "Fever; mild to moderate pain", ""),
    ("amlodipine", "amlodipine", "Amlodipine besylate", "High blood pressure; angina", "2.5,5,10"),
    ("telmisartan", "telmisartan", "Telmisartan", "High blood pressure", "20,40,80"),
    ("ondansetron", "ondansetron", "Ondansetron", "Nausea and vomiting", "4,8"),
    ("emset", "ondansetron", "Ondansetron", "Nausea and vomiting", ""),
    ("levofloxacin", "levofloxacin", "Levofloxacin", "Bacterial infections (antibiotic)", "250,500,750"),
    ("febuxostat", "febuxostat", "Febuxostat", "Gout (lowers uric acid)", "40,80"),
    ("folvite", "folic acid", "Folic acid", "Folate deficiency; anaemia", ""),
    ("dytor", "torsemide", "Torsemide", "Fluid retention (oedema); heart/liver/kidney related", ""),
    ("levolin", "levosalbutamol", "Levosalbutamol", "Asthma / wheezing (bronchodilator)", ""),
    ("meftal-p", "mefenamic acid + paracetamol", "Mefenamic acid + Paracetamol", "Fever; pain", ""),
]

def seed_starter_medicines():
    with engine.begin() as c:
        if c.execute(select(medicine_master.c.id).limit(1)).first():
            return
        for n, g, comp, uses, st in STARTER:
            c.execute(insert(medicine_master).values(name=n, generic=g, composition=comp, uses=uses,
                                                     strengths_mg=st, source="starter_seed_REPLACE_WITH_REAL_DB"))

MED_INDEX = {}      # lower-case name or generic -> row dict

def load_med_index():
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(select(medicine_master)).mappings().all()]
    MED_INDEX.clear()
    for r in rows:
        MED_INDEX[r["name"].lower()] = r
        if r["generic"]:
            MED_INDEX.setdefault(r["generic"].lower(), r)
    return len(rows)

def import_medicine_csv(path, source="csv_import"):
    """CSV columns: name, generic, composition, uses, strengths_mg  (strengths_mg like 250,500)"""
    n = 0
    with open(path, newline="", encoding="utf-8") as f, engine.begin() as c:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip().lower()
            if not name:
                continue
            vals = dict(generic=(row.get("generic") or "").strip(), composition=(row.get("composition") or "").strip(),
                        uses=(row.get("uses") or "").strip(), strengths_mg=(row.get("strengths_mg") or "").strip(), source=source)
            ex = c.execute(select(medicine_master.c.id).where(medicine_master.c.name == name)).first()
            if ex:
                c.execute(update(medicine_master).where(medicine_master.c.id == ex[0]).values(**vals))
            else:
                c.execute(insert(medicine_master).values(name=name, **vals))
            n += 1
    load_med_index()
    return n

seed_starter_medicines()
print("medicine_master rows:", load_med_index())

"""## 4. Pre-processing, OCR model, reading-order lines
The OCR model is loaded **once** and reused for every upload.
"""

from PIL import Image, ImageOps

PRE_DIR = "preprocessed"
os.makedirs(PRE_DIR, exist_ok=True)

def preprocess_image(data: bytes, min_long_side=1200, max_long_side=1800):
    """bytes -> path of cleaned PNG, (w, h). Fixes phone rotation, faded ink, tiny and huge images."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=1)
    w, h = img.size
    long_side = max(w, h)
    if long_side < min_long_side or long_side > max_long_side:
        s = (min_long_side if long_side < min_long_side else max_long_side) / long_side
        img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    out = os.path.join(PRE_DIR, hashlib.sha256(data).hexdigest()[:16] + ".png")
    img.save(out)
    return out, img.size

import paddle
import threading

if '_PADDLEOCR_READY' not in globals():

    from paddleocr import PaddleOCRVL

    print(
        "PaddlePaddle:", paddle.__version__,
        "| GPU:", paddle.is_compiled_with_cuda()
    )

    ocr = PaddleOCRVL(
        device=os.environ.get("PADDLEOCR_DEVICE", "cpu")
    )

    OCR_LOCK = threading.Lock()

    OCR_ENGINE = "PaddleOCR-VL"

    _PADDLEOCR_READY = True

else:
    print("PaddleOCR-VL already initialized, skipping re-initialization.")

# def run_ocr(path, fallback_size):
#     """-> (raw boxes list, (w, h) of the image the boxes refer to)"""
#     with OCR_LOCK:
#         res = ocr.predict(path)[0]
#     w, h = fallback_size
#     try:                                   # boxes refer to the (possibly rotated) preprocessed image
#         arr = res["doc_preprocessor_res"]["output_img"]
#         h, w = arr.shape[:2]
#     except Exception:
#         pass
#     raw = []
#     polys = res["rec_polys"] if "rec_polys" in res else res["dt_polys"]
#     for text, score, poly in zip(res["rec_texts"], res["rec_scores"], polys):
#         text = text.strip()
#         if not re.search(r"[A-Za-z0-9]", text):          # drop lone ':' / punctuation noise
#             continue
#         xs, ys = [float(p[0]) for p in poly], [float(p[1]) for p in poly]
#         raw.append(dict(text=text, conf=float(score), x0=min(xs), x1=max(xs), y0=min(ys), y1=max(ys)))
#     return raw, (w, h)


# def build_lines(raw, img_w, img_h):
#     """Reading order + rows. Lines at the same height share a row number (e.g. 'Age/Sex : 34/M')."""
#     if not raw:
#         return []
#     for r in raw:
#         r["cy"] = (r["y0"] + r["y1"]) / 2
#         r["h"] = r["y1"] - r["y0"]
#     med_h = statistics.median(r["h"] for r in raw) or 1.0
#     raw = sorted(raw, key=lambda r: r["cy"])
#     rows, cur = [], [raw[0]]
#     for r in raw[1:]:
#         row_cy = sum(x["cy"] for x in cur) / len(cur)
#         if abs(r["cy"] - row_cy) <= 0.6 * med_h:
#             cur.append(r)
#         else:
#             rows.append(cur)
#             cur = [r]
#     rows.append(cur)
#     lines, n = [], 0
#     for ri, row in enumerate(rows, start=1):
#         for r in sorted(row, key=lambda r: r["x0"]):
#             n += 1
#             lines.append(dict(id=f"L{n:02d}", row=ri, text=r["text"], conf=round(r["conf"], 4),
#                               x=round(r["x0"] / img_w, 3), y=round(r["cy"] / img_h, 3)))
#     return lines


# def mask_pii(text):
#     """Clinic phone / e-mail are not needed for extraction - do not send them to an external API."""
#     text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[EMAIL]", text)
#     text = re.sub(r"(?<!\d)(?:\+?91[- ]?)?\d{2,5}[- ]?\d{6,8}(?!\d)", "[PHONE]", text)
#     return text


# def lines_to_prompt_block(lines):
#     return "\n".join(f"{l['id']} | row {l['row']} | x={l['x']} y={l['y']} | conf={l['conf']:.3f} | {mask_pii(l['text'])}"
#                      for l in lines)

def run_ocr(path, fallback_size):
    """
    Run PaddleOCR-VL and return:
        (raw boxes list, (w, h) of the image)
    """

    with OCR_LOCK:
        output = ocr.predict(path)

    w, h = fallback_size
    raw = []

    for res in output:

        parsing_res_list = res.get("parsing_res_list", [])

        for item in parsing_res_list:

            # PaddleOCR-VL returns PaddleOCRVLBlock objects
            # instead of normal dictionaries.

            text = getattr(item, "content", "")

            if text is None:
                text = ""

            text = str(text).strip()

            # Ignore empty text
            if not text:
                continue

            # Ignore punctuation-only noise
            if not re.search(r"[A-Za-z0-9]", text):
                continue

            # Get bounding box from PaddleOCRVLBlock
            bbox = getattr(item, "bbox", None)

            if bbox is None:
                continue

            # Convert bbox to normal Python list
            bbox = list(bbox)

            if len(bbox) != 4:
                continue

            x0, y0, x1, y1 = map(float, bbox)

            raw.append(
                dict(
                    text=text,
                    conf=1.0,
                    x0=x0,
                    x1=x1,
                    y0=y0,
                    y1=y1
                )
            )

    return raw, (w, h)


def build_lines(raw, img_w, img_h):
    """Reading order + rows. Lines at the same height share a row number (e.g. 'Age/Sex : 34/M')."""

    if not raw:
        return []

    for r in raw:
        r["cy"] = (r["y0"] + r["y1"]) / 2
        r["h"] = r["y1"] - r["y0"]

    med_h = statistics.median(r["h"] for r in raw) or 1.0

    raw = sorted(raw, key=lambda r: r["cy"])

    rows, cur = [], [raw[0]]

    for r in raw[1:]:
        row_cy = sum(x["cy"] for x in cur) / len(cur)

        if abs(r["cy"] - row_cy) <= 0.6 * med_h:
            cur.append(r)
        else:
            rows.append(cur)
            cur = [r]

    rows.append(cur)

    lines, n = [], 0

    for ri, row in enumerate(rows, start=1):

        for r in sorted(row, key=lambda r: r["x0"]):
            n += 1

            lines.append(
                dict(
                    id=f"L{n:02d}",
                    row=ri,
                    text=r["text"],
                    conf=round(r["conf"], 4),
                    x=round(r["x0"] / img_w, 3),
                    y=round(r["cy"] / img_h, 3)
                )
            )

    return lines


def mask_pii(text):
    """Clinic phone / e-mail are not needed for extraction - do not send them to an external API."""

    text = re.sub(
        r"[\w.+-]+@[\w-]+\.[\w.]+",
        "[EMAIL]",
        text
    )

    text = re.sub(
        r"(?<!\d)(?:\+?91[- ]?)?\d{2,5}[- ]?\d{6,8}(?!\d)",
        "[PHONE]",
        text
    )

    return text


def lines_to_prompt_block(lines):

    return "\n".join(
        f"{l['id']} | row {l['row']} | "
        f"x={l['x']} y={l['y']} | "
        f"conf={l['conf']:.3f} | "
        f"{mask_pii(l['text'])}"
        for l in lines
    )

"""## 5. Gemini structuring
Every value carries `src` (the OCR line ids it was read from). The LLM **never reports a confidence number** - code computes it as the minimum
confidence of the source lines. The LLM may not correct or invent anything.
"""

from pydantic import BaseModel
from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_API_KEY)


class Val(BaseModel):
    value: Optional[str]      # exactly as in the OCR text (do NOT correct); null if absent
    src: List[str]            # OCR line ids this value was read from

class Medicine(BaseModel):
    name: Val                 # medicine name only: no Tab./Cap./Syp. prefix, no numbering, no strength
    form: Val                 # Tab / Cap / Inj / Syp / Neb ...
    strength: Val             # "500 mg", "250/5", "60K"
    dose: Val                 # amount per intake: "1 cap", "3 ml"
    frequency: Val            # "1-0-1", "TDS", "Q6H", "once a week", "SOS"
    timing: Val               # "after food", "night"
    duration: Val             # "30 days", "5d", "8 weeks"
    route: Val                # oral / IV / IM ... only if written
    ambiguity_note: Optional[str]    # why a human should look at it, else null

class Vital(BaseModel):
    name: str                 # "BP", "Sugar (FBS)", "Weight", "PR", "Temp", "SpO2" ... as written
    value: Val

class Prescription(BaseModel):
    looks_like_prescription: bool
    hospital_name: Val
    doctor_name: Val
    doctor_reg_no: Val
    patient_name: Val
    patient_uhid: Val
    patient_age: Val
    patient_sex: Val
    patient_ward_bed: Val
    date: Val
    vitals: List[Vital]
    diagnosis: List[Val]      # complaints / clinical description / diagnosis lines (e.g. "URTI")
    allergies: List[Val]      # ONLY if explicitly written ("Allergic to ...", "NKDA")
    medicines: List[Medicine]
    advice: List[Val]
    follow_up: Val


SYSTEM_PROMPT = """
You are a medical prescription OCR interpretation and structured-data extraction system.

Your input is OCR output generated from ONE medical prescription image by an OCR/Vision-OCR system such as PaddleOCR-VL.

Your job is to:
1. Understand the OCR text and its layout.
2. Correct obvious OCR character errors only when there is sufficient evidence.
3. Identify and structure patient information, vitals, clinical information, medicines, investigations, advice, and follow-up information.
4. Preserve the original OCR reading so that every interpreted value can be traced back to the OCR output.
5. Never invent information that is not supported by the OCR.

IMPORTANT:
You are NOT looking at the original prescription image.
You must work ONLY from the OCR lines provided in the input.
Do not assume that you can see handwriting that is not present in the OCR text.

==================================================
INPUT FORMAT
==================================================

Each OCR line has this format:

<line_id> | row <n> | x=<0-1> y=<0-1> | conf=<0-1> | <text>

Example:

L01 | row 1 | x=0.12 y=0.10 | conf=0.98 | Lloyds Kali Ammal Memorial Hospital
L02 | row 2 | x=0.15 y=0.18 | conf=0.91 | MR-54560
L03 | row 3 | x=0.16 y=0.22 | conf=0.84 | Age 61 M
L04 | row 7 | x=0.12 y=0.45 | conf=0.71 | BP 137/65 mm
L05 | row 8 | x=0.12 y=0.48 | conf=0.62 | Pulse 84/min

The OCR confidence is the confidence supplied by the OCR system.

IMPORTANT:
OCR confidence is NOT medical correctness.
A high OCR confidence does not guarantee that the OCR text is correct.
A low OCR confidence means the text should be treated with additional caution.

Lines with the same row number belong to the same visual line.

Use:
- row number
- x coordinate
- y coordinate
- proximity
- neighboring lines

to determine relationships between fields.

Medicine details such as strength, dose, frequency, timing, duration, and route may appear on the same line, directly below a medicine, or beside it.

==================================================
OCR ERROR HANDLING
==================================================

Handwritten prescription OCR may contain character-level errors such as:

o / 0
I / l / 1
S / 5
G / 6
B / 8
rn / m
cl / d
u / v
c / e
missing spaces
extra spaces
incorrect punctuation
incorrect capitalization

Indian prescription notation may include:

1-0-1
0-1-0
1-1-1
OD
BD
TDS
QID
SOS
HS
Q6H
Q8H
5d
7d
x 30 days
Syp
Tab
Cap
Inj
3 ml
250/5

These are common prescription notations, but DO NOT invent them when they are absent.

==================================================
GENERAL EXTRACTION RULES
==================================================

1. Extract information only when it is supported by the OCR input.

2. Never invent a missing value.

3. If a value is not present or cannot be reliably determined:
   - return null for that field
   - return [] for its src field

4. Every extracted value must include the OCR line IDs that support it in `src`.

5. If multiple OCR lines support one value, include all relevant line IDs.

6. Do not use unrelated lines merely because they are nearby.

7. Use coordinates, row numbers, and surrounding text to determine which fields belong together.

8. Preserve the original OCR text in raw/original fields whenever applicable.

9. Do not silently discard uncertain OCR information.

10. If information is ambiguous, preserve the raw OCR text and mark the interpretation as CHECK instead of inventing a value.

11. Do not create information from general medical expectations.

12. Do not assume that a commonly used dose, frequency, duration, or medicine is intended simply because it would be medically typical.

==================================================
MEDICINE EXTRACTION
==================================================

Medicine extraction requires special handling because handwritten medicine names are often corrupted by OCR.

For EVERY medicine-like item:

1. Identify the raw medicine name exactly as it appears in the OCR text.

2. Preserve the raw OCR medicine name.

3. You MAY normalize/correct the medicine name when the OCR text provides sufficient evidence that the intended medicine can be identified reliably.

4. Medicine-name normalization may use:
   - character-level OCR confusion
   - spelling similarity
   - surrounding medicine-related words
   - dosage/form information
   - prescription notation
   - common medicine naming patterns
   - medical knowledge

5. However, medical knowledge MUST NOT be used to invent a medicine when the OCR evidence is insufficient.

6. If several different medicines are plausible interpretations of the OCR text:
   - do not arbitrarily select one
   - preserve the raw OCR name
   - set the normalized medicine name to null
   - mark the medicine as CHECK

7. If the medicine name is unreadable or highly corrupted:
   - preserve whatever OCR text exists in the raw name
   - normalized name = null
   - status = CHECK

8. Never replace the raw OCR value with the normalized medicine name.

9. The raw OCR value and normalized medicine name must remain distinguishable.

Example:

OCR:
"Thiomerum"

Possible interpretation:
"Thiomerum"

If the evidence is insufficient to confidently identify the actual medicine:
raw_name = "Thiomerum"
normalized_name = null
status = "CHECK"

Do NOT invent a completely different medicine.

==================================================
MEDICINE FIELD RULES
==================================================

For each medicine, keep these fields separate:

- name
- form
- strength
- dose
- frequency
- timing
- duration
- route

Do NOT combine them.

Examples:

"500 mg" → strength

"1 tablet" → dose

"BD" → frequency

"after food" → timing

"5 days" → duration

"oral" → route

"Tab" → form

Do not assume that "BD" means a specific numerical schedule unless the OCR explicitly provides it.

Do not convert "1-0-1" into "twice daily" unless the output schema specifically requires normalization.

Preserve the original prescription notation.

==================================================
NUMBERS AND MEDICAL VALUES
==================================================

Be extremely conservative with numbers.

DO NOT change a numerical value merely because it appears medically unusual.

For example:

OCR:
"500 mg"

Keep:
"500 mg"

OCR:
"5o0 mg"

Do NOT silently change it to:
"500 mg"

Instead:

raw value = "5o0 mg"
normalized value = null or CHECK

Similarly:

OCR:
"981"

Do NOT automatically change it to "98".

An unusual value must be preserved and flagged for validation.

The LLM may recognize obvious OCR formatting problems only when the interpretation is strongly supported by the surrounding OCR text, but the original OCR value must always be preserved.

==================================================
VITALS
==================================================

Extract each vital separately.

Supported vitals include:

- BP / blood pressure
- Pulse
- Heart rate
- SpO2 / oxygen saturation
- RBS / random blood sugar
- FBS / fasting blood sugar
- blood sugar
- temperature
- respiratory rate
- weight
- height

For every vital:

- preserve the value text as OCR
- do not silently correct unusual numerical values
- include src
- flag suspicious or malformed values for validation

Example:

OCR:
"BP 137/65 mm"

Output should preserve:
"137/65 mm"

Do not silently change it to another number.

==================================================
PATIENT INFORMATION
==================================================

Extract when present:

- patient name
- UHID
- MR number
- registration number if it is clearly a patient identifier
- age
- sex/gender
- ward
- bed number

Do not confuse:

- doctor registration number
- hospital phone number
- patient UHID
- medical record number

with each other.

==================================================
DATE
==================================================

Extract the prescription date when present.

Preserve the date exactly as OCR reads it.

Examples:

"22/07/26"
"22-07-2026"
"2/7/26"

Do NOT reformat the date.

Do NOT infer a missing year.

Do NOT use today's date.

If the date is unclear:
date_raw = null

==================================================
DOCTOR AND HOSPITAL
==================================================

Extract:

- hospital name
- doctor name
- doctor registration number

only when clearly identifiable.

Do not confuse hospital information with patient information.

Ignore:

- hospital slogans
- advertisements
- phone numbers
- email addresses
- generic promotional text
- website addresses

unless they are explicitly required by the output schema.

==================================================
DIAGNOSIS / CLINICAL INFORMATION
==================================================

`diagnosis` may include:

- chief complaints
- symptoms
- clinical history
- diagnosis
- relevant medical history
- clearly written clinical observations

Preserve the meaning of the OCR text.

Do not create a medical diagnosis from symptoms.

For example, if OCR says:

"pain abdomen"

do not convert it into:

"gastritis"

unless the OCR explicitly contains that diagnosis.

==================================================
ALLERGIES
==================================================

Extract allergies ONLY when explicitly stated.

Examples:

"Allergy: Penicillin"
"Drug allergy: none"
"NKDA"
"No known drug allergy"

Do not infer an allergy from medicines prescribed.

Do not assume that absence of allergy information means NKDA.

==================================================
INVESTIGATIONS
==================================================

Capture explicitly mentioned tests/investigations.

Examples:

CBC
LFT
KFT
HbA1c
TSH
ECG
USG
X-ray
MRI

Do not invent investigations.

==================================================
ADVICE
==================================================

Capture explicit advice given by the doctor.

Examples:

- diet advice
- exercise advice
- hydration advice
- medication instructions
- monitoring instructions
- test instructions

Keep advice separate from diagnosis.

==================================================
FOLLOW-UP
==================================================

Capture follow-up/review information when explicitly present.

Examples:

"Review after 7 days"
"Follow up after 2 weeks"
"Review with reports"

Do not infer a follow-up date.

==================================================
NON-ENGLISH / GARBLED TEXT
==================================================

If OCR contains non-English text that is clearly garbled and cannot be interpreted reliably:

- do not guess its meaning
- ignore it for structured extraction

If the text is clearly readable and relevant, preserve it if the output schema supports it.

==================================================
SOURCE LINE RULE
==================================================

Every extracted field must contain `src`.

Example:

{
  "value": "61",
  "src": ["L03"]
}

If the field is not found:

{
  "value": null,
  "src": []
}

For a medicine whose fields come from multiple lines:

{
  "name": "...",
  "src": ["L20"],
  "strength": "...",
  "src": ["L21"],
  "frequency": "...",
  "src": ["L22"]
}

Do not cite a line unless that line actually supports the value.

==================================================
MEDICINE CONFIDENCE / STATUS
==================================================

Use the OCR confidence as supporting evidence.

For medicine names, distinguish:

1. OCR reading
2. LLM normalization
3. verification status

A high OCR confidence does NOT automatically mean the normalized medicine name is correct.

Use:

"OK"
when the medicine name is reasonably clear from the OCR.

Use:

"CHECK"
when:
- handwriting/OCR is ambiguous
- multiple medicine names are plausible
- the medicine name is heavily corrupted
- strength/dose/frequency is unclear
- required medicine information is missing

Never mark an uncertain medicine as verified simply because a plausible medicine exists.

==================================================
IMPORTANT DISTINCTION
==================================================

The OCR output is the source material.

The LLM is allowed to INTERPRET noisy OCR, especially medicine names.

The LLM is NOT allowed to fabricate information.

Therefore:

GOOD:
OCR: "Paracitamol"
→ normalized medicine: "Paracetamol"
when the evidence is sufficiently strong.

GOOD:
OCR: "Paracitamol 500 mg"
→ raw name: "Paracitamol"
→ normalized name: "Paracetamol"
→ strength: "500 mg"

UNCERTAIN:
OCR: "Thiomerum"
→ raw name: "Thiomerum"
→ normalized name: null
→ status: "CHECK"

BAD:
OCR: "Thiomerum"
→ invent a completely different medicine because it is medically plausible.

BAD:
OCR: "500 mg"
→ assume which medicine has 500 mg strength.

BAD:
OCR: "St. St."
→ assume it means a specific frequency.

==================================================
PRESCRIPTION DETECTION
==================================================

Set:

looks_like_prescription = true

only when the OCR content contains enough evidence that the document is a medical prescription, treatment sheet, consultation note, or similar clinical document.

Set:

looks_like_prescription = false

when the document clearly is not a prescription or treatment-related document.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

Do not return:
- Markdown
- explanations
- comments
- ```json code fences
- introductory text
- conclusions

The output must conform exactly to the JSON schema supplied by the application.

Do not add extra top-level fields that are not part of the required schema.

Return ALL detected medicines.

Never merge two separate medicine entries into one.

Never omit a medicine merely because some fields are missing.

Use null for missing scalar fields and [] for missing source lists.

==================================================
FINAL QUALITY CHECK BEFORE RETURNING JSON
==================================================

Before producing the final JSON, verify:

1. Is every extracted value supported by OCR?
2. Does every value have correct src line IDs?
3. Did you preserve the raw OCR reading?
4. Did you accidentally invent a medicine?
5. Did you accidentally change a number?
6. Did you merge separate medicines?
7. Are strength, dose, frequency, timing, duration and route separate?
8. Did you distinguish patient ID from doctor/hospital information?
9. Did you distinguish symptoms from diagnosis?
10. Did you avoid assuming allergies?
11. Did you preserve dates exactly as OCR?
12. Did you mark ambiguous medicine names as CHECK?
13. Did you return all medicines?
14. Is the final response valid JSON only?
"""


def call_gemini(lines, image_path=None, retries_per_model=2):

    contents = [
        f"OCR LINES:\n{lines_to_prompt_block(lines)}"
    ]

    if SEND_IMAGE_TO_LLM and image_path:

        with open(image_path, "rb") as f:
            contents.insert(
                0,
                types.Part.from_bytes(
                    data=f.read(),
                    mime_type="image/png"
                )
            )

        contents.append(
            "The image is given only to double-check lines with conf < 0.90. "
            "Do not add anything that is not in the OCR lines; "
            "keep using the OCR line ids as src."
        )

    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=Prescription
    )

    last_error = None

    for model_name in MODEL_CANDIDATES:

        for attempt in range(retries_per_model):

            try:

                print(
                    f"Trying {model_name} "
                    f"(attempt {attempt + 1}/{retries_per_model})..."
                )

                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=cfg
                )

                prescription = Prescription.model_validate_json(
                    response.text
                )

                print(
                    f"SUCCESS! Model used: {model_name}"
                )

                return prescription, model_name

            except Exception as e:
                last_error = str(e)
                print(f"[{model_name}] Error: {last_error[:200]}")
                # If model is expiencing temporary demand spikes (503), fast-fail to next model immediately
                if "503" in last_error or "UNAVAILABLE" in last_error or "429" in last_error:
                    print(f"{model_name} currently unavailable (503/429), immediately falling back to next candidate...\n")
                    break
                if attempt < retries_per_model - 1:
                    print("Retrying in 2 seconds...\n")
                    time.sleep(2)
                else:
                    print(f"{model_name} unavailable. Trying next model...\n")

    raise RuntimeError(
        f"All Gemini models failed. "
        f"Last error: {last_error}"
    )

"""## 6. Validators, auto-corrections, medicine lookup, vitals, dates
* Safe OCR-confusion fixes are applied, but **every corrected value is flagged `check`** - the user must see it.
* Medicine names: exact match in `medicine_master` -> *verified* (generic / composition / uses attached). Near match -> flagged, **never auto-accepted**
  (look-alike drug names are a safety risk). Not found -> *unverified* (nothing is generated).
* Vitals are parsed to numbers and range-checked; BP needs `systolic > diastolic`.
"""

from rapidfuzz import fuzz, process

UNITS = r"(?:mg|mcg|ug|µg|g|gm|ml|iu|k|%)"
NUM   = r"\d+(?:\.\d+)?"
DIG   = r"(?:\d(?:\.\d)?|½)"
STRENGTH_RE = re.compile(rf"^{NUM}\s*{UNITS}?(?:\s*/\s*{NUM}\s*{UNITS}?)*$", re.I)
FREQ_RE = re.compile(
    rf"^(?:{DIG}\s*-\s*{DIG}\s*-\s*{DIG}(?:\s*-\s*{DIG})?|od|bd|bid|tds|tid|qid|qd|hs|sos|stat|prn|q\d{{1,2}}h"
    rf"|(?:once|twice|thrice)\s+(?:a\s+|per\s+)?(?:day|week|month)|\d\s*times\s*(?:a|per)\s*(?:day|week)"
    rf"|weekly|daily|every\s+\d+\s*(?:h|hr|hrs|hours))$", re.I)
DURATION_RE = re.compile(
    r"^(?:[x×*]?\s*\d+\s*(?:d|day|days|w|wk|wks|week|weeks|m|mo|month|months)\.?|continue|ongoing|lifelong|till review)$", re.I)
FORM_PREFIX = re.compile(r"^\s*\d*\.?\s*(tab|tablet|cap|capsule|inj|syp|syrup|neb|drop|drops|oint|susp)\b\.?\s*", re.I)
FREQ_SUGGEST = {"tos": "TDS", "t0s": "TDS", "t.o.s": "T.D.S"}

_DIGITMAP = str.maketrans({"o": "0", "O": "0", "l": "1", "I": "1", "S": "5", "G": "6"})
_TOKEN = re.compile(r"(?<![A-Za-z])[0-9oOlISG.]*\d[0-9oOlISG.]*(?![A-Za-z])")


def fix_digits(s):
    """Letters that look like digits are fixed ONLY inside tokens that already contain a real digit
    (5o0 -> 500, 2S0 -> 250), plus a lone 'I'/'l' before a unit (I cap -> 1 cap)."""
    if not s:
        return s
    s2 = _TOKEN.sub(lambda m: m.group(0).translate(_DIGITMAP), s)
    s2 = re.sub(r"\b[Il]\b(?=\s*(cap|tab|tablet|capsule|ml|drop|puff|amp)\b)", "1", s2, flags=re.I)
    return s2


def fix_duration(s):
    """'Sd' -> '5d', 'x 3O days' -> 'x 30 days' (a duration number can only be digits)."""
    if not s:
        return s
    m = re.match(r"^(\s*[x×*]?\s*)([0-9oOlISG]+)(\s*(?:d|days?|w|wks?|weeks?|m|mo|months?)\.?\s*)$", s, re.I)
    if m:
        num = m.group(2).translate(_DIGITMAP)
        if num.isdigit() and int(num) > 0:
            return m.group(1) + num + m.group(3)
    return s


def fix_frequency(s):
    """1-O-1 -> 1-0-1,  QGH -> Q6H"""
    if not s:
        return s
    t = s.strip()
    if re.fullmatch(r"[0-9oOlI½.]+(\s*-\s*[0-9oOlI½.]+)+", t) and re.search(r"\d", t):
        return t.translate(str.maketrans({"o": "0", "O": "0", "l": "1", "I": "1"}))
    m = re.fullmatch(r"([qQ])\s*([0-9oOlISG]{1,2})\s*([hH])", t)
    if m:
        num = m.group(2).translate(_DIGITMAP)
        if num.isdigit():
            return f"{m.group(1)}{num}{m.group(3)}"
    return s


def field_conf(v, by_id):
    """None = field absent.  0.0 = value present but no valid source line (LLM could not ground it)."""
    if v is None or not v.value:
        return None
    ids = [i for i in v.src if i in by_id]
    return min(by_id[i]["conf"] for i in ids) if ids else 0.0


def lookup_medicine(name):
    """exact -> verified. near (fuzzy) -> must be confirmed by a human. none -> unverified. NEVER generates content."""
    if not name:
        return dict(status="none")
    q = re.sub(r"[^a-z0-9 \-]", "", re.sub(r"\s+", " ", name.lower())).strip()
    row = MED_INDEX.get(q)
    if row:
        return dict(status="exact", score=100, row=row)
    if len(q) >= 5 and MED_INDEX:            # short brand names (pan, emset ...) are never fuzzy matched
        best = process.extractOne(q, list(MED_INDEX.keys()), scorer=fuzz.ratio)
        if best and best[1] >= 85:
            return dict(status="near", score=round(best[1]), row=MED_INDEX[best[0]])
    return dict(status="none")


def _issue(field, code, msg):
    return dict(field=field, code=code, msg=msg)


MED_FIELDS = ("name", "form", "strength", "dose", "frequency", "timing", "duration", "route")


def analyze_medicine(med, by_id):
    issues, warnings, corrected = [], [], []
    conf = {f: field_conf(getattr(med, f), by_id) for f in MED_FIELDS}
    read = {f: getattr(med, f).value for f in MED_FIELDS}
    final = dict(read)
    corrected_fields = set()

    final["name"] = (FORM_PREFIX.sub("", read["name"]).strip() or None) if read["name"] else None
    for f, fn in dict(strength=fix_digits, dose=fix_digits, frequency=fix_frequency, duration=fix_duration).items():
        if read[f]:
            fixed = fn(read[f])
            if fixed != read[f]:
                final[f] = fixed
                corrected_fields.add(f)
                corrected.append(f"{f}: '{read[f]}' -> '{fixed}'")

    if final["duration"]:
        final["duration"] = re.sub(r"^\s*[x×*]\s*", "", final["duration"]).strip()

    # --- format validators
    s = final["strength"]
    if s and not STRENGTH_RE.match(re.sub(r"[()]", "", s).strip()):
        issues.append(_issue("strength", "format_invalid", f"unreadable strength '{s}'"))
    q = final["frequency"]
    if q and not FREQ_RE.match(q.strip()):
        hint = FREQ_SUGGEST.get(q.strip().lower())
        issues.append(_issue("frequency", "format_invalid", f"unreadable frequency '{q}'" + (f" (did you mean {hint}?)" if hint else "")))
    d = final["duration"]
    if d and not DURATION_RE.match(d.strip()):
        issues.append(_issue("duration", "format_invalid", f"unreadable duration '{d}'"))
    for f in CRITICAL_FIELDS:
        if not final[f]:
            issues.append(_issue(f, "missing", f"{f} not found"))
        elif conf[f] == 0.0:
            issues.append(_issue(f, "no_source_line", f"{f} has no valid OCR source line"))

    # --- medicine database
    match = lookup_medicine(final["name"])
    info = dict(verified=False, db_name=None, generic=None, composition=None, uses=None, score=None)
    if match["status"] == "exact":
        r = match["row"]
        info.update(verified=True, db_name=r["name"], generic=r["generic"], composition=r["composition"], uses=r["uses"], score=100)
        if r.get("strengths_mg") and s:
            m = re.match(rf"^\s*({NUM})\s*(?:mg)?\s*$", re.sub(r"[()]", "", s))
            known = [float(x) for x in r["strengths_mg"].split(",") if x.strip()]
            if m and known and float(m.group(1)) not in known:
                issues.append(_issue("strength", "unusual_strength", f"{s} is not a usual strength for {r['name']} (usual: {r['strengths_mg']})"))
    elif match["status"] == "near":
        r = match["row"]
        info.update(db_name=r["name"], score=match["score"])
        issues.append(_issue("name", "near_match", f"'{final['name']}' looks like '{r['name']}' ({match['score']}%) - confirm the exact name"))
    elif final["name"]:
        warnings.append(f"'{final['name']}' not found in medicine database (unverified)")

    # --- per-field flag for the UI
    bad = {i["field"] for i in issues}
    flags = {}
    for f in MED_FIELDS:
        c = conf[f]
        if not final[f]:
            flags[f] = "missing" if f in CRITICAL_FIELDS else "empty"
        elif c is not None and c < THRESH_LOW:
            flags[f] = "low"
        elif (c is not None and c < THRESH_OK) or f in bad or f in corrected_fields:
            flags[f] = "check"
        else:
            flags[f] = "ok"
    crit = [conf[f] for f in CRITICAL_FIELDS if conf[f] is not None]
    min_conf = min(crit) if crit else 0.0
    if any(flags[f] == "low" for f in CRITICAL_FIELDS):
        status = "LOW"
    elif issues or corrected or any(flags[f] in ("check", "missing") for f in CRITICAL_FIELDS):
        status = "CHECK"
    else:
        status = "OK"

    return dict(**final,
                fields={f: dict(read=read[f], conf=conf[f], flag=flags[f]) for f in MED_FIELDS},
                status=status, min_conf=round(min_conf, 4), issues=issues, warnings=warnings, corrected=corrected,
                ambiguity_note=med.ambiguity_note, db=info)


# ---------------------------------------------------------------------------------------------------------
# vitals + date
# ---------------------------------------------------------------------------------------------------------
SUGAR_NAME = re.compile(r"sugar|glucose|\bfbs\b|\bppbs\b|\brbs\b|\bppg\b|\bfbg\b|\brbg\b|hba1c|\ba1c\b|gluco", re.I)

def parse_vital(name, value):
    """-> dict(kind, ok, ...). ok=False + error = skip it for trends. kind 'other' = not tracked."""
    n, v = (name or "").lower(), fix_digits(value or "")
    text = f"{n} {v}"
    num = re.search(r"(\d+(?:\.\d+)?)", v)
    if re.search(r"\bbp\b|blood\s*pressure", n):
        m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", v)
        if not m:
            return dict(kind="bp", ok=False, error="could not read systolic/diastolic")
        s_, d_ = float(m.group(1)), float(m.group(2))
        if not (60 <= s_ <= 260 and 30 <= d_ <= 160 and s_ > d_):
            return dict(kind="bp", ok=False, error=f"implausible BP {s_:.0f}/{d_:.0f}")
        return dict(kind="bp", ok=True, systolic=s_, diastolic=d_, unit="mmHg")
    if SUGAR_NAME.search(n):
        if not num:
            return dict(kind="sugar_unspecified", ok=False, error="no number found")
        x = float(num.group(1))
        if re.search(r"hba1c|\ba1c\b", text):
            kind, unit, lo, hi = "hba1c", "%", 3, 20
        else:
            if re.search(r"\bfbs\b|\bfbg\b|fasting", text): kind = "sugar_fasting"
            elif re.search(r"\bppbs\b|\bppg\b|\bpp\b|post", text): kind = "sugar_post_meal"
            elif re.search(r"\brbs\b|\brbg\b|random", text): kind = "sugar_random"
            else: kind = "sugar_unspecified"
            unit = "mmol/L" if "mmol" in text else "mg/dL"
            lo, hi = (1, 45) if unit == "mmol/L" else (20, 800)
        if not (lo <= x <= hi):
            return dict(kind=kind, ok=False, error=f"implausible value {x:g} {unit}")
        return dict(kind=kind, ok=True, value=x, unit=unit)
    spec = [("pulse", r"\bpr\b|pulse|heart\s*rate|\bhr\b", 30, 220, "/min"),
            ("temp", r"temp", 30, 110, "F/C"),
            ("spo2", r"spo2|oxygen|o2\s*sat", 50, 100, "%"),
            ("weight", r"weight|\bwt\b", 1, 300, "kg")]
    for kind, pat, lo, hi, unit in spec:
        if re.search(pat, n):
            if not num:
                return dict(kind=kind, ok=False, error="no number found")
            x = float(num.group(1))
            if kind == "temp":
                unit = "F" if x >= 90 else "C"
                lo, hi = (90, 110) if unit == "F" else (30, 43)
            if not (lo <= x <= hi):
                return dict(kind=kind, ok=False, error=f"implausible value {x:g}")
            return dict(kind=kind, ok=True, value=x, unit=unit)
    return dict(kind="other", ok=False, error=None)


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

def parse_date(s):
    """-> (iso 'YYYY-MM-DD' or None, ambiguous_dayfirst: bool). Indian format = day first."""
    if not s:
        return None, False
    for cand in (s, fix_digits(s)):
        m = re.search(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})", cand)
        if m:
            dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            yy = yy + 2000 if yy < 100 else yy
            try:
                return datetime.date(yy, mm, dd).isoformat(), (dd <= 12 and mm <= 12 and dd != mm)
            except ValueError:
                pass
        m = re.search(r"(\d{1,2})\s*([A-Za-z]{3})[a-z]*\.?,?\s*(\d{2,4})", cand)
        if m and m.group(2).lower() in _MONTHS:
            yy = int(m.group(3)); yy = yy + 2000 if yy < 100 else yy
            try:
                return datetime.date(yy, _MONTHS[m.group(2).lower()], int(m.group(1))).isoformat(), False
            except ValueError:
                pass
    return None, False

def _g(v):
    return v.value if v is not None and v.value else None


def analyze_prescription(rx, by_id, expected_name=None):
    """-> dict(record=<UI record>, gate=<status+reasons>, warnings=[...])"""
    reasons, warnings = [], []
    meds = [analyze_medicine(m, by_id) for m in rx.medicines]

    # identity
    ident_conf = field_conf(rx.patient_name, by_id)
    identity_issue = None
    if _g(rx.patient_name) is None:
        identity_issue = "patient name not found on the prescription"
    elif ident_conf is not None and ident_conf < THRESH_OK:
        identity_issue = f"patient name read with low confidence ({ident_conf:.2f})"
    if expected_name and _g(rx.patient_name):
        if fuzz.token_set_ratio(expected_name.lower(), _g(rx.patient_name).lower()) < 70:
            identity_issue = f"name on prescription ('{_g(rx.patient_name)}') does not match the logged-in patient ('{expected_name}')"
            reasons.append("NAME_MISMATCH")
    if identity_issue:
        reasons.append(identity_issue)

    # date
    date_iso, ambiguous = parse_date(_g(rx.date))
    date_issue = None
    if date_iso is None:
        date_issue = "date missing or unreadable - set it before confirming (needed for the timeline and trends)"
    elif date_iso > (datetime.date.today() + datetime.timedelta(days=1)).isoformat():
        date_issue = f"date {date_iso} is in the future - check it"
    elif ambiguous:
        warnings.append(f"date read as day/month/year -> {date_iso}")
    if date_issue:
        reasons.append(date_issue)

    # vitals
    vit = []
    vital_issue = False
    for v in rx.vitals:
        val = _g(v.value)
        p = parse_vital(v.name, val)
        c = field_conf(v.value, by_id)
        flag = "ok"
        if p["kind"] != "other":
            if not p["ok"]:
                flag, vital_issue = "check", True
                reasons.append(f"vital {v.name}: {p['error']}")
            elif c is not None and c < THRESH_LOW:
                flag, vital_issue = "low", True
                reasons.append(f"vital {v.name} read with low confidence ({c:.2f})")
            elif c is not None and c < THRESH_OK:
                flag, vital_issue = "check", True
        vit.append(dict(name=v.name, value=val, conf=c, flag=flag, kind=p["kind"], parsed={k: x for k, x in p.items() if k not in ("kind",)}))

    for m in meds:
        if m["status"] != "OK":
            reasons.append(f"{m['name'] or '?'}: {m['status']} " + "; ".join(i["msg"] for i in m["issues"]) + (" | auto-corrected: " + ", ".join(m["corrected"]) if m["corrected"] else ""))
        warnings.extend(m["warnings"])

    # page level gate
    low = sum(m["status"] == "LOW" for m in meds)
    if not rx.looks_like_prescription:
        status = "LOW_QUALITY"; reasons.insert(0, "does not look like a prescription")
    elif not meds:
        status = "LOW_QUALITY"; reasons.insert(0, "no medicines could be read - ask the user to re-upload a clearer photo")
    elif low * 2 >= len(meds):
        status = "LOW_QUALITY"; reasons.insert(0, "most medicines were read with low confidence - ask for a clearer photo")
    elif identity_issue or date_issue or vital_issue or any(m["status"] != "OK" for m in meds):
        status = "NEEDS_CHECK"
    else:
        status = "HIGH_CONFIDENCE"

    record = dict(
        patient=dict(name=_g(rx.patient_name), uhid=_g(rx.patient_uhid), age=_g(rx.patient_age), sex=_g(rx.patient_sex),
                     ward_bed=_g(rx.patient_ward_bed), name_conf=ident_conf),
        hospital=_g(rx.hospital_name),
        doctor=dict(name=_g(rx.doctor_name), reg_no=_g(rx.doctor_reg_no)),
        date_raw=_g(rx.date), date_iso=date_iso,
        vitals=vit, diagnosis=[x.value for x in rx.diagnosis if x.value], allergies=[x.value for x in rx.allergies if x.value],
        medicines=meds, advice=[x.value for x in rx.advice if x.value], follow_up=_g(rx.follow_up))
    return dict(record=record, gate=dict(status=status, reasons=reasons), warnings=warnings)

"""## 7. Pipeline functions (OCR -> raw DB -> LLM -> validation -> draft DB)"""

class PipelineError(Exception):
    def __init__(self, msg, raw_ocr_id=None, http=500):
        super().__init__(msg); self.raw_ocr_id, self.http = raw_ocr_id, http


def _payload(extraction_id, raw_id, status, analysis, model, duplicate=False):
    return dict(ocr_id=raw_id, extraction_id=extraction_id, status=status, llm_model=model, duplicate=duplicate, **analysis)


def structure_from_raw(raw_id, expected_name=None, image_path=None):
    """Step 4-6: run the LLM on the STORED raw OCR (also used to retry after an LLM failure without re-running OCR)."""
    t_start = time.time()
    log_stage("DB_FETCH", f"Fetching stored raw OCR lines for raw_ocr_id={raw_id}")
    with engine.connect() as c:
        row = c.execute(select(raw_ocr).where(raw_ocr.c.id == raw_id)).mappings().first()
    if not row:
        log_stage("ERROR", f"raw_ocr row #{raw_id} not found in database")
        raise PipelineError("raw_ocr row not found", http=404)
    lines = json.loads(row["lines_json"])
    by_id = {l["id"]: l for l in lines}
    log_stage("LLM_STRUCTURING", f"Invoking Google Gemini on {len(lines)} OCR lines...")
    t_llm = time.time()
    try:
        rx, model = call_gemini(lines, image_path)
        log_stage("LLM_STRUCTURING", f"Gemini structuring succeeded using model '{model}'", time.time() - t_llm)
    except Exception as e:
        log_stage("ERROR", f"Gemini structuring failed: {e}\n{traceback.format_exc()}", time.time() - t_llm)
        with engine.begin() as c:
            audit(c, "llm_failed", None, dict(raw_ocr_id=raw_id, error=str(e)[:300]))
        raise PipelineError(f"LLM structuring failed: {e}", raw_ocr_id=raw_id, http=502)

    t_val = time.time()
    log_stage("VALIDATION", "Analyzing prescription entities and cross-referencing Drug Master...")
    analysis = analyze_prescription(rx, by_id, expected_name)
    med_count = len(analysis.get("record", {}).get("medicines", []))
    gate_st = analysis.get("gate", {}).get("status", "UNKNOWN")
    log_stage("VALIDATION", f"Validation complete: gate={gate_st}, {med_count} medicines extracted", time.time() - t_val)

    t_db = time.time()
    with engine.begin() as c:
        eid = c.execute(insert(extractions).values(raw_ocr_id=raw_id, llm_model=model, analysis_json=jd(analysis),
                                                   status="PENDING_USER_CONFIRMATION", created_at=now_iso())).inserted_primary_key[0]
        audit(c, "extracted", eid, dict(raw_ocr_id=raw_id, gate=gate_st, model=model))
    log_stage("DATABASE", f"Draft extraction #{eid} committed to database", time.time() - t_db)
    log_stage("PIPELINE_COMPLETE", f"Structuring completed successfully for extraction #{eid}", time.time() - t_start)
    return _payload(eid, raw_id, "PENDING_USER_CONFIRMATION", analysis, model)


def process_image(data: bytes, filename: str, patient_id: str, expected_name: Optional[str] = None):
    t_pipeline_start = time.time()
    sha = hashlib.sha256(data).hexdigest()
    log_stage("UPLOAD_RECEIVED", f"Processing upload: filename='{filename}', size={len(data)} bytes, sha256={sha[:12]}...")

    # same image already processed for this patient and not discarded -> return it (no second OCR / LLM cost)
    with engine.connect() as c:
        hit = c.execute(
            select(extractions.c.id, extractions.c.raw_ocr_id, extractions.c.status, extractions.c.llm_model, extractions.c.analysis_json)
            .join(raw_ocr, raw_ocr.c.id == extractions.c.raw_ocr_id)
            .where(raw_ocr.c.image_sha256 == sha, raw_ocr.c.patient_id == patient_id, extractions.c.status != "DISCARDED")
            .order_by(extractions.c.id.desc())).first()
    if hit:
        log_stage("CACHE_HIT", f"Identical image already processed for this patient -> returning extraction #{hit.id}", time.time() - t_pipeline_start)
        return _payload(hit.id, hit.raw_ocr_id, hit.status, json.loads(hit.analysis_json), hit.llm_model, duplicate=True)

    t_prep = time.time()
    try:
        path, size = preprocess_image(data)
        log_stage("PREPROCESSING", f"Image cleaned and saved to {path} (resolution={size[0]}x{size[1]})", time.time() - t_prep)
    except Exception as e:
        log_stage("ERROR", f"Image preprocessing failed: {e}\n{traceback.format_exc()}", time.time() - t_prep)
        raise PipelineError(f"not a readable image: {e}", http=400)

    t_ocr = time.time()
    log_stage("OCR_INFERENCE", f"Starting PaddleOCR-VL model inference on CPU (resolution={size[0]}x{size[1]})...")
    try:
        raw, (w, h) = run_ocr(path, size)
        log_stage("OCR_INFERENCE", f"PaddleOCR-VL inference completed ({len(raw)} text boxes detected)", time.time() - t_ocr)
    except Exception as e:
        log_stage("ERROR", f"PaddleOCR-VL inference failed: {e}\n{traceback.format_exc()}", time.time() - t_ocr)
        raise PipelineError(f"PaddleOCR-VL inference failed: {e}", http=500)

    t_lines = time.time()
    lines = build_lines(raw, w, h)
    log_stage("LINE_PARSING", f"Reconstructed reading order into {len(lines)} lines", time.time() - t_lines)

    if not lines:
        log_stage("ERROR", "No text found in the image")
        raise PipelineError("no text found in the image - ask the user to re-upload a clearer photo", http=422)
    avg = round(sum(l["conf"] for l in lines) / len(lines), 4)

    t_db = time.time()
    with engine.begin() as c:                      # RAW OCR is saved before the LLM is called
        raw_id = c.execute(insert(raw_ocr).values(image_sha256=sha, patient_id=patient_id, filename=filename, ocr_engine=OCR_ENGINE,
                                                  image_w=w, image_h=h, avg_conf=avg, lines_json=jd(lines),
                                                  created_at=now_iso())).inserted_primary_key[0]
        audit(c, "ocr_saved", None, dict(raw_ocr_id=raw_id, lines=len(lines), avg_conf=avg))
    log_stage("DATABASE", f"Raw OCR saved with raw_ocr_id={raw_id} (avg_conf={avg})", time.time() - t_db)

    result = structure_from_raw(raw_id, expected_name, path)
    log_stage("PIPELINE_COMPLETE", "Full prescription pipeline completed successfully", time.time() - t_pipeline_start)
    return result

"""## 8. API (FastAPI)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | no auth, quick check |
| POST | `/ocr` | multipart: `file`, `patient_id`, optional `patient_name` -> draft extraction |
| POST | `/structure/{ocr_id}` | re-run the LLM on stored raw OCR (after a 502) |
| GET | `/extractions/{id}` | fetch a draft again |
| GET | `/raw_ocr/{id}` | raw OCR lines |
| POST | `/confirm/{extraction_id}` | JSON `{record, confirmed_by, allow_duplicate}` -> save to patient record + observations |
| POST | `/discard/{extraction_id}` | user threw the draft away |
| GET | `/patients/{patient_id}/prescriptions` | timeline of confirmed prescriptions |
| GET | `/patients/{patient_id}/observations?kind=bp` | numeric series for trends / baseline |

All except `/health` need header `X-API-Key: <API_TOKEN>`.
"""

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Prescription OCR service", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
                   allow_methods=["*"], allow_headers=["*"])


def require_key(x_api_key: str = Header(default=None)):
    if not x_api_key or not secrets.compare_digest(x_api_key, API_TOKEN):
        raise HTTPException(401, "invalid or missing X-API-Key")


@app.exception_handler(PipelineError)
def _pipeline_err(request, exc: PipelineError):
    return JSONResponse(status_code=exc.http, content=dict(error=str(exc), raw_ocr_id=exc.raw_ocr_id))


@app.get("/health")
def health():
    return dict(ok=True, ocr=OCR_ENGINE, medicine_names_indexed=len(MED_INDEX), time=now_iso())


@app.get("/ocr")
def api_ocr_info():
    """Informational endpoint when /ocr is opened via browser GET request."""
    return dict(
        status="ready",
        service="Prescription OCR & Information Extraction Service",
        protocol="Use HTTP POST with multipart/form-data to submit a prescription image for OCR.",
        required_method="POST",
        required_headers={"X-API-Key": "<API_TOKEN>"},
        required_form_fields={
            "file": "Image file (JPEG, PNG, WebP up to 10MB)",
            "patient_id": "Patient identifier / UHID (e.g. UHID-10023, P-101)",
        },
        optional_form_fields={
            "patient_name": "Patient full name (for record cross-referencing)",
        },
        web_upload_ui="http://localhost:3000/upload",
        swagger_docs="/docs#/default/api_ocr_ocr_post",
    )


@app.post("/ocr", dependencies=[Depends(require_key)])
def api_ocr(file: UploadFile = File(...), patient_id: str = Form(...), patient_name: Optional[str] = Form(None)):
    t0 = time.time()
    log_stage("ENDPOINT_OCR", f"Received POST /ocr request: filename='{file.filename}', content_type='{file.content_type}'")
    ctype = (file.content_type or "").lower().strip()
    if ctype not in ALLOWED_TYPES and not (file.filename or "").lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        log_stage("ERROR", f"Rejected unsupported file type: '{file.content_type}'")
        raise HTTPException(415, f"unsupported file type {file.content_type}; use jpg/png/webp")
    data = file.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        log_stage("ERROR", f"File size exceeds maximum {MAX_UPLOAD_MB} MB")
        raise HTTPException(413, f"file larger than {MAX_UPLOAD_MB} MB")
    try:
        res = process_image(data, file.filename or "upload", patient_id, patient_name)
        log_stage("ENDPOINT_OCR", "POST /ocr returning HTTP 200 successfully", time.time() - t0)
        return res
    except HTTPException:
        raise
    except PipelineError as pe:
        log_stage("ERROR", f"PipelineError in api_ocr: {pe}\n{traceback.format_exc()}", time.time() - t0)
        raise
    except Exception as ex:
        log_stage("ERROR", f"Unexpected error in api_ocr: {ex}\n{traceback.format_exc()}", time.time() - t0)
        raise HTTPException(500, f"Internal error during prescription OCR: {ex}")


@app.post("/structure/{ocr_id}", dependencies=[Depends(require_key)])
def api_structure(ocr_id: int, patient_name: Optional[str] = None):
    return structure_from_raw(ocr_id, patient_name)


@app.get("/extractions", dependencies=[Depends(require_key)])
def api_list_extractions(limit: int = 20, patient_id: Optional[str] = None):
    with engine.connect() as c:
        q = select(
            extractions.c.id,
            extractions.c.raw_ocr_id,
            extractions.c.llm_model,
            extractions.c.status,
            extractions.c.created_at,
            raw_ocr.c.patient_id,
            raw_ocr.c.filename,
            raw_ocr.c.avg_conf,
            extractions.c.analysis_json,
        ).join(raw_ocr, raw_ocr.c.id == extractions.c.raw_ocr_id)
        if patient_id:
            q = q.where(raw_ocr.c.patient_id == patient_id)
        q = q.order_by(extractions.c.id.desc()).limit(limit)
        rows = c.execute(q).mappings().all()

    out = []
    for r in rows:
        analysis = json.loads(r["analysis_json"]) if r["analysis_json"] else {}
        out.append(dict(
            extraction_id=r["id"],
            ocr_id=r["raw_ocr_id"],
            llm_model=r["llm_model"],
            status=r["status"],
            created_at=r["created_at"],
            patient_id=r["patient_id"],
            filename=r["filename"],
            avg_conf=r["avg_conf"],
            gate=analysis.get("gate", {}),
            record=analysis.get("record", {}),
        ))
    return out


@app.get("/extractions/{extraction_id}", dependencies=[Depends(require_key)])
def api_get_extraction(extraction_id: int):
    with engine.connect() as c:
        r = c.execute(select(extractions).where(extractions.c.id == extraction_id)).mappings().first()
        if not r:
            raise HTTPException(404, "not found")
        patient_id = c.execute(select(raw_ocr.c.patient_id).where(raw_ocr.c.id == r["raw_ocr_id"])).scalar()
    
    analysis = json.loads(r["analysis_json"])
    if r["status"] == "CONFIRMED":
        with engine.connect() as c:
            cp = c.execute(select(confirmed_prescriptions.c.data_json, confirmed_prescriptions.c.patient_id).where(confirmed_prescriptions.c.extraction_id == extraction_id)).mappings().first()
            if cp and cp["data_json"]:
                analysis["record"] = json.loads(cp["data_json"])
                if cp["patient_id"]:
                    patient_id = cp["patient_id"]

    res = _payload(r["id"], r["raw_ocr_id"], r["status"], analysis, r["llm_model"])
    res["patient_id"] = patient_id
    return res


@app.get("/raw_ocr/{ocr_id}", dependencies=[Depends(require_key)])
def api_get_raw(ocr_id: int):
    with engine.connect() as c:
        r = c.execute(select(raw_ocr).where(raw_ocr.c.id == ocr_id)).mappings().first()
    if not r:
        raise HTTPException(404, "not found")
    d = dict(r); d["lines"] = json.loads(d.pop("lines_json"))
    return d


# ---------------------------------------------------------------------------------------------------------
META_KEYS = {"fields", "status", "issues", "warnings", "corrected", "min_conf", "ambiguity_note", "db", "conf", "flag", "parsed", "kind", "name_conf"}

def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in META_KEYS:
                continue
            out += diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            out += diff(a[i] if i < len(a) else None, b[i] if i < len(b) else None, f"{path}[{i}]")
    elif a != b:
        out.append(dict(path=path, machine=a, confirmed=b))
    return out


class ConfirmBody(BaseModel):
    record: dict                       # the (possibly edited) record, same shape as returned by /ocr
    confirmed_by: Optional[str] = None
    allow_duplicate: bool = False


@app.post("/confirm/{extraction_id}", dependencies=[Depends(require_key)])
def api_confirm(extraction_id: int, body: ConfirmBody):
    t0 = time.time()
    log_stage("CONFIRM", f"Processing confirmation for extraction #{extraction_id}, allow_duplicate={body.allow_duplicate}")
    with engine.connect() as c:
        ex = c.execute(select(extractions).where(extractions.c.id == extraction_id)).mappings().first()
        if not ex:
            log_stage("ERROR", f"Extraction #{extraction_id} not found")
            raise HTTPException(404, "extraction not found")
        patient_id = c.execute(select(raw_ocr.c.patient_id).where(raw_ocr.c.id == ex["raw_ocr_id"])).scalar()

    rec = body.record
    if not patient_id or str(patient_id).strip() == "":
        patient_id = (rec.get("patient") or {}).get("uhid") or (rec.get("patient") or {}).get("name") or "UNKNOWN_PATIENT"

    if ex["status"] == "CONFIRMED":
        log_stage("WARN", f"Extraction #{extraction_id} was already confirmed")
        with engine.connect() as c:
            cp = c.execute(select(confirmed_prescriptions).where(confirmed_prescriptions.c.extraction_id == extraction_id)).mappings().first()
        if cp:
            return dict(prescription_id=cp["id"], patient_id=cp["patient_id"], rx_date=cp["rx_date"], edits=json.loads(cp["edits_json"] or "[]"),
                        observations_saved=0, observations_skipped=[], already_confirmed=True)
        raise HTTPException(409, "already confirmed")
    if ex["status"] == "DISCARDED":
        log_stage("WARN", f"Extraction #{extraction_id} was discarded")
        raise HTTPException(409, "this draft was discarded")

    date_iso = rec.get("date_iso")
    try:
        datetime.date.fromisoformat(date_iso or "")
    except ValueError:
        date_iso, _ = parse_date(rec.get("date_raw"))
    if not date_iso:
        date_iso = datetime.date.today().isoformat()
        log_stage("CONFIRM", f"No date found in prescription; defaulting to today: {date_iso}")
    rec["date_iso"] = date_iso
    meds = rec.get("medicines") or []
    if not meds:
        log_stage("ERROR", "Confirmation rejected: at least one medicine is required")
        raise HTTPException(422, "At least one medicine is required to confirm prescription")
    
    doc_raw = rec.get("doctor") or {}
    doctor = doc_raw if isinstance(doc_raw, dict) else {"name": str(doc_raw), "reg_no": None}

    names = sorted((m.get("name") or "").strip().lower() for m in meds if isinstance(m, dict))
    if not body.allow_duplicate:
        with engine.connect() as c:
            same = c.execute(select(confirmed_prescriptions.c.id, confirmed_prescriptions.c.data_json).where(
                confirmed_prescriptions.c.patient_id == patient_id, confirmed_prescriptions.c.rx_date == date_iso)).all()
        for sid, sdata in same:
            old = json.loads(sdata)
            if sorted((m.get("name") or "").strip().lower() for m in old.get("medicines", [])) == names:
                log_stage("CONFIRM_DUPLICATE", f"Duplicate detected matching confirmed prescription #{sid}")
                raise HTTPException(409, f"looks like a duplicate of confirmed prescription #{sid} (same patient, date and medicines). Send allow_duplicate=true to save anyway.")

    original = json.loads(ex["analysis_json"])["record"]
    edits = diff(original, rec)
    skipped, saved_obs = [], 0
    with engine.begin() as c:
        pid = c.execute(insert(confirmed_prescriptions).values(
            extraction_id=extraction_id, patient_id=patient_id, rx_date=date_iso, hospital=rec.get("hospital"),
            doctor=doctor.get("name"), doctor_reg_no=doctor.get("reg_no"), data_json=jd(rec), edits_json=jd(edits),
            confirmed_by=body.confirmed_by, confirmed_at=now_iso())).inserted_primary_key[0]
        for v in rec.get("vitals") or []:
            if not isinstance(v, dict):
                continue
            p = parse_vital(v.get("name"), v.get("value"))
            if p["kind"] == "other":
                continue
            if not p["ok"]:
                skipped.append(dict(name=v.get("name"), value=v.get("value"), reason=p["error"]))
                continue
            c.execute(insert(observations).values(
                patient_id=patient_id, prescription_id=pid, obs_date=date_iso, kind=p["kind"], systolic=p.get("systolic"),
                diastolic=p.get("diastolic"), value=p.get("value"), unit=p.get("unit"),
                raw_text=f"{v.get('name')} {v.get('value')}"[:120], created_at=now_iso()))
            saved_obs += 1
        
        # Keep extractions analysis_json synced with the confirmed doctor review
        analysis = json.loads(ex["analysis_json"])
        analysis["record"] = rec
        c.execute(update(extractions).where(extractions.c.id == extraction_id).values(status="CONFIRMED", analysis_json=jd(analysis)))
        audit(c, "confirmed", extraction_id, dict(prescription_id=pid, by=body.confirmed_by, edits=len(edits), observations=saved_obs))
    
    log_stage("CONFIRM", f"Prescription #{pid} successfully confirmed and saved (edits={len(edits)}, vitals={saved_obs})", time.time() - t0)
    return dict(prescription_id=pid, patient_id=patient_id, rx_date=date_iso, edits=edits,
                observations_saved=saved_obs, observations_skipped=skipped)


@app.post("/discard/{extraction_id}", dependencies=[Depends(require_key)])
def api_discard(extraction_id: int):
    with engine.begin() as c:
        st = c.execute(select(extractions.c.status).where(extractions.c.id == extraction_id)).scalar()
        if st is None:
            raise HTTPException(404, "not found")
        if st == "CONFIRMED":
            raise HTTPException(409, "already confirmed")
        c.execute(update(extractions).where(extractions.c.id == extraction_id).values(status="DISCARDED"))
        audit(c, "discarded", extraction_id)
    return dict(ok=True)


@app.get("/patients/{patient_id}/prescriptions", dependencies=[Depends(require_key)])
def api_patient_rx(patient_id: str):
    with engine.connect() as c:
        rows = c.execute(select(confirmed_prescriptions).where(confirmed_prescriptions.c.patient_id == patient_id)
                         .order_by(confirmed_prescriptions.c.rx_date)).mappings().all()
    out = []
    for r in rows:
        d = dict(r); d["data"] = json.loads(d.pop("data_json")); d["edits"] = json.loads(d.pop("edits_json") or "[]")
        out.append(d)
    return out


@app.get("/patients/{patient_id}/observations", dependencies=[Depends(require_key)])
def api_patient_obs(patient_id: str, kind: Optional[str] = None):
    q = select(observations).where(observations.c.patient_id == patient_id)
    if kind:
        q = q.where(observations.c.kind == kind)
    with engine.connect() as c:
        rows = c.execute(q.order_by(observations.c.obs_date, observations.c.id)).mappings().all()
    return [dict(r) for r in rows]

"""## 9. Start the local API
Run this file from the VS Code terminal. The API is available only on this computer by default.
"""

import uvicorn

PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "127.0.0.1")

if __name__ == "__main__":
    print("Starting local Prescription OCR API...")
    print("API token:", API_TOKEN)
    print(f"Health check: http://{HOST}:{PORT}/health")
    print(f"API docs:    http://{HOST}:{PORT}/docs")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

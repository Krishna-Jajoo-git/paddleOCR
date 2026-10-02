from dotenv import load_dotenv

load_dotenv()

import os, re, io, json, time, hashlib, datetime, statistics, threading, secrets, getpass, subprocess, csv
from typing import List, Optional


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
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

# ---- database --------------------------------------------------------------------------------------------
if not DATABASE_URL:
    # Local development database; created in the project folder.
    DATABASE_URL = "sqlite:///rx_local.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("DB      :", DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL)
if not _tok:
    print("API key : (auto-generated for this session) ->", API_TOKEN)

"""## 3. Database
Tables: `raw_ocr` (raw OCR lines) - `extractions` (LLM draft + validation result) - `confirmed_prescriptions` (what the user confirmed) -
`observations` (numeric BP / sugar / weight rows for trends) - `medicine_master` (authenticated medicine data) - `audit_log`.

`medicine_master` is seeded with a **tiny starter list** so the pipeline works. Replace it with your authenticated database using
`import_medicine_csv("file.csv")` (columns: `name, generic, composition, uses, strengths_mg`).
"""

DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String, Text, Float,
                        select, insert, update, func)

_kw = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {"pool_pre_ping": True}
engine = create_engine(DATABASE_URL, **_kw)
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

def preprocess_image(data: bytes, min_long_side=1600, max_long_side=3500):
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
You convert OCR output of ONE medical prescription into structured JSON for a patient-history system.

INPUT FORMAT - one OCR line per row:
  <line_id> | row <n> | x=<0-1> y=<0-1> | conf=<0-1> | <text>
Lines with the same row number are on the same printed line. y grows downward. A medicine's details
(timing, frequency, duration) are usually on the lines directly below or beside it, with similar x.
Handwritten OCR often contains character confusions (o/0, I/l/1, S/5, G/6, rn/m). Prescriptions may contain Indian
notation: 1-0-1, OD/BD/TDS/QID/SOS/HS, Q6H, 5d (days), x 30 days, Syp 250/5, 3 ml.

RULES
1. Use ONLY the OCR text. Never use medical knowledge to fix a drug name, strength or number.
   Copy values exactly as OCR read them (e.g. "5o0 mg" stays "5o0 mg", "Sd" stays "Sd"). Code validates them later.
2. For every value list the line ids it came from in `src`. Value null and src [] if not present.
3. Return ALL medicines, one object per prescribed item. Never merge or drop any.
4. Keep strength, dose, frequency, timing, duration and route in separate fields.
5. Capture vitals (BP, sugar, weight, pulse, temperature, SpO2) - each as its own Vital with the value text as written.
6. diagnosis = complaint / clinical description / diagnosis lines. allergies = only if the text explicitly states an allergy or NKDA.
7. Capture advice lines and follow-up/review instructions.
8. Ignore clinic slogans, address, phone, e-mail. Text in non-English scripts that was garbled by OCR must be ignored.
9. Never guess a missing field. null is always better than a guess.
10. looks_like_prescription = false if the page is not a prescription / treatment sheet.
11. Dates: copy as printed (do not reformat).
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
                # If model is experiencing temporary demand spikes (503), fast-fail to next model immediately
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
    with engine.connect() as c:
        row = c.execute(select(raw_ocr).where(raw_ocr.c.id == raw_id)).mappings().first()
    if not row:
        raise PipelineError("raw_ocr row not found", http=404)
    lines = json.loads(row["lines_json"])
    by_id = {l["id"]: l for l in lines}
    try:
        rx, model = call_gemini(lines, image_path)
    except Exception as e:
        with engine.begin() as c:
            audit(c, "llm_failed", None, dict(raw_ocr_id=raw_id, error=str(e)[:300]))
        raise PipelineError(f"LLM structuring failed: {e}", raw_ocr_id=raw_id, http=502)
    analysis = analyze_prescription(rx, by_id, expected_name)
    with engine.begin() as c:
        eid = c.execute(insert(extractions).values(raw_ocr_id=raw_id, llm_model=model, analysis_json=jd(analysis),
                                                   status="PENDING_USER_CONFIRMATION", created_at=now_iso())).inserted_primary_key[0]
        audit(c, "extracted", eid, dict(raw_ocr_id=raw_id, gate=analysis["gate"]["status"], model=model))
    return _payload(eid, raw_id, "PENDING_USER_CONFIRMATION", analysis, model)


def process_image(data: bytes, filename: str, patient_id: str, expected_name: Optional[str] = None):
    sha = hashlib.sha256(data).hexdigest()

    # same image already processed for this patient and not discarded -> return it (no second OCR / LLM cost)
    with engine.connect() as c:
        hit = c.execute(
            select(extractions.c.id, extractions.c.raw_ocr_id, extractions.c.status, extractions.c.llm_model, extractions.c.analysis_json)
            .join(raw_ocr, raw_ocr.c.id == extractions.c.raw_ocr_id)
            .where(raw_ocr.c.image_sha256 == sha, raw_ocr.c.patient_id == patient_id, extractions.c.status != "DISCARDED")
            .order_by(extractions.c.id.desc())).first()
    if hit:
        return _payload(hit.id, hit.raw_ocr_id, hit.status, json.loads(hit.analysis_json), hit.llm_model, duplicate=True)

    try:
        path, size = preprocess_image(data)
    except Exception as e:
        raise PipelineError(f"not a readable image: {e}", http=400)
    raw, (w, h) = run_ocr(path, size)
    lines = build_lines(raw, w, h)
    if not lines:
        raise PipelineError("no text found in the image - ask the user to re-upload a clearer photo", http=422)
    avg = round(sum(l["conf"] for l in lines) / len(lines), 4)

    with engine.begin() as c:                      # RAW OCR is saved before the LLM is called
        raw_id = c.execute(insert(raw_ocr).values(image_sha256=sha, patient_id=patient_id, filename=filename, ocr_engine=OCR_ENGINE,
                                                  image_w=w, image_h=h, avg_conf=avg, lines_json=jd(lines),
                                                  created_at=now_iso())).inserted_primary_key[0]
        audit(c, "ocr_saved", None, dict(raw_ocr_id=raw_id, lines=len(lines), avg_conf=avg))
    return structure_from_raw(raw_id, expected_name, path)

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


@app.post("/ocr", dependencies=[Depends(require_key)])
def api_ocr(file: UploadFile = File(...), patient_id: str = Form(...), patient_name: Optional[str] = Form(None)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"unsupported file type {file.content_type}; use jpg/png/webp")
    data = file.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"file larger than {MAX_UPLOAD_MB} MB")
    return process_image(data, file.filename or "upload", patient_id, patient_name)


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
    return _payload(r["id"], r["raw_ocr_id"], r["status"], json.loads(r["analysis_json"]), r["llm_model"])


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
    with engine.connect() as c:
        ex = c.execute(select(extractions).where(extractions.c.id == extraction_id)).mappings().first()
        if not ex:
            raise HTTPException(404, "extraction not found")
        patient_id = c.execute(select(raw_ocr.c.patient_id).where(raw_ocr.c.id == ex["raw_ocr_id"])).scalar()
    if ex["status"] == "CONFIRMED":
        raise HTTPException(409, "already confirmed")
    if ex["status"] == "DISCARDED":
        raise HTTPException(409, "this draft was discarded")

    rec = body.record
    date_iso = rec.get("date_iso")
    try:
        datetime.date.fromisoformat(date_iso or "")
    except ValueError:
        date_iso, _ = parse_date(rec.get("date_raw"))
    if not date_iso:
        raise HTTPException(422, "date_iso (YYYY-MM-DD) is required - the timeline and trends depend on it")
    rec["date_iso"] = date_iso
    meds = rec.get("medicines") or []
    if not meds:
        raise HTTPException(422, "at least one medicine is required")
    doctor = (rec.get("doctor") or {})

    names = sorted((m.get("name") or "").strip().lower() for m in meds)
    if not body.allow_duplicate:
        with engine.connect() as c:
            same = c.execute(select(confirmed_prescriptions.c.id, confirmed_prescriptions.c.data_json).where(
                confirmed_prescriptions.c.patient_id == patient_id, confirmed_prescriptions.c.rx_date == date_iso)).all()
        for sid, sdata in same:
            old = json.loads(sdata)
            if sorted((m.get("name") or "").strip().lower() for m in old.get("medicines", [])) == names:
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
        c.execute(update(extractions).where(extractions.c.id == extraction_id).values(status="CONFIRMED"))
        audit(c, "confirmed", extraction_id, dict(prescription_id=pid, by=body.confirmed_by, edits=len(edits), observations=saved_obs))
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

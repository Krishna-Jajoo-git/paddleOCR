"""
Supabase PostgreSQL Database Connection & Schema Verification Script
Run this script to verify your Supabase PostgreSQL connection, ensure tables exist,
and test reads and writes without loading the PaddleOCR deep learning model.

Usage:
  python test_supabase_connection.py
"""

import os
import re
import urllib.parse
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Text, Float,
    select, insert, delete, inspect
)
from sqlalchemy.engine import make_url

# Load environment variables from model/.env and workspace root
script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(script_dir, ".env"))
load_dotenv()


def sanitize_database_url(raw_url: str) -> str:
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


def verify_supabase_connection():
    print("=" * 65)
    print("  Supabase PostgreSQL Verification & Schema Initialization")
    print("=" * 65)

    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        print("\n[ERROR] DATABASE_URL is not set in model/.env.")
        print("Please configure your Supabase connection string in model/.env:")
        print("  DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres")
        print("  (or connection pooler: postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres)")
        print("\nFor local offline testing, you can use:")
        print("  DATABASE_URL=sqlite:///rx_local.db\n")
        return False

    clean_url = sanitize_database_url(raw_url)

    try:
        parsed_url = make_url(clean_url)
        masked_url = parsed_url.render_as_string(hide_password=True)
        is_postgres = parsed_url.drivername.startswith("postgresql")
    except Exception as e:
        print(f"\n[ERROR] Invalid DATABASE_URL format: {e}")
        return False

    print(f"\n[INFO] Connecting to: {masked_url}")
    print(f"[INFO] Database Engine: {'PostgreSQL (Supabase)' if is_postgres else 'SQLite (Local Dev)'}")

    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    } if is_postgres else {
        "connect_args": {"check_same_thread": False}
    }

    try:
        engine = create_engine(clean_url, **engine_kwargs)
        with engine.connect() as conn:
            conn.execute(select(1))
        print("[SUCCESS] Connection test successful!")
    except Exception as err:
        print(f"\n[ERROR] Connection failed: {err}")
        print("\nTroubleshooting tips:")
        print("1. Check if the password in model/.env contains special characters; these are auto-encoded, but ensure the password itself is accurate.")
        print("2. For IPv4 connections, use the Supabase Connection Pooler string (port 6543 or 5432).")
        print("3. Check that your Supabase project is active and not paused.")
        return False

    # Define metadata and tables
    md = MetaData()

    raw_ocr = Table("raw_ocr", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("image_sha256", String(64), index=True),
        Column("patient_id", String(64), index=True),
        Column("filename", String(255)),
        Column("ocr_engine", String(64)),
        Column("image_w", Integer), Column("image_h", Integer),
        Column("avg_conf", Float),
        Column("lines_json", Text),
        Column("created_at", String(32)))

    extractions = Table("extractions", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("raw_ocr_id", Integer, index=True),
        Column("llm_model", String(64)),
        Column("analysis_json", Text),
        Column("status", String(32), index=True),
        Column("created_at", String(32)))

    confirmed_prescriptions = Table("confirmed_prescriptions", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("extraction_id", Integer, unique=True),
        Column("patient_id", String(64), index=True),
        Column("rx_date", String(10), index=True),
        Column("hospital", String(255)), Column("doctor", String(255)), Column("doctor_reg_no", String(64)),
        Column("data_json", Text),
        Column("edits_json", Text),
        Column("confirmed_by", String(64)),
        Column("confirmed_at", String(32)))

    observations = Table("observations", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("patient_id", String(64), index=True),
        Column("prescription_id", Integer, index=True),
        Column("obs_date", String(10), index=True),
        Column("kind", String(24), index=True),
        Column("systolic", Float), Column("diastolic", Float), Column("value", Float),
        Column("unit", String(16)), Column("raw_text", String(120)),
        Column("created_at", String(32)))

    medicine_master = Table("medicine_master", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String(120), unique=True),
        Column("generic", String(160)), Column("composition", Text), Column("uses", Text),
        Column("strengths_mg", String(200)),
        Column("source", String(80)))

    audit_log = Table("audit_log", md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("ts", String(32)), Column("event", String(40)),
        Column("extraction_id", Integer), Column("detail", Text))

    print("\n[INFO] Creating/verifying database schema in target database...")
    md.create_all(engine)

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    required = ["raw_ocr", "extractions", "confirmed_prescriptions", "observations", "medicine_master", "audit_log"]

    all_found = True
    for t in required:
        if t in existing_tables:
            print(f"  [OK] Table '{t}' verified.")
        else:
            print(f"  [FAIL] Table '{t}' was not found.")
            all_found = False

    if not all_found:
        print("\n[ERROR] One or more tables could not be verified.")
        return False

    # Seed starter medicines if empty
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

    with engine.begin() as conn:
        has_meds = conn.execute(select(medicine_master.c.id).limit(1)).first()
        if not has_meds:
            print("[INFO] Seeding starter medicines into medicine_master table...")
            for n, g, comp, uses, st in STARTER:
                conn.execute(insert(medicine_master).values(
                    name=n, generic=g, composition=comp, uses=uses, strengths_mg=st, source="starter_seed_REPLACE_WITH_REAL_DB"
                ))
            print(f"[SUCCESS] Seeded {len(STARTER)} starter medicines.")
        else:
            med_count = conn.execute(select(medicine_master.c.id)).all()
            print(f"[INFO] medicine_master table already contains {len(med_count)} medicines.")

    # Test write and read with test audit record
    print("\n[INFO] Testing database write and read permissions with a test transaction...")
    with engine.begin() as conn:
        res = conn.execute(insert(audit_log).values(
            ts="2026-10-02T00:00:00Z",
            event="SUPABASE_VERIFICATION_TEST",
            extraction_id=None,
            detail='{"test": "connectivity_verification"}'
        ))
        test_id = res.inserted_primary_key[0]
        # Read back
        row = conn.execute(select(audit_log).where(audit_log.c.id == test_id)).first()
        assert row is not None, "Failed to read inserted test record"
        # Clean up test row
        conn.execute(delete(audit_log).where(audit_log.c.id == test_id))
    print("[SUCCESS] Test write, read, and cleanup verified successfully!")

    print("\n" + "=" * 65)
    print("  VERIFICATION COMPLETE: Database is ready for OCR service!")
    print("=" * 65 + "\n")
    return True


if __name__ == "__main__":
    success = verify_supabase_connection()
    if not success:
        exit(1)

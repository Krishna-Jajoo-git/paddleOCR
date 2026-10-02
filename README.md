# Prescription Intelligence — Production-Ready AI Prescription OCR & Medical Extraction Platform

A clinical-grade, full-stack AI platform for digitizing handwritten and printed medical prescriptions. Built with **PaddleOCR-VL** for document vision and layout recognition, **Google Gemini** for clinical entity structuring and validation, **FastAPI** for high-performance Python inference, and **Next.js (App Router, TypeScript, Tailwind CSS)** for an intuitive healthcare dashboard.

---

## 1. System Architecture & Request Flow

```
┌────────────────────────────────────────────────────────┐
│               Clinician / Pharmacist Web               │
│              (Desktop & Mobile Responsive)             │
└───────────────────────────┬────────────────────────────┘
                            │  HTTPS / Multipart Upload
                            ▼
┌────────────────────────────────────────────────────────┐
│           Next.js Integration Layer (Frontend)         │
│          App Router • TypeScript • Tailwind CSS        │
│    • Drag-and-drop file upload & preview               │
│    • Client-side MIME (JPEG/PNG/WebP) & 10MB limits    │
│    • Server-side API Route Handlers (app/api/*)        │
│    • Private credential protection (Server only)       │
└───────────────────────────┬────────────────────────────┘
                            │  X-API-Key: PYTHON_API_TOKEN
                            ▼
┌────────────────────────────────────────────────────────┐
│            Python FastAPI Processing Service           │
│  • Rate limiting & upload payload validation           │
│  • Image auto-contrast, rotation & resizing            │
│  • PaddleOCR-VL Vision Transformer (0.9B)              │
│  • Multi-model fallback: Gemini 3.8/3.7/3.6/3.5        │
│  • Clinical validation gating & drug master lookup     │
│  • SQLAlchemy ORM (SQLite / PostgreSQL)                │
└───────────────────────────┬────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
┌────────────────────────┐      ┌────────────────────────┐
│ Local Medicine Master  │      │ Google Gemini AI       │
│ & Clinical DB (SQLite) │      │ Structured JSON Output │
└────────────────────────┘      └────────────────────────┘
```

---

## 2. Project Directory Structure

```
paddle/
├── docker-compose.yml              # Local & production multi-container orchestration
├── .gitignore                      # Git exclusion rules for secrets, DBs, models
├── README.md                       # Comprehensive system documentation
├── model/                          # Python Backend Service
│   ├── .env                        # Local backend environment (ignored by git)
│   ├── test_supabase_connection.py # Supabase PostgreSQL connection & schema test
│   ├── Dockerfile                  # Container definition for PaddleOCR + FastAPI
│   ├── requirements.txt            # Production Python dependencies
│   ├── requirements-local.txt      # Local Windows development requirements
│   ├── final_prescription_ocr_service_windows.py  # FastAPI service entrypoint
│   ├── rx_local.db                 # Local SQLite database (clinical records)
│   └── preprocessed/               # Auto-rotated and contrast-adjusted image cache
└── frontend/                       # Next.js Frontend Application
    ├── .env.local                  # Local frontend secrets (ignored by git)
    ├── .env.example                # Frontend environment template
    ├── Dockerfile                  # Multi-stage standalone Next.js container
    ├── package.json                # Next.js, React 19, Lucide, Tailwind v4
    ├── next.config.ts              # Standalone output configuration
    ├── app/
    │   ├── globals.css             # Glassmorphism, healthcare midnight theme
    │   ├── layout.tsx              # Root layout with navigation & meta tags
    │   ├── page.tsx                # Main Dashboard & real prescription history
    │   ├── upload/
    │   │   └── page.tsx            # Drag & drop upload, validation & progress
    │   ├── extractions/[id]/
    │   │   └── page.tsx            # Clinical review, drug editor, confirm/discard
    │   └── api/                    # Server-side API proxies with X-API-Key injection
    │       ├── health/route.ts
    │       ├── extractions/route.ts
    │       ├── ocr/route.ts
    │       ├── confirm/[id]/route.ts
    │       ├── discard/[id]/route.ts
    │       ├── structure/[ocrId]/route.ts
    │       ├── raw-ocr/[ocrId]/route.ts
    │       └── patients/[patientId]/...
    ├── components/
    │   ├── Navbar.tsx              # System navigation & live backend health badge
    │   ├── MedicalDisclaimer.tsx   # Unverified draft clinical safety banner
    │   ├── StatusBadge.tsx         # Badges for confidence, gates, & drug master
    │   ├── MedicineEditor.tsx      # Interactive medication editor with validation
    │   ├── VitalsDisplay.tsx       # Vitals indicators & implausible value warnings
    │   └── RawOcrViewer.tsx        # Bounding box & reading-order line inspector
    └── lib/
        ├── api.ts                  # Typed client for Python & Next.js routes
        └── types.ts                # TypeScript interfaces matching backend models
```

---

## 3. Environment Variables & Database Configuration

### Backend (`model/.env`)
| Variable | Description | Default / Example |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key for clinical structuring | `AIzaSy...` |
| `API_TOKEN` | Shared secret token for `X-API-Key` auth | `rx_secure_token_123` |
| `DATABASE_URL` | Supabase PostgreSQL or SQLite connection string | See Supabase Setup below |
| `PADDLEOCR_DEVICE` | Hardware device for inference | `cpu` or `cuda` |
| `PORT` | ASGI server port | `8000` |
| `HOST` | ASGI bind host (`127.0.0.1` locally, `0.0.0.0` in Docker) | `127.0.0.1` |
| `FRONTEND_ORIGIN` | Allowed origin for CORS | `http://localhost:3000` |

### Supabase PostgreSQL Setup
1. **Create a fresh project** at [database.new](https://database.new) or in your Supabase Dashboard.
2. In your Supabase Dashboard, navigate to **Project Settings** → **Database** → **Connection string**.
3. Select **URI** and copy the connection string:
   * **Option A: Connection Pooler (Recommended - Port 6543 / Transaction mode)**:
     ```env
     DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
     ```
     *(IPv4 compatible, optimal for cloud & concurrent connections)*
   * **Option B: Direct Connection (Port 5432)**:
     ```env
     DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
     ```
   * **Option C: Offline Local Testing (SQLite)**:
     ```env
     DATABASE_URL=sqlite:///rx_local.db
     ```
4. **Special Characters in Passwords**:
   If your Supabase password contains special symbols (e.g. `@`, `#`, `%`, `!`, `&`), the backend's `sanitize_database_url` function automatically encodes them to prevent URL parsing errors.
5. **Fast Connection Verification**:
   Verify your Supabase connection and initialize tables in 1 second without loading the PaddleOCR model:
   ```powershell
   python model/test_supabase_connection.py
   ```

### Frontend (`frontend/.env.local`)
| Variable | Description | Default / Example |
|---|---|---|
| `PYTHON_API_URL` | Internal server-side URL to Python FastAPI | `http://127.0.0.1:8000` |
| `PYTHON_API_TOKEN` | Shared secret token sent as `X-API-Key` header | `rx_secure_token_123` |

> **Security Note:** Private credentials (`GEMINI_API_KEY`, `API_TOKEN`, and `DATABASE_URL`) remain strictly on the backend server. The browser communicates only with Next.js route handlers (`/api/*`), which attach the authentication token securely. Database credentials are never exposed to the client bundle.

---

## 4. Local Development Instructions

### Step 1: Verify Supabase Database Connection
```powershell
# Navigate to model folder
cd c:\Users\swaya\Development\paddle\model

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Test connection and initialize tables
python test_supabase_connection.py
```

### Step 2: Run the Python Backend Service
```powershell
# Run the FastAPI server
python final_prescription_ocr_service_windows.py
```
* Backend starts at `http://127.0.0.1:8000`.
* Health check: `http://127.0.0.1:8000/health`.
* Interactive Swagger Docs: `http://127.0.0.1:8000/docs`.

### Step 3: Run the Next.js Frontend
Open a second terminal in `frontend/`:
```bash
# Navigate to frontend folder
cd c:\Users\swaya\Development\paddle\frontend

# Install dependencies
npm install

# Run the Next.js development server
npm run dev
```
* Frontend starts at `http://localhost:3000`.

---

## 5. Testing & Verification Commands

### Test Frontend Production Build
```bash
cd c:\Users\swaya\Development\paddle\frontend
npm run build
```

### Test Python Backend Endpoints
```powershell
# 1. Health check (no auth required)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"

# 2. Check unauthenticated rejection (expects 401)
try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/extractions" } catch { $_.Exception.Response.StatusCode.value__ }

# 3. Check authenticated extractions list
Invoke-RestMethod -Uri "http://127.0.0.1:8000/extractions" -Headers @{ "X-API-Key" = "rx_local_dev_token_2026_secure" }
```

### Test Next.js Integration Layer Proxy
```powershell
# Verify Next.js routes to Python backend securely
Invoke-RestMethod -Uri "http://localhost:3000/api/health"
Invoke-RestMethod -Uri "http://localhost:3000/api/extractions"
```

---

## 6. Docker & Container Deployment

### Local Docker Compose Full-Stack Run
```bash
# Set your Gemini API key
export GEMINI_API_KEY="your-gemini-key"
export PYTHON_API_TOKEN="your-secure-token"

# Start both services
docker compose up --build
```
* **Persistent Volumes**:
  * `paddlex-cache`: Caches `PaddleOCR-VL` and layout weights (`/root/.paddlex`) across container restarts.
  * `db-data`: Persists the SQLite database (`/app/data/rx_local.db`).

---

## 7. Performance & Hosting Guidelines

1. **CPU vs GPU Inference**:
   * On **CPU**, `PaddleOCR-VL-1.6-0.9B` vision transformer inference takes approximately 30–90 seconds per prescription image and consumes ~4 GB of RAM during model loading.
   * On **NVIDIA GPU (CUDA)**, inference takes ~1.5–3 seconds per prescription image. Set `PADDLEOCR_DEVICE=cuda` if a GPU is available.
2. **Serverless Limitations**:
   * Do **not** deploy the Python OCR service to AWS Lambda, Vercel Serverless, or Google Cloud Functions. The PaddleOCR package and model weights exceed serverless package limits (250MB) and cold-start timeout constraints.
   * Recommended hosting for Python OCR: **Persistent Docker container or VM** on AWS EC2 (t3.xlarge or g4dn.xlarge with GPU), GCP Compute Engine, or Azure VM with minimum 8GB RAM.
   * The Next.js frontend can be deployed to Vercel, AWS ECS, or any standard container host.
3. **Medical Safety**:
   * Extracted records are strictly marked as **Unverified Drafts** until reviewed and confirmed by an authorized human clinician.
   * Dosage formats, frequencies, and durations are validated against strict clinical safety patterns. Any OCR auto-correction (such as digit confusion fixes) is explicitly flagged for human inspection.

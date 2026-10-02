import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";
export const maxDuration = 300; // 5 minutes for CPU vision transformer + LLM structuring

const MAX_UPLOAD_MB = 10;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const ALLOWED_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file") as File | null;
    const patientId = formData.get("patient_id") as string | null;
    const patientName = formData.get("patient_name") as string | null;

    if (!file) {
      return NextResponse.json(
        { error: "Prescription image file is required" },
        { status: 400 }
      );
    }

    if (!patientId || !patientId.trim()) {
      return NextResponse.json(
        { error: "Patient ID is required" },
        { status: 400 }
      );
    }

    if (!ALLOWED_MIME_TYPES.has(file.type)) {
      return NextResponse.json(
        { error: `Unsupported file type (${file.type}). Allowed formats: JPEG, PNG, WebP.` },
        { status: 415 }
      );
    }

    if (file.size > MAX_UPLOAD_BYTES) {
      return NextResponse.json(
        { error: `File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds maximum allowed limit of ${MAX_UPLOAD_MB} MB.` },
        { status: 413 }
      );
    }

    // Prepare outbound multipart form data for Python FastAPI
    const backendFormData = new FormData();
    backendFormData.append("file", file, file.name);
    backendFormData.append("patient_id", patientId.trim());
    if (patientName && patientName.trim()) {
      backendFormData.append("patient_name", patientName.trim());
    }

    const result = await pythonBackendFetch(
      "ocr",
      {
        method: "POST",
        body: backendFormData,
      },
      300000 // 5 minutes timeout for PaddleOCR vision model + Gemini
    );

    if (!result.ok) {
      return NextResponse.json(
        {
          error: result.error || "OCR and structuring failed",
          raw_ocr_id: result.rawOcrId,
        },
        { status: result.status }
      );
    }

    return NextResponse.json(result.data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || "Failed to process prescription upload" },
      { status: 500 }
    );
  }
}

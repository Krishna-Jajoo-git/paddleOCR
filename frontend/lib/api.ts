import {
  ExtractionPayload,
  ExtractionSummaryItem,
  PrescriptionRecord,
  ConfirmResult,
  ConfirmedPrescription,
  ObservationRecord,
  HealthResponse,
  RawOcrData,
} from "./types";

/**
 * Server-side helper to make authenticated requests to the Python FastAPI backend.
 * Only call this within Next.js API route handlers / Server Components.
 */
export async function pythonBackendFetch<T>(
  endpoint: string,
  options: RequestInit = {},
  timeoutMs = 300000 // 5 minutes default timeout for heavy OCR/LLM workloads
): Promise<{ ok: boolean; status: number; data?: T; error?: string; rawOcrId?: number }> {
  const baseUrl = process.env.PYTHON_API_URL || "http://127.0.0.1:8000";
  const apiToken = process.env.PYTHON_API_TOKEN || "";

  const url = `${baseUrl.replace(/\/+$/, "")}/${endpoint.replace(/^\/+/, "")}`;

  const headers = new Headers(options.headers || {});
  if (apiToken) {
    headers.set("X-API-Key", apiToken);
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
      cache: "no-store",
    });

    clearTimeout(timeoutId);

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    if (!res.ok) {
      let errMsg = `Backend responded with HTTP ${res.status}`;
      let rawOcrId: number | undefined;

      if (isJson) {
        try {
          const errBody = await res.json();
          errMsg = errBody.detail || errBody.error || errMsg;
          rawOcrId = errBody.raw_ocr_id;
        } catch {
          // ignore json parse error
        }
      } else {
        const text = await res.text();
        if (text) errMsg = text.slice(0, 300);
      }

      return {
        ok: false,
        status: res.status,
        error: errMsg,
        rawOcrId,
      };
    }

    const data = (isJson ? await res.json() : await res.text()) as T;
    return { ok: true, status: res.status, data };
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      return {
        ok: false,
        status: 504,
        error: `Request timed out after ${timeoutMs / 1000} seconds. The OCR/LLM model is taking longer than usual on CPU.`,
      };
    }
    return {
      ok: false,
      status: 500,
      error: err.message || "Failed to communicate with Python backend service",
    };
  }
}

/**
 * Client-side API functions to interact with Next.js App Router API endpoints.
 */
export const clientApi = {
  async checkHealth(): Promise<HealthResponse> {
    const res = await fetch("/api/health");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Health check failed (${res.status})`);
    }
    return res.json();
  },

  async listExtractions(patientId?: string): Promise<ExtractionSummaryItem[]> {
    const url = patientId ? `/api/extractions?patient_id=${encodeURIComponent(patientId)}` : "/api/extractions";
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to fetch extractions (${res.status})`);
    }
    return res.json();
  },

  async getExtraction(id: number): Promise<ExtractionPayload> {
    const res = await fetch(`/api/extractions/${id}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to fetch extraction #${id}`);
    }
    return res.json();
  },

  async getRawOcr(ocrId: number): Promise<RawOcrData> {
    const res = await fetch(`/api/raw-ocr/${ocrId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to fetch raw OCR #${ocrId}`);
    }
    return res.json();
  },

  async uploadPrescription(
    file: File,
    patientId: string,
    patientName?: string
  ): Promise<ExtractionPayload> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("patient_id", patientId);
    if (patientName && patientName.trim()) {
      formData.append("patient_name", patientName.trim());
    }

    const res = await fetch("/api/ocr", {
      method: "POST",
      body: formData,
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err: any = new Error(body.error || `Upload and OCR failed (${res.status})`);
      err.status = res.status;
      err.rawOcrId = body.raw_ocr_id;
      throw err;
    }

    return body;
  },

  async confirmExtraction(
    extractionId: number,
    record: PrescriptionRecord,
    confirmedBy?: string,
    allowDuplicate = false
  ): Promise<ConfirmResult> {
    const res = await fetch(`/api/confirm/${extractionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        record,
        confirmed_by: confirmedBy || null,
        allow_duplicate: allowDuplicate,
      }),
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err: any = new Error(body.error || `Confirmation failed (${res.status})`);
      err.status = res.status;
      throw err;
    }

    return body;
  },

  async discardExtraction(extractionId: number): Promise<{ ok: boolean }> {
    const res = await fetch(`/api/discard/${extractionId}`, {
      method: "POST",
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.error || `Discard failed (${res.status})`);
    }

    return body;
  },

  async retryStructure(ocrId: number, patientName?: string): Promise<ExtractionPayload> {
    const res = await fetch(`/api/structure/${ocrId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient_name: patientName || null }),
    });

    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.error || `Re-structuring failed (${res.status})`);
    }

    return body;
  },

  async getPatientPrescriptions(patientId: string): Promise<ConfirmedPrescription[]> {
    const res = await fetch(`/api/patients/${encodeURIComponent(patientId)}/prescriptions`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to fetch patient prescriptions (${res.status})`);
    }
    return res.json();
  },

  async getPatientObservations(patientId: string, kind?: string): Promise<ObservationRecord[]> {
    const url = kind
      ? `/api/patients/${encodeURIComponent(patientId)}/observations?kind=${encodeURIComponent(kind)}`
      : `/api/patients/${encodeURIComponent(patientId)}/observations`;
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to fetch patient observations (${res.status})`);
    }
    return res.json();
  },
};

import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(
  req: NextRequest,
  context: { params: Promise<{ ocrId: string }> }
) {
  try {
    const { ocrId } = await context.params;
    let patientName: string | null = null;
    try {
      const body = await req.json();
      patientName = body?.patient_name || null;
    } catch {
      // empty body
    }

    const endpoint = patientName
      ? `structure/${encodeURIComponent(ocrId)}?patient_name=${encodeURIComponent(patientName)}`
      : `structure/${encodeURIComponent(ocrId)}`;

    const result = await pythonBackendFetch(
      endpoint,
      { method: "POST" },
      120000 // 2 minutes for LLM
    );

    if (!result.ok) {
      return NextResponse.json(
        { error: result.error || "Structuring failed" },
        { status: result.status }
      );
    }

    return NextResponse.json(result.data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || "Failed to structure OCR data" },
      { status: 500 }
    );
  }
}

import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ ocrId: string }> }
) {
  const { ocrId } = await context.params;
  const result = await pythonBackendFetch(`raw_ocr/${encodeURIComponent(ocrId)}`, { method: "GET" });

  if (!result.ok) {
    return NextResponse.json(
      { error: result.error || "Failed to fetch raw OCR lines" },
      { status: result.status }
    );
  }
  return NextResponse.json(result.data);
}

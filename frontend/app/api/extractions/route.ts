import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const patientId = searchParams.get("patient_id");
  const limit = searchParams.get("limit") || "20";

  let endpoint = `extractions?limit=${encodeURIComponent(limit)}`;
  if (patientId) {
    endpoint += `&patient_id=${encodeURIComponent(patientId)}`;
  }

  const result = await pythonBackendFetch(endpoint, { method: "GET" });
  if (!result.ok) {
    return NextResponse.json(
      { error: result.error || "Failed to fetch extractions" },
      { status: result.status }
    );
  }
  return NextResponse.json(result.data);
}

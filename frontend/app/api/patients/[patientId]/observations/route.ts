import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ patientId: string }> }
) {
  const { patientId } = await context.params;
  const { searchParams } = new URL(req.url);
  const kind = searchParams.get("kind");

  const endpoint = kind
    ? `patients/${encodeURIComponent(patientId)}/observations?kind=${encodeURIComponent(kind)}`
    : `patients/${encodeURIComponent(patientId)}/observations`;

  const result = await pythonBackendFetch(endpoint, { method: "GET" });

  if (!result.ok) {
    return NextResponse.json(
      { error: result.error || "Failed to fetch patient observations" },
      { status: result.status }
    );
  }

  return NextResponse.json(result.data);
}

import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ patientId: string }> }
) {
  const { patientId } = await context.params;
  const result = await pythonBackendFetch(
    `patients/${encodeURIComponent(patientId)}/prescriptions`,
    { method: "GET" }
  );

  if (!result.ok) {
    return NextResponse.json(
      { error: result.error || "Failed to fetch patient prescriptions" },
      { status: result.status }
    );
  }

  return NextResponse.json(result.data);
}

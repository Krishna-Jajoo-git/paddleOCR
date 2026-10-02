import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const result = await pythonBackendFetch(`extractions/${encodeURIComponent(id)}`, { method: "GET" });

  if (!result.ok) {
    return NextResponse.json(
      { error: result.error || "Failed to fetch extraction" },
      { status: result.status }
    );
  }
  return NextResponse.json(result.data);
}

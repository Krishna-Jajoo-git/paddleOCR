import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(
  _req: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const result = await pythonBackendFetch(`discard/${encodeURIComponent(id)}`, {
    method: "POST",
  });

  if (!result.ok) {
    return NextResponse.json(
      { error: result.error || "Discard failed" },
      { status: result.status }
    );
  }

  return NextResponse.json(result.data);
}

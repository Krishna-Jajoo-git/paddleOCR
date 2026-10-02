import { NextRequest, NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST(
  req: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await context.params;
    const body = await req.json();

    const result = await pythonBackendFetch(
      `confirm/${encodeURIComponent(id)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );

    if (!result.ok) {
      return NextResponse.json(
        { error: result.error || "Confirmation failed" },
        { status: result.status }
      );
    }

    return NextResponse.json(result.data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || "Failed to confirm prescription" },
      { status: 500 }
    );
  }
}

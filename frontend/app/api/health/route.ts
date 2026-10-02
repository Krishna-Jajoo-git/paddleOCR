import { NextResponse } from "next/server";
import { pythonBackendFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET() {
  const result = await pythonBackendFetch("health", { method: "GET" }, 5000);
  if (!result.ok) {
    return NextResponse.json(
      { ok: false, error: result.error || "Python service unreachable" },
      { status: result.status || 503 }
    );
  }
  return NextResponse.json(result.data);
}

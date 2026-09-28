/**
 * Server-side proxy to the ListingIQ backend.
 *
 * Forwards the caller's session cookie so the backend can identify the logged-in
 * account and meter the request against its quota. The browser holds only an
 * httpOnly session cookie — no API key is ever sent to the client.
 *
 * Responses, including the SSE pipeline stream, pass through unbuffered.
 */
import { cookies } from "next/headers";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const SESSION_COOKIE = "liq_session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

async function forward(req: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const incoming = new URL(req.url);
  const target = `${BACKEND}/api/${path.join("/")}${incoming.search}`;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  if (session) headers["Authorization"] = `Bearer ${session}`;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body:
        req.method === "GET" || req.method === "HEAD" ? undefined : await req.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: "Cannot reach the ListingIQ backend. Is it running?" },
      { status: 502 },
    );
  }

  const contentType = upstream.headers.get("content-type") ?? "application/json";
  const out = new Headers({
    "Content-Type": contentType,
    "Cache-Control": "no-cache, no-transform",
  });
  if (contentType.includes("text/event-stream")) {
    out.set("Connection", "keep-alive");
    out.set("X-Accel-Buffering", "no");
  }
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) out.set("Retry-After", retryAfter);

  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;

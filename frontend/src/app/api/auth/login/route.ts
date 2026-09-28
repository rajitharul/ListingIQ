/**
 * Login: exchanges credentials for a session, then stores the token in an
 * httpOnly cookie. Handled here rather than by the catch-all proxy because only
 * a route handler can set a cookie on the browser, and because the raw token
 * must never be returned to client-side JavaScript.
 */
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const SESSION_COOKIE = "liq_session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await req.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: "Cannot reach the ListingIQ backend. Is it running?" },
      { status: 502 },
    );
  }

  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return Response.json(data, { status: upstream.status });
  }

  // Strip the token before it reaches the browser; it lives in the cookie only.
  const { token, account, expires_at } = data as {
    token: string;
    account: unknown;
    expires_at: string;
  };
  const res = Response.json({ account, expires_at });
  res.headers.append(
    "Set-Cookie",
    [
      `${SESSION_COOKIE}=${token}`,
      "Path=/",
      "HttpOnly",
      "SameSite=Lax",
      `Max-Age=${60 * 60 * 24 * 7}`,
      process.env.NODE_ENV === "production" ? "Secure" : "",
    ]
      .filter(Boolean)
      .join("; "),
  );
  return res;
}

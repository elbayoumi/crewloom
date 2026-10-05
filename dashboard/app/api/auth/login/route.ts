import {
  accessToken,
  clearedSessionCookie,
  credentialRefusal,
  issueSession,
  originTrusted,
  revokeSession,
  secretEquals,
  sessionCookie,
} from '../../../../lib/auth.ts';

export const dynamic = 'force-dynamic';

const CROSS_ORIGIN = Response.json({ error: 'Cross-origin request refused' }, { status: 403 });

/**
 * Exchange the operator token for a signed, HttpOnly session cookie.
 *
 * The token arrives in the request body, never in a URL, so it stays out of browser
 * history, proxy access logs, and `Referer` headers. The origin is checked first: a page
 * on another site must not be able to make the operator's browser adopt a session, and a
 * forged `Host` cannot widen the allowlist because the allowlist never reads the request.
 * A wrong, empty, or unknown token returns the same refusal, so the endpoint cannot be
 * used to probe for valid secrets, and a well-formed JSON body of the wrong shape is refused
 * as that same invalid credential rather than reaching the session exchange.
 */
export async function POST(req: Request) {
  const token = accessToken();
  if (!token) {
    return Response.json({ error: credentialRefusal() }, { status: 503 });
  }
  if (!originTrusted(req.headers.get('origin'))) return CROSS_ORIGIN;
  // Valid JSON is not a valid request: `null`, an array, a number and a bare string all
  // parse, so the shape is checked before any property is read. Refusing them as an invalid
  // credential keeps one response for every wrong shape, and an unexpected body can never
  // become an uncaught error that answers with a stack trace instead of a refusal.
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: 'Expected { token: string }' }, { status: 400 });
  }
  const submitted = body !== null && typeof body === 'object' && !Array.isArray(body)
    ? (body as { token?: unknown }).token
    : undefined;
  if (typeof submitted !== 'string' || !secretEquals(submitted.trim(), token)) {
    return Response.json({ error: 'Invalid dashboard credential' }, { status: 401 });
  }
  const session = issueSession(token);
  return Response.json(
    { authenticated: true, expires_at: session.expiresAt },
    {
      status: 200,
      headers: {
        'Set-Cookie': sessionCookie(session.value),
        'Cache-Control': 'no-store',
        Vary: 'Cookie',
      },
    },
  );
}

/**
 * Effective logout: the server revokes the session it issued and clears the cookie with
 * the attributes it was issued with, so a copy of the cookie stops working too.
 */
export async function DELETE(req: Request) {
  if (!accessToken()) {
    return Response.json({ error: credentialRefusal() }, { status: 503 });
  }
  if (!originTrusted(req.headers.get('origin'))) return CROSS_ORIGIN;
  revokeSession(req.headers.get('cookie'));
  return Response.json(
    { authenticated: false },
    {
      status: 200,
      headers: { 'Set-Cookie': clearedSessionCookie(), 'Cache-Control': 'no-store', Vary: 'Cookie' },
    },
  );
}
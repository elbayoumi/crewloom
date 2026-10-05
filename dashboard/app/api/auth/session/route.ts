import { accessToken, authorize, credentialRefusal, privateHeaders, sessionState } from '../../../../lib/auth.ts';

export const dynamic = 'force-dynamic';

/**
 * Whether this browser currently holds a session, so the page can show the sign-in form.
 *
 * It reports only the boolean and the expiry: never the token, never the cookie value, and
 * never any project data, so it is safe to read before authentication.
 */
export async function GET(req: Request) {
  const token = accessToken();
  if (!token) {
    return Response.json({ authenticated: false, error: credentialRefusal() },
      { status: 503, headers: { ...privateHeaders } });
  }
  const decision = authorize(req);
  if (decision.ok && decision.method === 'bearer') {
    return Response.json({ authenticated: true, method: 'bearer', expires_at: null },
      { status: 200, headers: { ...privateHeaders } });
  }
  const session = sessionState(req.headers.get('cookie'), token);
  return Response.json(
    { authenticated: session.ok, method: 'session', expires_at: session.ok ? session.expiresAt : null },
    { status: 200, headers: { ...privateHeaders } },
  );
}
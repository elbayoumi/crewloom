/**
 * Server-only dashboard authentication.
 *
 * The dashboard reads one bound project and can execute registered tools inside it, so
 * every API read, every API write, and the event stream are authenticated before any
 * project file is touched. Three rules shape this module:
 *
 * 1. The secret arrives only through the server environment. `CREWLOOM_DASHBOARD_TOKEN`
 *    is read here and nowhere else, is never declared as a `NEXT_PUBLIC_` value, and so
 *    cannot reach a browser bundle. It never appears in a query string, a run record, or
 *    any response body.
 * 2. Browser access is a signed, expiring, HttpOnly cookie. The login endpoint exchanges
 *    the token for that cookie; the raw token is never stored in the browser.
 * 3. Mutating requests need an exact trusted `Origin`. The allowlist is built from server
 *    configuration, never from the request's `Host` or `Referer`, so a forged `Host`
 *    cannot widen it.
 *
 * Explicit bearer authentication is the automation path: a browser never attaches an
 * `Authorization` header on its own, so a bearer caller is exempt from the origin rule by
 * construction rather than by trust.
 */
import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

export const SESSION_COOKIE = 'crewloom_session';
export const SESSION_TTL_SECONDS = 3600;
/**
 * The policy floor for `CREWLOOM_DASHBOARD_TOKEN`, matching `secrets.token_urlsafe(32)`.
 *
 * This is a length policy, not an entropy guarantee: 32 characters of `'a'` satisfy it and
 * are trivially guessed. It refuses the obvious mistakes (empty, `'password'`, a short id),
 * and generating the value with `secrets.token_urlsafe(32)` is what actually supplies the
 * entropy.
 */
export const MIN_TOKEN_LENGTH = 32;
const TOKEN_ENV = 'CREWLOOM_DASHBOARD_TOKEN';
const HOST_ENV = 'CREWLOOM_DASHBOARD_HOST';
const PORT_ENV = 'CREWLOOM_DASHBOARD_PORT';
const SCHEME_ENV = 'CREWLOOM_DASHBOARD_SCHEME';
const ORIGINS_ENV = 'CREWLOOM_DASHBOARD_ORIGINS';
const LOOPBACK = ['127.0.0.1', 'localhost', '[::1]'];
const KEY_DOMAIN = 'crewloom-dashboard-session-key-v1';
const SIGN_DOMAIN = 'crewloom-dashboard-session-signature-v1';
const COMPARE_DOMAIN = 'crewloom-dashboard-constant-time-compare-v1';
const MAX_SESSIONS = 512;
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
const NO_STORE = { 'Cache-Control': 'no-store', Vary: 'Cookie' };

export type Decision =
  | { ok: true; method: 'bearer' | 'session'; expiresAt: number | null }
  | { ok: false; status: number; error: string };

/** Compare two secrets in constant time without leaking length through an early return. */
export function secretEquals(presented: unknown, expected: string): boolean {
  if (typeof presented !== 'string' || !expected) return false;
  const digest = (value: string) => createHash('sha256').update(COMPARE_DOMAIN).update(value).digest();
  return timingSafeEqual(digest(presented), digest(expected));
}

/**
 * The configured access token, or null when the server was started without a usable one.
 *
 * A short value is refused rather than accepted, because a four-character "password" that
 * authorizes project reads and tool execution is indistinguishable from no authentication
 * at all. Failing closed here means the operator sees a refusal instead of a working
 * dashboard they believe is protected.
 */
export function accessToken(): string | null {
  const configured = process.env[TOKEN_ENV];
  const trimmed = typeof configured === 'string' ? configured.trim() : '';
  return trimmed.length >= MIN_TOKEN_LENGTH ? trimmed : null;
}

/** Why no usable credential is configured, for an honest refusal instead of a silent 503. */
export function credentialRefusal(): string | null {
  const configured = (process.env[TOKEN_ENV] ?? '').trim();
  if (!configured) return 'Dashboard authentication is not configured';
  return 'Dashboard authentication is not configured: the credential must be at least '
    + MIN_TOKEN_LENGTH + ' characters';
}

function sessionKey(token: string): Buffer {
  return createHmac('sha256', token).update(KEY_DOMAIN).digest();
}

function sign(token: string, payload: string): string {
  return createHmac('sha256', sessionKey(token)).update(SIGN_DOMAIN).update(payload).digest('hex');
}

/**
 * Live sessions, so logging out actually revokes access.
 *
 * A signed cookie proves possession of the token, which means clearing the cookie in one
 * browser would leave a copy working elsewhere. The server therefore remembers which
 * sessions it issued and stops accepting one the moment it is logged out. The record is
 * per process: restarting the dashboard invalidates every session, which fails closed.
 */
// Next.js can load the same server module in several route bundles and hot reload it.
// Keep revocation state shared across those copies within one process.
const processSessions = globalThis as typeof globalThis & { __crewloomDashboardSessions?: Map<string, number> };
const liveSessions = processSessions.__crewloomDashboardSessions ??= new Map<string, number>();

function pruneSessions(now: number): void {
  for (const [nonce, expiresAt] of liveSessions) {
    if (expiresAt * 1000 <= now) liveSessions.delete(nonce);
  }
  while (liveSessions.size > MAX_SESSIONS) {
    const oldest = liveSessions.keys().next();
    if (oldest.done) break;
    liveSessions.delete(oldest.value);
  }
}

/**
 * A session value: expiry, a unique nonce, and an HMAC over both.
 *
 * The nonce is a session identifier, not a single-use request nonce: it makes every issued
 * value distinct and is the key `revokeSession` deletes. It is not replay protection for a
 * single request, because the cookie is deliberately reusable until it expires or is logged
 * out.
 */
export function issueSession(token: string, now: number = Date.now()): { value: string; expiresAt: number; nonce: string } {
  const expiresAt = Math.floor(now / 1000) + SESSION_TTL_SECONDS;
  const nonce = randomBytes(16).toString('hex');
  const payload = `${expiresAt}.${nonce}`;
  pruneSessions(now);
  liveSessions.set(nonce, expiresAt);
  return { value: `${payload}.${sign(token, payload)}`, expiresAt, nonce };
}

/** Revoke one presented session; a revoked value stops authorizing immediately. */
export function revokeSession(header: string | null | undefined): boolean {
  const raw = readCookie(header);
  const split = raw?.lastIndexOf('.') ?? -1;
  if (!raw || split <= 0) return false;
  const nonce = raw.slice(0, split).split('.')[1] ?? '';
  return liveSessions.delete(nonce);
}

/** One named cookie from a request `Cookie` header, or null. */
export function readCookie(header: string | null | undefined, name: string = SESSION_COOKIE): string | null {
  if (!header) return null;
  for (const part of header.split(';')) {
    const index = part.indexOf('=');
    if (index < 0) continue;
    if (part.slice(0, index).trim() === name) return part.slice(index + 1).trim();
  }
  return null;
}

/** Verify a presented session against the current token and the current clock. */
export function sessionState(
  header: string | null | undefined,
  token: string | null,
  now: number = Date.now(),
): { ok: boolean; expiresAt: number | null } {
  const raw = readCookie(header);
  if (!raw || !token) return { ok: false, expiresAt: null };
  const split = raw.lastIndexOf('.');
  if (split <= 0) return { ok: false, expiresAt: null };
  const payload = raw.slice(0, split);
  const expiresAt = Number.parseInt(payload.split('.')[0] ?? '', 10);
  if (!Number.isFinite(expiresAt)) return { ok: false, expiresAt: null };
  if (expiresAt * 1000 <= now) return { ok: false, expiresAt };
  if (!secretEquals(raw.slice(split + 1), sign(token, payload))) return { ok: false, expiresAt: null };
  pruneSessions(now);
  return liveSessions.has(payload.split('.')[1] ?? '')
    ? { ok: true, expiresAt }
    : { ok: false, expiresAt: null };
}

/** `Secure` is set only when the operator configured an https origin. */
export function secureCookies(): boolean {
  return expectedOrigins().some((origin) => origin.startsWith('https:'));
}

export function sessionCookie(value: string): string {
  const parts = [`${SESSION_COOKIE}=${value}`, 'Path=/', 'HttpOnly', 'SameSite=Strict', `Max-Age=${SESSION_TTL_SECONDS}`];
  if (secureCookies()) parts.push('Secure');
  return parts.join('; ');
}

/** Logging out clears the cookie with the same attributes the session was issued with. */
export function clearedSessionCookie(): string {
  const parts = [`${SESSION_COOKIE}=`, 'Path=/', 'HttpOnly', 'SameSite=Strict', 'Max-Age=0'];
  if (secureCookies()) parts.push('Secure');
  return parts.join('; ');
}

/**
 * Accept only a bare serialized origin.
 *
 * A serialized `Origin` is scheme, host, and port and nothing else. Anything carrying a
 * path, a query, a fragment, or credentials is malformed rather than merely different, so
 * it is refused instead of being normalized down to a value that would match.
 */
function normalizeOrigin(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    return parsed.origin === value ? parsed.origin : null;
  } catch {
    return null;
  }
}

/**
 * The exact origins this server accepts. Built from server configuration alone: a request
 * header can never add, remove, or rewrite an entry.
 */
export function expectedOrigins(): string[] {
  const host = (process.env[HOST_ENV] ?? '127.0.0.1').trim() || '127.0.0.1';
  const port = (process.env[PORT_ENV] ?? '4317').trim() || '4317';
  const scheme = process.env[SCHEME_ENV] === 'https' ? 'https' : 'http';
  const configured = (process.env[ORIGINS_ENV] ?? '')
    .split(',')
    .map((item) => normalizeOrigin(item))
    .filter((item): item is string => item !== null);
  const hosts = LOOPBACK.includes(host) ? LOOPBACK : [host];
  return [...new Set([...hosts.map((name) => `${scheme}://${name}:${port}`), ...configured])];
}

/** Exact origin match against the configured allowlist; never a prefix or a referer fallback. */
export function originTrusted(origin: string | null | undefined): boolean {
  const normalized = normalizeOrigin(origin);
  return normalized !== null && expectedOrigins().includes(normalized);
}

function bearerCredential(req: Request): string | null {
  const header = req.headers.get('authorization');
  if (!header) return null;
  const match = header.trim().match(/^bearer\s+(.*)$/i);
  return match ? match[1].trim() : null;
}

/** Decide one request. Every failure mode is closed, and none reveals which part was wrong. */
export function authorize(req: Request): Decision {
  const token = accessToken();
  if (!token) return { ok: false, status: 503, error: credentialRefusal() ?? 'Dashboard authentication is not configured' };
  const presented = bearerCredential(req);
  if (presented !== null) {
    return secretEquals(presented, token)
      ? { ok: true, method: 'bearer', expiresAt: null }
      : { ok: false, status: 401, error: 'Invalid dashboard credential' };
  }
  const session = sessionState(req.headers.get('cookie'), token);
  if (!session.ok) return { ok: false, status: 401, error: 'Authentication required' };
  // Authentication first, provenance second: an anonymous caller is told it is anonymous,
  // while a browser session may only mutate from an origin the operator configured.
  if (!SAFE_METHODS.has(req.method.toUpperCase()) && !originTrusted(req.headers.get('origin'))) {
    return { ok: false, status: 403, error: 'Cross-origin request refused' };
  }
  return { ok: true, method: 'session', expiresAt: session.expiresAt };
}

/** The refusal response for a denied request, or null when the request is authorized. */
export function guard(req: Request): Response | null {
  const decision = authorize(req);
  if (decision.ok) return null;
  const headers: Record<string, string> = { ...NO_STORE };
  if (decision.status === 401) headers['WWW-Authenticate'] = 'Bearer realm="crewloom-dashboard"';
  return Response.json({ error: decision.error }, { status: decision.status, headers });
}

/** The response headers a guarded read must carry: private, and never shared between identities. */
export const privateHeaders: Record<string, string> = { ...NO_STORE };
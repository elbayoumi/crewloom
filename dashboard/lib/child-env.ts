/**
 * Environment and output hygiene for child processes the dashboard launches.
 *
 * The server process holds the operator token and may hold other credentials. A registered tool
 * only needs a normal process environment, so children receive a copy without the dashboard
 * credential and without variables whose names mark them as secrets. Names are a defense in depth,
 * not a promise that every secret is recognized: tools must still not print their environment.
 */
type Environment = Record<string, string | undefined>;

const ALWAYS_REMOVED = new Set(['CREWLOOM_DASHBOARD_TOKEN']);
const SECRET_NAME = /(^|_)(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|API_?KEY|PRIVATE_?KEY|ACCESS_?KEY)(_|$)/i;
const REDACTED = '[redacted]';
const SECRET_VALUE = /(ghp_[A-Za-z0-9]{20,}|gh[ousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,}|xox[bap]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*)/g;

/** A copy of `source` safe to hand to a child, plus the explicit `extra` values. */
export function childEnvironment(
  extra: Record<string, string> = {},
  source: Environment = process.env,
): NodeJS.ProcessEnv {
  const env: Environment = {};
  for (const [name, value] of Object.entries(source)) {
    if (value === undefined || ALWAYS_REMOVED.has(name) || SECRET_NAME.test(name)) continue;
    env[name] = value;
  }
  return { ...env, ...extra } as NodeJS.ProcessEnv;
}

/** Replace the exact secret values in `source` and common credential shapes before text is stored. */
export function redactOutput(text: string, source: Environment = process.env): string {
  let result = text;
  for (const [name, value] of Object.entries(source)) {
    if (value && value.length >= 8 && (ALWAYS_REMOVED.has(name) || SECRET_NAME.test(name))) {
      result = result.split(value).join(REDACTED);
    }
  }
  return result.replace(SECRET_VALUE, REDACTED);
}

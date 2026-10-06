'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { parseArgv } from '../lib/argv.ts';

type Skill = { id: string; description: string; lastActivity: string | null; openTasks: number; doneEntries: number; openChallenges: number; resolvedChallenges: number; unknownChallenges: number; ideas: number; tools: string[]; runs: number; failedRuns: number; currentFailures: string[]; evidence: { documented: boolean; configured: boolean; exercised: boolean; verified: boolean; acceptance: string }; status: 'attention' | 'verified' | 'exercised' | 'configured' | 'documented' };
type Tool = { id: string; skill: string; description: string; example_args: string; effect: string };
type Run = { ts: string; tool: string; skill: string; exit_code: number; duration_ms: number; source: string; output?: string };
type Overview = { projectRoot: string; generatedAt: string; totals: Record<string, number>; skills: Skill[]; tools: Tool[]; runs: Run[] };
type Detail = { id: string; skill: string; brain: Record<string, string> };

const T = {
  en: { skills: 'Roles', tools: 'Tools', attention: 'Need attention', tasks: 'Open tasks', challenges: 'Open challenges', failed: 'Failed runs (last 50)', live: 'Live', offline: 'Reconnecting', search: 'Search roles', all: 'All', run: 'Run', runs: 'Recent runs', checks: 'Run repository checks', args: 'Arguments (space separated, project-relative)', none: 'No runs recorded yet. Run a tool here or with the CLI.', role: 'Role', status: 'Status', activity: 'Last memory update', done: 'Done', open: 'Open', ideas: 'Ideas', lang: 'العربية', signIn: 'Sign in', signOut: 'Sign out', token: 'Dashboard access token', unauthorized: 'Sign in to view this project.' },
  ar: { skills: 'الأدوار', tools: 'الأدوات', attention: 'تحتاج متابعة', tasks: 'مهام مفتوحة', challenges: 'تحديات مفتوحة', failed: 'تشغيل فاشل (آخر 50)', live: 'مباشر', offline: 'إعادة اتصال', search: 'ابحث في الأدوار', all: 'الكل', run: 'تشغيل', runs: 'آخر التشغيلات', checks: 'شغّل فحوص الريبو', args: 'المعاملات (بمسافات، مسارات نسبية للمشروع)', none: 'لا توجد تشغيلات بعد. شغّل أداة من هنا أو من الـ CLI.', role: 'الدور', status: 'الحالة', activity: 'آخر تحديث للذاكرة', done: 'منجز', open: 'مفتوح', ideas: 'أفكار', lang: 'English', signIn: 'تسجيل الدخول', signOut: 'تسجيل الخروج', token: 'رمز دخول لوحة المعلومات', unauthorized: 'سجّل الدخول لعرض هذا المشروع.' },
} as const;

const ago = (iso: string | null) => {
  if (!iso) return '—';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  return s < 60 ? `${Math.floor(s)}s` : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : `${Math.floor(s / 86400)}d`;
};

export default function Dashboard() {
  const [lang, setLang] = useState<'en' | 'ar'>('en');
  const t = T[lang];
  const [data, setData] = useState<Overview | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | Skill['status']>('all');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState('skill');
  const [toolId, setToolId] = useState('');
  const [args, setArgs] = useState('');
  const [busy, setBusy] = useState(false);
  const [output, setOutput] = useState<{ ok: boolean; text: string } | null>(null);
  const [token, setToken] = useState('');
  const [auth, setAuth] = useState<'unknown' | 'in' | 'out' | 'error'>('unknown');
  const openId = useRef<string | null>(null);

  const session = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/session', { cache: 'no-store' });
      const body = await res.json();
      setAuth(res.ok && body.authenticated ? 'in' : 'out');
    } catch { setAuth('error'); }
  }, []);

  const signIn = async () => {
    const res = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) });
    if (res.ok) { setToken(''); setAuth('in'); } else setAuth('error');
  };

  const signOut = async () => {
    await fetch('/api/auth/login', { method: 'DELETE' });
    setData(null); setDetail(null); setLive(false); setAuth('out');
  };

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/overview', { cache: 'no-store' });
      if (res.status === 401 || res.status === 403) { setAuth('out'); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json()); setError('');
    } catch (e) { setError(String(e)); }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    const res = await fetch(`/api/skills/${id}`, { cache: 'no-store' });
    if (res.ok) setDetail(await res.json());
  }, []);

  useEffect(() => { document.documentElement.lang = lang; document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'; }, [lang]);
  useEffect(() => { void session(); }, [session]);
  useEffect(() => { if (auth === 'in') void load(); }, [auth, load]);
  useEffect(() => {
    if (auth !== 'in') return;
    const source = new EventSource('/api/events');
    source.addEventListener('ready', () => setLive(true));
    source.addEventListener('change', () => { void load(); if (openId.current) void loadDetail(openId.current); });
    source.onerror = () => setLive(false);
    return () => source.close();
  }, [auth, load, loadDetail]);
  useEffect(() => { const id = setInterval(() => setData((d) => d && { ...d }), 30000); return () => clearInterval(id); }, []);
  useEffect(() => { if (data && !toolId && data.tools[0]) { setToolId(data.tools[0].id); setArgs(data.tools[0].example_args.replace('{input}', '')); } }, [data, toolId]);

  const skills = useMemo(() => (data?.skills ?? []).filter((s) => (filter === 'all' || s.status === filter) && (`${s.id} ${s.description}`.toLowerCase().includes(query.toLowerCase()))), [data, filter, query]);

  const pickSkill = (id: string) => { openId.current = id; setTab('skill'); void loadDetail(id); };
  const parsedArgs = useMemo(() => parseArgv(args), [args]);
  const runTool = async () => {
    if (parsedArgs.error) { setOutput({ ok: false, text: parsedArgs.error }); return; }
    setBusy(true); setOutput(null);
    try {
      const res = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tool: toolId, args: parsedArgs.argv }) });
      const body = await res.json();
      if (res.status === 401 || res.status === 403) { setAuth('out'); return; }
      setOutput({ ok: res.ok && body.exit_code === 0, text: body.error ?? body.output ?? '' });
    } catch (e) { setOutput({ ok: false, text: String(e) }); } finally { setBusy(false); }
  };
  const runChecks = async () => {
    setBusy(true); setOutput(null);
    try { const res = await fetch('/api/check', { method: 'POST' });
      if (res.status === 401 || res.status === 403) { setAuth('out'); return; }
      const body = await res.json(); setOutput({ ok: body.exit_code === 0, text: body.output }); }
    catch (e) { setOutput({ ok: false, text: String(e) }); } finally { setBusy(false); }
  };

  const totals = data?.totals ?? {};
  if (auth !== 'in') {
    return (
      <main className="wrap">
        <header className="top">
          <h1>Crewloom</h1>
          <div className="toolbar">
            <button className="ghost" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}>{t.lang}</button>
          </div>
        </header>
        <section className="card">
          <h2>{t.signIn}</h2>
          <p>{t.unauthorized}</p>
          <div className="toolbar">
            <input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={t.token} aria-label={t.token} autoComplete="off" />
            <button onClick={signIn} disabled={!token}>{t.signIn}</button>
          </div>
          {auth === 'error' && <div className="card" role="alert">401</div>}
        </section>
      </main>
    );
  }
  return (
    <main className="wrap">
      <header className="top">
        <h1>Crewloom</h1>
        <div className="toolbar">
          <span className="live" role="status"><i className={`dot ${live ? 'on' : ''}`} />{live ? t.live : t.offline}</span>
          <button className="ghost" onClick={signOut}>{t.signOut}</button>
          <button className="ghost" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}>{t.lang}</button>
        </div>
      </header>
      <p>{lang === "ar" ? "المشروع الحالي" : "Current project"}: <code>{data?.projectRoot ?? "…"}</code></p>
      {error && <div className="card" role="alert">API: {error}</div>}
      <section className="tiles" aria-label="Totals">
        <div className="tile"><b>{totals.skills ?? '—'}</b><span>{t.skills}</span></div>
        <div className="tile"><b>{totals.tools ?? '—'}</b><span>{t.tools}</span></div>
        <div className={`tile ${totals.attention ? 'warn' : ''}`}><b>{totals.attention ?? '—'}</b><span>{t.attention}</span></div>
        <div className="tile"><b>{totals.openTasks ?? '—'}</b><span>{t.tasks}</span></div>
        <div className={`tile ${totals.openChallenges ? 'warn' : ''}`}><b>{totals.openChallenges ?? '—'}</b><span>{t.challenges}</span></div>
        <div className={`tile ${totals.failedRuns ? 'bad' : ''}`}><b>{totals.failedRuns ?? '—'}</b><span>{t.failed}</span></div>
      </section>
      <div className="grid">
        <div>
          <section className="card">
            <h2>{t.skills}</h2>
            <div className="toolbar">
              <input type="search" placeholder={t.search} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={t.search} />
              <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} aria-label={t.status}>
                <option value="all">{t.all}</option><option value="attention">attention</option><option value="verified">verified</option><option value="exercised">exercised</option><option value="configured">configured</option><option value="documented">documented</option>
              </select>
            </div>
            <div className="scroll">
              <table>
                <thead><tr><th>{t.role}</th><th>{t.status}</th><th>{t.tasks}</th><th>{t.done}</th><th>{t.challenges}</th><th>{t.runs}</th><th>{t.activity}</th></tr></thead>
                <tbody>
                  {skills.map((s) => (
                    <tr key={s.id} className="row" tabIndex={0} onClick={() => pickSkill(s.id)} onKeyDown={(e) => e.key === 'Enter' && pickSkill(s.id)}>
                      <td><b>{s.id}</b></td>
                      <td><span className={`badge ${s.status}`} title={`documented ${s.evidence.documented ? 'yes' : 'no'} · installed in project ${s.evidence.configured ? 'yes' : 'no'} · exercised ${s.evidence.exercised ? 'yes' : 'no'} · acceptance ${s.evidence.acceptance}`}>{s.status}</span></td>
                      <td>{s.openTasks}</td><td>{s.doneEntries}</td><td>{s.openChallenges}{s.unknownChallenges ? <span className="badge unknown" title="Challenge entries without a recognised status line"> {s.unknownChallenges}?</span> : null}</td>
                      <td>{s.runs}{s.failedRuns ? <span className="badge fail"> {s.failedRuns}✕</span> : null}</td>
                      <td>{ago(s.lastActivity)}</td>
                    </tr>
                  ))}
                  {!skills.length && <tr><td colSpan={7} className="empty">—</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
          {detail && (
            <section className="card" aria-live="polite">
              <h2>{detail.id}</h2>
              <div className="tabs">
                {['skill', ...Object.keys(detail.brain)].map((k) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{k}</button>)}
                <button className="ghost" onClick={() => { setDetail(null); openId.current = null; }}>✕</button>
              </div>
              <pre>{tab === 'skill' ? detail.skill : detail.brain[tab]}</pre>
            </section>
          )}
        </div>
        <div>
          <section className="card">
            <h2>{t.tools}</h2>
            <div className="toolbar">
              <select value={toolId} onChange={(e) => { const tool = data?.tools.find((x) => x.id === e.target.value); setToolId(e.target.value); setArgs(tool?.example_args.replace('{input}', '') ?? ''); }} aria-label={t.tools}>
                {data?.tools.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}
              </select>
              <button onClick={runTool} disabled={busy || !toolId || !!parsedArgs.error}>{t.run}</button>
            </div>
            <input style={{ width: '100%' }} value={args} onChange={(e) => setArgs(e.target.value)} placeholder={t.args} aria-label={t.args} />
            <p className="empty" dir="ltr" aria-live="polite">{parsedArgs.error ? parsedArgs.error : `argv: ${JSON.stringify(parsedArgs.argv)}`}</p>
            <p className="empty">{data?.tools.find((x) => x.id === toolId)?.description}</p>
            <button className="ghost" onClick={runChecks} disabled={busy}>{t.checks}</button>
            {output && <pre style={{ borderColor: output.ok ? 'var(--ok)' : 'var(--bad)' }}>{output.text || (output.ok ? 'PASS' : 'FAIL')}</pre>}
          </section>
          <section className="card">
            <h2>{t.runs}</h2>
            <ul className="feed">
              {data?.runs.map((r, i) => (
                <li key={`${r.ts}-${i}`}>
                  <span><span className={`badge ${r.exit_code === 0 ? 'healthy' : 'fail'}`}>{r.exit_code === 0 ? 'PASS' : `EXIT ${r.exit_code}`}</span> <b>{r.tool}</b></span>
                  <small>{r.source} · {r.duration_ms}ms · {ago(r.ts)}</small>
                </li>
              ))}
              {data && !data.runs.length && <li className="empty">{t.none}</li>}
            </ul>
          </section>
        </div>
      </div>
    </main>
  );
}

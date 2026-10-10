'use client';

export type Activity = {
  window: number;
  days: { date: string; total: number; failed: number }[];
  roles: { role: string; total: number; failed: number; average_ms: number }[];
};
export type Controls = {
  queue: { configured: boolean; error?: string; jobs?: { id: string; project_id: string; priority: number; status: string; error?: string; waiting_for?: string }[] };
  budget: { configured: boolean; error?: string; requests?: number; max_requests?: number; reserved_or_reported_usd?: number; max_usd?: number | null; unknown_cost_calls?: number; over_allowance?: boolean };
};

export default function ActivityPanel({ activity, controls, language }: { activity?: Activity; controls?: Controls; language: 'en' | 'ar' }) {
  const ar = language === 'ar';
  const budget = controls?.budget;
  const queue = controls?.queue;
  const statusLabel = (value: string) => ar ? ({queued:'بانتظار التشغيل', running:'تعمل الآن', verified:'تم التحقق', failed:'فاشلة', cancelled:'ملغاة', interrupted:'متوقفة'} as Record<string, string>)[value] ?? value : value;
  const maximum = Math.max(1, ...(activity?.days.map((d) => d.total) ?? []));
  return <section className="card" aria-label={ar ? 'الأداء وطابور التشغيل' : 'Activity and queue'}>
    <h2>{ar ? 'الأداء وطابور التشغيل' : 'Activity and queue'}</h2>
    <p>{ar ? 'آخر ٧ أيام بتوقيت UTC؛ ضمن آخر' : 'Last 7 days in UTC, within the latest'} {activity?.window ?? 0} {ar ? 'تشغيل أداة مسجّل لهذا المشروع.' : 'recorded tool runs for this project.'}</p>
    <div className="activity-bars">{activity?.days.map((day) => <div key={day.date}>
      <span>{day.date.slice(5)}</span>
      <meter min={0} max={maximum} value={day.total} aria-label={`${day.date}: ${day.total}`} />
      <span>{day.total} · {day.failed} {ar ? 'فشل' : 'failed'}</span>
    </div>)}</div>
    {activity?.roles.length ? <div className="scroll"><table><thead><tr>
      <th>{ar ? 'الدور' : 'Role'}</th><th>{ar ? 'التشغيلات' : 'Runs'}</th><th>{ar ? 'الفشل' : 'Failures'}</th><th>{ar ? 'متوسط الزمن' : 'Mean duration'}</th>
    </tr></thead><tbody>{activity.roles.map((role) => <tr key={role.role}>
      <td>{role.role}</td><td>{role.total}</td><td>{role.failed}</td><td>{role.average_ms} ms</td>
    </tr>)}</tbody></table></div> : <p>{ar ? 'لا يوجد سجل أدوات صالح بعد.' : 'No valid tool history yet.'}</p>}
    <h3>{ar ? 'حد الاستهلاك المشترك' : 'Shared admission budget'}</h3>
    {budget?.error && <p role="alert">{budget.error}</p>}
    {budget?.configured && !budget.error ? <>
      <p>{ar ? 'الطلبات' : 'Requests'}: <bdi dir="ltr">{budget.requests} / {budget.max_requests}</bdi></p>
      <p>{ar ? 'تكلفة محجوزة أو مُبلّغ عنها' : 'Reserved or reported cost'}: <bdi dir="ltr">${budget.reserved_or_reported_usd} / {budget.max_usd == null ? '—' : `$${budget.max_usd}`}</bdi></p>
      <p>{ar ? 'طلبات بتكلفة غير معروفة' : 'Calls with unknown cost'}: {budget.unknown_cost_calls}</p>
      {budget.over_allowance && <p role="alert">{ar ? 'التكلفة المبلّغ عنها تجاوزت المخصص؛ الطلبات الجديدة مرفوضة.' : 'Reported cost exceeded the allowance; new calls are refused.'}</p>}
      <p>{ar ? 'المبلغ مخصص لقبول الطلبات، وليس سقف فوترة يفرضه المزوّد.' : 'Dollar amounts control admission; they are not a vendor-enforced billing cap.'}</p>
    </> : !budget?.error && <p>{ar ? 'لم يتم إعداد حد مشترك بعد.' : 'No shared budget configured yet.'}</p>}
    <h3>{ar ? 'طابور المشاريع' : 'Project queue'}</h3>
    {queue?.error && <p role="alert">{queue.error}</p>}
    {queue?.configured && !queue.error ? <ul>{queue.jobs?.map((job) => <li key={job.id}>
      <strong dir="ltr">{job.project_id}</strong> · {statusLabel(job.status)} · {ar ? 'أولوية' : 'priority'} {job.priority}
      {job.waiting_for && <p>{ar ? 'بانتظار انتهاء' : 'Waiting for'}: <bdi>{job.waiting_for}</bdi></p>}
      {job.error && <p role="alert">{job.error}</p>}
    </li>)}{!queue.jobs?.length && <li>{ar ? 'الطابور فارغ.' : 'Queue is empty.'}</li>}</ul> : !queue?.error && <p>{ar ? 'لم يتم إعداد طابور بعد.' : 'No queue configured yet.'}</p>}
  </section>;
}

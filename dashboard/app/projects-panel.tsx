'use client';
import { useEffect, useState } from 'react';
import { projectCommand, type ProjectCatalog } from '../lib/project-commands';

export default function ProjectsPanel({ language }: { language: 'en' | 'ar' }) {
  const [catalog, setCatalog] = useState<ProjectCatalog | null>(null);
  const [error, setError] = useState('');
  const ar = language === 'ar';
  const stateLabel = (state: string) => ar ? ({ active: 'نشطة', awaiting_verification: 'بانتظار التحقق', complete: 'مكتملة', failed: 'فاشلة', cancelled: 'ملغاة', interrupted: 'متوقفة', running: 'تعمل الآن', pending: 'بانتظار التشغيل', blocked: 'معطّلة', awaiting_task: 'بانتظار تنفيذ التاسك', prepared: 'جاهزة للمراجعة', reviewed: 'تمت المراجعة', published: 'منشورة' } as Record<string, string>)[state] ?? state : state;
  const [pending, setPending] = useState('');
  const cancelTask = async (projectId: string, taskId: string) => {
    setPending(projectId + taskId);
    try {
      const response = await fetch('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cancel-task', project_id: projectId, task_id: taskId }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? 'Cancellation refused');
      const refreshed = await fetch('/api/projects', { cache: 'no-store' });
      if (!refreshed.ok) throw new Error('Cannot refresh projects');
      setCatalog(await refreshed.json()); setError('');
    } catch (failure) { setError(String(failure)); } finally { setPending(''); }
  };
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch('/api/projects', { cache: 'no-store' });
        if (!response.ok) throw new Error(ar ? 'تعذّر قراءة المشاريع' : 'Cannot read projects');
        const value = await response.json();
        if (active) { setCatalog(value); setError(''); }
      } catch (failure) { if (active) setError(String(failure)); }
    };
    void refresh(); const timer = setInterval(refresh, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [ar]);
  return <section className="card project-panel" aria-label={ar ? 'المشاريع والتاسكات' : 'Projects and tasks'}>
    <h2>{ar ? 'المشاريع والتاسكات' : 'Projects and tasks'}</h2>
    {(error || catalog?.error) && <p role="alert">{error || catalog?.error}</p>}
    {catalog && !catalog.configured && <p>{ar ? 'حدّد CREWLOOM_CATALOG عند تشغيل اللوحة لعرض سجل المشاريع.' : 'Set CREWLOOM_CATALOG when launching the dashboard to show registered projects.'}</p>}
    {catalog?.configured && !catalog.error && catalog.projects.length === 0 && <p>{ar ? 'لا توجد مشاريع مسجّلة بعد. استخدم crewloom projects add.' : 'No registered projects yet. Use crewloom projects add.'}</p>}
    {catalog?.projects.map((project) => <article key={project.project_id} className="project-record">
      <h3>{project.project_id} <span className="badge">{project.available ? (project.reservation || project.managed_workflow || project.active_batch ? (ar ? 'محجوز' : 'Reserved') : (ar ? 'متاح' : 'Available')) : (ar ? 'يحتاج مراجعة' : 'Needs reconciliation')}</span></h3>
      <p><code dir="ltr">{project.project_root}</code></p>
      {project.error && <p role="alert">{project.error}</p>}
      {project.available && <>
        <p>{ar ? 'سياسة التشغيل' : 'Policy'}: {project.policy_mode} · {ar ? 'المسار النشط' : 'Active workflow'}: {project.managed_workflow?.workflow ?? '—'}</p>
        <ul>{project.tasks.map((task) => <li key={task.task_id}><strong>{task.task_id}</strong> · {task.role} · {stateLabel(task.status)}
          <details><summary>{ar ? 'فحص أو إلغاء' : 'Inspect or cancel'}</summary>
            <pre dir="ltr">{projectCommand(project, 'status', task.task_id)}</pre>
            {!['complete', 'failed', 'cancelled'].includes(task.status) && <>
              <p>{ar ? 'استكمال السياق:' : 'Resume context:'}</p><pre dir="ltr">{projectCommand(project, 'enter', task.task_id)}</pre>
              {!project.managed_workflow && <button disabled={Boolean(pending)} onClick={() => void cancelTask(project.project_id, task.task_id)}>{ar ? 'إلغاء التاسك مع حفظ الملفات' : 'Cancel task, retain files'}</button>}
              {project.managed_workflow && <p>{ar ? 'التاسك مرتبطة بمسار تشغيل؛ استخدم خطة المسار الأصلية للاستكمال أو الإلغاء.' : 'This task belongs to a workflow; resume or cancel using its original plan.'}</p>}
            </>}
          </details></li>)}</ul>
        {[...project.workflows.map((item) => ({ ...item, kind: ar ? 'مسار' : 'Workflow' })), ...project.batches.map((item) => ({ ...item, kind: ar ? 'دفعة' : 'Batch' }))].map((item) => <p key={item.kind + item.id}>{item.kind}: <strong>{item.id}</strong> · {stateLabel(item.status)}{item.reason ? ' · ' + item.reason : ''}</p>)}
        {project.tasks.length + project.workflows.length + project.batches.length === 0 && <p>{ar ? 'لم تبدأ تاسكات بعد.' : 'No tasks started yet.'}</p>}
      </>}
    </article>)}
  </section>;
}

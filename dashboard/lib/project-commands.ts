export type ProjectRecord = {
  project_id: string; project_root: string; checkout_id: string; available: boolean; error?: string;
  policy_mode?: string; reservation?: { task_id: string; owner?: string } | null;
  active_batch?: { batch?: string } | null;
  managed_workflow?: { workflow: string } | null;
  tasks: { task_id: string; role: string; status: string }[];
  workflows: { id: string; status: string; reason?: string }[];
  batches: { id: string; status: string; reason?: string }[];
};
export type ProjectCatalog = { configured: boolean; projects: ProjectRecord[]; error?: string };

/** Commands are displayed for the operator, never evaluated as shell input by the UI. */
export function projectCommand(project: ProjectRecord, action: 'status' | 'cancel' | 'enter', taskId: string): string {
  const quote = (text: string) => "'" + text.replaceAll("'", "'\\''") + "'";
  return ['crewloom', 'project', action, '--project', quote(project.project_root),
    '--project-id', quote(project.project_id), '--task-id', quote(taskId),
    ...(action === 'enter' ? ['--role', quote(project.tasks.find((task) => task.task_id === taskId)?.role ?? 'context-guardian')] : []),
    ...(action === 'cancel' ? ['--reason', quote('operator request')] : [])].join(' ');
}

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const appDir = resolve(import.meta.dirname, '../app');

test('WCAG 2.1 AA: Root layout specifies document language', () => {
  const layout = readFileSync(resolve(appDir, 'layout.tsx'), 'utf8');
  assert.ok(layout.includes('lang="en"'), 'HTML root must define explicit lang attribute');
});

test('WCAG 2.1 AA: Dashboard main page contains semantic landmarks and live regions', () => {
  const page = readFileSync(resolve(appDir, 'page.tsx'), 'utf8');

  // Landmark elements
  assert.ok(page.includes('<main className="wrap">'), 'Must include a main landmark');
  assert.ok(page.includes('<header className="top">'), 'Must include a header landmark');
  assert.ok(page.includes('aria-label="Totals"'), 'Tiles section must have accessible aria-label');

  // Live status indicators
  assert.ok(page.includes('role="status"'), 'Live connection indicator must declare role="status"');
  assert.ok(page.includes('role="alert"'), 'Error announcements must declare role="alert"');
  assert.ok(page.includes('aria-live="polite"'), 'Dynamic detail panel must announce updates via aria-live="polite"');
});

test('WCAG 2.1 AA: All interactive form controls have accessible names', () => {
  const page = readFileSync(resolve(appDir, 'page.tsx'), 'utf8');

  // Form controls
  assert.ok(page.includes('aria-label={t.token}'), 'Password/token input must have aria-label');
  assert.ok(page.includes('aria-label={t.search}'), 'Role search input must have aria-label');
  assert.ok(page.includes('aria-label={t.status}'), 'Status select filter must have aria-label');
  assert.ok(page.includes('aria-label={t.tools}'), 'Tools select must have aria-label');
  assert.ok(page.includes('aria-label={t.args}'), 'Arguments input must have aria-label');
});

test('WCAG 2.1 AA: Data tables declare column scope for assistive technology', () => {
  const page = readFileSync(resolve(appDir, 'page.tsx'), 'utf8');
  assert.ok(page.includes('scope="col"'), 'Table header cells must declare scope="col"');
});

test('WCAG 2.1 AA: Icon-only and symbol buttons have explicit accessible labels', () => {
  const page = readFileSync(resolve(appDir, 'page.tsx'), 'utf8');
  assert.ok(page.includes('aria-label="Close detail view"'), 'Close detail button must have aria-label');
  assert.ok(page.includes('>✕</button>'), 'Symbol button must exist');
});

test('WCAG 2.1 AA: Computer Use companion panel declares switch role and state', () => {
  const panel = readFileSync(resolve(appDir, 'computer-use-panel.tsx'), 'utf8');
  assert.ok(panel.includes('aria-label="Crewloom Browser Companion"'), 'Panel section must have accessible name');
  assert.ok(panel.includes('role="switch"'), 'Companion toggle must declare role="switch"');
  assert.ok(panel.includes('aria-checked={enabled === true}'), 'Companion switch must communicate aria-checked state');
  assert.ok(panel.includes('aria-label={ar ?'), 'Companion switch must have bilingual aria-label');
});

test('WCAG 2.1 AA: Projects and tasks panel structure declares semantic headings and alert regions', () => {
  const panel = readFileSync(resolve(appDir, 'projects-panel.tsx'), 'utf8');
  assert.ok(panel.includes('aria-label={ar ?'), 'Projects section must have accessible name');
  assert.ok(panel.includes('role="alert"'), 'Projects error state must declare role="alert"');
  assert.ok(panel.includes('className="project-record"'), 'Project items must use project-record container');
});

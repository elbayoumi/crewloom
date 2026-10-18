/**
 * Crewloom Computer Use - Content Script
 * Manual Page Visual Grounding, DOM Indexing, Element Labeling, and Action Simulation.
 */

const MAX_INDEXED_ELEMENTS = 400;
const INTERACTIVE_SELECTOR =
  'button, a, input, select, textarea, [role="button"], [role="link"], [role="tab"], [role="checkbox"], [tabindex="0"]';

let isInspectorActive = false;
let inspectorBox = null;
let hudElement = null;
let trackedTags = [];
let repositionFrame = null;
let indexGeneration = 0;
const documentToken = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;

function parentAcrossRoots(element) {
  if (element.parentElement) return element.parentElement;
  const root = element.getRootNode();
  if (root.host) return root.host;
  try { return element.ownerDocument.defaultView.frameElement; } catch { return null; }
}

function canInteract(element) {
  if (!element.isConnected || element.disabled || element.getAttribute('aria-disabled') === 'true') return false;
  const rect = element.getBoundingClientRect();
  if (rect.width <= 8 || rect.height <= 8) return false;
  for (let node = element; node; node = parentAcrossRoots(node)) {
    const style = node.ownerDocument.defaultView.getComputedStyle(node);
    if (node.inert || node.hidden || style.display === 'none' || style.visibility !== 'visible' ||
        Number(style.opacity) === 0 || style.pointerEvents === 'none') return false;
  }
  return true;
}

function targetFingerprint(element) {
  const form = ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName);
  return JSON.stringify([element.tagName, element.getAttribute('role'), element.getAttribute('type'),
    element.getAttribute('href'), element.getAttribute('formaction'), element.getAttribute('aria-label'),
    element.getAttribute('name'), element.getAttribute('placeholder'), form ? '' : element.textContent]);
}

function pageRect(element) {
  const rect = element.getBoundingClientRect();
  let x = rect.x, y = rect.y, view = element.ownerDocument.defaultView;
  while (view !== window) {
    let frame;
    try { frame = view.frameElement; } catch { break; }
    if (!frame) break;
    const bounds = frame.getBoundingClientRect();
    x += bounds.x + frame.clientLeft; y += bounds.y + frame.clientTop;
    view = frame.ownerDocument.defaultView;
  }
  return { x, y, left: x, top: y, right: x + rect.width, bottom: y + rect.height,
    width: rect.width, height: rect.height };
}

function hitTarget(element) {
  const bounds = element.getBoundingClientRect();
  let x = bounds.left + bounds.width / 2, y = bounds.top + bounds.height / 2;
  const doc = element.ownerDocument;
  let hit = doc.elementFromPoint(x, y);
  while (hit?.shadowRoot) {
    const inner = hit.shadowRoot.elementFromPoint(x, y);
    if (!inner || inner === hit) break;
    hit = inner;
  }
  if (hit !== element && !element.contains(hit)) return false;
  let view = doc.defaultView;
  while (view !== window.top) {
    const frame = view.frameElement;
    if (!frame) return false;
    const rect = frame.getBoundingClientRect();
    x += rect.left + frame.clientLeft; y += rect.top + frame.clientTop;
    const outer = frame.ownerDocument.elementFromPoint(x, y);
    if (outer !== frame) return false;
    view = frame.ownerDocument.defaultView;
  }
  return true;
}

// The page language belongs to the site; only our HUD adopts the operator's choice.
let contentLanguage = 'en';
let hudStatus = {key:'active', vars:{}};
const HUD_TEXT = {
  en: {active:'Active', indexed:'{total} elements indexed', limited:'Indexed {count} of {total} (limit {limit})',
    clicked:'Clicked [{index}]', inspector:'Inspector active', close:'Hide Overlay'},
  ar: {active:'نشط', indexed:'تم ترقيم {total} عنصر', limited:'تم ترقيم {count} من {total} (الحد {limit})',
    clicked:'تم الضغط على [{index}]', inspector:'الفاحص نشط', close:'إخفاء الإشارات'}
};
function hudText(key, vars = {}) {
  return HUD_TEXT[contentLanguage][key].replace(/\{(\w+)\}/g, (match,name) =>
    Object.prototype.hasOwnProperty.call(vars,name) ? String(vars[name]) : match);
}
function renderHudLanguage() {
  if (!hudElement) return;
  hudElement.lang = contentLanguage;
  hudElement.dir = contentLanguage === 'ar' ? 'rtl' : 'ltr';
  hudElement.querySelector('.crewloom-hud-text').textContent = hudText(hudStatus.key,hudStatus.vars);
  const closeBtn = hudElement.querySelector('.crewloom-hud-close');
  closeBtn.title = hudText('close');
  closeBtn.setAttribute('aria-label', hudText('close'));
}
function setHudLanguage(value) {
  contentLanguage = value === 'ar' ? 'ar' : 'en';
  renderHudLanguage();
}

// Ensure HUD banner exists without translating or changing the underlying page.
function showHud(key = 'active', vars = {}) {
  hudStatus = {key,vars};
  if (hudElement) {
    renderHudLanguage();
    hudElement.style.setProperty('display','flex','important');
    return;
  }
  hudElement = document.createElement('div');
  hudElement.className = 'crewloom-agent-hud';
  hudElement.setAttribute('role', 'region');
  hudElement.setAttribute('aria-label', 'Crewloom Computer Use Status HUD');
  const logoUrl = chrome.runtime.getURL('icons/icon-32.png');
  hudElement.innerHTML = `
    <img src="${logoUrl}" alt="Crewloom" class="crewloom-hud-logo">
    <span class="crewloom-hud-title">Crewloom Computer Use</span>
    <div class="crewloom-hud-status" role="status" aria-live="polite">
      <span class="crewloom-hud-dot" aria-hidden="true"></span>
      <span class="crewloom-hud-text"></span>
    </div>
    <button class="crewloom-hud-close" aria-label="✕">✕</button>
  `;
  renderHudLanguage();
  hudElement.querySelector('.crewloom-hud-close').addEventListener('click', () => {
    clearAllIndexTags();
    hudElement.style.setProperty('display','none','important');
  });
  document.body.appendChild(hudElement);
}

// Overlay container for index tags
function getGroundingOverlay() {
  let overlay = document.getElementById('crewloom-grounding-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'crewloom-grounding-overlay';
    document.body.appendChild(overlay);
  }
  return overlay;
}

function placeTag(entry) {
  const rect = pageRect(entry.element);
  const left = Math.round(rect.left + window.scrollX);
  const top = Math.max(0, Math.round(rect.top + window.scrollY - 16));
  entry.tag.style.left = `${left}px`;
  entry.tag.style.top = `${top}px`;
  entry.tag.style.display = rect.bottom < 0 || rect.top > window.innerHeight ? 'none' : '';
}

function repositionTags() {
  repositionFrame = null;
  const overlay = document.getElementById('crewloom-grounding-overlay');
  if (!overlay || !trackedTags.length) return;
  overlay.style.width = `${Math.max(document.documentElement.scrollWidth, window.innerWidth)}px`;
  overlay.style.height = `${Math.max(document.documentElement.scrollHeight, window.innerHeight)}px`;
  trackedTags.forEach(placeTag);
}

function scheduleReposition() {
  if (repositionFrame !== null) return;
  repositionFrame = window.requestAnimationFrame(repositionTags);
}

// Index all interactive elements with numbered labels [1], [2], [3]
function indexInteractiveElements(options = {}) {
  clearAllIndexTags();
  // A cross-origin boundary hides frameElement, so the embedding hit test
  // cannot prove that a target is exposed. Do not advertise unusable handles.
  let view = window;
  while (view !== window.top) {
    let frame;
    try { frame = view.frameElement; } catch { frame = null; }
    if (!frame) {
      hudElement?.remove(); hudElement = null;
      return {generation:indexGeneration,documentToken,items:[],total:0,blockedFrames:1,
        truncated:false,limit:0};
    }
    view = frame.ownerDocument.defaultView;
  }
  const overlay = getGroundingOverlay();
  overlay.style.display = 'block';
  overlay.style.width = `${Math.max(document.documentElement.scrollWidth, window.innerWidth)}px`;
  overlay.style.height = `${Math.max(document.documentElement.scrollHeight, window.innerHeight)}px`;

  const elements = [];
  const roots = new Set();
  let blockedFrames = 0;
  function collect(root) {
    if (roots.has(root)) return;
    roots.add(root);
    elements.push(...root.querySelectorAll(INTERACTIVE_SELECTOR));
    for (const node of root.querySelectorAll('*')) {
      if (node.shadowRoot) collect(node.shadowRoot);
      if (options.includeFrames !== false && node.tagName === 'IFRAME') {
        try { if (node.contentDocument) collect(node.contentDocument); else blockedFrames++; }
        catch { blockedFrames++; }
      }
    }
  }
  collect(document);
  const distance = (element) => {
    const rect = pageRect(element);
    return Math.max(0, -rect.bottom, rect.top - innerHeight) + Math.max(0, -rect.right, rect.left - innerWidth);
  };
  // Keep DOM order within the viewport, then bring nearer targets ahead of off-screen ones.
  elements.sort((a, b) => distance(a) - distance(b));
  const items = [];
  let total = 0;
  const offset = Number.isInteger(options.offset) && options.offset >= 0 ? options.offset : 0;
  const limit = Number.isInteger(options.limit) && options.limit >= 0
    ? Math.min(options.limit, MAX_INDEXED_ELEMENTS) : MAX_INDEXED_ELEMENTS;

  for (const el of elements) {
    // Skip our own overlay chrome
    if (el.closest('.crewloom-agent-hud') || el.closest('#crewloom-grounding-overlay')) continue;

    const rect = pageRect(el);
    if (!canInteract(el)) continue;

    total += 1;

    // Bound the overlay so dense pages cannot flood the DOM
    if (items.length >= limit) continue;

    const index = offset + items.length + 1;
    el.classList.add('crewloom-indexed-element');
    el.dataset.crewloomIndex = index;

    const tag = document.createElement('div');
    tag.className = 'crewloom-indexed-tag';
    tag.textContent = `[${index}]`;
    tag.dataset.targetIndex = index;
    overlay.appendChild(tag);

    const entry = { element: el, tag, index, fingerprint: targetFingerprint(el) };
    trackedTags.push(entry);
    placeTag(entry);

    items.push({
      index,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || null,
      id: el.id || null,
      text: (['input', 'textarea', 'select'].includes(el.tagName.toLowerCase())
        ? (el.getAttribute('aria-label') || el.placeholder || '')
        : (el.textContent || el.getAttribute('aria-label') || ''))
        .trim()
        .slice(0, 40),
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    });
  }

  trackedTags.forEach(placeTag);
  window.addEventListener('scroll', scheduleReposition, { passive: true });
  window.addEventListener('resize', scheduleReposition, { passive: true });

  showHud(items.length < total ? 'limited' : 'indexed', {count:items.length,total,limit});

  return { generation: indexGeneration, documentToken, items, total, blockedFrames,
    truncated: items.length < total, limit };
}

// Clear all indexed tags
function clearAllIndexTags() {
  indexGeneration += 1;
  if (repositionFrame !== null) {
    window.cancelAnimationFrame(repositionFrame);
    repositionFrame = null;
  }
  window.removeEventListener('scroll', scheduleReposition);
  window.removeEventListener('resize', scheduleReposition);

  trackedTags.forEach(({element: el}) => {
    el.classList.remove('crewloom-indexed-element');
    delete el.dataset.crewloomIndex;
  });
  const overlay = document.getElementById('crewloom-grounding-overlay');
  if (overlay) {
    overlay.innerHTML = '';
    overlay.style.display = 'none';
  }
  trackedTags = [];
}

// Trigger simulated agent click with visual wave
function clickElementByIndex(index, generation = indexGeneration, expectedDocument = documentToken) {
  if (!Number.isInteger(index) || index < 1 || generation !== indexGeneration) {
    return { ok: false, error: 'Stale or invalid element index; re-index the page' };
  }
  if (expectedDocument !== documentToken) return { ok: false, error: 'Document changed; re-index the page' };
  const entry = trackedTags.find((entry) => entry.index === index);
  const el = entry?.element;
  if (!el?.isConnected) return { ok: false, error: 'Indexed element was removed; re-index the page' };
  if (targetFingerprint(el) !== entry.fingerprint || !canInteract(el)) {
    return { ok: false, error: 'Indexed element changed or is not interactive; re-index the page' };
  }
  el.scrollIntoView({ behavior: 'instant', block: 'center' });
  if (!canInteract(el) || targetFingerprint(el) !== entry.fingerprint || !hitTarget(el)) {
    return { ok: false, error: 'Indexed element is covered or changed; re-index the page' };
  }
  const rect = pageRect(el);
  const clickX = rect.left + rect.width / 2;
  const clickY = rect.top + rect.height / 2;

  // Render expanding click wave
  const wave = document.createElement('div');
  wave.className = 'crewloom-click-wave';
  wave.style.left = `${clickX}px`;
  wave.style.top = `${clickY}px`;
  document.body.appendChild(wave);
  setTimeout(() => wave.remove(), 500);

  // Trigger real click
  el.focus();
  if (targetFingerprint(el) !== entry.fingerprint || !canInteract(el) || !hitTarget(el)) {
    return { ok: false, error: 'Target changed on focus; re-index the page' };
  }
  el.click();

  showHud('clicked', {index});
  return { ok: true, x: clickX, y: clickY, tag: el.tagName.toLowerCase() };
}

// Mouse Inspector functionality
function toggleInspector(forceState) {
  isInspectorActive = forceState !== undefined ? forceState : !isInspectorActive;

  if (isInspectorActive) {
    if (!inspectorBox) {
      inspectorBox = document.createElement('div');
      inspectorBox.className = 'crewloom-inspector-box';
      inspectorBox.innerHTML = '<span class="crewloom-inspector-label"></span>';
      document.body.appendChild(inspectorBox);
    }
    document.addEventListener('mousemove', onInspectorMouseMove, { passive: true });
    showHud('inspector');
  } else {
    if (inspectorBox) inspectorBox.remove();
    inspectorBox = null;
    document.removeEventListener('mousemove', onInspectorMouseMove);
  }
}

function onInspectorMouseMove(e) {
  if (!isInspectorActive || !inspectorBox) return;
  const original = e.composedPath?.()[0];
  const target = original?.nodeType === 1 ? original : document.elementFromPoint(e.clientX, e.clientY);
  if (!target || target.closest('.crewloom-agent-hud') || target === inspectorBox) return;

  const rect = target.getBoundingClientRect();
  inspectorBox.style.left = `${rect.left}px`;
  inspectorBox.style.top = `${rect.top}px`;
  inspectorBox.style.width = `${rect.width}px`;
  inspectorBox.style.height = `${rect.height}px`;

  const label = inspectorBox.querySelector('.crewloom-inspector-label');
  const tagDesc = `${target.tagName.toLowerCase()}${target.id ? '#' + target.id : ''}`;
  label.textContent = `<${tagDesc}> (${Math.round(rect.width)}×${Math.round(rect.height)})`;
}

// Message Listener from Sidepanel & Background
function handleMessage(message, sender, sendResponse) {
  if (message.type === 'INDEX_PAGE') {
    const result = indexInteractiveElements(message);
    sendResponse({
      ok: true,
      generation: result.generation,
      documentToken: result.documentToken,
      blockedFrames: result.blockedFrames,
      count: result.items.length,
      total: result.total,
      truncated: result.truncated,
      limit: result.limit,
      items: result.items
    });
    return false;
  }

  if (message.type === 'CLEAR_INDEX') {
    clearAllIndexTags();
    hudElement?.remove(); hudElement = null;
    sendResponse({ ok: true });
    return false;
  }

  if (message.type === 'CLICK_INDEX') {
    if (!Number.isInteger(message.generation) || message.documentToken !== documentToken) {
      sendResponse({ ok: false, error: 'Index generation and document token required; re-index the page' }); return;
    }
    sendResponse(clickElementByIndex(message.index, message.generation, message.documentToken));
    return false;
  }

  if (message.type === 'TOGGLE_INSPECTOR') {
    toggleInspector();
    sendResponse({ ok: true, active: isInspectorActive });
    return false;
  }

  if (message.type === 'GET_PAGE_SUMMARY') {
    sendResponse({
      ok: true,
      title: document.title,
      url: window.location.href,
      elementsCount: document.querySelectorAll('*').length
    });
    return false;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CLEAR_INDEX') { handleMessage(message, sender, sendResponse); return false; }
  chrome.storage.local.get({ 'crewloom.enabled': false, 'crewloom.lang': 'en' }, (stored) => {
    setHudLanguage(stored['crewloom.lang']);
    if (!stored['crewloom.enabled']) return sendResponse({ ok: false, error: 'Browser companion is disabled' });
    handleMessage(message, sender, sendResponse);
  });
  return true;
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes['crewloom.lang']) setHudLanguage(changes['crewloom.lang'].newValue);
  if (area === 'local' && changes['crewloom.enabled']?.newValue === false) {
    clearAllIndexTags();
    isInspectorActive = false;
    document.removeEventListener('mousemove', onInspectorMouseMove);
    inspectorBox?.remove(); inspectorBox = null;
    hudElement?.remove(); hudElement = null;
  }
});

// Only the operator's local dashboard can request a state change. Other pages cannot.
const dashboardPage = location.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) && location.port === '4317';
if (dashboardPage) {
  window.addEventListener('message', (event) => {
    if (event.source !== window || event.origin !== location.origin) return;
    const type = event.data?.type;
    if (!['CREWLOOM_GET_CONTROL', 'CREWLOOM_SET_CONTROL'].includes(type)) return;
    if (type === 'CREWLOOM_SET_CONTROL' && typeof event.data.enabled !== 'boolean') return;
    chrome.runtime.sendMessage({ type: type === 'CREWLOOM_SET_CONTROL' ? 'SET_CONTROL' : 'GET_CONTROL', enabled: event.data.enabled }, (result) => {
      if (chrome.runtime.lastError || !result?.ok) return;
      window.postMessage({ type: 'CREWLOOM_CONTROL_STATE', enabled: result.enabled, version: result.version }, location.origin);
    });
  });
}

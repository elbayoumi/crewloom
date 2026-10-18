/**
 * Crewloom Computer Use - Background Service Worker (Manifest V3)
 * Manual browser companion: persistent activation, visible-tab capture and local dashboard status.
 */

// Open the side panel immediately when the action icon is clicked
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error('Error setting panel behavior:', error));

// Create Context Menus (recreate on install/update so entries never duplicate)
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: 'crewloom-inspect',
      title: 'Inspect with Crewloom Computer Use',
      contexts: ['all']
    });
    chrome.contextMenus.create({
      id: 'crewloom-capture',
      title: 'Capture Visual Frame for Agent',
      contexts: ['all']
    });
  });
});

const captureKey = (windowId) => `crewloom.pendingCapture.${windowId}`;

// Handle Context Menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab?.id || !Number.isInteger(tab.windowId) || tab.windowId < 0) return;
  const windowId = tab.windowId;

  // Open the side panel for this window
  chrome.sidePanel.open({ windowId }).catch((error) => {
    console.error('Error opening side panel:', error);
  });

  if (info.menuItemId === 'crewloom-inspect') {
    chrome.tabs.sendMessage(tab.id, { type: 'TOGGLE_INSPECTOR' }, () => {
      void chrome.runtime.lastError;
    });
  } else if (info.menuItemId === 'crewloom-capture') {
    // Persist before notifying: a newly opened panel consumes this on readiness.
    chrome.storage.session.set({ [captureKey(windowId)]: { tabId: tab.id, createdAt: Date.now() } }, () => {
      chrome.runtime.sendMessage({ type: 'CAPTURE_REQUEST', windowId }).catch(() => {});
    });
  }
});

// Central Message Routing
function handleMessage(message, sender, sendResponse) {
  // Capture the visible tab. windowId comes from the caller so the right window is captured.
  if (message.type === 'CAPTURE_TAB') {
    const windowId = message.windowId;
    if (!Number.isInteger(windowId) || windowId < 0) { sendResponse({ ok: false, error: 'Explicit panel window required' }); return false; }
    chrome.tabs.captureVisibleTab(windowId, { format: 'png' }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        chrome.storage.local.get({ 'crewloom.enabled': false }, (value) => sendResponse(value['crewloom.enabled'] ? { ok: true, dataUrl } : { ok: false, error: 'Browser companion was disabled during capture' }));
      }
    });
    return true; // Keep channel open for async response
  }

  if (message.type === 'PANEL_READY') {
    if (!Number.isInteger(message.windowId) || message.windowId < 0) { sendResponse({ ok: false, error: 'Explicit panel window required' }); return false; }
    const key = captureKey(message.windowId);
    chrome.storage.session.get(key, (value) => {
      const pending = value[key];
      chrome.storage.session.remove(key, () => sendResponse({ ok: true, pending: pending && Date.now() - pending.createdAt < 30000 ? pending : null }));
    });
    return true;
  }

  // Get active tab info
  if (message.type === 'GET_ACTIVE_TAB') {
    if (!Number.isInteger(message.windowId) || message.windowId < 0) { sendResponse({ ok: false, error: 'Explicit panel window required' }); return false; }
    chrome.tabs.query({ active: true, windowId: message.windowId }, (tabs) => {
      if (tabs && tabs[0]) {
        sendResponse({ ok: true, tab: tabs[0] });
      } else {
        sendResponse({ ok: false, error: 'No active tab' });
      }
    });
    return true;
  }

  // Helper for resilient localhost / 127.0.0.1 fetch
  const fetchWithFallback = async (path, options = {}) => {
    try {
      const res = await fetch(`http://localhost:4317${path}`, { ...options, signal: AbortSignal.timeout(5000) });
      if (res.ok) return res.json();
      throw new Error(`HTTP ${res.status}`);
    } catch {
      const fallbackRes = await fetch(`http://127.0.0.1:4317${path}`, { ...options, signal: AbortSignal.timeout(5000) });
      if (fallbackRes.ok) return fallbackRes.json();
      throw new Error(`HTTP ${fallbackRes.status}`);
    }
  };

  // Check Local Crewloom Daemon
  if (message.type === 'CHECK_LOCAL_DAEMON') {
    fetchWithFallback('/api/extension')
      .then((data) => { if (data.daemon !== 'crewloom' || data.browserCompanion !== 'manual') throw new Error('Unsupported dashboard handshake'); sendResponse({ ok: true, connected: true, data }); })
      .catch((err) => sendResponse({ ok: false, connected: false, error: err.message }));
    return true;
  }

  // Read current macOS permission state from the dashboard API
  if (message.type === 'GET_SYSTEM_PERMISSIONS') {
    fetchWithFallback('/api/system-permissions')
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (message.type === 'OPEN_MACOS_SETTINGS') {
    chrome.tabs.create({ url: 'http://127.0.0.1:4317/' }, () => sendResponse(chrome.runtime.lastError
      ? {ok:false,error:chrome.runtime.lastError.message}
      : { ok: true, instruction: 'Open Settings from the authenticated dashboard' }));
    return true;
  }

  sendResponse({ ok: false, error: 'unknown error' });
  return false;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const ownPanel = sender.id === chrome.runtime.id && sender.url === chrome.runtime.getURL('sidepanel.html');
  let dashboard = false;
  try { const url = new URL(sender.url); dashboard = url.protocol === 'http:' && ['localhost','127.0.0.1','[::1]'].includes(url.hostname) && url.port === '4317'; } catch {}
  if (['GET_CONTROL','SET_CONTROL'].includes(message.type)) {
    if (!ownPanel && !dashboard) { sendResponse({ ok: false, error: 'Untrusted control sender' }); return false; }
    if (message.type === 'SET_CONTROL') {
      if (typeof message.enabled !== 'boolean') { sendResponse({ ok: false, error: 'Invalid enabled state' }); return false; }
      chrome.storage.local.set({ 'crewloom.enabled': message.enabled }, () => sendResponse({ ok: true, enabled: message.enabled, version: chrome.runtime.getManifest().version }));
    } else chrome.storage.local.get({ 'crewloom.enabled': false }, (value) => sendResponse({ ok: true, enabled: value['crewloom.enabled'], version: chrome.runtime.getManifest().version }));
    return true;
  }
  if (!ownPanel) { sendResponse({ ok: false, error: 'Only the companion panel may request this action' }); return false; }
  chrome.storage.local.get({ 'crewloom.enabled': false }, (value) => {
    if (message.type === 'CAPTURE_TAB' && !value['crewloom.enabled']) return sendResponse({ ok: false, error: 'Browser companion is disabled' });
    handleMessage(message, sender, sendResponse);
  });
  return true;
});

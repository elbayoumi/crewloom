/**
 * Crewloom Computer Use - Side Panel Controller
 * Manual tab management, DOM indexing, visual capture & execution.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const tabTitle = document.getElementById('tabTitle');
  const tabUrl = document.getElementById('tabUrl');
  const refreshTabBtn = document.getElementById('refreshTabBtn');
  const indexBtn = document.getElementById('indexBtn');
  let currentGeneration = null;
  let panelWindowId = null;
  const captureBtn = document.getElementById('captureBtn');
  const inspectBtn = document.getElementById('inspectBtn');
  const clearBtn = document.getElementById('clearBtn');
  const visionImg = document.getElementById('visionImg');
  const visionEmpty = document.getElementById('visionEmpty');
  const frameMeta = document.getElementById('frameMeta');
  const elementInput = document.getElementById('elementInput');
  const clickElementBtn = document.getElementById('clickElementBtn');
  const directoryList = document.getElementById('directoryList');
  const elemCountBadge = document.getElementById('elemCountBadge');
  const terminalLogs = document.getElementById('terminalLogs');
  const clearConsoleBtn = document.getElementById('clearConsoleBtn');
  const openMacSettingsBtn = document.getElementById('openMacSettingsBtn');
  const langToggle = document.getElementById('langToggle');
  const daemonLabel = document.getElementById('daemonLabel');

  const LANG_KEY = 'crewloom.lang';
  const MAX_DIRECTORY_ROWS = 50;
  const RESTRICTED_URL = /^(chrome|edge|brave|about|chrome-extension|devtools|view-source):/i;

  let currentTab = null;
  let navigationEpoch = 0;
  let refreshRequest = 0;
  let indexRequest = 0;
  let indexedTargets = new Map();
  const overlayFrames = new Map();
  let directoryResult = null;
  let directoryPage = 0;
  let daemonConnected = null;
  let language = 'en';
  let directoryEmptyKey = 'dirIdle';
  let lastDirectoryNote = null;
  let lastCaptureTime = null;

  const i18n = {
    en: {
      errorCaptureDisabled: "Browser companion was disabled during capture",
      errorWindow: "Explicit panel window required",
      errorNoTab: "No active tab",
      errorHandshake: "Unsupported dashboard handshake",
      errorSender: "Untrusted control sender",
      errorEnabled: "Invalid enabled state",
      errorPanelOnly: "Only the companion panel may request this action",
      companion: "Browser companion",
      computerUse: "Computer Use",
      switchLanguage: "Switch Language",
      refreshTab: "Refresh Tab State",
      previewAlt: "Visual Frame Preview",
      errorUnknown: "unknown error",
      errorNotFound: "element not found",
      errorConnection: "connection refused",
      errorManyFrames: "Too many frames; open the target frame separately",
      errorIndexFrame: "A frame could not be indexed; reload and retry",
      errorClearFrames: "One or more frames could not be cleared; reload and retry",
      errorStale: "Stale or invalid element index; re-index the page",
      errorDocument: "Document changed; re-index the page",
      errorRemoved: "Indexed element was removed; re-index the page",
      errorChanged: "Indexed element changed or is not interactive; re-index the page",
      errorCovered: "Indexed element is covered or changed; re-index the page",
      errorFocus: "Target changed on focus; re-index the page",
      errorToken: "Index generation and document token required; re-index the page",
      errorDisabled: "Browser companion is disabled",
      untitled: 'Untitled',
      languageName: 'English',
      indexName: 'Auto-Index Page',
      indexSub: 'Number buttons [1], [2]...',
      captureName: 'Vision Capture',
      captureSub: 'Capture tab screenshot',
      inspectName: 'Hover Inspector',
      inspectSub: 'Inspect DOM elements',
      clearName: 'Clear Overlays',
      clearSub: 'Remove in-page tags',
      visionTitle: 'Visual Vision Frame',
      visionEmpty: 'Click "Vision Capture" to stream the visual tab state for the AI agent.',
      noCapture: 'No capture yet',
      captureMeta: 'Captured {time}',
      inputPlaceholder: 'Element # (e.g. 1)',
      clickBtn: 'Execute Click',
      interactiveTitle: 'Interactive Elements',
      terminalTitle: 'Agent Execution Stream',
      clearConsole: 'Clear',
      permAcc: '🖥️ Accessibility',
      permScreen: '📸 Screen Capture',
      macSettings: 'macOS Settings ↗',
      daemonOnline: 'Online :4317',
      daemonStandalone: 'Standalone',
      dirIdle: 'Click "Auto-Index Page" to detect interactive elements.',
      dirEmpty: 'No interactive elements detected.',
      dirCleared: 'Overlays cleared.',
      dirShowing: 'Showing {start}–{end} of {indexed} indexed; {total} found.',
      dirTruncated: 'Showing {start}–{end} of {indexed} indexed; {total} found (limit {limit}).',
      previous: 'Previous', next: 'Next',
      itemClick: 'Click',
      logInit: 'Panel ready. Extension version {version}.',
      logTab: 'Focused tab: {title}',
      logNoTab: 'No readable tab.',
      logIndexing: 'Indexing interactive elements on page...',
      logIndexed: 'Indexed {count} interactive elements.',
      logIndexLimited: 'Indexed {shown} of {total} elements; page limit {limit} reached.',
      logIndexFailed: 'Index failed: {error}',
      logSkippedFrames: 'Skipped {count} frames whose embedding cannot be verified; open the target frame separately.',
      logRestricted: 'This page blocks extensions (browser settings page).',
      logCleared: 'In-page grounding tags cleared.',
      logClearFailed: 'Clear failed: {error}',
      logInspecting: 'Inspector activated: hover over page elements.',
      logInspectorOff: 'Inspector deactivated.',
      logInspectorFailed: 'Inspector failed: {error}',
      logCapture: 'Capturing high-resolution visual tab frame...',
      logCaptured: 'Visual frame captured at {time}.',
      logCaptureFailed: 'Vision capture failed: {error}',
      logClick: 'Executing browser click on element [{index}]...',
      logClicked: 'Click dispatched on <{tag}> at ({x}, {y}).',
      logClickFailed: 'Click failed: {error}',
      logMacOpening: 'Opening macOS Accessibility settings...',
      logMacOpened: 'macOS settings request sent to the dashboard.',
      logMacFailed: 'Could not reach the dashboard API: {error}',
      logDaemon: 'Local Crewloom daemon handshake verified.',
      logDaemonOffline: 'Dashboard API offline on :4317 ({error}).',
      logLang: 'Language switched to {language}.'
    },
    ar: {
      errorCaptureDisabled: "تم تعطيل إضافة المتصفح أثناء الالتقاط",
      errorWindow: "يجب تحديد نافذة لوحة الإضافة",
      errorNoTab: "لا يوجد تبويب نشط",
      errorHandshake: "اتصال الداشبورد غير متوافق",
      errorSender: "مرسل طلب التحكم غير موثوق",
      errorEnabled: "حالة تفعيل غير صالحة",
      errorPanelOnly: "لوحة الإضافة وحدها يمكنها طلب هذا الإجراء",
      companion: "إضافة المتصفح",
      computerUse: "التحكم بالحاسوب",
      switchLanguage: "تبديل اللغة",
      refreshTab: "تحديث حالة التبويب",
      previewAlt: "معاينة لقطة التبويب",
      errorUnknown: "خطأ غير معروف",
      errorNotFound: "لم يتم العثور على العنصر",
      errorConnection: "تعذر الاتصال",
      errorManyFrames: "عدد الإطارات كبير؛ افتح الإطار المطلوب في تبويب منفصل",
      errorIndexFrame: "تعذر ترقيم أحد الإطارات؛ أعد تحميل الصفحة وحاول مجددًا",
      errorClearFrames: "تعذر مسح إطار أو أكثر؛ أعد تحميل الصفحة وحاول مجددًا",
      errorStale: "رقم العنصر قديم أو غير صالح؛ أعد ترقيم الصفحة",
      errorDocument: "تغير المستند؛ أعد ترقيم الصفحة",
      errorRemoved: "تمت إزالة العنصر؛ أعد ترقيم الصفحة",
      errorChanged: "تغير العنصر أو لم يعد تفاعليًا؛ أعد ترقيم الصفحة",
      errorCovered: "العنصر مغطى أو تغير؛ أعد ترقيم الصفحة",
      errorFocus: "تغير العنصر عند التركيز عليه؛ أعد ترقيم الصفحة",
      errorToken: "بيانات الترقيم والمستند مطلوبة؛ أعد ترقيم الصفحة",
      errorDisabled: "إضافة المتصفح غير مفعلة",
      untitled: 'بدون عنوان',
      languageName: 'العربية',
      indexName: 'ترقيم الصفحة',
      indexSub: 'ترقيم العناصر التفاعلية [1]، [2]...',
      captureName: 'التقاط الرؤية',
      captureSub: 'أخذ لقطة فورية للتبويب',
      inspectName: 'الفاحص المباشر',
      inspectSub: 'فحص شجرة DOM للويب',
      clearName: 'مسح الإشارات',
      clearSub: 'إزالة أرقام العناصر',
      visionTitle: 'إطار الرؤية البصرية',
      visionEmpty: 'اضغط "التقاط الرؤية" لبث لقطة التبويب لوكيل الذكاء الاصطناعي.',
      noCapture: 'لا يوجد التقاط بعد',
      captureMeta: 'تم الالتقاط {time}',
      inputPlaceholder: 'رقم العنصر (مثال: 1)',
      clickBtn: 'تنفيذ النقر',
      interactiveTitle: 'العناصر التفاعلية',
      terminalTitle: 'سجل تنفيذ الوكيل',
      clearConsole: 'مسح',
      permAcc: '🖥️ إمكانية الوصول',
      permScreen: '📸 تسجيل الشاشة',
      macSettings: 'إعدادات الماك ↗',
      daemonOnline: 'متصل :4317',
      daemonStandalone: 'مستقل',
      dirIdle: 'اضغط "ترقيم الصفحة" لاكتشاف العناصر التفاعلية.',
      dirEmpty: 'لم يتم العثور على عناصر تفاعلية.',
      dirCleared: 'تم مسح الإشارات.',
      dirShowing: 'عرض {start}–{end} من {indexed} مفهرس؛ {total} موجود.',
      dirTruncated: 'عرض {start}–{end} من {indexed} مفهرس؛ {total} موجود (الحد {limit}).',
      previous: 'السابق', next: 'التالي',
      itemClick: 'اضغط',
      logInit: 'اللوحة جاهزة. إصدار الإضافة {version}.',
      logTab: 'التبويب النشط: {title}',
      logNoTab: 'لا يوجد تبويب قابل للقراءة.',
      logIndexing: 'جارٍ ترقيم العناصر التفاعلية في الصفحة...',
      logIndexed: 'تم ترقيم {count} عنصر تفاعلي.',
      logIndexLimited: 'تم ترقيم {shown} من {total} عنصر؛ تم بلوغ حد الصفحة {limit}.',
      logIndexFailed: 'فشل الترقيم: {error}',
      logSkippedFrames: 'تم تجاوز {count} إطار لا يمكن التحقق من موضعه؛ افتح الإطار المطلوب في تبويب منفصل.',
      logRestricted: 'هذه الصفحة تمنع الإضافات (صفحة إعدادات المتصفح).',
      logCleared: 'تم مسح أرقام العناصر من الصفحة.',
      logClearFailed: 'فشل المسح: {error}',
      logInspecting: 'تم تفعيل الفاحص: مرّر المؤشر فوق عناصر الصفحة.',
      logInspectorOff: 'تم إيقاف الفاحص.',
      logInspectorFailed: 'فشل الفاحص: {error}',
      logCapture: 'جارٍ التقاط إطار الرؤية بدقة عالية...',
      logCaptured: 'تم التقاط الإطار البصري في {time}.',
      logCaptureFailed: 'فشل التقاط الرؤية: {error}',
      logClick: 'جارٍ تنفيذ نقرة الوكيل على العنصر [{index}]...',
      logClicked: 'تم إرسال نقرة إلى <{tag}> عند ({x}، {y}).',
      logClickFailed: 'فشلت النقرة: {error}',
      logMacOpening: 'جارٍ فتح إعدادات الوصول في macOS...',
      logMacOpened: 'تم إرسال طلب الإعدادات إلى الداشبورد.',
      logMacFailed: 'تعذر الوصول إلى واجهة الداشبورد: {error}',
      logDaemon: 'تم التحقق من الاتصال بالداشبورد المحلي.',
      logDaemonOffline: 'واجهة الداشبورد غير متاحة على :4317 ({error}).',
      logLang: 'تم تبديل اللغة إلى {language}.'
    }
  };

  const errorKeys = {
    "Browser companion was disabled during capture": "errorCaptureDisabled",
    "Explicit panel window required": "errorWindow",
    "No active tab": "errorNoTab",
    "Unsupported dashboard handshake": "errorHandshake",
    "Untrusted control sender": "errorSender",
    "Invalid enabled state": "errorEnabled",
    "Only the companion panel may request this action": "errorPanelOnly",
    "unknown error": "errorUnknown",
    "element not found": "errorNotFound",
    "connection refused": "errorConnection",
    "Too many frames; open the target frame separately": "errorManyFrames",
    "A frame could not be indexed; reload and retry": "errorIndexFrame",
    "One or more frames could not be cleared; reload and retry": "errorClearFrames",
    "Stale or invalid element index; re-index the page": "errorStale",
    "Document changed; re-index the page": "errorDocument",
    "Indexed element was removed; re-index the page": "errorRemoved",
    "Indexed element changed or is not interactive; re-index the page": "errorChanged",
    "Indexed element is covered or changed; re-index the page": "errorCovered",
    "Target changed on focus; re-index the page": "errorFocus",
    "Index generation and document token required; re-index the page": "errorToken",
    "Browser companion is disabled": "errorDisabled"
};

  function t(key, vars) {
    const template = i18n[language][key] ?? i18n.en[key] ?? key;
    if (!vars) return template;
    return template.replace(/\{(\w+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match
    );
  }

  function getTime() {
    return new Date().toLocaleTimeString('en-US', { hour12: false });
  }

  function log(key, type = 'info', vars) {
    const line = document.createElement('div');
    line.className = `log-line log-${type}`;
    line.textContent = `[${getTime()}] ${t(key, vars)}`;
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  function errorMessage(error) {
    const message = error || 'unknown error';
    return Object.prototype.hasOwnProperty.call(errorKeys,message) ? t(errorKeys[message]) : message;
  }

  function describeError(error, key = 'logIndexFailed') {
    const message = chrome.runtime.lastError?.message || error || 'unknown error';
    if (RESTRICTED_URL.test(currentTab?.url || '')) {
      return log('logRestricted', 'warn');
    }
    return log(key, 'warn', { error: errorMessage(message) });
  }

  function setDirectoryText(textKey) {
    directoryEmptyKey = textKey;
    lastDirectoryNote = null;
    directoryList.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'directory-empty';
    empty.textContent = t(textKey);
    directoryList.appendChild(empty);
  }

  function setDirectoryNote(key, vars) {
    lastDirectoryNote = { key, vars };
    const note = document.createElement('div');
    note.className = 'directory-note';
    note.textContent = t(key, vars);
    directoryList.insertBefore(note, directoryList.firstChild);
  }

  function rememberFrame(tabId, frameId) {
    if (!overlayFrames.has(tabId)) overlayFrames.set(tabId, new Set());
    overlayFrames.get(tabId).add(frameId);
  }

  function clearFrameOverlays(tabId, done = () => {}) {
    const ids = overlayFrames.get(tabId) || new Set([0]);
    let pending = ids.size, failed = false;
    if (!pending) return done(true);
    for (const frameId of [...ids]) {
      chrome.tabs.sendMessage(tabId, {type:'CLEAR_INDEX'}, {frameId}, (res) => {
        if (chrome.runtime.lastError || !res?.ok) failed = true;
        else ids.delete(frameId);
        if (--pending === 0) {
          if (!ids.size) overlayFrames.delete(tabId);
          done(!failed);
        }
      });
    }
  }

  function resetIndexState() {
    navigationEpoch += 1;
    indexRequest += 1;
    indexedTargets.clear();
    directoryResult = null;
    currentGeneration = null;
    elemCountBadge.textContent = '0';
    setDirectoryText('dirIdle');
  }

  // Refresh active tab info
  function refreshActiveTab(onReady) {
    if (!Number.isInteger(panelWindowId)) return;
    const request = ++refreshRequest;
    chrome.runtime.sendMessage({ type: 'GET_ACTIVE_TAB', windowId: panelWindowId }, (res) => {
      if (request !== refreshRequest) return;
      const previousId = currentTab?.id;
      const previousUrl = currentTab?.url;
      currentTab = res?.tab ?? null;

      if (!currentTab?.id) {
        resetIndexState();
        tabTitle.textContent = t('logNoTab');
        tabUrl.textContent = '—';
        return;
      }

      tabTitle.textContent = currentTab.title || t('untitled');
      tabUrl.textContent = currentTab.url ? new URL(currentTab.url).hostname : '—';
      log('logTab', 'info', { title: tabTitle.textContent });

      if (previousId && (previousId !== currentTab.id || previousUrl !== currentTab.url)) {
        // Indices from the previous page no longer describe this tab
        clearFrameOverlays(previousId);
        resetIndexState();
      }
      if (typeof onReady === 'function') onReady();
    });
  }

  // Auto-Index Page
  indexBtn.addEventListener('click', () => {
    if (!currentTab?.id) return refreshActiveTab();
    const tabId = currentTab.id;
    const url = currentTab.url;
    const epoch = navigationEpoch;
    const request = ++indexRequest;
    indexedTargets.clear();
    currentGeneration = null;
    const fresh = () => request === indexRequest && epoch === navigationEpoch &&
      currentTab?.id === tabId && currentTab?.url === url;
    log('logIndexing', 'action');
    const accept = (res) => {
      if (!fresh()) return;
      if (chrome.runtime.lastError || !res?.ok) {
        clearFrameOverlays(tabId);
        currentGeneration = null;
    elemCountBadge.textContent = '0';
        setDirectoryText('dirIdle');
        return describeError(res?.error);
      }
      currentGeneration = res.generation;
      indexedTargets = new Map((res.items || []).map(item => [item.index, {
        tabId, frameId: item.frameId ?? 0, documentToken: item.documentToken ?? res.documentToken,
        generation: item.generation ?? res.generation
      }]));
      elemCountBadge.textContent = res.count;
      if (res.truncated) {
        log('logIndexLimited', 'warn', {
          shown: res.count,
          total: res.total,
          limit: res.limit
        });
      } else {
        log('logIndexed', 'success', { count: res.count });
      }
      renderDirectory(res);
      if (res.blockedFrames) log('logSkippedFrames', 'warn', {count:res.blockedFrames});
    };
    if (!chrome.scripting?.executeScript) {
      rememberFrame(tabId, 0);
      chrome.tabs.sendMessage(tabId, { type: 'INDEX_PAGE' }, accept);
      return;
    }
    const discover = () => chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: () => true }, (frames) => {
      if (!fresh()) return;
      if (chrome.runtime.lastError || !frames?.length) return accept(null);
      const ids = [...new Set(frames.map(frame => frame.frameId))].sort((a,b) => a-b);
      if (ids.length > 128) return accept({ok:false,error:'Too many frames; open the target frame separately'});
      const combined = { ok: true, items: [], total: 0, limit: 400, generation: null, truncated: false, blockedFrames: 0 };
      function scan(position) {
        if (!fresh()) return;
        if (position === ids.length) {
          combined.count = combined.items.length;
          combined.truncated = combined.count < combined.total;
          accept(combined); return;
        }
        const frameId = ids[position];
        rememberFrame(tabId, frameId); // Also retain frames whose indexing reply fails.
        chrome.tabs.sendMessage(tabId, { type: 'INDEX_PAGE', includeFrames: false,
          offset: combined.items.length, limit: Math.max(0,400-combined.items.length) }, {frameId}, (res) => {
          if (!fresh()) return;
          if (chrome.runtime.lastError || !res?.ok) {
            return accept({ok:false,error:'A frame could not be indexed; reload and retry'});
          }
          combined.total += res.total;
          combined.blockedFrames += res.blockedFrames || 0;
          combined.items.push(...res.items.map(item => ({...item,frameId,
            generation:res.generation,documentToken:res.documentToken})));
          scan(position+1);
        });
      }
      scan(0);
    });
    clearFrameOverlays(tabId, () => { if (fresh()) discover(); });
  });

  // Render directory list
  function renderDirectory(res, page = 0) {
    directoryResult = res;
    directoryPage = page;
    const items = res.items || [];
    directoryList.innerHTML = '';
    if (!items.length) {
      setDirectoryText('dirEmpty');
      return;
    }

    const start = page * MAX_DIRECTORY_ROWS;
    const shown = Math.min(items.length-start, MAX_DIRECTORY_ROWS);
    setDirectoryNote(res.truncated ? 'dirTruncated' : 'dirShowing', {
      shown, start:start+1, end:start+shown, indexed:items.length,
      total: res.total ?? items.length,
      limit: res.limit ?? items.length
    });

    items.slice(start, start+shown).forEach((item) => {
      const row = document.createElement('div');
      row.className = 'directory-item';

      const idx = document.createElement('span');
      idx.className = 'elem-idx';
      idx.textContent = `[${item.index}]`;

      const desc = document.createElement('span');
      desc.className = 'elem-desc';
      desc.textContent = `<${item.tag}> ${item.text || '—'}`;
      desc.title = `<${item.tag}> ${item.text || ''}`;

      const click = document.createElement('button');
      click.className = 'btn-item-click';
      click.dataset.index = item.index;
      click.textContent = t('itemClick');
      click.addEventListener('click', () => executeClick(item.index));

      row.append(idx, desc, click);
      directoryList.appendChild(row);
    });
    if (items.length > MAX_DIRECTORY_ROWS) {
      const controls = document.createElement('div');
      controls.className = 'directory-pagination';
      controls.setAttribute('role','group');
      for (const [id, label, delta, disabled] of [
        ['directoryPrevious','previous',-1,page===0],
        ['directoryNext','next',1,start+shown===items.length]
      ]) {
        const button = document.createElement('button');
        button.className='btn-ghost';
        button.id=id; button.textContent=t(label); button.disabled=disabled;
        button.addEventListener('click',()=>renderDirectory(res,page+delta));
        controls.appendChild(button);
      }
      directoryList.appendChild(controls);
    }
  }

  // Execute Click on Element Index
  function executeClick(index) {
    const target = indexedTargets.get(index);
    if (!currentTab?.id || !target || target.tabId !== currentTab.id) return;
    log('logClick', 'action', { index });
    const message = { type: 'CLICK_INDEX', index, generation: target.generation, documentToken:target.documentToken };
    const reply = (res) => {
      if (res?.ok) {
        log('logClicked', 'success', {
          tag: res.tag,
          x: Math.round(res.x),
          y: Math.round(res.y)
        });
      } else {
        log('logClickFailed', 'warn', { error: errorMessage(res?.error || 'element not found') });
      }
    };
    chrome.tabs.sendMessage(target.tabId,message,{frameId:target.frameId},reply);
  }

  clickElementBtn.addEventListener('click', () => {
    const value = parseInt(elementInput.value, 10);
    if (Number.isFinite(value) && value > 0) {
      executeClick(value);
      elementInput.value = '';
    }
  });

  elementInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') clickElementBtn.click();
  });

  // Vision Capture
  function captureFrame() {
    log('logCapture', 'action');
    chrome.runtime.sendMessage(
      { type: 'CAPTURE_TAB', windowId: panelWindowId },
      (res) => {
        if (res?.ok && res.dataUrl) {
          visionImg.src = res.dataUrl;
          visionImg.classList.remove('hidden');
          visionEmpty.classList.add('hidden');
          const time = getTime();
          lastCaptureTime = time;
          frameMeta.textContent = t('captureMeta', { time });
          log('logCaptured', 'success', { time });
        } else {
          log('logCaptureFailed', 'warn', { error: errorMessage(res?.error) });
        }
      }
    );
  }

  captureBtn.addEventListener('click', captureFrame);

  let consumingCapture = false;
  function consumePendingCapture() {
    if (consumingCapture || !Number.isInteger(panelWindowId)) return;
    consumingCapture = true;
    chrome.runtime.sendMessage({ type: 'PANEL_READY', windowId: panelWindowId }, (res) => {
      consumingCapture = false;
      if (!res?.ok || !res.pending) return;
      refreshActiveTab(() => {
        // Refuse if the clicked tab changed while the panel was opening.
        if (currentTab?.id === res.pending.tabId && currentTab.windowId === panelWindowId) captureFrame();
      });
    });
  }
  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === 'CAPTURE_REQUEST' && message.windowId === panelWindowId) consumePendingCapture();
  });

  // Hover Inspector
  inspectBtn.addEventListener('click', () => {
    if (!currentTab?.id) return;
    chrome.tabs.sendMessage(currentTab.id, { type: 'TOGGLE_INSPECTOR' }, (res) => {
      if (chrome.runtime.lastError || !res?.ok) {
        return describeError(res?.error, 'logInspectorFailed');
      }
      log(res.active ? 'logInspecting' : 'logInspectorOff', 'info');
    });
  });

  // Clear Overlays
  clearBtn.addEventListener('click', () => {
    if (!currentTab?.id) return;
    const tabId = currentTab.id;
    resetIndexState();
    const epoch = navigationEpoch;
    clearFrameOverlays(tabId, (ok) => {
      if (currentTab?.id !== tabId || epoch !== navigationEpoch) return;
      if (!ok) {
        return describeError('One or more frames could not be cleared; reload and retry', 'logClearFailed');
      }
      currentGeneration = null;
    elemCountBadge.textContent = '0';
      setDirectoryText('dirCleared');
      log('logCleared', 'info');
    });
  });

  // Refresh tab
  refreshTabBtn.addEventListener('click', refreshActiveTab);

  // Clear console
  clearConsoleBtn.addEventListener('click', () => {
    terminalLogs.innerHTML = '';
  });

  // macOS Settings Deep Link
  openMacSettingsBtn.addEventListener('click', () => {
    log('logMacOpening', 'action');
    chrome.runtime.sendMessage(
      { type: 'OPEN_MACOS_SETTINGS', pane: 'Privacy_Accessibility' },
      (res) => {
        if (res?.ok) log('logMacOpened', 'success');
        else log('logMacFailed', 'warn', { error: errorMessage(res?.error) });
      }
    );
  });

  function applyLanguage(lang) {
    language = lang === 'ar' ? 'ar' : 'en';
    const isRtl = language === 'ar';
    document.documentElement.setAttribute('dir', isRtl ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', language);
    langToggle.textContent = isRtl ? 'English' : 'العربية';
    langToggle.title = t('switchLanguage');
    langToggle.setAttribute('aria-label', t('switchLanguage'));
    document.getElementById('companionLabel').textContent = t('companion');
    document.querySelector('.sp-badge').textContent = t('computerUse');
    refreshTabBtn.title = t('refreshTab');
    refreshTabBtn.setAttribute('aria-label', t('refreshTab'));
    visionImg.alt = t('previewAlt');
    elementInput.setAttribute('aria-label',t('inputPlaceholder'));
    if (currentTab && !currentTab.title) tabTitle.textContent = t('untitled');

    document.querySelector('#indexBtn .tool-name').textContent = t('indexName');
    document.querySelector('#indexBtn .tool-sub').textContent = t('indexSub');
    document.querySelector('#captureBtn .tool-name').textContent = t('captureName');
    document.querySelector('#captureBtn .tool-sub').textContent = t('captureSub');
    document.querySelector('#inspectBtn .tool-name').textContent = t('inspectName');
    document.querySelector('#inspectBtn .tool-sub').textContent = t('inspectSub');
    document.querySelector('#clearBtn .tool-name').textContent = t('clearName');
    document.querySelector('#clearBtn .tool-sub').textContent = t('clearSub');
    document.querySelector('#visionSection .section-title').textContent = t('visionTitle');
    document.querySelector('#visionEmpty span').textContent = t('visionEmpty');
    elementInput.placeholder = t('inputPlaceholder');
    clickElementBtn.textContent = t('clickBtn');
    clickElementBtn.setAttribute('aria-label', t('clickBtn'));
    document.querySelector('.directory-section .section-title').textContent = t('interactiveTitle');
    document.querySelector('.terminal-section .section-title').textContent = t('terminalTitle');
    clearConsoleBtn.textContent = t('clearConsole');
    clearConsoleBtn.setAttribute('aria-label', t('clearConsole'));
    document.getElementById('permAcc').textContent = t('permAcc');
    document.getElementById('permScreen').textContent = t('permScreen');
    openMacSettingsBtn.textContent = t('macSettings');
    openMacSettingsBtn.setAttribute('aria-label', t('macSettings'));
    frameMeta.textContent = lastCaptureTime ? t('captureMeta', { time: lastCaptureTime }) : t('noCapture');

    const empty = directoryList.querySelector('.directory-empty');
    if (empty) empty.textContent = t(directoryEmptyKey);
    const note = directoryList.querySelector('.directory-note');
    if (note && lastDirectoryNote) note.textContent = t(lastDirectoryNote.key, lastDirectoryNote.vars);
    if (directoryResult) renderDirectory(directoryResult,directoryPage);
    if (daemonConnected !== null) daemonLabel.textContent = t(daemonConnected ? 'daemonOnline' : 'daemonStandalone');
  }

  // Language Toggle (English <-> Arabic) persisted across panel sessions
  function setLanguage(lang, announce) {
    applyLanguage(lang);
    chrome.storage.local.set({ [LANG_KEY]: language });
    if (announce) log('logLang', 'info', { language: t('languageName') });
  }

  langToggle.addEventListener('click', () => {
    setLanguage(language === 'ar' ? 'en' : 'ar', true);
  });

  chrome.storage.local.get(LANG_KEY, (stored) => {
    applyLanguage(stored?.[LANG_KEY]);
    log('logInit', 'info', { version: chrome.runtime.getManifest().version });
    refreshActiveTab();
  });

  const control = document.getElementById('companionEnabled');
  function showControl(enabled) {
    control.checked = enabled;
    for (const id of ['indexBtn','captureBtn','inspectBtn','clickElementBtn']) document.getElementById(id).disabled = !enabled;
  }
  chrome.runtime.sendMessage({ type: 'GET_CONTROL' }, (res) => showControl(res?.ok && res.enabled));
  control.addEventListener('change', () => chrome.runtime.sendMessage({ type: 'SET_CONTROL', enabled: control.checked }, (res) => showControl(res?.ok && res.enabled)));
  chrome.storage.onChanged.addListener((changes, area) => { if (area === 'local' && changes['crewloom.enabled']) showControl(changes['crewloom.enabled'].newValue); });

  // Refresh measured status without overlapping requests or repeating unchanged logs.
  let daemonCheckPending = false;
  function checkDaemon() {
    if (daemonCheckPending) return;
    daemonCheckPending = true;
    chrome.runtime.sendMessage({ type: 'CHECK_LOCAL_DAEMON' }, (res) => {
    daemonCheckPending = false;
    const connected = res?.connected === true;
    const changed = connected !== daemonConnected;
    daemonConnected = connected;
    daemonLabel.title = new Date().toISOString();
    if (res?.connected) {
      daemonLabel.textContent = t('daemonOnline');
      daemonLabel.style.color = '';
      if (changed) log('logDaemon', 'success');
    } else {
      daemonLabel.textContent = t('daemonStandalone');
      daemonLabel.style.color = 'var(--warn)';
      if (changed) log('logDaemonOffline', 'warn', { error: errorMessage(res?.error || 'connection refused') });
    }
  });
  }
  checkDaemon();
  const daemonTimer = setInterval(checkDaemon, 15000);
  window.addEventListener('unload',()=>clearInterval(daemonTimer));

  chrome.windows?.getCurrent((w) => { panelWindowId = w.id; refreshActiveTab(consumePendingCapture); });

  // Dynamic tab tracking like Claude/Codex
  if (chrome.tabs?.onActivated) {
    chrome.tabs.onActivated.addListener((info) => {
      if (info && info.windowId !== panelWindowId) return;
      resetIndexState();
      refreshActiveTab();
    });
  }
  if (chrome.tabs?.onUpdated) {
    chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (currentTab && tabId === currentTab.id && (changeInfo.status || changeInfo.url)) {
        clearFrameOverlays(tabId);
        resetIndexState();
        refreshActiveTab();
      }
    });
  }
});

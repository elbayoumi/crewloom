# Crewloom Computer Use — Chrome / Brave / Edge Extension

Manifest V3 companion extension for **Crewloom Computer Use**. It opens a Chrome Side Panel
cockpit that indexes interactive page elements, draws numbered grounding tags on them, inspects
hovered elements, captures the visible tab for vision models, and drives clicks by element index.

---

## Requirements

- Chrome 114+, Brave, or Edge (the Side Panel API is the primary surface).
- Optional: the Crewloom dashboard running on `http://localhost:4317` for the daemon badge and
  the macOS permission deep link. Without it the panel still works and reports `Standalone`.

## Install (load unpacked)

1. Open `chrome://extensions`, `brave://extensions`, or `edge://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select this directory:
   ```
   /absolute/path/to/crewloom/extensions/chrome
   ```
4. Click the Crewloom toolbar icon, or press `Cmd+Shift+L` (macOS) / `Ctrl+Shift+L`
   (Windows, Linux) to open the panel.

## Files

| File | Purpose |
| --- | --- |
| `manifest.json` | MV3 declaration: side panel, content script, commands, context menus, web-accessible icons |
| `background.js` | Service worker: side-panel behavior, context menus, tab capture, dashboard API bridge |
| `sidepanel.html/css/js` | The cockpit UI, bilingual EN/AR labels, execution stream |
| `content.js/css` | In-page indexing, grounding overlay, hover inspector, click wave |
| `icons/` | 16/32/48/128 px brand icons |

Enable the companion explicitly using its checkbox. It starts disabled and activation persists across sessions; this is an extension-wide browser setting. See the [verified behavior guide](../../documentation/CHROME_EXTENSION_SIDE_PANEL.md).

## Capabilities

- **Numbered visual grounding** — indexes buttons, links, inputs, selects, textareas and ARIA
  roles, then draws `[1]`, `[2]`, … tags in a dedicated non-destructive overlay layer. Tags
  re-anchor on scroll and resize.
- **Bounded indexing** — at most 400 targets per tab, prioritized by viewport distance. Readable
  frames share that budget; open Shadow DOM is traversed. The panel paginates the directory in
  50-row pages and distinguishes displayed, indexed and found counts.
- **Click by index** — type a number or use the `Click` button next of a row; the content script
  scrolls the element into view, focuses it, clicks it, and renders a click wave.
- **Hover inspector** — highlights the element under the cursor with its tag, id, and pixel size.
- **Vision capture** — `chrome.tabs.captureVisibleTab` for the focused window, previewed in-panel.
- **Live tab tracking** — `chrome.tabs.onActivated` / `onUpdated` refresh the banner and reset
  stale indices when the tab changes or finishes loading.
- **Bilingual EN/AR** — instant switch with full RTL flip; the choice is stored in
  `chrome.storage.local` and restored on the next panel open.
- **Dashboard status** — daemon health on `:4317` refreshes every 15 seconds. The settings button
  opens the authenticated dashboard, where the user can open macOS settings.

## Permissions and why they are needed

| Permission | Reason |
| --- | --- |
| `sidePanel` | Opens the cockpit panel and the click-to-open behavior |
| `activeTab`, `scripting` | Tab-scoped inspection and messaging |
| `tabs` | Reads the active tab title, URL, and window id |
| `storage` | Persists the EN/AR language choice |
| `contextMenus` | Adds the "Inspect with Crewloom" and "Capture Visual Frame" entries |
| host `<all_urls>` | Injects the grounding overlay and lets `chrome.tabs.captureVisibleTab` produce a frame. Chrome rejects a capture without `<all_urls>` or a transient `activeTab` grant, and the panel cannot rely on a user gesture |
| host `localhost` / `127.0.0.1` | Dashboard API calls only (implied by `<all_urls>`) |

## Message contract

| Message | From → To | Payload → Response |
| --- | --- | --- |
| `GET_ACTIVE_TAB` | panel → background | `{windowId}` → `{ok, tab}` |
| `CAPTURE_TAB` | panel → background | `{windowId}` → `{ok, dataUrl}` |
| `CHECK_LOCAL_DAEMON` | panel → background | `{}` → `{ok, connected, data}` |
| `GET_SYSTEM_PERMISSIONS` | panel → background | `{}` → `{ok, data}` |
| `OPEN_MACOS_SETTINGS` | panel → background | `{}` → `{ok, instruction}`; opens the dashboard |
| `CAPTURE_REQUEST` | background → panel | `{windowId}` → triggers a capture |
| `INDEX_PAGE` | panel → content | `{includeFrames?, offset?, limit?}` → `{ok, documentToken, generation, count, total, truncated, limit, items}` |
| `CLEAR_INDEX` | panel → content | `{}` → `{ok}` |
| `CLICK_INDEX` | panel → content | `{index, generation, documentToken}` with target `frameId` → `{ok, x, y, tag}` |
| `TOGGLE_INSPECTOR` | panel or context menu → content | `{}` → `{ok, active}` |
| `GET_PAGE_SUMMARY` | panel → content | `{}` → `{ok, title, url, elementsCount}` |

## Known limits

- Browser-internal pages (`chrome://`, the Web Store, PDF viewer) block content scripts; the panel
  reports this instead of failing silently.
- Indexing prioritizes targets in the current viewport, then nearby off-screen targets. Re-index
  after scrolling to reach later targets. Readable frames consume the remaining shared 400-target budget without reserving space for empty frames;
  more than 128 frames are refused explicitly. Closed Shadow DOM and restricted pages are unavailable.
- Clicks require the original document token and generation. Action attributes, ancestor
  interactivity and hit-test visibility are checked before dispatch. Open a cross-origin frame
  separately if its parent visibility cannot be verified.
- Overlay tags are page-global: a page that repaints its own layout can still move elements under
  stale tags until the next re-index.

## Verification

The side-panel regression test mocks the Chrome APIs in a headless browser and asserts the panel
behavior plus the manifest contract:

```bash
python3 -m unittest scripts.test_sidepanel
CREWLOOM_SCREENSHOTS=1 python3 -m unittest scripts.test_sidepanel   # refresh the preview images
CREWLOOM_REAL_BROWSER=1 python3 -m unittest scripts.test_sidepanel  # load the unpacked extension
```

The third form loads this folder into headed Chromium against a synthetic HTTP fixture on an
ephemeral port. It checks manifest acceptance, grounding tags, the HUD logo, real click events
and a real `captureVisibleTab` frame. It skips when the runtime is unavailable; no user dashboard
or private project page is required.

### 2.3.1 frame corrections

Clear Overlays, tab changes and failed partial scans clear every contacted frame, including its HUD. Indexing carries unused capacity forward under the shared limit. Frames behind an origin boundary whose embedding hit test cannot be verified are omitted with a visible warning; open the target frame separately. The extension does not advertise handles it cannot safely click. No new permissions are required.

For unpacked installations, keep one stable installation directory and reload the existing extension after reviewed updates. A new directory produces a different unpacked Chrome extension ID. Immutable Crewloom release directories remain unchanged.

The language choice also applies to the owned in-page HUD and known companion errors. Language changes preserve the underlying site and hidden HUD state. Unknown external diagnostics retain their exact text. See [the language support contract](../../documentation/LANGUAGES.md).

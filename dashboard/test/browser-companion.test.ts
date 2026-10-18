import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

test('worker persists activation, rejects foreign senders, and gates capture', () => {
  let handler: (message: any, sender: any, reply: (value: any) => void) => unknown;
  const state: Record<string, unknown> = {};
  let captures = 0;
  const chrome = {
    runtime: { id: 'owned', getURL: (p: string) => `chrome-extension://owned/${p}`, getManifest: () => ({version:'2.2.0'}), onInstalled: {addListener() {}}, onMessage: {addListener(fn: typeof handler) {handler=fn;}} },
    sidePanel: {setPanelBehavior: () => Promise.resolve()},
    contextMenus: {onClicked: {addListener() {}}},
    storage: {local: {get: (defaults: object, cb: any) => cb({...defaults,...state}), set: (value: object, cb: any) => {Object.assign(state,value);cb();}}},
    tabs: {captureVisibleTab: (_: unknown, __: unknown, cb: any) => {captures++;cb('png');}}
  };
  const context = vm.createContext({chrome,console,URL,AbortSignal});
  vm.runInContext(readFileSync('../extensions/chrome/background.js','utf8'),vm.createContext({chrome,console,URL,AbortSignal,Date}));
  const panel={id:'owned',url:'chrome-extension://owned/sidepanel.html'};
  const call=(type: string, sender=panel, extra={}) => {let reply: any; handler!({type,...extra},sender,r=>reply=r);return reply;};
  assert.equal(call('CAPTURE_TAB').ok,false); assert.equal(captures,0);
  assert.equal(call('SET_CONTROL',{id:'owned',url:'https://foreign.example'},{enabled:true}).ok,false);
  assert.equal(call('SET_CONTROL',panel,{enabled:true}).enabled,true);
  assert.equal(call('CAPTURE_TAB').ok,false);
  assert.equal(call('CAPTURE_TAB',panel,{windowId:-1}).ok,false);
  assert.equal(captures,0);
  assert.equal(call('CAPTURE_TAB',panel,{windowId:7}).ok,true); assert.equal(captures,1);
  vm.runInContext(readFileSync('../extensions/chrome/background.js','utf8'),vm.createContext({chrome,console,URL,AbortSignal,Date}));
  assert.equal(call('GET_CONTROL').enabled,true);
  call('SET_CONTROL',panel,{enabled:false}); assert.equal(call('CAPTURE_TAB').ok,false); assert.equal(captures,1);
});


test('fresh panel consumes queued capture once, only in its requested window', () => {
  let handler: any, clicked: any;
  const pending: Record<string, any> = {};
  const chrome = {
    runtime: {id:'owned',getURL:(p: string)=>`chrome-extension://owned/${p}`,onInstalled:{addListener(){}},onMessage:{addListener(fn: any){handler=fn;}},sendMessage:()=>Promise.resolve()},
    sidePanel:{setPanelBehavior:()=>Promise.resolve(),open:()=>Promise.resolve()},
    contextMenus:{onClicked:{addListener(fn: any){clicked=fn;}}},
    storage:{local:{get:(defaults: object,cb: any)=>cb(defaults)},session:{
      set:(values: object,cb: any)=>{Object.assign(pending,values);cb();},
      get:(key: string,cb: any)=>cb({[key]:pending[key]}),
      remove:(key: string,cb: any)=>{delete pending[key];cb();}
    }}
  };
  const context=vm.createContext({chrome,console,URL,AbortSignal,Date});
  vm.runInContext(readFileSync('../extensions/chrome/background.js','utf8'),vm.createContext({chrome,console,URL,AbortSignal,Date}));
  clicked({menuItemId:'crewloom-capture'},{id:31,windowId:7});
  // A suspended worker must retain the first request until panel initialization.
  vm.runInContext(readFileSync('../extensions/chrome/background.js','utf8'),vm.createContext({chrome,console,URL,AbortSignal,Date}));
  const call=(windowId: number,sender={id:'owned',url:'chrome-extension://owned/sidepanel.html'})=>{let reply: any;handler({type:'PANEL_READY',windowId},sender,(r: any)=>reply=r);return reply;};
  assert.equal(call(8).pending,null);
  assert.equal(call(7,{id:'owned',url:'https://foreign.example'}).ok,false);
  assert.equal(call(7).pending.tabId,31);
  assert.equal(call(7).pending,null);
  clicked({menuItemId:'crewloom-capture'},{id:32,windowId:7});
  pending['crewloom.pendingCapture.7'].createdAt=Date.now()-31000;
  assert.equal(call(7).pending,null);
  assert.equal(call(-1).ok,false);
});
test('extension download refuses anonymous requests and serves only the packaged ZIP', async () => {
  const {GET}=await import('../app/api/extension/download/route.ts');
  const previous=process.env.CREWLOOM_DASHBOARD_TOKEN;
  const token='synthetic-download-credential-with-enough-characters';
  process.env.CREWLOOM_DASHBOARD_TOKEN=token;
  try {
    assert.equal((await GET(new Request('http://127.0.0.1:4317/api/extension/download'))).status,401);
    const response=await GET(new Request('http://127.0.0.1:4317/api/extension/download',{headers:{authorization:'Bearer '+token}}));
    assert.equal(response.status,200);
    assert.equal(response.headers.get('Content-Type'),'application/zip');
    const bytes=new Uint8Array(await response.arrayBuffer());
    assert.deepEqual([...bytes.slice(0,2)],[80,75]);
    assert.ok(bytes.length>100);
  } finally {
    if(previous===undefined) delete process.env.CREWLOOM_DASHBOARD_TOKEN;
    else process.env.CREWLOOM_DASHBOARD_TOKEN=previous;
  }
});

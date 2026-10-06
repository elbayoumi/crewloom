"""Trusted model RPC without filesystem, shell, browser or delegated-agent tools."""
import json
import os
import multiprocessing
import urllib.error
import urllib.request
from model_host import MAX_TEXT, SCHEMA, validate_artifacts

PROVIDERS={'openai':('https://api.openai.com/v1/responses','OPENAI_API_KEY'),
           'anthropic':('https://api.anthropic.com/v1/messages','ANTHROPIC_API_KEY')}
MAX_RESPONSE_BYTES=2*1024*1024
MAX_OUTPUT_TOKENS=4096
MAX_PROJECT_MODEL_REQUESTS=32


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Provider redirects are forbidden')


def _request(provider,model,prompt,timeout,max_output_tokens=None):
    if provider not in PROVIDERS:raise ValueError('Unknown API provider')
    if not isinstance(model,str) or not model.strip() or len(model)>200:raise ValueError('API steps require an explicit model identifier')
    if len(prompt.encode())>MAX_TEXT:raise ValueError('Prompt budget exceeded')
    ceiling=_ceiling(max_output_tokens)
    url,variable=PROVIDERS[provider];key=os.environ.get(variable)
    if not key:raise ValueError('Configure '+variable+' locally; never put its value in a plan')
    if provider=='openai':
        payload={'model':model,'input':prompt,'tools':[],'max_output_tokens':ceiling,'store':False,
                 'text':{'format':{'type':'json_schema','name':'crewloom_artifacts','strict':True,'schema':SCHEMA}}}
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    else:
        payload={'model':model,'max_tokens':ceiling,'tools':[],
                 'messages':[{'role':'user','content':prompt+'\nReturn only valid JSON matching this schema: '+json.dumps(SCHEMA)}]}
        headers={'x-api-key':key,'anthropic-version':'2023-06-01','Content-Type':'application/json'}
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
    # Explicit fixed HTTPS endpoints, no redirects or implicit proxy credential routing.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(req,timeout=timeout) as response:
            raw=response.read(MAX_RESPONSE_BYTES+1)
    except urllib.error.HTTPError as exc:
        raise ValueError('Provider rejected generation (HTTP '+str(exc.code)+'); response body withheld') from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ValueError('Provider connection failed; no automatic retry or host fallback') from None
    if len(raw)>MAX_RESPONSE_BYTES:raise ValueError('Provider response budget exceeded')
    return json.loads(raw)


def _ceiling(requested):
    """The output-token bound sent to the provider: the adapter maximum, tightened (never raised) by a request bound."""
    if requested is None:return MAX_OUTPUT_TOKENS
    if type(requested) is not int or not 1<=requested<=MAX_OUTPUT_TOKENS:raise ValueError('Output token ceiling must be an integer from 1 to '+str(MAX_OUTPUT_TOKENS))
    return requested


def _worker(provider,model,prompt,timeout,connection,max_output_tokens=None):
    try:
        value={'response':_request(provider,model,prompt,timeout,max_output_tokens)}
    except Exception as exc:
        value={'error':str(exc) if type(exc) is ValueError else 'Provider RPC failed; response/configuration withheld'}
    try:connection.send_bytes(json.dumps(value).encode())
    finally:connection.close()


def request(provider,model,prompt,timeout,max_output_tokens=None):
    if type(timeout) is not int or not 1<=timeout<=3600:raise ValueError('Provider timeout must be from 1 to 3600')
    if provider not in PROVIDERS:raise ValueError('Unknown API provider')
    if not model:raise ValueError('API steps require an explicit model identifier')
    _ceiling(max_output_tokens)
    if not os.environ.get(PROVIDERS[provider][1]):raise ValueError('Configure '+PROVIDERS[provider][1]+' locally')
    context=multiprocessing.get_context('spawn')
    receive,send=context.Pipe(duplex=False)
    process=context.Process(target=_worker,args=(provider,model,prompt,timeout,send,max_output_tokens))
    process.start();send.close()
    try:
        from model_host import _track_owned
        _track_owned('process',process.pid,process.pid)
        if not receive.poll(timeout):raise ValueError('Provider wall-time budget exhausted')
        value=json.loads(receive.recv_bytes(MAX_RESPONSE_BYTES+65536))
        if 'error' in value:raise ValueError(value['error'])
        return value['response']
    finally:
        try:
            from model_host import _untrack_owned
            _untrack_owned('process',process.pid)
        except Exception:pass
        if process.is_alive():process.terminate()
        process.join(timeout=2)
        if process.is_alive():process.kill();process.join(timeout=2)
        receive.close()


def parse(provider,value,outputs,max_output_tokens=None):
    if not isinstance(value,dict):raise ValueError('Malformed provider response')
    text=[]
    if provider=='openai':
        if value.get('status')!='completed':raise ValueError('Provider generation is incomplete')
        for item in value.get('output',[]):
            if item.get('type')=='reasoning':continue
            if item.get('type')!='message':raise ValueError('Provider tool/call output is forbidden')
            for content in item.get('content',[]):
                if content.get('type')!='output_text':raise ValueError('Provider refused or returned unsupported content')
                text.append(content['text'])
    else:
        if value.get('stop_reason')!='end_turn':raise ValueError('Provider generation is incomplete or attempted a tool')
        for block in value.get('content',[]):
            if block.get('type')!='text':raise ValueError('Provider tool/call output is forbidden')
            text.append(block['text'])
    artifacts=validate_artifacts(json.loads(''.join(text)),outputs)
    return artifacts,{'provider':provider,'model_reported':value.get('model'),'usage':value.get('usage',{}),
                      'max_output_tokens':_ceiling(max_output_tokens),'execution_boundary':'tool-free provider RPC; brokered artifacts'}


def generate(provider,prompt,outputs,timeout,model,max_output_tokens=None):
    return parse(provider,request(provider,model,prompt,timeout,max_output_tokens),outputs,max_output_tokens)

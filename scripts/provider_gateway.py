"""Trusted model RPC without filesystem, shell, browser or delegated-agent tools."""
import json
import os
import multiprocessing
import urllib.error
import urllib.request
from model_host import MAX_TEXT, SCHEMA, validate_artifacts

PROVIDERS={'openai':('https://api.openai.com/v1/responses','OPENAI_API_KEY'),
           'anthropic':('https://api.anthropic.com/v1/messages','ANTHROPIC_API_KEY'),
           'ollama':('http://127.0.0.1:11434/api/chat','OLLAMA_ENDPOINT'),
           'vllm':('http://127.0.0.1:8000/v1/chat/completions','VLLM_ENDPOINT')}
LOCAL_PROVIDERS=('ollama','vllm')
MAX_RESPONSE_BYTES=2*1024*1024
MAX_OUTPUT_TOKENS=4096
MAX_PROJECT_MODEL_REQUESTS=32


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Provider redirects are forbidden')


def _resolve_endpoint(provider):
    default_url,env_var=PROVIDERS[provider]
    url_str=os.environ.get(env_var,default_url) if provider in LOCAL_PROVIDERS else default_url
    if provider in LOCAL_PROVIDERS:
        from urllib.parse import urlsplit
        url=urlsplit(url_str)
        if (url.scheme not in ('http','https') or url.hostname not in ('localhost','127.0.0.1','::1')
                or url.username is not None or url.password is not None or url.query or url.fragment
                or any(char.isspace() for char in url_str)):
            raise ValueError('Local provider must use a loopback URL without credentials or query')
        if url.port is None or url.port==0:
            raise ValueError('Local provider requires an explicit port')
    return url_str


def _request(provider,model,prompt,timeout):
    if provider not in PROVIDERS:raise ValueError('Unknown API provider')
    if not isinstance(model,str) or not model.strip() or len(model)>200:raise ValueError('API steps require an explicit model identifier')
    if len(prompt.encode())>MAX_TEXT:raise ValueError('Prompt budget exceeded')
    url=_resolve_endpoint(provider)
    _,variable=PROVIDERS[provider]
    key=os.environ.get(variable)
    if provider not in LOCAL_PROVIDERS and not key:
        raise ValueError('Configure '+variable+' locally; never put its value in a plan')
    if provider=='openai':
        payload={'model':model,'input':prompt,'tools':[],'max_output_tokens':MAX_OUTPUT_TOKENS,'store':False,
                 'text':{'format':{'type':'json_schema','name':'crewloom_artifacts','strict':True,'schema':SCHEMA}}}
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    elif provider=='anthropic':
        payload={'model':model,'max_tokens':MAX_OUTPUT_TOKENS,'tools':[],
                 'messages':[{'role':'user','content':prompt+'\nReturn only valid JSON matching this schema: '+json.dumps(SCHEMA)}]}
        headers={'x-api-key':key,'anthropic-version':'2023-06-01','Content-Type':'application/json'}
    elif provider=='ollama':
        payload={'model':model,'messages':[{'role':'user','content':prompt+'\nReturn only valid JSON matching this schema: '+json.dumps(SCHEMA)}],
                 'stream':False,'format':'json','options':{'num_predict':MAX_OUTPUT_TOKENS}}
        headers={'Content-Type':'application/json'}
    else: # vllm
        payload={'model':model,'messages':[{'role':'user','content':prompt+'\nReturn only valid JSON matching this schema: '+json.dumps(SCHEMA)}],
                 'max_tokens':MAX_OUTPUT_TOKENS,'temperature':0.0,'response_format':{'type':'json_object'}}
        headers={'Content-Type':'application/json'}
        if os.environ.get('VLLM_API_KEY'):headers['Authorization']='Bearer '+os.environ['VLLM_API_KEY']
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
    # Explicit fixed HTTPS or loopback endpoints, no redirects or implicit proxy credential routing.
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


def _worker(provider,model,prompt,timeout,connection):
    try:
        value={'response':_request(provider,model,prompt,timeout)}
    except Exception as exc:
        value={'error':str(exc) if type(exc) is ValueError else 'Provider RPC failed; response/configuration withheld'}
    try:connection.send_bytes(json.dumps(value).encode())
    finally:connection.close()


def request(provider,model,prompt,timeout):
    if type(timeout) is not int or not 1<=timeout<=3600:raise ValueError('Provider timeout must be from 1 to 3600')
    if provider not in PROVIDERS:raise ValueError('Unknown API provider')
    if not model:raise ValueError('API steps require an explicit model identifier')
    if provider not in LOCAL_PROVIDERS and not os.environ.get(PROVIDERS[provider][1]):
        raise ValueError('Configure '+PROVIDERS[provider][1]+' locally')
    context=multiprocessing.get_context('spawn')
    receive,send=context.Pipe(duplex=False)
    process=context.Process(target=_worker,args=(provider,model,prompt,timeout,send))
    process.start();send.close()
    try:
        if not receive.poll(timeout):raise ValueError('Provider wall-time budget exhausted')
        value=json.loads(receive.recv_bytes(MAX_RESPONSE_BYTES+65536))
        if 'error' in value:raise ValueError(value['error'])
        return value['response']
    finally:
        if process.is_alive():process.terminate()
        process.join(timeout=2)
        if process.is_alive():process.kill();process.join(timeout=2)
        receive.close()


def parse(provider,value,outputs):
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
        usage=value.get('usage',{})
    elif provider=='anthropic':
        if value.get('stop_reason')!='end_turn':raise ValueError('Provider generation is incomplete or attempted a tool')
        for block in value.get('content',[]):
            if block.get('type')!='text':raise ValueError('Provider tool/call output is forbidden')
            text.append(block['text'])
        usage=value.get('usage',{})
    elif provider=='ollama':
        if not value.get('done',False):raise ValueError('Ollama generation is incomplete')
        message=value.get('message',{})
        if message.get('role')!='assistant' or not message.get('content'):
            raise ValueError('Ollama returned invalid message payload')
        text.append(message['content'])
        prompt_eval=value.get('prompt_eval_count',0);eval_count=value.get('eval_count',0)
        usage={'input_tokens':prompt_eval,'output_tokens':eval_count,'total_tokens':prompt_eval+eval_count}
    elif provider=='vllm':
        choices=value.get('choices',[])
        if not choices or not isinstance(choices,list):raise ValueError('vLLM returned empty choices')
        choice=choices[0]
        if choice.get('finish_reason') not in ('stop','length'):
            raise ValueError('vLLM generation incomplete or rejected')
        message=choice.get('message',{})
        content=message.get('content')
        if not content:raise ValueError('vLLM returned empty message content')
        text.append(content)
        usage=value.get('usage',{})
    else:
        raise ValueError('Unknown provider: '+str(provider))
    raw=''.join(text).strip()
    if raw.startswith('```json') and raw.endswith('```'):raw=raw[7:-3].strip()
    elif raw.startswith('```') and raw.endswith('```'):raw=raw[3:-3].strip()
    artifacts=validate_artifacts(json.loads(raw),outputs)
    return artifacts,{'provider':provider,'model_reported':value.get('model'),'usage':usage,
                      'max_output_tokens':MAX_OUTPUT_TOKENS,'execution_boundary':'tool-free provider RPC; brokered artifacts'}


def generate(provider,prompt,outputs,timeout,model):
    return parse(provider,request(provider,model,prompt,timeout),outputs)

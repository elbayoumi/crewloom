"""Trusted model RPC without filesystem, shell, browser or delegated-agent tools.

Provides hardened HTTP clients for cloud and local model providers:
- OpenAI (/v1/responses)
- Anthropic (/v1/messages)
- Ollama (/api/chat)
- vLLM (/v1/chat/completions)

Adheres strictly to the Python standard library with zero external dependencies.
"""

from __future__ import annotations

import ipaddress
import http.client
import socket
import json
import multiprocessing
import multiprocessing.connection
import os
import re
from typing import Any, Dict, List, Sequence, Tuple
import urllib.error
from urllib.parse import urlsplit, urlunsplit
import urllib.request

from model_host import MAX_TEXT, SCHEMA, validate_artifacts

PROVIDERS: Dict[str, Tuple[str, str]] = {
    'openai': ('https://api.openai.com/v1/responses', 'OPENAI_API_KEY'),
    'anthropic': ('https://api.anthropic.com/v1/messages', 'ANTHROPIC_API_KEY'),
    'ollama': ('http://127.0.0.1:11434/api/chat', 'OLLAMA_ENDPOINT'),
    'vllm': ('http://127.0.0.1:8000/v1/chat/completions', 'VLLM_ENDPOINT'),
}
LOCAL_PROVIDERS: Tuple[str, ...] = ('ollama', 'vllm')
MAX_RESPONSE_BYTES: int = 2 * 1024 * 1024
DEFAULT_MAX_OUTPUT_TOKENS: int = 4096
MAX_OUTPUT_TOKENS_CEILING: int = 32768
MAX_PROJECT_MODEL_REQUESTS: int = 32


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Enforce strict refusal of HTTP redirects to prevent SSRF and credential leaks."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> Any:
        raise ValueError('Provider redirects are forbidden')


ALLOWED_LOCAL_NETWORKS: Tuple[Any, ...] = (
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
)


def _is_ip_allowed(ip: Any) -> bool:
    """Verify that an IP address is within permitted loopback or RFC 1918 / ULA CIDRs."""
    return any(ip in network for network in ALLOWED_LOCAL_NETWORKS)


def _validate_local_endpoint_host(hostname: str) -> Tuple[str, ...]:
    """Validate that hostname resolves strictly to approved loopback or RFC 1918 CIDRs."""
    if not hostname:
        raise ValueError('Local provider hostname cannot be empty')

    # Try parsing directly as an IP literal first
    try:
        ip = ipaddress.ip_address(hostname)
        if not _is_ip_allowed(ip):
            raise ValueError(
                f'Local provider address {hostname} is outside allowed loopback and RFC 1918 CIDRs'
            )
        return (str(ip),)
    except ValueError as exc:
        if 'outside allowed loopback' in str(exc):
            raise

    # Return the validated addresses so transport can connect without resolving again.
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f'Failed to resolve local provider hostname {hostname!r}: {exc}') from None

    if not addr_info:
        raise ValueError(f'Local provider hostname {hostname!r} resolved to no addresses')

    for _family, _socktype, _proto, _canonname, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f'Invalid resolved IP address {ip_str!r} for {hostname!r}') from None
        if not _is_ip_allowed(ip):
            raise ValueError(
                f'Local provider hostname {hostname!r} resolved to {ip_str}, which is outside allowed CIDRs'
            )

    return tuple(dict.fromkeys(info[4][0] for info in addr_info))

def _resolve_endpoint(provider: str, *, validate_host: bool = True) -> str:
    """Resolve and validate the provider API endpoint."""
    default_url, env_var = PROVIDERS[provider]
    url_str = os.environ.get(env_var, default_url) if provider in LOCAL_PROVIDERS else default_url

    if provider in LOCAL_PROVIDERS:
        url = urlsplit(url_str)
        if (
            url.scheme not in ('http', 'https')
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(char.isspace() for char in url_str)
        ):
            raise ValueError('Local provider must use a valid loopback or private network URL without credentials or query')

        if url.port is None or url.port == 0:
            raise ValueError('Local provider requires an explicit port')

        allow_remote = os.environ.get('CREWLOOM_ALLOW_REMOTE_GATEWAY') == '1'
        if not allow_remote and validate_host:
            _validate_local_endpoint_host(url.hostname or '')

        path = url.path.rstrip('/')
        if provider == 'ollama':
            if not path:
                path = '/api/chat'
            elif not path.endswith('/api/chat'):
                path = path + '/api/chat'
        elif provider == 'vllm':
            if not path:
                path = '/v1/chat/completions'
            elif path.endswith('/v1'):
                path = path + '/chat/completions'
            elif not path.endswith('/chat/completions'):
                path = path + '/chat/completions'

        url_str = urlunsplit((url.scheme, url.netloc, path, '', ''))

    return url_str



def _pinned_local_handlers(url: str) -> List[Any]:
    """Keep URL host/SNI/certificate checks while connecting only to validated IPs."""
    addresses = _validate_local_endpoint_host(urlsplit(url).hostname or '')

    def connect(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
        last_error = None
        for ip in addresses:
            family = socket.AF_INET6 if ipaddress.ip_address(ip).version == 6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            try:
                if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)
                if source_address:
                    sock.bind(source_address)
                # Numeric sockaddr: no second DNS lookup, including during TLS setup.
                sock.connect((ip, address[1]))
                return sock
            except OSError as exc:
                last_error = exc
                sock.close()
        raise last_error or OSError('No validated local provider addresses')

    def factory(connection_type):
        def create(host, **kwargs):
            connection = connection_type(host, **kwargs)
            connection._create_connection = connect
            return connection
        return create

    class HTTP(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(factory(http.client.HTTPConnection), req)

    class HTTPS(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(factory(http.client.HTTPSConnection), req,
                                context=self._context)

    return [HTTP(), HTTPS()]

def _max_output_tokens() -> int:
    """Retrieve effective max output tokens, allowing configuration up to ceiling."""
    configured = os.environ.get('CREWLOOM_MAX_OUTPUT_TOKENS', '').strip()
    if configured and configured.isdigit():
        return min(MAX_OUTPUT_TOKENS_CEILING, max(512, int(configured)))
    return DEFAULT_MAX_OUTPUT_TOKENS


# Backwards compatibility alias
MAX_OUTPUT_TOKENS = DEFAULT_MAX_OUTPUT_TOKENS


def _request(provider: str, model: str, prompt: str, timeout: int) -> Dict[str, Any]:
    """Execute raw HTTP RPC request to model provider with strict timeout."""
    if provider not in PROVIDERS:
        raise ValueError('Unknown API provider')
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise ValueError('API steps require an explicit model identifier')
    if len(prompt.encode('utf-8')) > MAX_TEXT:
        raise ValueError('Prompt budget exceeded')

    url = _resolve_endpoint(provider, validate_host=False)
    _, variable = PROVIDERS[provider]
    key = os.environ.get(variable)
    if provider not in LOCAL_PROVIDERS and not key:
        raise ValueError(f'Configure {variable} locally; never put its value in a plan')

    effective_max_tokens = _max_output_tokens()

    if provider == 'openai':
        payload = {
            'model': model,
            'input': prompt,
            'tools': [],
            'max_output_tokens': effective_max_tokens,
            'store': False,
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': 'crewloom_artifacts',
                    'strict': True,
                    'schema': SCHEMA,
                }
            },
        }
        headers = {
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
        }
    elif provider == 'anthropic':
        payload = {
            'model': model,
            'max_tokens': effective_max_tokens,
            'tools': [],
            'messages': [
                {
                    'role': 'user',
                    'content': prompt + '\nReturn only valid JSON matching this schema: ' + json.dumps(SCHEMA),
                }
            ],
        }
        headers = {
            'x-api-key': key or '',
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json',
        }
    elif provider == 'ollama':
        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt + '\nReturn only valid JSON matching this schema: ' + json.dumps(SCHEMA),
                }
            ],
            'stream': False,
            'format': 'json',
            'options': {'num_predict': effective_max_tokens},
        }
        headers = {'Content-Type': 'application/json'}
    else:  # vllm
        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt + '\nReturn only valid JSON matching this schema: ' + json.dumps(SCHEMA),
                }
            ],
            'max_tokens': effective_max_tokens,
            'temperature': 0.0,
            'response_format': {'type': 'json_object'},
        }
        headers = {'Content-Type': 'application/json'}
        if os.environ.get('VLLM_API_KEY'):
            headers['Authorization'] = f'Bearer {os.environ["VLLM_API_KEY"]}'

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST',
    )

    restricted_local = provider in LOCAL_PROVIDERS and os.environ.get('CREWLOOM_ALLOW_REMOTE_GATEWAY') != '1'
    handlers = _pinned_local_handlers(url) if restricted_local else []
    # A proxy could resolve or forward the original hostname outside the pinned boundary.
    trust_proxies = not restricted_local and os.environ.get('CREWLOOM_TRUST_SYSTEM_PROXIES') == '1'
    proxy_handler = urllib.request.ProxyHandler() if trust_proxies else urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler, NoRedirect(), *handlers)

    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Provider rejected generation (HTTP {exc.code}); response body withheld') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('Provider connection failed; no automatic retry or host fallback') from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('Provider response budget exceeded')

    return json.loads(raw.decode('utf-8'))


def _worker(
    provider: str,
    model: str,
    prompt: str,
    timeout: int,
    connection: multiprocessing.connection.Connection,
) -> None:
    """Subprocess target executing the provider request within isolated memory."""
    try:
        value = {'response': _request(provider, model, prompt, timeout)}
    except Exception as exc:
        value = {
            'error': str(exc) if isinstance(exc, ValueError) else 'Provider RPC failed; response/configuration withheld'
        }
    try:
        connection.send_bytes(json.dumps(value).encode('utf-8'))
    finally:
        connection.close()


def request(provider: str, model: str, prompt: str, timeout: int) -> Dict[str, Any]:
    """Execute model request within a spawned worker process enforcing strict timeout."""
    if not isinstance(timeout, int) or not (1 <= timeout <= 3600):
        raise ValueError('Provider timeout must be from 1 to 3600')
    if provider not in PROVIDERS:
        raise ValueError('Unknown API provider')
    if not model:
        raise ValueError('API steps require an explicit model identifier')
    if provider not in LOCAL_PROVIDERS and not os.environ.get(PROVIDERS[provider][1]):
        raise ValueError(f'Configure {PROVIDERS[provider][1]} locally')

    context = multiprocessing.get_context('spawn')
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(provider, model, prompt, timeout, send))
    process.start()
    send.close()

    try:
        if not receive.poll(timeout):
            raise ValueError('Provider wall-time budget exhausted')
        value = json.loads(receive.recv_bytes(MAX_RESPONSE_BYTES + 65536).decode('utf-8'))
        if 'error' in value:
            raise ValueError(value['error'])
        return value['response']
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        receive.close()


def parse(
    provider: str,
    value: Dict[str, Any],
    outputs: Sequence[str],
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Parse and validate model response into certified project artifacts."""
    if not isinstance(value, dict):
        raise ValueError('Malformed provider response')

    text: List[str] = []
    if provider == 'openai':
        if value.get('status') != 'completed':
            raise ValueError('Provider generation is incomplete')
        for item in value.get('output', []):
            if item.get('type') == 'reasoning':
                continue
            if item.get('type') != 'message':
                raise ValueError('Provider tool/call output is forbidden')
            for content in item.get('content', []):
                if content.get('type') != 'output_text':
                    raise ValueError('Provider refused or returned unsupported content')
                text.append(content['text'])
        usage = value.get('usage', {})
    elif provider == 'anthropic':
        if value.get('stop_reason') != 'end_turn':
            raise ValueError('Provider generation is incomplete or attempted a tool')
        for block in value.get('content', []):
            if block.get('type') != 'text':
                raise ValueError('Provider tool/call output is forbidden')
            text.append(block['text'])
        usage = value.get('usage', {})
    elif provider == 'ollama':
        if not value.get('done', False):
            raise ValueError('Ollama generation is incomplete')
        message = value.get('message', {})
        if message.get('role') != 'assistant' or not message.get('content'):
            raise ValueError('Ollama returned invalid message payload')
        text.append(message['content'])
        prompt_eval = value.get('prompt_eval_count', 0)
        eval_count = value.get('eval_count', 0)
        usage = {
            'input_tokens': prompt_eval,
            'output_tokens': eval_count,
            'total_tokens': prompt_eval + eval_count,
        }
    elif provider == 'vllm':
        choices = value.get('choices', [])
        if not choices or not isinstance(choices, list):
            raise ValueError('vLLM returned empty choices')
        choice = choices[0]
        if choice.get('finish_reason') not in ('stop', 'length'):
            raise ValueError('vLLM generation incomplete or rejected')
        message = choice.get('message', {})
        content = message.get('content')
        if not content:
            raise ValueError('vLLM returned empty message content')
        text.append(content)
        raw_usage = value.get('usage') or {}
        prompt_tokens = raw_usage.get('prompt_tokens', 0)
        completion_tokens = raw_usage.get('completion_tokens', 0)
        total_tokens = raw_usage.get('total_tokens', prompt_tokens + completion_tokens)
        usage = {
            'input_tokens': prompt_tokens,
            'output_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
        }
    raw = ''.join(text).strip()

    # Cleanly strip only a leading model reasoning block outside the JSON payload
    if raw.startswith('<think>'):
        end_idx = raw.find('</think>')
        if end_idx != -1:
            raw = raw[end_idx + len('</think>'):].strip()

    # Strip markdown code fences if present
    if raw.startswith('```json') and raw.endswith('```'):
        raw = raw[7:-3].strip()
    elif raw.startswith('```') and raw.endswith('```'):
        raw = raw[3:-3].strip()

    artifacts = validate_artifacts(json.loads(raw), outputs)
    return artifacts, {
        'provider': provider,
        'model_reported': value.get('model'),
        'usage': usage,
        'max_output_tokens': _max_output_tokens(),
        'execution_boundary': 'tool-free provider RPC; brokered artifacts',
    }


def generate(
    provider: str,
    prompt: str,
    outputs: Sequence[str],
    timeout: int,
    model: str,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Synchronously request, validate, and parse model generation into artifacts."""
    return parse(provider, request(provider, model, prompt, timeout), outputs)

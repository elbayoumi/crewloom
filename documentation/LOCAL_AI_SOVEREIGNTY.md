# Local AI Sovereignty Guide

Crewloom provides **complete data and computation sovereignty**, allowing you to execute multi-agent software engineering workflows 100% offline with zero data leaving your machine or private VPC.

---

## Why Local AI Sovereignty Matters

Enterprise software engineering requires strict control over intellectual property and confidential data. Cloud-based LLM APIs present fundamental risks:

1. **Code Exfiltration**: Proprietary source code and architecture documents are sent over public networks to third-party model providers.
2. **Telemetry & Log Retention**: Model vendors may log prompts, system instructions, and completion history for training or moderation.
3. **Regulatory Non-Compliance**: GDPR, HIPAA, SOC 2, and defense regulations often forbid transmitting unencrypted source code outside designated geographic or organizational boundaries.
4. **API Outages & Vendor Lock-In**: Cloud outages halt developer velocity, and sudden pricing or model deprecations disrupt workflows.

With Crewloom's **native loopback provider gateway**, you can run all 44 specialist agent roles entirely on local open-weights models using **Ollama** or **vLLM** with zero external pip dependencies.

---

## Supported Local Model Runtimes

| Runtime | Protocol | Default Endpoint | Key Advantage |
|---|---|---|---|
| **Ollama** | Native REST `/api/chat` | `http://127.0.0.1:11434` | Zero-configuration setup, CPU/Apple Silicon/GPU support, one-line model pull |
| **vLLM** | OpenAI-Compatible `/v1/chat/completions` | `http://127.0.0.1:8000` | High-throughput PagedAttention, multi-GPU tensor parallelism, continuous batching |

---

## Recommended Open-Weights Models

Crewloom has been benchmarked and verified with the following open-weights models:

### 1. Code Generation & Architecture
- **Qwen 2.5 Coder (32B / 14B / 7B)**: Exceptional Python, TypeScript, and Go code generation; adheres strictly to multi-step execution plans.
- **DeepSeek Coder V2 (Lite / 236B)**: Superior algorithmic reasoning, repository map comprehension, and unit test synthesis.

### 2. Deep Reasoning & Contract Verification
- **DeepSeek R1**: Chain-of-thought verification for safety audits, formal contracts, and complex edge-case exploration.

### 3. General Orchestration & Review
- **Llama 3.3 (70B Instruct)**: High instruction fidelity for role routing, workflow milestone tracking, and bilingual Arabic/English documentation.
- **Mistral Small 24B**: Balanced footprint and fast inference for low-latency developer loops.

---

## Quickstart: Running 100% Local with Ollama

### Step 1: Install & Start Ollama

Download and install Ollama from [ollama.com](https://ollama.com):

```bash
# Pull the recommended coding model
ollama pull qwen2.5-coder:14b

# Ollama automatically listens on loopback: http://127.0.0.1:11434
```

### Step 2: Configure Workflow Plan for Ollama

No API key is required. In your workflow plan JSON (or `workflows/*.json`), declare `"host": "ollama"` and your desired model for any model-generation steps:

```json
{
  "id": "implement-algorithm",
  "role": "backend-developer",
  "host": "ollama",
  "model": "qwen2.5-coder:14b",
  "inputs": {"spec": "requirements.md"},
  "outputs": {"code": "solution.py"}
}
```

If your Ollama instance runs on a custom loopback port or host, set the endpoint environment variable (the gateway automatically appends `/api/chat` if omitted):

```bash
export OLLAMA_ENDPOINT=http://127.0.0.1:11434
```

### Step 3: Run Workflow

```bash
# Verify system readiness
python3 scripts/crewloom.py workflow doctor

# Execute workflow against your local Ollama runtime
python3 scripts/crewloom.py workflow run --project ./my-app --plan workflows/my-plan.json
```

All 44 agent roles, memory queries, and contract verifications will execute against your local Ollama instance with zero outbound internet traffic.

---

## Quickstart: High-Throughput Production with vLLM

For multi-GPU servers or enterprise on-prem clusters:

### Step 1: Launch vLLM Server

```bash
python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-Coder-32B-Instruct \
    --host 127.0.0.1 \
    --port 8000 \
    --tensor-parallel-size 2 \
    --max-model-len 32768
```

### Step 2: Configure Workflow Plan for vLLM

In your workflow plan JSON, declare `"host": "vllm"` and your model identifier:

```json
{
  "id": "synthesize-architecture",
  "role": "distributed-systems-architect",
  "host": "vllm",
  "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
  "inputs": {"spec": "requirements.md"},
  "outputs": {"architecture": "system_design.md"}
}
```

If using a custom loopback port or host, specify `VLLM_ENDPOINT` (the gateway automatically appends `/chat/completions` or `/v1/chat/completions` if omitted):

```bash
export VLLM_ENDPOINT=http://127.0.0.1:8000/v1
```

---

## Local & Private Network Security Enforcement

Crewloom's provider gateway validates local endpoints to prevent Server-Side Request Forgery (SSRF) and DNS rebinding attacks while supporting dedicated GPU servers on private networks:

1. **Loopback & Private Network (LAN) Default**: Endpoint hosts must resolve to loopback (`127.0.0.1`, `localhost`, `::1`) or private RFC 1918 / mDNS networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `.local`, `.internal`, `.lan`).
2. **Dedicated LAN GPU Clusters**: Teams hosting Ollama or vLLM on dedicated LAN servers (e.g. `http://192.168.1.100:11434` or Kubernetes service `http://ollama-service.internal:11434`) are supported out of the box.
3. **Explicit Port Required**: Endpoints must declare an explicit non-zero port (e.g. `:11434` or `:8000`).
4. **No Embedded Credentials or Queries**: Endpoints containing userinfo (`http://user:pass@...`) or query parameters are immediately rejected.
5. **No External Redirects**: HTTP redirect status codes (301, 302, 307, 308) are rejected to prevent redirecting local RPC to public hosts.
6. **Fence & Reasoning-Stripping Robustness**: Automatically strips markdown code fences (````json````) and DeepSeek R1 reasoning tags (`<think>...</think>`) before parsing JSON artifacts.
7. **Remote Gateway Opt-In**: To reach an external gateway outside private networks, set `CREWLOOM_ALLOW_REMOTE_GATEWAY=1`.
8. **Corporate Proxy Compatibility**: To route requests through corporate proxies, set `CREWLOOM_TRUST_SYSTEM_PROXIES=1`.

---

## Offline Verification Checklist

To prove complete offline sovereignty:

```bash
# 1. Unplug Ethernet or disconnect Wi-Fi
# 2. Run repository checks and local test suite
python3 scripts/check_repository.py

# 3. Verify zero outbound sockets while running:
# On macOS:
netstat -an | grep ESTABLISHED
# On Linux:
ss -tunap | grep ESTABLISHED
```

You have complete independence: no tokens counted by third parties, no credit card billing, and 100% intellectual property containment.

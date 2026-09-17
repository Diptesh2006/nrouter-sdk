# nRouter Pure-Curl Health Checks

This directory contains modular, grouped pure-curl health checks for nRouter (`https://api.nrouter.ai/v1`).

By testing using raw `curl` requests rather than language-specific SDKs, these health checks continuously verify the true wire contract, edge WAF, response headers, and upstream provider connectivity with zero SDK bias.

## Grouped Health Checks

| Check Group | Script | Focus / Description |
|---|---|---|
| **Consolidated Suite** | [`run_all.sh`](run_all.sh) / [`run_all.py`](run_all.py) | Executes all health check groups sequentially, aggregates results, and generates a unified status report. |
| **Models & Providers** | [`model_curl.sh`](model_curl.sh) / [`model_curl.py`](model_curl.py) | Verifies `GET /v1/models` catalog, provider discovery & distribution, and live provider chat completion inference. |
| **Guardrails** | [`guardrail_curl.sh`](guardrail_curl.sh) / [`guardrail_curl.py`](guardrail_curl.py) | Verifies platform moderation floor, PII redaction, prompt injection & secret leakage detection, evasion resistance, and wire contract assertions. |

## Quickstart

### 1. Offline Self-Test (No API key needed)
```bash
# Run all health checks offline
bash scripts/curl_health_checks/run_all.sh --self-test
# or python3 scripts/curl_health_checks/run_all.py --self-test

# Individual module self-tests:
bash scripts/curl_health_checks/model_curl.sh --self-test
bash scripts/curl_health_checks/guardrail_curl.sh --self-test
```

### 2. Live Health Check
```bash
export NROUTER_API_KEY="sk-nrouter-..."

# Run all health checks live (quick or full)
bash scripts/curl_health_checks/run_all.sh --quick
bash scripts/curl_health_checks/run_all.sh

# Individual checks:
bash scripts/curl_health_checks/model_curl.sh
bash scripts/curl_health_checks/guardrail_curl.sh --quick
bash scripts/curl_health_checks/guardrail_curl.sh
```

### 3. CI / GitHub Actions Step Summary
```bash
bash scripts/curl_health_checks/run_all.sh --step-summary
```

### 4. JSON Output
```bash
python3 scripts/curl_health_checks/run_all.py --json
```


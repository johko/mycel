# Plan — Local on-device inference for Diplomat nodes

> **Update (2026-06-20).** Two structural changes landed after this plan was
> written, so adjust paths/commands when following it: (1) the agent is now an
> **MCP client** that fetches data from a connector, not a local datastore — the
> "local inference" story is unchanged (it's about *where the model runs*), but a
> local node also runs a local connector; (2) all demo assets, including
> `docker-compose.local.yml` and `devices/*.yaml`, moved under
> `src/mycel/demo/assets/` and are laid down with `mycel-demo init`. Run the
> overlay from a scaffolded demo directory.

**Branch:** `local-llm`
**Goal:** let a Diplomat node run its LLM on *local hardware* instead of the Hugging Face router, so sensitive data is processed entirely on-device — the privacy endgame of the federated framing. Hardware/runtime is declared in a loosely-specified file, and the node picks/configures a model accordingly.
**First milestone:** run **one** node in Docker (like the others) but powered by a **local model on this laptop's CPU**, via an Ollama container — model `qwen2.5:3b-instruct`.

**End vision — deployment templates.** The backend is config-driven so the same node codebase can be shipped as a set of Docker **templates** for different target systems:

| Template | Inference backend | For |
|---|---|---|
| **cloud** | HF router / hosted API (current default) | managed, no local GPU |
| **on-prem** | self-hosted GPU server (e.g. vLLM) | data-center, owns hardware |
| **open-source / edge** | **Ollama container, local CPU/GPU** ← *milestone 1* | laptops, on-device, air-gapped |

Each template = a compose file + a backend/device profile; the node code is identical. Milestone 1 builds the open-source/edge template concretely; the others follow the same pattern.

---

## 1. Hardware survey (this machine, measured)

| Resource | Finding | Implication |
|---|---|---|
| CPU | Intel Core Ultra 7 155U (Meteor Lake), 14 logical CPUs | Capable CPU inference of small models |
| RAM | ~19 GB in WSL2 (host 20 GB), ~15 GB free | Fits a 3B–7B model quantized; not a 13B+ |
| GPU | Arc iGPU present on host, **but `/dev/dri` absent in WSL2** | **No GPU acceleration** without a heavy Intel WSL stack |
| NPU | Intel AI Boost present on host, **`/dev/accel` absent in WSL2** | NPU not usable from WSL today |
| Disk | 905 GB free | Model weights are a non-issue |
| Tooling | **Ollama 0.13.0 installed & running** (`:11434`, OpenAI `/v1` live), `uv`, Python 3.12 | Inference server already in place |

**The decisive constraint: this is CPU-only inference inside WSL2.** The iGPU/NPU are not passed through. Exposing them would require Intel's `level-zero` + IPEX-LLM stack and a kernel with the right dxg/compute support — fragile and out of scope for the first milestone. We design for CPU now and leave an explicit upgrade path (§9).

---

## 2. Framework choice — Ollama

**Recommendation: Ollama**, for the first milestone.

Why it fits:
- **Already installed and running** here — zero setup cost.
- Exposes an **OpenAI-compatible** `/v1/chat/completions` endpoint **with tool/function calling**, which is exactly what mycel's agent loop and planner need (the agent calls `list_records`/`get_record`; the planner/extractor use forced tool calls).
- Single resident model serves all requests — so even when several nodes go local later, they can share one loaded model in RAM rather than each loading its own.
- Trivial model management (`ollama pull`), good GGUF/quantization defaults.

Alternatives considered (and why not now):
- **llama.cpp (`llama-server`)** — same engine Ollama wraps; more knobs, more manual setup. Reach for it only if we need finer control (specific quant, grammar-constrained tool output).
- **vLLM (CPU)** — built for GPU throughput; CPU mode is not the sweet spot and setup is heavier.
- **IPEX-LLM (Intel)** — the route to actually using the Arc iGPU/NPU. Powerful but fragile under WSL; deferred to §9.

---

## 3. Model choice — must be tool-calling capable

The hard requirement is **reliable function calling**, because the Diplomat agent is a tool-use loop and the node also does structured fact extraction (forced `submit_facts`). Small models are the weak point here, so model selection prioritizes tool-calling quality, then speed, then size.

Note the contrast with today's default (`moonshotai/Kimi-K2-Instruct`, a very large hosted model): a local 3B–7B will produce malformed tool calls more often. The codebase already retries (`planner._MAX_ATTEMPTS`, agent robustness, extraction attempts), which absorbs some of this; prompts may need tightening for small models (§6e).

| Role | Model | Quant / size | Why |
|---|---|---|---|
| **Primary (quality)** | `qwen2.5:7b-instruct` | Q4_K_M, ~4.7 GB | Best small-model tool-calling reputation; fits RAM with headroom |
| **Fast (dev/iteration)** | `qwen2.5:3b-instruct` | Q4_K_M, ~2 GB | Snappy multi-call loops; good enough tool calling |
| **Alternative** | `llama3.2:3b` | Q4_K_M, ~2 GB | Official Llama tool support, similar footprint |

**Rough CPU performance expectation (Meteor Lake, 14 threads):** ~5–9 tok/s for 7B Q4, ~15–25 tok/s for 3B Q4. One user query drives *several sequential* LLM calls (agent turns + extraction), so a 7B node turn may take tens of seconds. **Recommendation: develop against the 3B for fast iteration, validate quality on the 7B.** Bump to Q5/Q8 only if quality is the bottleneck and RAM allows (7B Q8 ≈ 8 GB).

This file should declare the model loosely (see §6b) so swapping is a one-line change.

---

## 4. Topology for milestone 1 (Docker, hybrid)

Everything stays in Docker, like the rest of the stack. We add an **Ollama service** (CPU) and point **one node** at it; the orchestrator and other nodes are unchanged.

```
        ORCHESTRATOR  (planner / aggregation)         ← stays on HF router
                 │
   ┌─────────────┼───────────────┬──────────────┐
   ▼             ▼               ▼              ▼
 energy        commons         archivists   ★ local-node ──▶ ollama (container, CPU)
 (HF)          (HF)            (HF)           └─ OPA sidecar      qwen2.5:3b-instruct
```

- A new **`ollama` service** (`ollama/ollama` image) serves the model on the compose network at `http://ollama:11434/v1`; weights live in a named volume; the model is pulled on first start.
- The **local node** is the same Diplomat image, configured (via a mounted device profile + env) to send `chat_completion` to the `ollama` service instead of the HF router. It still enforces its **OPA policy** — privacy = local inference *and* local egress control.
- The orchestrator's planner/synthesis/alignment stay on HF for now (responsive). A **fully-local orchestrator** is a later step (§9).
- **No host-networking hacks:** node→ollama is service-to-service inside the compose network. (Using the *host's* already-installed Ollama instead is possible via `host.docker.internal`, but the self-contained container is the template-friendly choice.)

### Template packaging

Milestone 1 ships as a compose **overlay** so the base stack is untouched:

```
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

`docker-compose.local.yml` adds the `ollama` service and overrides one node's environment to use the local backend. This overlay *is* the first deployment template; later `docker-compose.{cloud,onprem,edge}.yml` follow the same shape (swap the backend service + profile).

---

## 5. The "loosely defined hardware file"

A device-profile file describes the machine and the chosen local runtime, decoupling *node identity* (which department) from *where/how its brain runs*. Proposed `devices/<name>.yaml`:

```yaml
# devices/laptop.yaml — loose hardware + runtime declaration
name: johannes-laptop
hardware:
  cpu_threads: 14          # hints, not hard limits
  ram_gb: 19
  accelerator: none        # none | intel-gpu | cuda | metal  (informational for now)
backend:
  kind: ollama             # ollama | hf | openai-compatible
  base_url: http://localhost:11434/v1
  model: qwen2.5:3b-instruct
  # optional knobs passed through to the backend
  options:
    num_ctx: 8192
    temperature: 0.2
```

- **Loose by design:** `hardware.*` are advisory hints (could later auto-suggest a model tier), not enforced. The authoritative choice is `backend.model`.
- A node opts into a device profile; absent one, it uses the HF default (unchanged behavior).
- Future: a tiny `recommend_model(hardware)` helper that maps RAM/accelerator → a default model, so the file can say "pick something that fits" rather than naming a model.

---

## 6. Integration design

### 6a. Inference-backend abstraction (`mycel/llm.py`)

Today `get_client()` returns a single HF `AsyncInferenceClient`. Generalize to a backend resolved from config:

```python
def get_client(backend: BackendConfig | None = None) -> AsyncInferenceClient:
    if backend and backend.kind in ("ollama", "openai-compatible"):
        return AsyncInferenceClient(base_url=backend.base_url, api_key="local")
    return AsyncInferenceClient(provider=os.environ.get("HF_PROVIDER", "auto"))
```

Verified: `huggingface_hub` 1.18 `AsyncInferenceClient` accepts `base_url`, so the **existing `chat_with_retry` / `chat_completion` code path is reused unchanged** — no new dependency. The `model` passed per call becomes the Ollama model name. (Fallback if the tool-call response shape misbehaves: add the `openai` SDK for the local backend only — see the §8 spike.)

### 6b. Config plumbing

- Load the device profile (path via `DEVICE_PROFILE` env or a `--device` flag) into a `DeviceProfile`/`BackendConfig` pydantic model.
- `NodeConfig` gains an optional backend reference; when set, the node threads it into `get_client()` and uses `backend.model` instead of `config.model`.
- Orchestrator (`planner`, strategies) keep their own model resolution — only the node changes for milestone 1.

### 6c. Call sites to touch

- `node/agent.py` — `run_agent` and `extract_facts`/`build_structured_answer` (`get_client()` → backend-aware; `model=backend.model`).
- `node/config.py` / `node/main.py` — load + pass the backend.
- `llm.py` — the `get_client` change above; keep `chat_with_retry` as-is.

### 6d. Defaults & safety

- No device profile → identical current behavior (HF). The local path is strictly opt-in.
- Tool-calling and `max_tokens` already flow through `chat_completion`; confirm Ollama honors them.

### 6e. Prompt robustness for small models

Small models fumble tool calls more. Mitigations (apply only if the spike shows problems): tighten the agent/extraction system prompts, lower temperature, and lean on existing retries. Keep changes additive so HF behavior is untouched.

---

## 7. Phased steps

| Step | What | Status |
|---|---|---|
| 0 | `ollama pull qwen2.5:3b-instruct` | ✅ pulled (host + container volume) |
| 1 | **Spike** — tool-call round-trip against Ollama `/v1` (free + forced `tool_choice`) | ✅ well-formed `tool_calls`, args parse |
| 2 | `BackendConfig` (`llm.py`) + `DeviceProfile` loader (`device.py`) + `devices/local-ollama.yaml` | ✅ |
| 3 | Backend-aware `get_client(backend)` in `llm.py` | ✅ HF path unchanged; local path reaches Ollama |
| 4 | Thread backend into `NodeConfig` (via `DEVICE_PROFILE`) → `run_agent` / extraction | ✅ |
| 5 | `ollama` service + model-pull + node override in `docker-compose.local.yml` | ✅ commons-node runs on local 3B in Docker |
| 6 | End-to-end via orchestrator (HF planner) + local node | ⬜ next: full-stack demo run |
| 7 | A `make`/script target + README for the edge template | ⬜ |

**Result (milestone 1, measured 2026-06-13):** `docker compose -f docker-compose.yml -f docker-compose.local.yml up` brings up an Ollama CPU service and runs `commons-scholars` on `qwen2.5:3b-instruct`. A direct `/invoke` answered correctly (grounded in the record, structured facts extracted, oblige attribution attached); Ollama logs confirm the node container drove `/v1/chat/completions`. **Latency ≈ 94 s/query** (agent loop = ~4 sequential CPU calls; one completion ≈ 41 s) — functional but slow, the expected CPU cost. 3B tool-calling was reliable in the run.

---

## 8. Validation & spikes

- **Tool-calling round-trip (Step 1, gating):** before any plumbing, confirm Ollama + the chosen model emit well-formed `tool_calls` for our exact tool schemas via `AsyncInferenceClient(base_url=…)`. If the response shape from the HF client against Ollama is lossy, switch the local backend to the `openai` SDK. This is the single biggest risk — do it first.
- **Latency budget:** time a full `/invoke` (agent loop + extraction) on 3B vs 7B; decide the dev default.
- **Policy still holds:** the local node must produce the same OPA verdicts — run the existing node tests against it.
- **Quality:** spot-check that the local model grounds answers in records (small models hallucinate more).

---

## 9. Risks & open questions

- **Tool-calling reliability of small models** — the core risk; mitigated by the Step-1 gate, retries, and prompt tightening.
- **CPU latency** — multi-call queries are slow on 7B; 3B is the pragmatic dev default. Sets expectations for the talk demo.
- **WSL RAM pressure** — model + node + (later) orchestrator share ~19 GB; one shared Ollama model instance keeps this bounded.
- **Response-shape compatibility** between the HF client and Ollama's `/v1` — resolved by the spike (HF client vs `openai` SDK).
- **Open:** should the device profile *recommend* a model from hardware, or always name one? (Start with naming; add `recommend_model()` later.)

---

## 10. Future (beyond milestone 1)

- **Intel GPU/NPU acceleration** via IPEX-LLM / `level-zero` once WSL passthrough is sorted (or run natively on Windows) — the real speedup for this hardware.
- **More local nodes**, sharing one Ollama instance; per-device profiles for a genuinely heterogeneous federation (the FL "different devices" story).
- **Fully-local orchestrator** — planner + aggregation on a local model too, so a query never leaves the machine.
- **Per-node heterogeneity** — different nodes on different models/devices, surfaced in the registry (extends the `tags` idea) and reflected in the UI.

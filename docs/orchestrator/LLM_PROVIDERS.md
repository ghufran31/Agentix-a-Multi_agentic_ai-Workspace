# LLM provider configuration

Set credentials in the repository-root ignored `.env`. Restart the Django
server and any worker after changing a key, provider, model, fallback order,
timeout, or free-tier confirmation. The developer console's mock mode does
not contact providers.

| Provider selector | Key | Default model setting |
| --- | --- | --- |
| `groq` | `GROQ_API_KEY` | `GROQ_MODEL_NAME=openai/gpt-oss-120b` |
| `gemini` | `GOOGLE_API_KEY` | `GEMINI_MODEL_NAME=gemini-2.5-flash` |
| `openrouter` | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL_NAME=openrouter/free` when selecting the free router directly |

Generate a Gemini key in [Google AI Studio](https://aistudio.google.com/apikey)
for a Google project on the Free Tier. Paste it into `GOOGLE_API_KEY` and
set `GEMINI_FREE_TIER_CONFIRMED=true` only for that project. Google lists
Gemini 2.5 Flash on both Free and Paid tiers. The model ID alone cannot
establish the project's billing tier. See
[Google's Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash).
The factory uses the Gemini Developer API and native JSON Schema with
Pydantic validation.

## Supervisor routing

```dotenv
SUPERVISOR_LLM_PROVIDER=groq
SUPERVISOR_LLM_MODEL=openai/gpt-oss-120b
SUPERVISOR_FALLBACK_ENABLED=true
SUPERVISOR_FALLBACK_1_PROVIDER=gemini
SUPERVISOR_FALLBACK_1_MODEL=gemini-2.5-flash
SUPERVISOR_FALLBACK_2_PROVIDER=openrouter
SUPERVISOR_FALLBACK_2_MODEL=openrouter/free
```

Set `SUPERVISOR_FALLBACK_ENABLED=false` to use only the primary. Either
fallback slot can be disabled by leaving its provider blank. Change
`SUPERVISOR_LLM_PROVIDER` and `SUPERVISOR_LLM_MODEL` together to select a
different primary. `SPECIALIST_LLM_PROVIDER` and `SPECIALIST_LLM_MODEL`
remain independent, with Groq the default.

Each provider receives at most one request per planning operation. The
router advances on 429, temporary network failures, and eligible temporary
HTTP errors. Missing credentials and fallback entries that fail the
free-tier checks are skipped. OpenRouter fallback accepts `:free` model
IDs and `openrouter/free`. Gemini accepts 2.5 Flash or Flash-Lite with
free-tier confirmation. If Groq is configured as a fallback, it requires
`GROQ_FREE_TIER_CONFIRMED=true` and `openai/gpt-oss-120b`. Configure a key
from a free account when using that option. A valid provider
`Retry-After` puts that provider on cooldown in Django's cache so later
planning requests can skip it without sleeping. With the default cache,
the cooldown is local to each Django process.

Authentication errors, malformed structured output, unauthorized plans,
and unsupported requests are terminal. The same strict plan validation
runs after every successful provider response and before any task executes.

To inspect configuration without an API request, run the following from
`agentix_backend`:

```powershell
python manage.py shell -c "from django.conf import settings; from orchestrator.core.llm_factory import resolve_llm_selection; print(resolve_llm_selection(role='supervisor'), settings.SUPERVISOR_FALLBACK_ENABLED, settings.SUPERVISOR_FALLBACK_PROVIDERS)"
```

Server-side execution metadata records provider attempts, the provider and
requested model that returned a response, the routed model when available,
and token usage when reported. Credentials and response bodies are omitted.

## Verification

The official `langchain-google-genai==4.5.2` integration was installed with
the existing `langchain-core==1.8.4` pin. The Gemini SDK test used a synthetic
response and checked both the outgoing JSON schema and parsed Pydantic
decision. No live provider calls were made.

All 148 distinct orchestrator tests passed across two disposable PostgreSQL
runs, including 14 new fallback tests. Django checks, the migration dry run,
`pip check`, and `git diff --check` passed.

## Supervisor Groq structured-decision troubleshooting

A live Flutter request received one Groq `openai/gpt-oss-120b` response
(2,252 input tokens and 1,174 output tokens). The saved diagnostic was
`planner_decision_schema`, Pydantic `model_type` at root `loc: []`. Failure
occurred in the structured parser before graph-plan validation or dispatch.
The historical raw response and finish reason were not retained, so the
precise received value type is unavailable.

Only the Groq Supervisor decision changed from best-effort `json_schema`
to `function_calling` with one named PlannerDecision response tool. The tool
is a response format and cannot dispatch a specialist. Pydantic and the
existing plan validator both still apply. Groq documents tool calling for
GPT-OSS 120B. The transport and parser were exercised offline with the
installed LangChain 1.5.2, LangChain Core 1.8.4, and langchain-groq 1.2.1.
See [the Groq model card](https://console.groq.com/docs/model/openai/gpt-oss-120b).

The checkpoint and sanitized logs now include the failure stage, category,
exception class, selected provider and model, response method, allowlisted
finish reason, usage, and validation locations when available. No response
body is persisted for diagnosis. Malformed or incomplete decisions end
planning without retrying or advancing to another model. Set
`SUPERVISOR_FALLBACK_ENABLED=false` for a single-provider live retest.

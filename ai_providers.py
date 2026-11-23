"""
Universal Vision AI Provider System for Quiz Cracker.
Supports all major AI providers on the market using pure Python stdlib (zero extra SDKs):
  - Google Gemini (AIza...)
  - OpenAI / ChatGPT (sk-..., sk-proj-...)
  - Anthropic Claude (sk-ant-...)
  - Groq (gsk_...)
  - OpenRouter (sk-or-...)
  - xAI Grok (xai-...)
  - Mistral AI (Pixtral / Mistral Vision)
  - Together AI (tgp_v1_...)
  - Fireworks AI (fw_...)
  - NVIDIA NIM (nvapi-...)
  - SambaNova Cloud
  - Hugging Face Router (hf_...)
  - Custom / Local OpenAI-Compatible (Ollama, LM Studio, DeepSeek, Azure, etc.)
"""

import json
import base64
import urllib.request
import urllib.error


USER_AGENT = "QuizCracker/2.1 (Windows NT 10.0; Win64; x64)"

MCQ_PROMPT = (
    "Look carefully at this screenshot and find the multiple-choice question (MCQ) "
    "currently displayed on screen. Solve it accurately.\n\n"
    "Respond ONLY with valid JSON (no markdown, no code fences) in this exact format:\n"
    '{"option": "<letter or short choice, e.g. A, B, C, D, True>", '
    '"answer": "<short exact text of the right option, max 8 words>", '
    '"reason": "<ultra-brief explanation, max 12 words>"}\n\n'
    "If no MCQ is clearly visible on screen, respond with:\n"
    '{"option": "—", "answer": "No MCQ detected", '
    '"reason": "Make sure the question and options are visible."}'
)


# ═══════════════════════════════════════════════════════════════
# Provider Registry
# ═══════════════════════════════════════════════════════════════

PROVIDERS = {
    "auto": {
        "name": "Auto-Detect from API Key",
        "protocol": "auto",
        "base_url": "",
        "key_url": "https://aistudio.google.com/apikey",
        "default_models": [],
        "free_tier": True,
    },
    "gemini": {
        "name": "Google Gemini (Free Tier)",
        "protocol": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key_url": "https://aistudio.google.com/apikey",
        "default_models": [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-flash-latest",
            "gemini-1.5-flash",
        ],
        "free_tier": True,
    },
    "groq": {
        "name": "Groq (Free Tier — Very Fast)",
        "protocol": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
        "default_models": [
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "llama-3.2-11b-vision-preview",
            "llama-3.2-90b-vision-preview",
        ],
        "free_tier": True,
    },
    "openrouter": {
        "name": "OpenRouter (Free + All Models)",
        "protocol": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "key_url": "https://openrouter.ai/keys",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/quiz-cracker",
            "X-Title": "Quiz Cracker",
        },
        "default_models": [
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-4-scout:free",
            "qwen/qwen2.5-vl-72b-instruct:free",
            "google/gemini-2.5-flash",
            "openai/gpt-4o-mini",
        ],
        "free_tier": True,
    },
    "openai": {
        "name": "OpenAI (ChatGPT / GPT-4o)",
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "key_url": "https://platform.openai.com/api-keys",
        "default_models": [
            "gpt-4o-mini",
            "gpt-4.1-mini",
            "gpt-4o",
            "gpt-4.1",
        ],
        "free_tier": False,
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "key_url": "https://console.anthropic.com/settings/keys",
        "default_models": [
            "claude-3-5-haiku-latest",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-latest",
            "claude-3-haiku-20240307",
        ],
        "free_tier": False,
    },
    "mistral": {
        "name": "Mistral AI (Free Tier — Pixtral)",
        "protocol": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "key_url": "https://console.mistral.ai/api-keys/",
        "default_models": [
            "pixtral-12b-2409",
            "mistral-small-latest",
            "pixtral-large-latest",
        ],
        "free_tier": True,
    },
    "xai": {
        "name": "xAI (Grok Vision)",
        "protocol": "openai",
        "base_url": "https://api.x.ai/v1",
        "key_url": "https://console.x.ai/",
        "default_models": [
            "grok-2-vision-latest",
            "grok-2-vision-1212",
            "grok-vision-beta",
        ],
        "free_tier": False,
    },
    "nvidia": {
        "name": "NVIDIA NIM (Free Tier)",
        "protocol": "openai",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_url": "https://build.nvidia.com/",
        "default_models": [
            "meta/llama-3.2-11b-vision-instruct",
            "meta/llama-3.2-90b-vision-instruct",
            "microsoft/phi-3.5-vision-instruct",
        ],
        "free_tier": True,
    },
    "together": {
        "name": "Together AI",
        "protocol": "openai",
        "base_url": "https://api.together.xyz/v1",
        "key_url": "https://api.together.xyz/settings/api-keys",
        "default_models": [
            "meta-llama/Llama-Vision-Free",
            "meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
            "Qwen/Qwen2.5-VL-72B-Instruct",
        ],
        "free_tier": True,
    },
    "fireworks": {
        "name": "Fireworks AI",
        "protocol": "openai",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "key_url": "https://fireworks.ai/account/api-keys",
        "default_models": [
            "accounts/fireworks/models/llama-v3p2-11b-vision-instruct",
            "accounts/fireworks/models/qwen2p5-vl-32b-instruct",
        ],
        "free_tier": False,
    },
    "sambanova": {
        "name": "SambaNova Cloud (Free Tier)",
        "protocol": "openai",
        "base_url": "https://api.sambanova.ai/v1",
        "key_url": "https://cloud.sambanova.ai/apis",
        "default_models": [
            "Llama-4-Maverick-17B-128E-Instruct",
            "Llama-3.2-11B-Vision-Instruct",
            "Llama-3.2-90B-Vision-Instruct",
        ],
        "free_tier": True,
    },
    "huggingface": {
        "name": "Hugging Face Router (Free Tier)",
        "protocol": "openai",
        "base_url": "https://router.huggingface.co/v1",
        "key_url": "https://huggingface.co/settings/tokens",
        "default_models": [
            "Qwen/Qwen2.5-VL-7B-Instruct",
            "meta-llama/Llama-3.2-11B-Vision-Instruct",
        ],
        "free_tier": True,
    },
    "custom": {
        "name": "Custom / Local (Ollama, LM Studio, Any OpenAI API)",
        "protocol": "openai",
        "base_url": "http://localhost:11434/v1",
        "key_url": "https://ollama.com/",
        "default_models": [
            "llava",
            "qwen2.5vl",
            "gemma3",
            "llama3.2-vision",
        ],
        "free_tier": True,
    },
}

PROVIDER_ORDER = [
    "auto",
    "gemini",
    "groq",
    "openrouter",
    "openai",
    "anthropic",
    "mistral",
    "xai",
    "nvidia",
    "together",
    "fireworks",
    "sambanova",
    "huggingface",
    "custom",
]

# Keywords used to rank vision-capable models when dynamically listing /models
VISION_KEYWORDS = (
    "vision", "vl", "pixtral", "4o", "4.1", "gpt-5", "gemini", "gemma-3",
    "claude-3", "claude-4", "claude-sonnet", "claude-haiku", "claude-opus",
    "llama-4", "scout", "maverick", "grok-2-vision", "grok-4", "llava",
    "qwen2.5-vl", "qwen2-vl", "phi-3.5-vision", "phi-4-multimodal", "omni",
)


# ═══════════════════════════════════════════════════════════════
# Key Cleaning & Provider Auto-Detection
# ═══════════════════════════════════════════════════════════════

def clean_api_key(raw: str) -> str:
    """Strip whitespace, newlines, accidental quotes, or leading 'Bearer '."""
    s = (raw or "").strip().strip('"').strip("'").replace("\r", "").replace("\n", "").strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    return s


def detect_provider_from_key(api_key: str) -> str:
    """
    Detect AI provider from API key prefix.
    Returns provider_id (e.g. 'gemini', 'openai', 'groq', ...) or '' if ambiguous.
    """
    k = clean_api_key(api_key)
    if not k:
        return ""
    if k.startswith("AIza"):
        return "gemini"
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("sk-or-"):
        return "openrouter"
    if k.startswith("gsk_"):
        return "groq"
    if k.startswith("xai-"):
        return "xai"
    if k.startswith("nvapi-"):
        return "nvidia"
    if k.startswith("hf_"):
        return "huggingface"
    if k.startswith("fw_"):
        return "fireworks"
    if k.startswith("tgp_v1_"):
        return "together"
    if k.startswith("sk-proj-") or k.startswith("sk-svcacct-") or k.startswith("sk-"):
        return "openai"
    return ""


# ═══════════════════════════════════════════════════════════════
# Response Parsing & HTTP Helpers
# ═══════════════════════════════════════════════════════════════

def parse_mcq_response(raw_text: str) -> dict:
    """Parse structured JSON from any AI model (handles code fences & plain-text fallback)."""
    text = (raw_text or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return {
                "option": str(obj.get("option", "?")).strip() or "?",
                "answer": str(obj.get("answer", "")).strip(),
                "reason": str(obj.get("reason", "")).strip(),
            }
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return {
                    "option": str(obj.get("option", "?")).strip() or "?",
                    "answer": str(obj.get("answer", "")).strip(),
                    "reason": str(obj.get("reason", "")).strip(),
                }
        except Exception:
            pass

    first_line = text.splitlines()[0] if text else "Could not parse answer"
    return {"option": "✓", "answer": first_line[:90], "reason": ""}


def _extract_error_message(err_body: str) -> str:
    """Extract readable error text from JSON error payloads across providers."""
    try:
        data = json.loads(err_body)
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"]).strip()[:140]
            if isinstance(err, str) and err.strip():
                return err.strip()[:140]
            if data.get("message"):
                return str(data["message"]).strip()[:140]
            if data.get("detail"):
                return str(data["detail"]).strip()[:140]
    except Exception:
        pass
    cleaned = (err_body or "").strip().splitlines()[0] if (err_body or "").strip() else ""
    return cleaned[:140]


def _http_json(url: str, payload: dict = None, headers: dict = None, timeout: int = 25) -> dict:
    """Perform HTTP GET or POST returning parsed JSON with proper User-Agent."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    method = "GET"
    if payload is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
        method = "POST"

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ═══════════════════════════════════════════════════════════════
# Live Model Discovery (Finds Working Models on User's Account!)
# ═══════════════════════════════════════════════════════════════

def _is_vision_model_name(model_id: str) -> bool:
    low = model_id.lower()
    if any(skip in low for skip in ("embed", "whisper", "tts", "audio", "dall-e", "moderation", "guard", "rerank", "bge-", "aqa")):
        return False
    return any(kw in low for kw in VISION_KEYWORDS)


def discover_models(provider_id: str, api_key: str, custom_base_url: str = "") -> list:
    """Query the provider's live /models endpoint and return vision-capable model IDs."""
    meta = PROVIDERS.get(provider_id)
    if not meta:
        return []
    protocol = meta["protocol"]
    base_url = (custom_base_url.strip().rstrip("/") if provider_id == "custom" and custom_base_url.strip()
                else meta["base_url"].rstrip("/"))

    try:
        if protocol == "gemini":
            data = _http_json(f"{base_url}/models?key={api_key}", timeout=10)
            models = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue
                name = str(m.get("name", ""))
                if name.startswith("models/"):
                    name = name[7:]
                if _is_vision_model_name(name):
                    models.append(name)
            # Prioritize flash models first (fast & high free quota)
            models.sort(key=lambda s: (
                0 if "2.5-flash" in s else
                1 if "2.0-flash" in s else
                2 if "flash" in s else
                3 if "pro" in s else 4,
                len(s),
            ))
            return models[:15]

        if protocol == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            data = _http_json(f"{base_url}/models", headers=headers, timeout=10)
            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            return [m for m in models if _is_vision_model_name(m)][:15]

        if protocol == "openai":
            headers = dict(meta.get("extra_headers", {}))
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            data = _http_json(f"{base_url}/models", headers=headers, timeout=10)
            items = data.get("data", []) if isinstance(data, dict) else []
            all_ids = [str(m.get("id", "")) for m in items if isinstance(m, dict) and m.get("id")]
            vision = [m for m in all_ids if _is_vision_model_name(m)]
            if provider_id == "openrouter":
                # Put free vision models first for OpenRouter!
                vision.sort(key=lambda s: (0 if ":free" in s else 1, s))
            return (vision or all_ids)[:15]
    except Exception:
        return []
    return []


# ═══════════════════════════════════════════════════════════════
# Protocol-Specific Vision Calls
# ═══════════════════════════════════════════════════════════════

def _call_gemini_single(image_bytes: bytes, api_key: str, model: str, mime_type: str, use_json_mode: bool = True) -> dict:
    b64_img = base64.b64encode(image_bytes).decode("ascii")
    gen_cfg = {"temperature": 0.1, "maxOutputTokens": 220}
    if use_json_mode:
        gen_cfg["responseMimeType"] = "application/json"

    payload = {
        "contents": [{
            "parts": [
                {"text": MCQ_PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": b64_img}},
            ]
        }],
        "generationConfig": gen_cfg,
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    data = _http_json(url, payload=payload, timeout=25)
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Empty response from Gemini.")
    parts = candidates[0].get("content", {}).get("parts", [])
    raw_text = "".join(p.get("text", "") for p in parts).strip()
    if not raw_text:
        raise RuntimeError("Response blocked or empty.")
    res = parse_mcq_response(raw_text)
    res["model"] = model
    res["provider"] = "gemini"
    return res


def _call_anthropic_single(image_bytes: bytes, api_key: str, model: str, mime_type: str) -> dict:
    b64_img = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "max_tokens": 220,
        "temperature": 0.1,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_img,
                    },
                },
                {"type": "text", "text": MCQ_PROMPT},
            ],
        }],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    data = _http_json("https://api.anthropic.com/v1/messages", payload=payload, headers=headers, timeout=25)
    blocks = data.get("content") or []
    raw_text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()
    if not raw_text:
        raise RuntimeError("Empty response from Claude.")
    res = parse_mcq_response(raw_text)
    res["model"] = model
    res["provider"] = "anthropic"
    return res


def _call_openai_compat_single(
    image_bytes: bytes,
    api_key: str,
    model: str,
    base_url: str,
    provider_id: str,
    mime_type: str,
    extra_headers: dict = None,
    use_max_completion: bool = False,
) -> dict:
    b64_img = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{b64_img}"

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": MCQ_PROMPT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }],
    }
    if use_max_completion:
        payload["max_completion_tokens"] = 220
    else:
        payload["max_tokens"] = 220
        payload["temperature"] = 0.1

    headers = dict(extra_headers or {})
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    data = _http_json(endpoint, payload=payload, headers=headers, timeout=30)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Empty response from {provider_id}.")
    msg = choices[0].get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):
        raw_text = "".join(p.get("text", "") for p in content if isinstance(p, dict)).strip()
    else:
        raw_text = str(content or "").strip()
    if not raw_text:
        raise RuntimeError(f"Empty content from {provider_id}.")
    res = parse_mcq_response(raw_text)
    res["model"] = model
    res["provider"] = provider_id
    return res


# ═══════════════════════════════════════════════════════════════
# Unified Solve Function (Auto-Fallback + Live Discovery!)
# ═══════════════════════════════════════════════════════════════

def _solve_single_provider(
    image_bytes: bytes,
    provider_id: str,
    api_key: str,
    model: str = "",
    custom_base_url: str = "",
    mime_type: str = "image/jpeg",
) -> dict:
    meta = PROVIDERS.get(provider_id)
    if not meta:
        raise RuntimeError(f"Unknown provider: {provider_id}")

    api_key = clean_api_key(api_key)
    if not api_key and provider_id != "custom":
        raise RuntimeError(f"API key missing for {meta['name']}.")

    protocol = meta["protocol"]
    base_url = (custom_base_url.strip().rstrip("/") if provider_id == "custom" and custom_base_url.strip()
                else meta["base_url"].rstrip("/"))
    extra_headers = meta.get("extra_headers", {})

    # Build ordered list of models to try
    candidates = []
    if model and model.strip():
        candidates.append(model.strip())
    for m in meta.get("default_models", []):
        if m not in candidates:
            candidates.append(m)

    tried = set()
    discovered_once = False
    last_error = None
    idx = 0

    while idx < len(candidates):
        mdl = candidates[idx]
        idx += 1
        if mdl in tried:
            continue
        tried.add(mdl)

        try:
            if protocol == "gemini":
                try:
                    return _call_gemini_single(image_bytes, api_key, mdl, mime_type, use_json_mode=True)
                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
                    if e.code == 400 and ("mime" in err_body.lower() or "json" in err_body.lower()):
                        return _call_gemini_single(image_bytes, api_key, mdl, mime_type, use_json_mode=False)
                    # Re-raise wrapped with body so outer handler sees it
                    raise _DetailedHTTPError(e.code, err_body)

            elif protocol == "anthropic":
                return _call_anthropic_single(image_bytes, api_key, mdl, mime_type)

            else:  # openai-compatible
                try:
                    return _call_openai_compat_single(
                        image_bytes, api_key, mdl, base_url, provider_id, mime_type, extra_headers,
                        use_max_completion=False,
                    )
                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
                    if e.code == 400 and "max_completion_tokens" in err_body.lower():
                        return _call_openai_compat_single(
                            image_bytes, api_key, mdl, base_url, provider_id, mime_type, extra_headers,
                            use_max_completion=True,
                        )
                    raise _DetailedHTTPError(e.code, err_body)

        except (_DetailedHTTPError, urllib.error.HTTPError) as e:
            if isinstance(e, _DetailedHTTPError):
                code, err_body = e.code, e.body
            else:
                code = e.code
                err_body = e.read().decode("utf-8", errors="ignore") if e.fp else ""

            detail = _extract_error_message(err_body)
            low_detail = (detail + " " + err_body).lower()

            # Definite invalid key -> fail immediately (no point trying other models)
            if code in (401, 403) or "api_key_invalid" in low_detail or "invalid api key" in low_detail or "incorrect api key" in low_detail:
                raise _AuthError(detail or f"Invalid API key for {meta['name']}.")

            # Model not found / rate-limited on this model / model doesn't support images -> try next model!
            if code in (404, 429, 400, 503):
                last_error = f"{mdl}: {detail or f'HTTP {code}'}"
                # If we ran out of static candidates, query live /models once to find a working model!
                if idx >= len(candidates) and not discovered_once:
                    discovered_once = True
                    for live_m in discover_models(provider_id, api_key, custom_base_url):
                        if live_m not in tried and live_m not in candidates:
                            candidates.append(live_m)
                continue

            raise RuntimeError(detail or f"{meta['name']} HTTP {code} error.")

        except urllib.error.URLError:
            raise RuntimeError("No internet connection (or unreachable endpoint).")
        except TimeoutError:
            raise RuntimeError(f"{meta['name']} timed out. Wiggle again to retry.")

    raise RuntimeError(last_error or f"No working vision model found for {meta['name']}.")


class _DetailedHTTPError(Exception):
    def __init__(self, code: int, body: str):
        super().__init__(f"HTTP {code}")
        self.code = code
        self.body = body


class _AuthError(RuntimeError):
    pass


def solve_mcq_with_provider(
    image_bytes: bytes,
    provider_id: str,
    api_key: str,
    model: str = "",
    custom_base_url: str = "",
    backup_keys: dict = None,
    mime_type: str = "image/jpeg",
) -> dict:
    """
    Solve an MCQ screenshot using the chosen provider (or auto-detected provider),
    with automatic model fallback, live model discovery, and optional failover to
    other saved provider keys if the primary provider fails!
    """
    api_key = clean_api_key(api_key)
    resolved = provider_id or "auto"
    if resolved == "auto":
        resolved = detect_provider_from_key(api_key) or "gemini"

    attempts = [(resolved, api_key, model)]
    if backup_keys and isinstance(backup_keys, dict):
        for bp_id, bp_key in backup_keys.items():
            cleaned = clean_api_key(bp_key)
            if bp_id in PROVIDERS and bp_id not in ("auto", resolved) and cleaned:
                attempts.append((bp_id, cleaned, ""))

    first_error = None
    for idx, (pid, key, mdl) in enumerate(attempts):
        try:
            return _solve_single_provider(
                image_bytes=image_bytes,
                provider_id=pid,
                api_key=key,
                model=mdl,
                custom_base_url=custom_base_url if pid == "custom" else "",
                mime_type=mime_type,
            )
        except Exception as e:
            if first_error is None:
                first_error = str(e)
            # Only fail over to backup keys if we actually have another saved key
            if idx + 1 < len(attempts):
                continue
            raise RuntimeError(first_error)

    raise RuntimeError(first_error or "No API key configured.")


# ═══════════════════════════════════════════════════════════════
# Live Key Tester + Automatic Provider & Model Discovery
# ═══════════════════════════════════════════════════════════════

def _ping_single_provider(provider_id: str, api_key: str, model: str = "", custom_base_url: str = "") -> tuple:
    """
    Test one provider with a lightweight request + live model discovery.
    Returns (ok: bool, working_model: str, discovered_models: list, message: str).
    """
    meta = PROVIDERS[provider_id]
    protocol = meta["protocol"]
    base_url = (custom_base_url.strip().rstrip("/") if provider_id == "custom" and custom_base_url.strip()
                else meta["base_url"].rstrip("/"))
    extra_headers = meta.get("extra_headers", {})

    # First discover live models on this account (fast GET — also verifies auth on most providers!)
    discovered = discover_models(provider_id, api_key, custom_base_url)

    candidates = []
    if model and model.strip():
        candidates.append(model.strip())
    for m in meta.get("default_models", []):
        if m not in candidates:
            candidates.append(m)
    for m in discovered:
        if m not in candidates:
            candidates.append(m)

    if not candidates:
        return False, "", discovered, f"No models found for {meta['name']}."

    last_err = ""
    for mdl in candidates[:8]:
        try:
            if protocol == "gemini":
                url = f"{base_url}/models/{mdl}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": "Reply OK"}]}],
                    "generationConfig": {"maxOutputTokens": 5},
                }
                _http_json(url, payload=payload, timeout=12)
                return True, mdl, discovered or meta["default_models"], f"Connected to Google Gemini ({mdl})"

            elif protocol == "anthropic":
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
                payload = {
                    "model": mdl,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Reply OK"}],
                }
                _http_json(f"{base_url}/messages", payload=payload, headers=headers, timeout=12)
                return True, mdl, discovered or meta["default_models"], f"Connected to Anthropic Claude ({mdl})"

            else:  # openai-compatible
                headers = dict(extra_headers)
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                payload = {
                    "model": mdl,
                    "messages": [{"role": "user", "content": "Reply OK"}],
                    "max_tokens": 5,
                }
                try:
                    _http_json(f"{base_url}/chat/completions", payload=payload, headers=headers, timeout=12)
                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
                    if e.code == 400 and "max_completion_tokens" in err_body.lower():
                        payload.pop("max_tokens", None)
                        payload["max_completion_tokens"] = 5
                        _http_json(f"{base_url}/chat/completions", payload=payload, headers=headers, timeout=12)
                    else:
                        raise _DetailedHTTPError(e.code, err_body)
                return True, mdl, discovered or meta["default_models"], f"Connected to {meta['name']} ({mdl})"

        except (_DetailedHTTPError, urllib.error.HTTPError) as e:
            if isinstance(e, _DetailedHTTPError):
                code, err_body = e.code, e.body
            else:
                code = e.code
                err_body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
            detail = _extract_error_message(err_body)
            low = (detail + " " + err_body).lower()

            if code in (401, 403) or "api_key_invalid" in low or "invalid api key" in low or "incorrect api key" in low:
                return False, "", discovered, detail or f"Invalid API key for {meta['name']}."

            if code in (404, 429, 400, 503):
                last_err = detail or f"HTTP {code} on {mdl}"
                continue

            return False, "", discovered, detail or f"HTTP {code} error."
        except urllib.error.URLError:
            return False, "", discovered, f"Cannot reach {meta['name']} — check your internet or Base URL."
        except TimeoutError:
            return False, "", discovered, f"Connection to {meta['name']} timed out."
        except Exception as e:
            return False, "", discovered, str(e)[:100]

    # If models were discovered (key authenticated!) but all hit 429 rate-limit, still inform clearly
    if discovered and any(tok in last_err.lower() for tok in ("quota", "429", "rate")):
        return True, discovered[0] if discovered else candidates[0], discovered, (
            f"Key valid for {meta['name']} (temporarily rate-limited: {last_err[:65]})"
        )
    return False, "", discovered, last_err or f"Could not find a working model for {meta['name']}."


def test_provider_key(provider_id: str, api_key: str, model: str = "", custom_base_url: str = "") -> tuple:
    """
    Universal key tester!
    - If provider_id == 'auto': detects from key prefix; if prefix is ambiguous (like Mistral/SambaNova),
      probes the candidate providers automatically!
    Returns: (ok: bool, resolved_provider: str, working_model: str, models_list: list, message: str)
    """
    api_key = clean_api_key(api_key)
    if not api_key and provider_id != "custom":
        return False, provider_id, "", [], "API key is empty — paste your key first."

    if provider_id != "auto" and provider_id in PROVIDERS:
        ok, mdl, models, msg = _ping_single_provider(provider_id, api_key, model, custom_base_url)
        return ok, provider_id, mdl, models, msg

    # Auto-detect by prefix first
    detected = detect_provider_from_key(api_key)
    if detected:
        ok, mdl, models, msg = _ping_single_provider(detected, api_key, model)
        return ok, detected, mdl, models, msg

    # Ambiguous prefix (e.g. Mistral, SambaNova, Together legacy, etc.) -> probe cleanly!
    probe_order = ["mistral", "sambanova", "together", "openrouter", "openai", "gemini"]
    last_msg = "Could not identify which provider this API key belongs to."
    for pid in probe_order:
        ok, mdl, models, msg = _ping_single_provider(pid, api_key, "")
        if ok:
            return True, pid, mdl, models, f"Auto-detected! {msg}"
        last_msg = msg

    return False, "auto", "", [], "Key wasn't accepted by any provider. Select your provider manually or check the key."

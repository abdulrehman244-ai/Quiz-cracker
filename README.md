# 🧠 Quiz Cracker

A lightweight, **mouse-move-only** Windows desktop overlay that solves MCQs automatically using **ANY major Vision AI model on the market** — **no clicking, no keyboard, no window switching**.

Just **wiggle your mouse left-and-right**, and a small, subtle answer card pops up in the corner of your screen.

---

## 🌐 Supported AI Providers (Paste ANY Key — Auto-Detected!)

| Provider | Key Prefix | Free Tier? | Vision Models (Auto-Fallback + Live Discovery) |
|---|---|---|---|
| **Google Gemini** | `AIza...` | ✅ Yes | `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.0-flash`, ... |
| **Groq** | `gsk_...` | ✅ Yes (Fast!) | `llama-4-scout`, `llama-4-maverick`, `llama-3.2-vision` |
| **OpenRouter** | `sk-or-...` | ✅ Yes (`:free`) | Free & paid vision models across Google, Meta, Qwen, OpenAI, Claude |
| **OpenAI (ChatGPT)** | `sk-...`, `sk-proj-...` | Paid | `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4.1` |
| **Anthropic Claude** | `sk-ant-...` | Paid | `claude-3-5-haiku`, `claude-sonnet-4`, `claude-3-5-sonnet` |
| **Mistral AI** | Any | ✅ Yes | `pixtral-12b-2409`, `mistral-small-latest`, `pixtral-large-latest` |
| **xAI (Grok)** | `xai-...` | Paid | `grok-2-vision-latest`, `grok-2-vision-1212` |
| **NVIDIA NIM** | `nvapi-...` | ✅ Yes | `llama-3.2-11b-vision`, `phi-3.5-vision` |
| **Together AI** | `tgp_v1_...` | ✅ Yes | `Llama-Vision-Free`, `Qwen2.5-VL-72B` |
| **Fireworks AI** | `fw_...` | Paid | `llama-v3p2-11b-vision`, `qwen2p5-vl-32b` |
| **SambaNova Cloud** | Any | ✅ Yes | `Llama-4-Maverick`, `Llama-3.2-Vision` |
| **Hugging Face Router** | `hf_...` | ✅ Yes | `Qwen2.5-VL-7B`, `Llama-3.2-11B-Vision` |
| **Custom / Local** | Optional | ✅ Free (Local) | **Ollama** (`http://localhost:11434/v1`), **LM Studio**, Azure, any OpenAI-compatible API |

### Built-In Reliability Fixes
- **Auto-Detect Provider**: Paste any key and Quiz Cracker automatically identifies the provider & vision models.
- **Live Model Discovery**: Clicking **`🔍 Test & Detect`** queries the provider's `/models` endpoint and picks a verified working vision model on your account.
- **Smart Fallback**: If one model hits a `404` or `429` rate limit, it automatically tries the next working vision model on your key.
- **Multi-Key Backup Failover**: Keys are saved per provider — if you save keys for 2+ providers (e.g., Groq + Gemini + OpenRouter), it automatically fails over if one hits a limit!
- **Cloudflare-Safe Headers**: Sends a proper desktop `User-Agent` so providers behind Cloudflare (Groq, OpenRouter, Mistral, xAI) never reject requests with HTTP 403.

---

## ⚡ Quick Start

1. Double-click **`Quiz Cracker`** on your Desktop (runs silently with no terminal window).
2. In Settings, paste **any** AI API key (or pick a provider and click **`🌐 Get API Key`**).
3. Click **`🔍 Test & Detect`** to confirm the key and auto-select a working model, then click **`💾 Save & Close`**.
4. Keep your MCQ visible and **wiggle your mouse left-and-right** — a small, subtle answer pops up in the corner!

---

## 📁 Project Files

- `quiz_cracker.py` — Main subtle desktop overlay & Settings UI
- `ai_providers.py` — Universal multi-provider Vision AI engine (13+ providers + auto-detect + live discovery)
- `Quiz Cracker.pyw` / `Launch Quiz Cracker.vbs` — Silent windowless launchers
- `assets/quiz_cracker.ico` — Custom Windows application icon
- `create_desktop_shortcut.ps1` — Creates the Desktop shortcut (`Quiz Cracker.lnk`)
- `build_exe.bat` — Optional standalone `Quiz Cracker.exe` builder
- `test_quiz_cracker.py` — Automated verification suite (19 tests)

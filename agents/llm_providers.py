"""
LLM provider abstraction layer.
Supports: Google Gemini, Groq, OpenRouter.

Strategy: health-check-first, then only use alive providers.
- At startup, each provider is tested with 1 tiny call (no retries)
- Dead providers are BLOCKED — zero wasted calls or backoff time
- On 429: escalating backoff 15s→30s→60s, then retry
- max_tokens=4096 (Gemini 2.5 Flash thinking model needs headroom; agent responses ~800-1500 tokens)
"""

import json
import re
import time
import threading
import requests
from config.settings import (
    GEMINI_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEY,
    GEMINI_LITE_API_KEY, GEMINI_LITE_MODEL, GEMINI_LITE_RPM,
    GEMINI_MODEL, GROQ_MODEL, OPENROUTER_MODEL,
    GEMINI_RPM_PER_KEY, GROQ_RPM_PER_KEY, OPENROUTER_RPM,
)


class RateLimiter:
    """
    Pre-emptive rate limiter using a sliding window of timestamps.
    Sleeps if at capacity before making the call.
    """

    def __init__(self, rpm_limit: int):
        self.rpm_limit = rpm_limit
        self.timestamps: list[float] = []
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            self.timestamps = [t for t in self.timestamps if now - t < 60]

            if len(self.timestamps) >= self.rpm_limit:
                sleep_time = 60 - (now - self.timestamps[0]) + 1.0
                if sleep_time > 0:
                    print(f"[RateLimit] Throttling for {sleep_time:.1f}s (at {self.rpm_limit} RPM limit)")
                    time.sleep(sleep_time)

            self.timestamps.append(time.time())

    def backoff_after_429(self, attempt: int):
        """Escalating backoff: 15s -> 30s -> 60s. Quick first retry, longer if persistent."""
        wait_times = [15, 30, 60]
        wait = wait_times[min(attempt, len(wait_times) - 1)]
        print(f"[RateLimit] 429 — waiting {wait}s (attempt {attempt + 1})")
        time.sleep(wait)


class LLMPool:
    """
    Manages multiple API keys across Gemini, Groq, and OpenRouter.

    Health-check-first strategy:
    1. check_provider_health() tests each provider once at startup
    2. Only alive providers are used — dead ones are skipped instantly
    3. On 429, wait 60s (full rate window reset), then retry
    4. max_tokens=1024 to conserve tokens-per-minute quota
    """

    MAX_RETRIES = 3  # 3 retries × 60s wait = 3 min max, but will succeed

    def __init__(self):
        self._gemini_idx = 0
        self._groq_idx = 0
        self._lock = threading.Lock()

        # Per-key rate limiters
        self._gemini_lite_limiter = RateLimiter(GEMINI_LITE_RPM) if GEMINI_LITE_API_KEY else None
        self._gemini_limiters = {k: RateLimiter(GEMINI_RPM_PER_KEY) for k in GEMINI_API_KEYS}
        self._groq_limiters = {k: RateLimiter(GROQ_RPM_PER_KEY) for k in GROQ_API_KEYS}
        self._openrouter_limiter = RateLimiter(OPENROUTER_RPM)

        # Alive providers — set by check_provider_health()
        # None means "not checked yet" (will try all); empty set means "all dead"
        self._alive_providers: set | None = None

        # Demotion tracking: providers with consecutive 429s get deprioritized
        self._consecutive_429s: dict = {"gemini_lite": 0, "gemini": 0, "groq": 0, "openrouter": 0}
        self._demoted_providers: set = set()

    def set_alive_providers(self, alive: list[str]):
        """Called after health check to lock in which providers to use."""
        self._alive_providers = set(alive)

    def _is_alive(self, provider: str) -> bool:
        """Check if provider passed health check. If no check done, allow all."""
        if self._alive_providers is None:
            return True  # No health check run yet, try everything
        return provider in self._alive_providers

    def _record_429(self, provider: str):
        """Track consecutive 429s. Demote provider after threshold."""
        from config.settings import PROVIDER_DEMOTE_AFTER_FAILURES
        self._consecutive_429s[provider] = self._consecutive_429s.get(provider, 0) + 1
        if self._consecutive_429s[provider] >= PROVIDER_DEMOTE_AFTER_FAILURES:
            self._demoted_providers.add(provider)
            print(f"[LLM] {provider} demoted after {self._consecutive_429s[provider]} consecutive 429s — deprioritized")

    def _record_success(self, provider: str):
        """Reset failure counter on success."""
        self._consecutive_429s[provider] = 0
        self._demoted_providers.discard(provider)

    def _is_demoted(self, provider: str) -> bool:
        return provider in self._demoted_providers

    def _next_gemini_key(self) -> str | None:
        with self._lock:
            if not GEMINI_API_KEYS:
                return None
            key = GEMINI_API_KEYS[self._gemini_idx % len(GEMINI_API_KEYS)]
            self._gemini_idx += 1
            return key

    def _next_groq_key(self) -> str | None:
        with self._lock:
            if not GROQ_API_KEYS:
                return None
            key = GROQ_API_KEYS[self._groq_idx % len(GROQ_API_KEYS)]
            self._groq_idx += 1
            return key

    # ── Gemini 2.5 Flash Lite (Tier 1 paid — PRIMARY) ────────────────────────

    def call_gemini_lite(self, prompt: str, system_instruction: str = "") -> str:
        if not GEMINI_LITE_API_KEY:
            raise RuntimeError("No Gemini Lite API key configured")

        for attempt in range(self.MAX_RETRIES):
            self._gemini_lite_limiter.acquire()

            try:
                from google import genai

                client = genai.Client(api_key=GEMINI_LITE_API_KEY)
                config = {"temperature": 0.7, "max_output_tokens": 4096}
                if system_instruction:
                    config["system_instruction"] = system_instruction

                response = client.models.generate_content(
                    model=GEMINI_LITE_MODEL,
                    contents=prompt,
                    config=config,
                )
                return response.text

            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str:
                    self._gemini_lite_limiter.backoff_after_429(attempt)
                    continue
                raise

        raise RuntimeError(f"Gemini Lite: exhausted {self.MAX_RETRIES} retries due to rate limits")

    # ── Gemini 2.5 Flash (free tier backup) ────────────────────────────────

    def call_gemini(self, prompt: str, system_instruction: str = "") -> str:
        for attempt in range(self.MAX_RETRIES):
            key = self._next_gemini_key()
            if not key:
                raise RuntimeError("No Gemini API keys configured")

            limiter = self._gemini_limiters[key]
            limiter.acquire()

            try:
                from google import genai

                client = genai.Client(api_key=key)
                config = {"temperature": 0.7, "max_output_tokens": 4096}
                if system_instruction:
                    config["system_instruction"] = system_instruction

                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
                return response.text

            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str:
                    limiter.backoff_after_429(attempt)
                    continue
                raise

        raise RuntimeError(f"Gemini: exhausted {self.MAX_RETRIES} retries due to rate limits")

    # ── Groq ──────────────────────────────────────────────────────────────────

    def call_groq(self, prompt: str, system_instruction: str = "") -> str:
        for attempt in range(self.MAX_RETRIES):
            key = self._next_groq_key()
            if not key:
                raise RuntimeError("No Groq API keys configured")

            limiter = self._groq_limiters[key]
            limiter.acquire()

            try:
                from groq import Groq
                client = Groq(api_key=key)

                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                response = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4096,
                )
                return response.choices[0].message.content

            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str or "rate limit" in err_str:
                    limiter.backoff_after_429(attempt)
                    continue
                raise

        raise RuntimeError(f"Groq: exhausted {self.MAX_RETRIES} retries due to rate limits")

    # ── OpenRouter ────────────────────────────────────────────────────────────

    def call_openrouter(self, prompt: str, system_instruction: str = "") -> str:
        if not OPENROUTER_API_KEY:
            raise RuntimeError("No OpenRouter API key configured")

        for attempt in range(self.MAX_RETRIES):
            self._openrouter_limiter.acquire()

            try:
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8501",
                        "X-Title": "Market Intelligence",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 4096,
                    },
                    timeout=120,
                )

                if resp.status_code == 429:
                    self._openrouter_limiter.backoff_after_429(attempt)
                    continue

                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

            except requests.exceptions.HTTPError as e:
                if "429" in str(e):
                    self._openrouter_limiter.backoff_after_429(attempt)
                    continue
                raise
            except Exception as e:
                if "429" in str(e):
                    self._openrouter_limiter.backoff_after_429(attempt)
                    continue
                raise

        raise RuntimeError(f"OpenRouter: exhausted {self.MAX_RETRIES} retries due to rate limits")

    # ── Quick Health Check (1 call per provider, no retries) ──────────────

    def check_provider_health(self) -> dict:
        """
        Test each provider with 1 tiny call. No retries.
        Returns {provider: True/False} and sets internal alive list.
        """
        results = {}
        test_prompt = "Reply with exactly one word: OK"

        # Test Gemini Lite (Tier 1 paid — top priority)
        results["gemini_lite"] = False
        if GEMINI_LITE_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=GEMINI_LITE_API_KEY)
                response = client.models.generate_content(
                    model=GEMINI_LITE_MODEL, contents=test_prompt,
                    config={"temperature": 0, "max_output_tokens": 10},
                )
                if response.text and len(response.text.strip()) > 0:
                    results["gemini_lite"] = True
            except Exception:
                pass

        # Test Gemini (free tier) — try ALL keys (one may be rate-limited while others work)
        results["gemini"] = False
        if GEMINI_API_KEYS:
            from google import genai
            for key in GEMINI_API_KEYS:
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model=GEMINI_MODEL, contents=test_prompt,
                        config={"temperature": 0, "max_output_tokens": 10},
                    )
                    if response.text and len(response.text.strip()) > 0:
                        results["gemini"] = True
                        break  # At least one key works
                except Exception:
                    continue  # Try next key

        # Test Groq — try ALL keys
        results["groq"] = False
        if GROQ_API_KEYS:
            from groq import Groq
            for key in GROQ_API_KEYS:
                try:
                    client = Groq(api_key=key)
                    response = client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": test_prompt}],
                        temperature=0, max_tokens=10,
                    )
                    if response.choices[0].message.content:
                        results["groq"] = True
                        break
                except Exception:
                    continue

        # Test OpenRouter
        try:
            if not OPENROUTER_API_KEY:
                results["openrouter"] = False
            else:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [{"role": "user", "content": test_prompt}],
                        "max_tokens": 10,
                    },
                    timeout=30,
                )
                results["openrouter"] = resp.status_code == 200
        except Exception:
            results["openrouter"] = False

        # Lock in alive providers
        alive = [p for p, ok in results.items() if ok]
        self.set_alive_providers(alive)
        return results

    # ── Unified Call — Only Uses Alive Providers ──────────────────────────

    def call_llm(self, prompt: str, system_instruction: str = "",
                 prefer: str = "groq") -> str:
        """
        Call LLM using ONLY providers that passed health check.
        - Preferred provider first, then fallback to other alive ones
        - Dead providers are skipped instantly (no call, no wait)
        """
        all_providers = {
            "gemini_lite": self.call_gemini_lite,
            "gemini": self.call_gemini,
            "groq": self.call_groq,
            "openrouter": self.call_openrouter,
        }

        from config.settings import PROVIDER_PRIORITY

        # Build order: preferred first (if not demoted), then by priority, skip demoted
        order = [prefer] if not self._is_demoted(prefer) else []
        for p in PROVIDER_PRIORITY:
            if p != prefer and not self._is_demoted(p):
                order.append(p)
        # If all demoted, try them anyway as last resort
        if not order:
            order = list(PROVIDER_PRIORITY)
        # Filter to alive only
        order = [p for p in order if self._is_alive(p)]

        if not order:
            raise RuntimeError("No LLM providers are alive. Run health check or wait for rate limits to reset.")

        last_error = None
        for provider_name in order:
            fn = all_providers[provider_name]
            try:
                result = fn(prompt, system_instruction)
                self._record_success(provider_name)
                return result
            except Exception as e:
                last_error = e
                # Track 429s for demotion
                err_str = str(e).lower()
                if "429" in err_str or "rate" in err_str:
                    self._record_429(provider_name)
                print(f"[LLM] {provider_name} failed: {e}, trying next...")
                continue

        raise RuntimeError(f"All alive LLM providers failed. Last error: {last_error}")


# Singleton pool
llm_pool = LLMPool()


def _repair_truncated_json(text: str) -> str:
    """
    Attempt to repair truncated JSON by closing open structures.
    Handles cases where max_output_tokens cut off the response mid-JSON.
    """
    # Count unmatched braces/brackets
    stack = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()

    # If we're inside a string, close it
    if in_string:
        text += '"'

    # Close any remaining open structures in reverse order
    for opener in reversed(stack):
        if opener == '{':
            text += '}'
        elif opener == '[':
            text += ']'

    return text


def _extract_field_from_truncated(raw_text: str, field: str) -> str | None:
    """Extract a specific field value from possibly-truncated JSON using regex."""
    # Match "field": "value" or "field": number
    pattern = rf'"{field}"\s*:\s*"([^"]*(?:\\.[^"]*)*)"'
    m = re.search(pattern, raw_text)
    if m:
        return m.group(1)
    # Try numeric
    pattern = rf'"{field}"\s*:\s*([\d.]+)'
    m = re.search(pattern, raw_text)
    if m:
        return m.group(1)
    return None


def _ensure_complete_result(result: dict, raw_text: str) -> dict:
    """
    Ensure a parsed (possibly partial) result has all required fields.
    Fills missing fields with regex-extracted values or sensible defaults.
    """
    defaults = {
        "verdict": "NEUTRAL",
        "confidence": 0.5,
        "score": 5.0,
        "reasoning": "",
        "key_points": [],
        "risks": [],
        "catalysts": [],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            # Try regex extraction for scalar fields
            if key in ("verdict", "confidence", "score", "reasoning"):
                extracted = _extract_field_from_truncated(raw_text, key)
                if extracted:
                    if key == "confidence":
                        result[key] = float(extracted)
                    elif key == "score":
                        result[key] = float(extracted)
                    elif key == "verdict":
                        result[key] = extracted.upper()
                    else:
                        result[key] = extracted
                else:
                    result[key] = default
            elif key in ("key_points", "risks", "catalysts"):
                # Try regex for arrays
                pattern = rf'"{key}"\s*:\s*(\[.*?\])'
                m = re.search(pattern, raw_text, re.DOTALL)
                if m:
                    try:
                        result[key] = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        result[key] = default
                else:
                    result[key] = default
            else:
                result[key] = default
    return result


def parse_agent_response(raw_text: str) -> dict:
    """
    Parse structured JSON from agent response.
    Handles:
    - Markdown code blocks (```json ... ```)
    - Gemini 2.5 Flash thinking model responses (may include <think> blocks)
    - Truncated JSON (from max_output_tokens cutoff) — attempts repair
    - Raw JSON without fences
    """
    if not raw_text or not raw_text.strip():
        return {
            "verdict": "NEUTRAL", "confidence": 0.3, "score": 5.0,
            "reasoning": "Empty response from LLM",
            "key_points": ["Empty response"], "risks": [], "catalysts": [],
        }

    text = raw_text.strip()

    # Strip Gemini thinking blocks if present (<think>...</think> or similar)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL).strip()

    # Strip ALL markdown code fences — handle multiple occurrences
    # Look for ```json ... ``` first
    json_blocks = re.findall(r'```json\s*(.*?)```', text, re.DOTALL)
    if json_blocks:
        # Use the longest JSON block (most likely the full response)
        text = max(json_blocks, key=len).strip()
    else:
        # Try generic ``` ... ```
        code_blocks = re.findall(r'```\s*(.*?)```', text, re.DOTALL)
        if code_blocks:
            # Find the one that looks like JSON
            for block in code_blocks:
                if '{' in block:
                    text = block.strip()
                    break

    # If still has unclosed ``` fence (truncated response), strip the opening fence
    if '```json' in text and '```' not in text.split('```json', 1)[1]:
        text = text.split('```json', 1)[1].strip()
    elif text.startswith('```'):
        text = text[3:].strip()

    # Attempt 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Find JSON object boundaries
    start = text.find("{")
    if start >= 0:
        # Find the best matching end brace
        end = text.rfind("}") + 1
        if end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Attempt 3: Repair truncated JSON
        json_fragment = text[start:]
        repaired = _repair_truncated_json(json_fragment)
        try:
            result = json.loads(repaired)
            if isinstance(result, dict) and result.get("verdict"):
                return _ensure_complete_result(result, raw_text)
        except json.JSONDecodeError:
            pass

        # Attempt 4: More aggressive truncation repair
        # Remove trailing incomplete key-value pairs before closing
        json_text = text[start:]
        for trim_at in [
            json_text.rfind('",'),
            json_text.rfind('"],'),
            json_text.rfind('},'),
            json_text.rfind('],'),
            json_text.rfind(': "'),
        ]:
            if trim_at > 0:
                candidate = json_text[:trim_at]
                if candidate.count('"') % 2 != 0:
                    candidate += '"'
                repaired = _repair_truncated_json(candidate)
                try:
                    result = json.loads(repaired)
                    if isinstance(result, dict) and result.get("verdict"):
                        return _ensure_complete_result(result, raw_text)
                except json.JSONDecodeError:
                    continue

    # Attempt 5: Regex extraction from raw text — last resort before full fallback
    verdict = _extract_field_from_truncated(raw_text, "verdict")
    confidence = _extract_field_from_truncated(raw_text, "confidence")
    score = _extract_field_from_truncated(raw_text, "score")
    reasoning = _extract_field_from_truncated(raw_text, "reasoning")

    if verdict:
        result = {
            "verdict": verdict.upper(),
            "confidence": float(confidence) if confidence else 0.5,
            "score": float(score) if score else 5.0,
            "reasoning": reasoning or raw_text[:2000],
            "key_points": [],
            "risks": [],
            "catalysts": [],
        }
        # Try to extract arrays
        for field in ["key_points", "risks", "catalysts"]:
            pattern = rf'"{field}"\s*:\s*(\[.*?\])'
            m = re.search(pattern, raw_text, re.DOTALL)
            if m:
                try:
                    result[field] = json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
        return result

    # Final fallback — nothing parseable
    return {
        "verdict": "NEUTRAL",
        "confidence": 0.3,
        "score": 5.0,
        "reasoning": raw_text[:2000],
        "key_points": ["Failed to parse structured response"],
        "risks": [],
        "catalysts": [],
    }

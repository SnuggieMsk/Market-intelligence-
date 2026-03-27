"""
LLM provider abstraction layer.
Supports: Google Gemini, Groq, OpenRouter.
Round-robins across multiple API keys with proper 429 rate limit handling.
429 errors trigger exponential backoff WITHOUT consuming quota.
"""

import json
import time
import threading
import requests
from config.settings import (
    GEMINI_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEY,
    GEMINI_MODEL, GROQ_MODEL, OPENROUTER_MODEL,
    GEMINI_RPM_PER_KEY, GROQ_RPM_PER_KEY, OPENROUTER_RPM,
)


class RateLimiter:
    """
    Pre-emptive rate limiter that throttles BEFORE making calls.
    Keeps a sliding window of timestamps and sleeps if at capacity.
    """

    def __init__(self, rpm_limit: int):
        self.rpm_limit = rpm_limit
        self.timestamps: list[float] = []
        self.lock = threading.Lock()

    def acquire(self):
        """Wait until we're safely under the rate limit, then record the call."""
        with self.lock:
            now = time.time()
            # Purge timestamps older than 60s
            self.timestamps = [t for t in self.timestamps if now - t < 60]

            if len(self.timestamps) >= self.rpm_limit:
                # Wait until the oldest call falls out of the window
                sleep_time = 60 - (now - self.timestamps[0]) + 1.0
                if sleep_time > 0:
                    print(f"[RateLimit] Throttling for {sleep_time:.1f}s (at {self.rpm_limit} RPM limit)")
                    time.sleep(sleep_time)

            self.timestamps.append(time.time())

    def backoff_after_429(self, attempt: int):
        """
        Called when a 429 is received. Does NOT count as a used request.
        Exponential backoff: 4s, 8s, 16s, 32s.
        """
        wait = min(10 * (2 ** attempt), 120)  # 10s, 20s, 40s, 80s, 120s
        print(f"[RateLimit] 429 received — backing off {wait}s (attempt {attempt + 1})")
        time.sleep(wait)


class LLMPool:
    """
    Manages multiple API keys across Gemini, Groq, and OpenRouter.
    Features:
    - Round-robin key rotation
    - Pre-emptive rate limiting (never hits 429 under normal conditions)
    - 429 exponential backoff with retry (no quota wasted)
    - Automatic fallback chain: preferred → next → next
    """

    MAX_RETRIES = 5

    def __init__(self):
        self._gemini_idx = 0
        self._groq_idx = 0
        self._lock = threading.Lock()

        # Per-key rate limiters
        self._gemini_limiters = {k: RateLimiter(GEMINI_RPM_PER_KEY) for k in GEMINI_API_KEYS}
        self._groq_limiters = {k: RateLimiter(GROQ_RPM_PER_KEY) for k in GROQ_API_KEYS}
        self._openrouter_limiter = RateLimiter(OPENROUTER_RPM)

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

    # ── Gemini ────────────────────────────────────────────────────────────────

    def call_gemini(self, prompt: str, system_instruction: str = "") -> str:
        """Call Gemini with rate limiting and 429 retry."""
        for attempt in range(self.MAX_RETRIES):
            key = self._next_gemini_key()
            if not key:
                raise RuntimeError("No Gemini API keys configured")

            limiter = self._gemini_limiters[key]
            limiter.acquire()

            try:
                from google import genai

                client = genai.Client(api_key=key)
                contents = prompt
                config = {"temperature": 0.7, "max_output_tokens": 4096}
                if system_instruction:
                    config["system_instruction"] = system_instruction

                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=config,
                )
                return response.text

            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str:
                    limiter.backoff_after_429(attempt)
                    continue  # Retry with next key
                raise  # Non-rate-limit error, bubble up

        raise RuntimeError(f"Gemini: exhausted {self.MAX_RETRIES} retries due to rate limits")

    # ── Groq ──────────────────────────────────────────────────────────────────

    def call_groq(self, prompt: str, system_instruction: str = "") -> str:
        """Call Groq with rate limiting and 429 retry."""
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
        """Call OpenRouter (free models) with rate limiting and 429 retry."""
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

    # ── Unified Call with Fallback Chain ──────────────────────────────────────

    def call_llm(self, prompt: str, system_instruction: str = "",
                 prefer: str = "gemini") -> str:
        """
        Call LLM with automatic fallback chain.
        Order: preferred provider → remaining providers.
        All 429 errors are handled with backoff BEFORE falling back.
        """
        all_providers = {
            "gemini": self.call_gemini,
            "groq": self.call_groq,
            "openrouter": self.call_openrouter,
        }

        # Build ordered fallback chain
        order = [prefer]
        for p in ["gemini", "groq", "openrouter"]:
            if p not in order:
                order.append(p)

        last_error = None
        for provider_name in order:
            fn = all_providers.get(provider_name)
            if not fn:
                continue
            try:
                return fn(prompt, system_instruction)
            except Exception as e:
                last_error = e
                print(f"[LLM] {provider_name} failed: {e}, trying next provider...")
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


# Singleton pool
llm_pool = LLMPool()


def parse_agent_response(raw_text: str) -> dict:
    """
    Parse structured JSON from agent response.
    Handles markdown code blocks and raw JSON.
    """
    text = raw_text.strip()

    # Strip markdown code fences
    if "```json" in text:
        text = text.split("```json", 1)[1]
        text = text.split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1]
        text = text.split("```", 1)[0]

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Return a structured fallback
        return {
            "verdict": "NEUTRAL",
            "confidence": 0.3,
            "score": 5.0,
            "reasoning": raw_text[:2000],
            "key_points": ["Failed to parse structured response"],
            "risks": [],
            "catalysts": [],
        }

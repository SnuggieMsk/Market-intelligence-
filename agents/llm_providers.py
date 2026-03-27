"""
LLM provider abstraction layer.
Supports: Google Gemini, Groq, OpenRouter.

Strategy: health-check-first, then only use alive providers.
- At startup, each provider is tested with 1 tiny call (no retries)
- Dead providers are BLOCKED — zero wasted calls or backoff time
- Alive providers get round-robin key rotation + light retry (2 attempts max)
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
        """Short backoff: 5s, 10s. We already know the provider is alive."""
        wait = min(5 * (2 ** attempt), 15)  # 5s, 10s, 15s max
        print(f"[RateLimit] 429 — backing off {wait}s (attempt {attempt + 1})")
        time.sleep(wait)


class LLMPool:
    """
    Manages multiple API keys across Gemini, Groq, and OpenRouter.

    Health-check-first strategy:
    1. check_provider_health() tests each provider once at startup
    2. Only alive providers are used — dead ones are skipped instantly
    3. Max 2 retries per provider (not 5) since we know they're alive
    4. Short backoff (5s/10s) instead of 10s→120s
    """

    MAX_RETRIES = 2  # Light retry — we already know the provider works

    def __init__(self):
        self._gemini_idx = 0
        self._groq_idx = 0
        self._lock = threading.Lock()

        # Per-key rate limiters
        self._gemini_limiters = {k: RateLimiter(GEMINI_RPM_PER_KEY) for k in GEMINI_API_KEYS}
        self._groq_limiters = {k: RateLimiter(GROQ_RPM_PER_KEY) for k in GROQ_API_KEYS}
        self._openrouter_limiter = RateLimiter(OPENROUTER_RPM)

        # Alive providers — set by check_provider_health()
        # None means "not checked yet" (will try all); empty set means "all dead"
        self._alive_providers: set | None = None

    def set_alive_providers(self, alive: list[str]):
        """Called after health check to lock in which providers to use."""
        self._alive_providers = set(alive)

    def _is_alive(self, provider: str) -> bool:
        """Check if provider passed health check. If no check done, allow all."""
        if self._alive_providers is None:
            return True  # No health check run yet, try everything
        return provider in self._alive_providers

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

        # Test Gemini
        try:
            key = self._next_gemini_key()
            if not key:
                results["gemini"] = False
            else:
                from google import genai
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model=GEMINI_MODEL, contents=test_prompt,
                    config={"temperature": 0, "max_output_tokens": 10},
                )
                results["gemini"] = bool(response.text and len(response.text.strip()) > 0)
        except Exception:
            results["gemini"] = False

        # Test Groq
        try:
            key = self._next_groq_key()
            if not key:
                results["groq"] = False
            else:
                from groq import Groq
                client = Groq(api_key=key)
                response = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": test_prompt}],
                    temperature=0, max_tokens=10,
                )
                results["groq"] = bool(response.choices[0].message.content)
        except Exception:
            results["groq"] = False

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
            "gemini": self.call_gemini,
            "groq": self.call_groq,
            "openrouter": self.call_openrouter,
        }

        # Build order: prefer first, then other alive providers
        order = [prefer]
        for p in ["gemini", "groq", "openrouter"]:
            if p != prefer:
                order.append(p)

        # Filter to alive only
        order = [p for p in order if self._is_alive(p)]

        if not order:
            raise RuntimeError("No LLM providers are alive. Run health check or wait for rate limits to reset.")

        last_error = None
        for provider_name in order:
            fn = all_providers[provider_name]
            try:
                result = fn(prompt, system_instruction)
                return result
            except Exception as e:
                last_error = e
                print(f"[LLM] {provider_name} failed: {e}, trying next...")
                continue

        raise RuntimeError(f"All alive LLM providers failed. Last error: {last_error}")


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

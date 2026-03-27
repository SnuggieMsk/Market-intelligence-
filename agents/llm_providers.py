"""
LLM provider abstraction layer.
Round-robins across multiple API keys to maximize free tier throughput.
Supports Google Gemini and Groq.
"""

import json
import time
import threading
from config.settings import (
    GEMINI_API_KEYS, GROQ_API_KEYS, GEMINI_MODEL, GROQ_MODEL,
    GEMINI_RPM_LIMIT, GROQ_RPM_LIMIT
)


class RateLimiter:
    """Simple token-bucket rate limiter per key."""

    def __init__(self, rpm_limit):
        self.rpm_limit = rpm_limit
        self.timestamps = []
        self.lock = threading.Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            self.timestamps = [t for t in self.timestamps if now - t < 60]
            if len(self.timestamps) >= self.rpm_limit:
                sleep_time = 60 - (now - self.timestamps[0]) + 0.5
                time.sleep(max(0, sleep_time))
            self.timestamps.append(time.time())


class LLMPool:
    """
    Manages multiple API keys and distributes calls across providers.
    Automatically falls back between Gemini and Groq.
    """

    def __init__(self):
        self._gemini_idx = 0
        self._groq_idx = 0
        self._gemini_limiters = {k: RateLimiter(GEMINI_RPM_LIMIT) for k in GEMINI_API_KEYS}
        self._groq_limiters = {k: RateLimiter(GROQ_RPM_LIMIT) for k in GROQ_API_KEYS}
        self._lock = threading.Lock()

    def _next_gemini_key(self):
        with self._lock:
            if not GEMINI_API_KEYS:
                return None
            key = GEMINI_API_KEYS[self._gemini_idx % len(GEMINI_API_KEYS)]
            self._gemini_idx += 1
            return key

    def _next_groq_key(self):
        with self._lock:
            if not GROQ_API_KEYS:
                return None
            key = GROQ_API_KEYS[self._groq_idx % len(GROQ_API_KEYS)]
            self._groq_idx += 1
            return key

    def call_gemini(self, prompt: str, system_instruction: str = "") -> str:
        key = self._next_gemini_key()
        if not key:
            raise RuntimeError("No Gemini API keys configured")

        self._gemini_limiters[key].wait_if_needed()

        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            GEMINI_MODEL,
            system_instruction=system_instruction if system_instruction else None,
        )
        response = model.generate_content(prompt)
        return response.text

    def call_groq(self, prompt: str, system_instruction: str = "") -> str:
        key = self._next_groq_key()
        if not key:
            raise RuntimeError("No Groq API keys configured")

        self._groq_limiters[key].wait_if_needed()

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

    def call_llm(self, prompt: str, system_instruction: str = "",
                 prefer: str = "gemini") -> str:
        """
        Call LLM with automatic fallback.
        prefer: 'gemini' or 'groq'
        """
        providers = (
            [("gemini", self.call_gemini), ("groq", self.call_groq)]
            if prefer == "gemini"
            else [("groq", self.call_groq), ("gemini", self.call_gemini)]
        )

        last_error = None
        for name, fn in providers:
            try:
                return fn(prompt, system_instruction)
            except Exception as e:
                last_error = e
                print(f"[LLM] {name} failed: {e}, trying next...")
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

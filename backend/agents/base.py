import json
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI
from tavily import TavilyClient

from backend.config import settings


class TavilyQuotaExceededError(Exception):
    """Raised when Tavily returns HTTP 433 (monthly search quota exhausted)."""


class BaseAgent:
    def __init__(self, name: str):
        self.name = name
        self.model = settings.llm_model
        self._llm = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=90.0,  # fail fast rather than hang indefinitely
        )
        self._tavily = TavilyClient(api_key=settings.tavily_api_key) if settings.tavily_api_key else None
        self._log = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        log_dir = settings.logs_dir / self.name.lower().replace(" ", "_")
        log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(self.name)
        if not logger.handlers:
            handler = logging.FileHandler(log_dir / "agent.log")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            logger.addHandler(logging.StreamHandler())
        logger.setLevel(settings.log_level)
        return logger

    def web_search(self, query: str, max_results: int = 5) -> list[dict]:
        """Execute a web search using Tavily."""
        if not self._tavily:
            self._log.warning("Tavily API key not set — skipping search for: %s", query)
            return []
        try:
            response = self._tavily.search(query=query, max_results=max_results, search_depth="advanced")
            results = response.get("results", [])
            self._log.debug("Search '%s' → %d results", query, len(results))
            return results
        except Exception as e:
            if "433" in str(e):
                self._log.error(
                    "Tavily quota exhausted (HTTP 433) — renew API key at app.tavily.com"
                )
                raise TavilyQuotaExceededError(
                    "Tavily monthly search quota exhausted. Renew at app.tavily.com."
                )
            self._log.error("Search error for '%s': %s", query, e)
            return []

    def _call(
        self,
        messages: list[dict],
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Call the LLM and return the text response."""
        if system:
            messages = [{"role": "system", "content": system}] + messages
        try:
            response = self._llm.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            msg = response.choices[0].message
            # Some reasoning models (MiniMax M2.7) return final output in content
            # but may also expose chain-of-thought in reasoning_content.
            # If content is empty, fall back to reasoning_content as the answer.
            content = msg.content or ""
            if not content.strip():
                content = getattr(msg, "reasoning_content", "") or ""
            return self._strip_thinking(content)
        except Exception as e:
            self._log.error("LLM call failed: %s", e)
            raise

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Strip <think>/<thinking> blocks, falling back to their content if nothing remains."""
        import re

        # First try: strip thinking blocks, keep everything outside them
        stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        stripped = re.sub(r"<thinking>.*?</thinking>", "", stripped, flags=re.DOTALL)
        result = stripped.strip()
        if result:
            return result

        # Fallback: model put the entire answer inside the think block (common in MiniMax M2.7).
        # Extract the innermost content and return it.
        m = re.search(r"<think[^>]*>(.*?)</think>", text, flags=re.DOTALL | re.IGNORECASE)
        if not m:
            m = re.search(r"<thinking[^>]*>(.*?)</thinking>", text, flags=re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else text.strip()

    def _stream(
        self,
        messages: list[dict],
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ):
        """Stream LLM response, yielding text chunks with thinking tokens stripped."""
        if system:
            messages = [{"role": "system", "content": system}] + messages
        try:
            stream = self._llm.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            in_thinking = False
            buf = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                # Some APIs expose reasoning tokens in a separate field — skip entirely
                if getattr(delta, "reasoning_content", None):
                    continue
                content = delta.content
                if not content:
                    continue
                buf += content
                # State machine: strip <think>...</think> blocks mid-stream
                while buf:
                    if in_thinking:
                        end = buf.find("</think>")
                        if end == -1:
                            buf = ""  # still inside thinking block, consume and wait
                            break
                        buf = buf[end + 8:]  # skip past </think>
                        in_thinking = False
                    else:
                        start = buf.find("<think>")
                        if start == -1:
                            yield buf
                            buf = ""
                            break
                        if start > 0:
                            yield buf[:start]  # yield content before the tag
                        buf = buf[start + 7:]  # skip past <think>
                        in_thinking = True
        except Exception as e:
            self._log.error("LLM stream failed: %s", e)
            raise

    def _call_json(
        self,
        messages: list[dict],
        system: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Any:
        """Call LLM expecting a JSON response. Returns parsed dict/list."""
        raw = self._call(messages, system=system, temperature=temperature, max_tokens=max_tokens)
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            self._log.warning("JSON parse failed, attempting extraction from: %s", clean[:200])
            # MiniMax M2.7 narrates before answering — the real JSON is at the END.
            # Walk backwards from the last closing bracket to find the matching opener.
            for open_ch, close_ch in [("[", "]"), ("{", "}")]:
                candidate = self._extract_last_json_block(clean, open_ch, close_ch)
                if candidate:
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
            raise ValueError(f"Could not parse JSON from LLM response: {raw[:500]}")

    @staticmethod
    def _extract_last_json_block(text: str, open_ch: str, close_ch: str) -> str | None:
        """Find the last complete JSON array/object by bracket-matching from the end."""
        last_close = text.rfind(close_ch)
        if last_close == -1:
            return None
        depth = 0
        in_string = False
        escape_next = False
        for i in range(last_close, -1, -1):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == close_ch:
                depth += 1
            elif ch == open_ch:
                depth -= 1
                if depth == 0:
                    return text[i:last_close + 1]
        return None

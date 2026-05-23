import json
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI
from tavily import TavilyClient

from backend.config import settings


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
            return self._strip_thinking(response.choices[0].message.content or "")
        except Exception as e:
            self._log.error("LLM call failed: %s", e)
            raise

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> and <thinking>...</thinking> blocks from text."""
        import re
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
        return text.strip()

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
            # Try to find JSON object/array in text
            for start_char, end_char in [("{", "}"), ("[", "]")]:
                start = clean.find(start_char)
                end = clean.rfind(end_char)
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(clean[start:end + 1])
                    except json.JSONDecodeError:
                        pass
            raise ValueError(f"Could not parse JSON from LLM response: {raw[:500]}")

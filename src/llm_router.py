# src/llm_router.py
import logging
import time
from crewai import LLM

logger = logging.getLogger(__name__)


class LLMRouter:
    """Handles the abstraction, validation, and instantiation of swappable 
    compute infrastructures (LLM providers) for the application."""

    _REQUEST_TIMEOUT_SECONDS = 90
    _LOCAL_MAX_OUTPUT_TOKENS = 1024

    # Note: AWS Bedrock paths use the format: bedrock/<provider>.<model>
    _BACKEND_MAP = {
        "Local Machine (Ollama - Llama3.2:3b)": {
            "model_string": "ollama/llama3.2:3b",
            "base_url": "http://localhost:11434"
        },
        "Local Machine (Ollama - Qwen3.5:9b)": {
            "model_string": "ollama/qwen3.5:9b",
            "base_url": "http://localhost:11434",
            "reasoning_effort": "none",
        },
        "Enterprise Cloud (AWS Bedrock - Claude 3.5 Sonnet) - NOT IMPLEMENTED": {
            "model_string": "bedrock/anthropic.claude-3-5-sonnet-v1:0",
            "base_url": None
        }
    }

    @classmethod
    def get_supported_backends(cls) -> list[str]:
        """Returns a list of human-readable compute labels for the UI dropdown."""
        return list(cls._BACKEND_MAP.keys())

    @classmethod
    def create_backend(cls, ui_choice: str) -> LLM:
        """Factory method that validates requirements and instantiates a 
        standardized CrewAI LLM object based on the user's interface selection."""
        
        if ui_choice not in cls._BACKEND_MAP:
            raise ValueError(f"Unsupported infrastructure selection: '{ui_choice}'")

        config = cls._BACKEND_MAP[ui_choice]
        model_str = config["model_string"]
        base_url = config["base_url"]
        logger.info("Initializing LLM backend=%s", ui_choice)

        started = time.perf_counter()
        try:
            # Instantiate the unified CrewAI wrapper. 
            # This object behaves identically regardless of the backing engine.
            llm_options = {"timeout": cls._REQUEST_TIMEOUT_SECONDS}
            if model_str.startswith("ollama/"):
                llm_options["max_tokens"] = cls._LOCAL_MAX_OUTPUT_TOKENS
            if "reasoning_effort" in config:
                llm_options["reasoning_effort"] = config["reasoning_effort"]

            llm = LLM(
                model=model_str,
                base_url=base_url,
                **llm_options
            )
            logger.info(
                "LLM backend initialized model=%s duration_seconds=%.2f",
                model_str,
                time.perf_counter() - started,
            )
            return llm
        except Exception as e:
            logger.error(
                "LLM backend initialization failed model=%s error_type=%s "
                "duration_seconds=%.2f",
                model_str,
                type(e).__name__,
                time.perf_counter() - started,
            )
            raise RuntimeError(
                f"Failed to initialize compute connection for {model_str}. "
                f"Details: {str(e)}"
            )
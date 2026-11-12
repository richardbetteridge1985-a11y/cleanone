# src/llm_router.py
import logging
import os
import time
from crewai import LLM

logger = logging.getLogger(__name__)


class LLMRouter:
    """Handles the abstraction, validation, and instantiation of swappable 
    compute infrastructures (LLM providers) for the application."""

    _REQUEST_TIMEOUT_SECONDS = 90
    _MAX_OUTPUT_TOKENS = 1024
    _LOCAL_CONTEXT_TOKENS = 4096

    # Note: AWS Bedrock paths use the format: bedrock/<provider>.<model>
    _BACKEND_MAP = {
        "Local Machine (Ollama - Llama3.2:3b)": {
            "model_string": "ollama/llama3.2:3b",
            "base_url": "http://localhost:11434"
        },
        "Enterprise Cloud (AWS Bedrock - Claude 3.5 Sonnet)": {
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

        # If the user selects the AWS Bedrock route, programmatically verify 
        # that their system environment has AWS keys set before calling the service.
        if model_str.startswith("bedrock/"):
            cls._verify_aws_credentials()

        started = time.perf_counter()
        try:
            # Instantiate the unified CrewAI wrapper. 
            # This object behaves identically regardless of the backing engine.
            llm_options = {
                "timeout": cls._REQUEST_TIMEOUT_SECONDS,
                "max_tokens": cls._MAX_OUTPUT_TOKENS,
            }
            if model_str.startswith("ollama/"):
                llm_options["num_ctx"] = cls._LOCAL_CONTEXT_TOKENS

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

    @staticmethod
    def _verify_aws_credentials():
        """Internal helper to ensure enterprise environment parameters are accessible."""
        required_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]

        if missing_vars:
            raise EnvironmentError(
                f"Missing required AWS Environment Variables for Bedrock authentication: {missing_vars}. "
                f"Please configure these inside your local environment or VS Code launch settings."
            )
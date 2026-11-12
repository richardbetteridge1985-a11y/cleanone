# main.py
import logging
import time

from src.logging_config import configure_logging
from src.ui import build_and_launch_ui
from src.rag_engine import RAGEngine

if __name__ == "__main__":
    configure_logging()
    logger = logging.getLogger(__name__)
    startup_started = time.perf_counter()
    logger.info("Application startup started")

    # Initialize the RAG Engine to ensure the local knowledge base is ready for retrieval-augmented generation tasks.
    try:
        RAGEngine.initialize_knowledge_base()
    except Exception as error:
        logger.error(
            "Knowledge base startup failed error_type=%s",
            type(error).__name__,
        )
        raise
    logger.info(
        "Application startup completed duration_seconds=%.2f",
        time.perf_counter() - startup_started,
    )

    # Start the app
    try:
        build_and_launch_ui()
    except Exception as error:
        logger.error(
            "Application stopped unexpectedly error_type=%s",
            type(error).__name__,
        )
        raise
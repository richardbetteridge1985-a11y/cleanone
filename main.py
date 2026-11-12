# main.py
from src.ui import build_and_launch_ui
from src.rag_engine import RAGEngine

if __name__ == "__main__":
    # Initialize the RAG Engine to ensure the local knowledge base is ready for retrieval-augmented generation tasks.
    RAGEngine.initialize_knowledge_base()

    # Start the app
    build_and_launch_ui()
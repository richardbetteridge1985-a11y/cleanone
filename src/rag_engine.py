# src/rag_engine.py
import os
import glob
import hashlib
import shutil
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from crewai.tools import tool
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    query: str = Field(..., description="The architectural concept or rule to look up.")

class ScopedKnowledgeTool(BaseTool):
    name: str = "Search Specialist Knowledge Base"
    description: str = "Searches your assigned architectural guideline document for specific rules and patterns."
    args_schema: type[BaseModel] = SearchInput
    source_filter: str | None = None

    def _run(self, query: str) -> str:
        return RAGEngine.query_knowledge_base(query, source_filter=self.source_filter)

class RAGEngine:
    """Manages reading, hashing, chunking, and embedding local Markdown files 
    into a persistent local vector database with automatic update detection."""
    
    _KB_DIR = "knowledge_base"
    _DB_PATH = os.path.join("config", "chroma_db")
    _HASH_FILE = os.path.join("config", "kb_hash.txt")
    _COLLECTION_NAME = "architectural_patterns"

    @classmethod
    def _calculate_directory_hash(cls) -> str:
        """Generates a single SHA-256 fingerprint across all .md files in knowledge_base/."""
        hasher = hashlib.sha256()
        md_files = sorted(glob.glob(os.path.join(cls._KB_DIR, "*.md")))
        
        for file_path in md_files:
            # Include filename and file content in the hash
            hasher.update(os.path.basename(file_path).encode("utf-8"))
            with open(file_path, "rb") as f:
                hasher.update(f.read())
                
        return hasher.hexdigest()

    @classmethod
    def initialize_knowledge_base(cls):
        """Scans local documents for updates and rebuilds the vector index if changes occur."""
        os.makedirs(cls._KB_DIR, exist_ok=True)
        os.makedirs("config", exist_ok=True)

        md_files = sorted(glob.glob(os.path.join(cls._KB_DIR, "*.md")))
        if not md_files:
            print(f"⚠️ [RAG Engine] No .md files found in '{cls._KB_DIR}/'. Add documents to index.")
            return

        # 1. Check if documents have changed since last boot
        current_hash = cls._calculate_directory_hash()
        previous_hash = ""
        if os.path.exists(cls._HASH_FILE):
            with open(cls._HASH_FILE, "r", encoding="utf-8") as f:
                previous_hash = f.read().strip()

        if current_hash == previous_hash and os.path.exists(cls._DB_PATH):
            print("📦 [RAG Engine] Local knowledge base is up to date. Skipping re-indexing.")
            return

        print("🔄 [RAG Engine] Document changes detected! Rebuilding local vector index...")

        # 2. Wipe old database so deleted/edited paragraphs don't leave ghost data
        if os.path.exists(cls._DB_PATH):
            shutil.rmtree(cls._DB_PATH)

        client = chromadb.PersistentClient(path=cls._DB_PATH)
        collection = client.get_or_create_collection(name=cls._COLLECTION_NAME)

        # 3. Read, chunk, and index each file with source metadata
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,
            chunk_overlap=60,
            separators=["\n\n", "\n", " ", ""]
        )

        total_chunks = 0
        for file_path in md_files:
            filename = os.path.basename(file_path)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            chunks = text_splitter.split_text(content)
            for idx, text_block in enumerate(chunks):
                collection.add(
                    documents=[text_block],
                    metadatas=[{"source": filename}],
                    ids=[f"{filename}_chunk_{idx}"]
                )
                total_chunks += 1

        # 4. Save the new fingerprint
        with open(cls._HASH_FILE, "w", encoding="utf-8") as f:
            f.write(current_hash)

        print(f"✅ [RAG Engine] Indexed {total_chunks} chunks across {len(md_files)} local documents.")

    @classmethod
    def query_knowledge_base(cls, search_query: str, n_results: int = 3, source_filter: str | None = None) -> str:
        """Performs a semantic vector search, optionally scoped to a single source document."""
        try:
            client = chromadb.PersistentClient(path=cls._DB_PATH)
            collection = client.get_collection(name=cls._COLLECTION_NAME)
            
            # Apply metadata filter if the agent has a dedicated area of concern
            where_clause = {"source": source_filter} if source_filter else None
            
            results = collection.query(
                query_texts=[search_query],
                n_results=n_results,
                where=where_clause
            )
            
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            
            if not docs:
                return f"No matching guidelines found in {source_filter or 'knowledge base'}."

            formatted_results = []
            for doc, meta in zip(docs, metas):
                source = meta.get("source", "Unknown")
                formatted_results.append(f"[Source: {source}]\n{doc}")
                
            return "\n---\n".join(formatted_results)
        except Exception as e:
            return f"Error executing context retrieval logic: {str(e)}"



@tool("Search Architectural Knowledge Base")
def search_architecture_kb(query: str) -> str:
    """Useful when you need to query local vetted guidelines, standards, and patterns 
    for Domain-Driven Design (DDD), Clean Architecture, and coding standards."""
    return RAGEngine.query_knowledge_base(query)

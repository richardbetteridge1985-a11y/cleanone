# src/proposal_processor.py
import logging
import os
import re
import tempfile
import shutil
import time
import docx
import pymupdf
import chromadb
import ollama
import boto3
from botocore.config import Config
from langchain_text_splitters import RecursiveCharacterTextSplitter
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr


logger = logging.getLogger(__name__)


class ProposalProcessor:
    """Extracts proposal content and stores it in a local review-scoped vector index."""

    _SESSION_DB_PATH = os.path.join("config", "session_proposal_db")
    _COLLECTION_NAME = "active_proposal"
    _MAX_UPLOAD_BYTES = 25 * 1024 * 1024
    _MAX_DIAGRAMS_PER_UPLOAD = 5
    _VISION_TIMEOUT_SECONDS = 120
    _LOCAL_VISION_MAX_OUTPUT_TOKENS = 512
    _OLLAMA_VISION_MODEL = os.getenv("CLEANONE_OLLAMA_VISION_MODEL", "qwen3.5:9b")
    _SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
    _SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".md"} | _SUPPORTED_IMAGE_EXTENSIONS

    @classmethod
    def process_file(cls, file_path: str, backend_choice: str, progress_callback=None) -> str:
        """Extracts text and diagrams, describes visuals, and builds a searchable session index."""
        started = time.perf_counter()
        _, raw_ext = os.path.splitext(file_path)
        ext = raw_ext.lower()
        if ext not in cls._SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file format: {ext or '[no extension]'}. "
                "Upload .docx, .pdf, .md, .png, .jpg, or .jpeg."
            )
        file_size_bytes = os.path.getsize(file_path)
        if file_size_bytes > cls._MAX_UPLOAD_BYTES:
            raise ValueError(
                f"Upload exceeds the {cls._MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
            )
        logger.info(
            "Proposal processing started file_type=%s file_size_bytes=%d backend=%s",
            ext,
            file_size_bytes,
            backend_choice,
        )
        os.makedirs(cls._SESSION_DB_PATH, exist_ok=True)
        client = chromadb.PersistentClient(path=cls._SESSION_DB_PATH)

        # Replace the prior proposal index without masking storage failures.
        collection_names = {
            collection if isinstance(collection, str) else collection.name
            for collection in client.list_collections()
        }
        if cls._COLLECTION_NAME in collection_names:
            client.delete_collection(name=cls._COLLECTION_NAME)

        temp_img_dir = tempfile.mkdtemp(prefix="proposal_imgs_")

        try:
            if progress_callback:
                progress_callback("Extracting text sections and embedded diagrams...")

            if ext == ".docx":
                sections = cls._extract_docx(file_path, temp_img_dir)
            elif ext == ".pdf":
                sections = cls._extract_pdf(file_path, temp_img_dir)
            elif ext == ".md":
                sections = cls._extract_markdown(file_path)
            elif ext in cls._SUPPORTED_IMAGE_EXTENSIONS:
                sections = [{
                    "heading": f"Uploaded Solution Image: {os.path.basename(file_path)}",
                    "text": "",
                    "images": [file_path],
                }]
            else:
                raise ValueError(f"Unsupported file format: {ext}")

            total_images = sum(len(s["images"]) for s in sections)
            if total_images > cls._MAX_DIAGRAMS_PER_UPLOAD:
                raise ValueError(
                    f"Proposal contains {total_images} diagrams; the limit is "
                    f"{cls._MAX_DIAGRAMS_PER_UPLOAD}. Reduce the number of diagrams "
                    "or split the proposal before reviewing it."
                )
            logger.info(
                "Proposal extraction completed sections=%d diagrams=%d "
                "duration_seconds=%.2f",
                len(sections),
                total_images,
                time.perf_counter() - started,
            )
            img_counter = 0
            analysed_images = 0
            failed_images = 0
            vision_failure_reason = None
            vision_preflight_error = None
            if total_images and "Ollama" in backend_choice:
                vision_preflight_error = cls._check_ollama_vision_model()

            for section in sections:
                diagram_descriptions = []
                for img_path in section["images"]:
                    img_counter += 1
                    if progress_callback:
                        progress_callback(
                            f"Analysing diagram {img_counter}/{total_images} "
                            f"under '{section['heading']}'..."
                        )
                    logger.info(
                        "Proposal diagram analysis started diagram=%d total=%d backend=%s",
                        img_counter,
                        total_images,
                        backend_choice,
                    )
                    if vision_preflight_error:
                        desc = vision_preflight_error
                    else:
                        desc = cls._describe_diagram(
                            img_path, section["heading"], backend_choice
                        )

                    if desc.startswith("[Vision Analysis Failed:"):
                        failed_images += 1
                        vision_failure_reason = vision_failure_reason or desc.strip("[]")
                        diagram_descriptions.append(
                            "[Diagram image present; vision analysis failed.]"
                        )
                    else:
                        analysed_images += 1
                        diagram_descriptions.append(
                            f"[Extracted Diagram Description]:\n{desc}"
                        )

                if diagram_descriptions:
                    section["text"] += "\n\n" + "\n\n".join(diagram_descriptions)

            if progress_callback:
                progress_callback("Indexing proposal into session vector store...")

            indexing_started = time.perf_counter()
            cls._index_sections(sections)
            logger.info(
                "Proposal indexing completed section_count=%d duration_seconds=%.2f",
                len(sections),
                time.perf_counter() - indexing_started,
            )

            toc = [s["heading"] for s in sections if s["heading"]]
            summary = (
                f"Proposal File: {os.path.basename(file_path)} | "
                f"Sections: {len(sections)} | Diagrams Analysed: "
                f"{analysed_images}/{total_images}; Analysis Failures: {failed_images}\n"
                + (
                    f"Vision Analysis Note: {vision_failure_reason}\n"
                    if vision_failure_reason
                    else ""
                )
                + f"Document Outline: {', '.join(toc[:25])}"
            )
            logger.info(
                "Proposal processing completed sections=%d diagrams=%d "
                "diagrams_analysed=%d diagram_analysis_failures=%d "
                "duration_seconds=%.2f",
                len(sections),
                total_images,
                analysed_images,
                failed_images,
                time.perf_counter() - started,
            )
            return summary

        except Exception as error:
            logger.error(
                "Proposal processing failed file_type=%s error_type=%s "
                "duration_seconds=%.2f",
                ext,
                type(error).__name__,
                time.perf_counter() - started,
            )
            raise
        finally:
            try:
                shutil.rmtree(temp_img_dir)
            except OSError as error:
                logger.warning(
                    "Proposal temporary image cleanup failed error_type=%s",
                    type(error).__name__,
                )

    @classmethod
    def _check_ollama_vision_model(cls) -> str | None:
        """Check model availability once so a missing model does not fail per diagram."""
        try:
            client = ollama.Client(timeout=10)
            response = client.list()
        except Exception as error:
            logger.warning(
                "Ollama vision model preflight failed model=%s error_type=%s",
                cls._OLLAMA_VISION_MODEL,
                type(error).__name__,
            )
            return (
                f"[Vision Analysis Failed: Ollama could not verify the configured "
                f"vision model '{cls._OLLAMA_VISION_MODEL}'.]"
            )

        models = (
            response.get("models", [])
            if isinstance(response, dict)
            else getattr(response, "models", [])
        )
        available_models = set()
        for model in models:
            if isinstance(model, dict):
                name = model.get("model") or model.get("name")
            else:
                name = getattr(model, "model", None) or getattr(model, "name", None)
            if name:
                available_models.add(name)

        if cls._OLLAMA_VISION_MODEL in available_models:
            try:
                details = client.show(cls._OLLAMA_VISION_MODEL)
            except Exception as error:
                logger.warning(
                    "Ollama vision model capability check failed model=%s error_type=%s",
                    cls._OLLAMA_VISION_MODEL,
                    type(error).__name__,
                )
                return (
                    f"[Vision Analysis Failed: Ollama could not verify that "
                    f"'{cls._OLLAMA_VISION_MODEL}' supports image input.]"
                )

            capabilities = (
                details.get("capabilities", [])
                if isinstance(details, dict)
                else getattr(details, "capabilities", [])
            )
            if capabilities and "vision" not in capabilities:
                logger.warning(
                    "Ollama model lacks vision capability model=%s capabilities=%s",
                    cls._OLLAMA_VISION_MODEL,
                    ",".join(capabilities),
                )
                return (
                    f"[Vision Analysis Failed: Ollama model "
                    f"'{cls._OLLAMA_VISION_MODEL}' does not support image input. "
                    "Set CLEANONE_OLLAMA_VISION_MODEL to an installed vision-capable model.]"
                )
            return None

        logger.warning(
            "Ollama vision model unavailable model=%s installed_model_count=%d",
            cls._OLLAMA_VISION_MODEL,
            len(available_models),
        )
        return (
            f"[Vision Analysis Failed: Ollama vision model "
            f"'{cls._OLLAMA_VISION_MODEL}' is not installed. Install a vision-capable "
            "model or set CLEANONE_OLLAMA_VISION_MODEL to an installed one. "
            "CleanOne will not download models automatically.]"
        )

    @classmethod
    def _extract_docx(cls, file_path: str, img_dir: str) -> list[dict]:
        """Extracts headings, paragraphs, and embedded images from a Word document."""
        doc = docx.Document(file_path)
        sections = [{"heading": "Document Overview", "text": "", "images": []}]
        img_index = 0

        # Map relationship IDs to extracted image files
        rel_to_img = {}
        for rel_id, rel in doc.part.rels.items():
            if rel.reltype.endswith("/image") and not rel.is_external:
                img_ext = os.path.splitext(rel.target_ref)[1] or ".png"
                img_path = os.path.join(img_dir, f"docx_img_{img_index}{img_ext}")
                with open(img_path, "wb") as f:
                    f.write(rel.target_part.blob)
                rel_to_img[rel_id] = img_path
                img_index += 1

        # Walk paragraphs in document order to keep images tied to their headings
        for para in doc.paragraphs:
            style_name = para.style.name if para.style else ""
            if style_name.startswith("Heading"):
                sections.append({"heading": para.text.strip(), "text": "", "images": []})
            elif para.text.strip():
                sections[-1]["text"] += para.text.strip() + "\n"

            # Check if this paragraph contains an inline drawing/image reference
            xml_str = para._element.xml
            for rel_id, img_path in rel_to_img.items():
                if rel_id in xml_str and img_path not in sections[-1]["images"]:
                    sections[-1]["images"].append(img_path)

        return sections

    @classmethod
    def _extract_pdf(cls, file_path: str, img_dir: str) -> list[dict]:
        """Extracts text and embedded images page-by-page from a PDF."""
        sections = []
        with pymupdf.open(file_path) as pdf:
            for page_num, page in enumerate(pdf, start=1):
                text = page.get_text("text").strip()
                images = []
                for img_idx, img_info in enumerate(page.get_images(full=True)):
                    xref = img_info[0]
                    base_img = pdf.extract_image(xref)
                    # Skip tiny icons/logos (< 150px) to avoid wasting Vision LLM calls.
                    if base_img["width"] < 150 or base_img["height"] < 150:
                        continue
                    img_path = os.path.join(
                        img_dir,
                        f"page_{page_num}_img_{img_idx}.{base_img['ext']}",
                    )
                    with open(img_path, "wb") as f:
                        f.write(base_img["image"])
                    images.append(img_path)

                sections.append({
                    "heading": f"Page {page_num}",
                    "text": text,
                    "images": images,
                })

        return sections

    @classmethod
    def _extract_markdown(cls, file_path: str) -> list[dict]:
        """Splits Markdown by headings while keeping Mermaid blocks intact."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split on Markdown headings (#, ##, ###)
        raw_parts = re.split(r"(?=^#{1,3}\s+)", content, flags=re.MULTILINE)
        sections = []
        for part in raw_parts:
            lines = part.strip().splitlines()
            if not lines:
                continue
            first_line = lines[0]
            heading = first_line.lstrip("#").strip() if first_line.startswith("#") else "Overview"
            sections.append({"heading": heading, "text": part.strip(), "images": []})
        return sections

    @classmethod
    def _describe_diagram(cls, img_path: str, section_heading: str, backend_choice: str) -> str:
        """Uses a Vision LLM to convert an architecture/flow diagram into structured text."""
        started = time.perf_counter()
        vision_prompt = (
            f"You are a Principal Solutions Architect analysing a diagram from the section '{section_heading}' "
            "of a technical proposal. Break down the visual intent completely:\n"
            "1. Diagram Type (e.g., Cloud Topology, Sequence Flow, Data Pipeline, Bounded Context Map).\n"
            "2. Components & Services (list every box, database, queue, actor, and cloud service).\n"
            "3. Data Flows & Interactions (trace every arrow, direction, sync/async protocol, and event).\n"
            "4. Boundaries & Trust Zones (VPCs, subnets, bounded contexts, external third parties).\n"
            "Be exhaustive and precise so another architect can review this design without seeing the image."
        )

        try:
            if "Ollama" in backend_choice:
                response = ollama.Client(
                    timeout=cls._VISION_TIMEOUT_SECONDS
                ).chat(
                    model=cls._OLLAMA_VISION_MODEL,
                    messages=[{
                        "role": "user",
                        "content": vision_prompt,
                        "images": [img_path]
                    }],
                    options={"num_predict": cls._LOCAL_VISION_MAX_OUTPUT_TOKENS},
                )
                logger.info(
                    "Proposal diagram analysis completed backend=%s duration_seconds=%.2f",
                    backend_choice,
                    time.perf_counter() - started,
                )
                return response["message"]["content"]
            else:
                # AWS Bedrock Claude 3.5 Sonnet Vision via boto3 converse API
                with open(img_path, "rb") as f:
                    img_bytes = f.read()
                ext = os.path.splitext(img_path)[1].lower().lstrip(".")
                img_format = "jpeg" if ext in ("jpg", "jpeg") else "png"

                bedrock = boto3.client(
                    "bedrock-runtime",
                    config=Config(
                        connect_timeout=10,
                        read_timeout=cls._VISION_TIMEOUT_SECONDS,
                        retries={"total_max_attempts": 1},
                    ),
                )
                response = bedrock.converse(
                    modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"text": vision_prompt},
                            {"image": {"format": img_format, "source": {"bytes": img_bytes}}}
                        ]
                    }]
                )
                logger.info(
                    "Proposal diagram analysis completed backend=%s duration_seconds=%.2f",
                    backend_choice,
                    time.perf_counter() - started,
                )
                return response["output"]["message"]["content"][0]["text"]
        except Exception as e:
            logger.error(
                "Proposal diagram analysis failed backend=%s error_type=%s "
                "duration_seconds=%.2f",
                backend_choice,
                type(e).__name__,
                time.perf_counter() - started,
            )
            model_name = (
                cls._OLLAMA_VISION_MODEL
                if "Ollama" in backend_choice
                else "AWS Bedrock Claude 3.5 Sonnet"
            )
            return (
                f"[Vision Analysis Failed: diagram could not be processed by "
                f"'{model_name}' ({type(e).__name__}).]"
            )

    @classmethod
    def _index_sections(cls, sections: list[dict]):
        """Chunks sections (keeping Mermaid blocks together) into ChromaDB."""
        client = chromadb.PersistentClient(path=cls._SESSION_DB_PATH)
        collection = client.get_or_create_collection(name=cls._COLLECTION_NAME)

        # Custom separators prevent splitting inside ```mermaid ... ``` code blocks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200,
            chunk_overlap=150,
            separators=["\n## ", "\n### ", "\n```\n", "\n\n", "\n", " "]
        )

        chunk_id = 0
        for section in sections:
            if not section["text"].strip():
                continue
            chunks = splitter.split_text(section["text"])
            for chunk in chunks:
                collection.add(
                    documents=[chunk],
                    metadatas=[{"section": section["heading"]}],
                    ids=[f"prop_chunk_{chunk_id}"],
                )
                chunk_id += 1

    @classmethod
    def get_indexed_proposal_text(cls) -> str:
        """Returns all indexed proposal chunks for deterministic specialist routing."""
        client = chromadb.PersistentClient(path=cls._SESSION_DB_PATH)
        collection = client.get_collection(name=cls._COLLECTION_NAME)
        result = collection.get(include=["documents"])
        return "\n".join(result.get("documents") or [])

    @classmethod
    def query_proposal(cls, search_query: str, n_results: int = 4) -> str:
        """Allows specialist agents to search specific parts of the uploaded 100-page proposal."""
        started = time.perf_counter()
        if not os.path.exists(cls._SESSION_DB_PATH):
            logger.warning("Proposal search requested without a session index")
            return "No proposal document was uploaded for this session."
        try:
            client = chromadb.PersistentClient(path=cls._SESSION_DB_PATH)
            collection = client.get_collection(name=cls._COLLECTION_NAME)
            results = collection.query(query_texts=[search_query], n_results=n_results)

            doc_lists = results.get("documents") or [[]]
            meta_lists = results.get("metadatas") or [[]]
            docs = doc_lists[0]
            metas = meta_lists[0]

            formatted = [
                f"[Proposal Section: {meta.get('section', 'Unknown')}]\n{doc}"
                for doc, meta in zip(docs, metas)
            ]
            logger.info(
                "Proposal search completed result_count=%d duration_seconds=%.2f",
                len(formatted),
                time.perf_counter() - started,
            )
            return "\n---\n".join(formatted) if formatted else "No matching sections found in proposal."
        except Exception as e:
            logger.error(
                "Proposal search failed error_type=%s duration_seconds=%.2f",
                type(e).__name__,
                time.perf_counter() - started,
            )
            return f"Error querying uploaded proposal: {str(e)}"


class ProposalSearchInput(BaseModel):
    query: str = Field(..., description="Topic, component, or flow to look up inside the uploaded proposal.")


class ProposalSearchTool(BaseTool):
    name: str = "Search Uploaded Solution Proposal"
    description: str = (
        "Searches the user's uploaded solution proposal (including extracted Lucidchart/architecture "
        "diagrams and Mermaid flows) for specific components, data flows, or design decisions."
    )
    args_schema: type[BaseModel] = ProposalSearchInput
    _retrieved_evidence: bool = PrivateAttr(default=False)

    @property
    def retrieved_evidence(self) -> bool:
        return self._retrieved_evidence

    def _run(self, query: str) -> str:
        result = ProposalProcessor.query_proposal(query)
        self._retrieved_evidence = result.startswith("[Proposal Section:")
        return result

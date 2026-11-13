# src/proposal_processor.py
import logging
import os
import re
import tempfile
import shutil
import time
import json
from typing import Literal

import docx
import pymupdf
import chromadb
import ollama
import boto3
from botocore.config import Config
from langchain_text_splitters import RecursiveCharacterTextSplitter
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr, ValidationError


logger = logging.getLogger(__name__)


class DiagramTechnology(BaseModel):
    name: str
    evidence: str


class DiagramAnalysis(BaseModel):
    classification: Literal[
        "solution_architecture",
        "non_architecture",
        "uncertain",
    ]
    diagram_type: str
    technologies: list[DiagramTechnology]
    goal: str
    components: list[str]
    flows: list[str]
    solution_map: list[str]
    confidence: Literal["high", "medium", "low"]
    uncertainties: list[str]


class ProposalProcessor:
    """Extracts proposal content and stores it in a local review-scoped vector index."""

    _SESSION_DB_PATH = os.path.join("config", "session_proposal_db")
    _COLLECTION_NAME = "active_proposal"
    _MAX_UPLOAD_BYTES = 25 * 1024 * 1024
    _MAX_IMAGES_TO_CLASSIFY_PER_UPLOAD = 20
    _MAX_DIAGRAMS_PER_UPLOAD = 5
    _VISION_TIMEOUT_SECONDS = 60
    _MAX_VISION_ANALYSIS_SECONDS_PER_UPLOAD = 180
    _LOCAL_VISION_MAX_OUTPUT_TOKENS = 1024
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

            image_jobs = [
                (image_index, section, img_path)
                for image_index, (section, img_path) in enumerate(
                    (
                        (section, img_path)
                        for section in sections
                        for img_path in section["images"]
                    ),
                    start=1,
                )
            ]
            total_images = len(image_jobs)
            image_jobs.sort(
                key=lambda job: (
                    cls._image_context_priority(job[1]),
                    job[0],
                )
            )
            skipped_images = max(
                0,
                total_images - cls._MAX_IMAGES_TO_CLASSIFY_PER_UPLOAD,
            )
            image_jobs = image_jobs[:cls._MAX_IMAGES_TO_CLASSIFY_PER_UPLOAD]
            logger.info(
                "Proposal extraction completed sections=%d diagrams=%d "
                "duration_seconds=%.2f",
                len(sections),
                total_images,
                time.perf_counter() - started,
            )
            architecture_diagrams = 0
            image_attempts = 0
            ignored_images = 0
            uncertain_images = 0
            failed_images = 0
            vision_failure_reason = None
            vision_preflight_error = None
            if total_images and "Ollama" in backend_choice:
                vision_preflight_error = cls._check_ollama_vision_model()

            diagram_sections = []
            analysis_started = time.perf_counter()
            for attempt_index, (image_index, section, img_path) in enumerate(
                image_jobs,
                start=1,
            ):
                if architecture_diagrams >= cls._MAX_DIAGRAMS_PER_UPLOAD:
                    skipped_images += len(image_jobs) - attempt_index + 1
                    break
                if (
                    time.perf_counter() - analysis_started
                    >= cls._MAX_VISION_ANALYSIS_SECONDS_PER_UPLOAD
                ):
                    skipped_images += len(image_jobs) - attempt_index + 1
                    logger.warning(
                        "Proposal image analysis budget reached skipped_images=%d",
                        skipped_images,
                    )
                    break

                if progress_callback:
                    progress_callback(
                        f"Classifying image {attempt_index}/{len(image_jobs)} "
                        f"under '{section['heading']}'..."
                    )
                logger.info(
                    "Proposal image classification started image=%d total=%d backend=%s",
                    attempt_index,
                    len(image_jobs),
                    backend_choice,
                )
                image_attempts += 1
                if vision_preflight_error:
                    response_text = vision_preflight_error
                else:
                    response_text = cls._describe_diagram(
                        img_path, section["heading"], backend_choice
                    )

                if response_text.startswith("[Vision Analysis Failed:"):
                    failed_images += 1
                    vision_failure_reason = (
                        vision_failure_reason or response_text.strip("[]")
                    )
                    continue

                analysis = cls._parse_diagram_analysis(response_text)
                if analysis is None:
                    failed_images += 1
                    vision_failure_reason = (
                        vision_failure_reason
                        or "Vision model returned an invalid structured analysis."
                    )
                    logger.warning(
                        "Proposal image classification response invalid image=%d",
                        attempt_index,
                    )
                    continue

                if analysis.classification == "non_architecture":
                    ignored_images += 1
                    logger.info(
                        "Proposal image ignored image=%d classification=%s "
                        "diagram_type=%s confidence=%s",
                        attempt_index,
                        analysis.classification,
                        analysis.diagram_type,
                        analysis.confidence,
                    )
                    continue
                if analysis.classification == "uncertain":
                    uncertain_images += 1
                    logger.warning(
                        "Proposal image classification uncertain image=%d "
                        "diagram_type=%s confidence=%s",
                        attempt_index,
                        analysis.diagram_type,
                        analysis.confidence,
                    )
                    continue

                architecture_diagrams += 1
                diagram_sections.append({
                    "heading": (
                        f"{section['heading']} - Architectural Diagram {image_index}"
                    ),
                    "text": (
                        "[AI-generated diagram analysis; not verified OCR]\n"
                        + cls._format_diagram_analysis(analysis)
                    ),
                    "images": [],
                    "kind": "diagram",
                })
                logger.info(
                    "Proposal architectural diagram classified image=%d "
                    "diagram_type=%s technologies=%d confidence=%s",
                    attempt_index,
                    analysis.diagram_type,
                    len(analysis.technologies),
                    analysis.confidence,
                )

            sections.extend(diagram_sections)

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
                f"Sections: {len(sections)} | Images Attempted: "
                f"{image_attempts}/{total_images}; "
                f"Architecture Diagrams Analysed: {architecture_diagrams}; "
                f"Images Ignored: {ignored_images}; Classification Uncertain: "
                f"{uncertain_images}; Analysis Failures: {failed_images}; "
                f"Images Skipped: {skipped_images}\n"
                + (
                    f"Vision Analysis Note: {vision_failure_reason}\n"
                    if vision_failure_reason
                    else ""
                )
                + f"Document Outline: {', '.join(toc[:25])}"
            )
            logger.info(
                "Proposal processing completed sections=%d diagrams=%d "
                "images_attempted=%d diagrams_analysed=%d images_ignored=%d "
                "images_uncertain=%d "
                "image_analysis_failures=%d images_skipped=%d "
                "duration_seconds=%.2f",
                len(sections),
                total_images,
                image_attempts,
                architecture_diagrams,
                ignored_images,
                uncertain_images,
                failed_images,
                skipped_images,
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

        assigned_images = {
            img_path for section in sections for img_path in section["images"]
        }
        unassigned_images = [
            img_path for img_path in rel_to_img.values()
            if img_path not in assigned_images
        ]
        if unassigned_images:
            sections.append({
                "heading": "Embedded Images Without Paragraph Context",
                "text": "",
                "images": unassigned_images,
            })

        return sections

    @staticmethod
    def _image_context_priority(section: dict) -> int:
        context = f"{section['heading']}\n{section['text'][:1500]}".casefold()
        architecture_terms = (
            r"\barchitecture\b|\barchitectural\b|\bc4\b|\bdiagram\b|"
            r"\bdeployment\b|\btopology\b|\bsequence\b|\bprocess flow\b|"
            r"\bdata flow\b|\bsystem design\b"
        )
        return 0 if re.search(architecture_terms, context) else 1

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
        """Classifies an image and describes relevant solution-architecture diagrams."""
        started = time.perf_counter()
        vision_prompt = (
            f"You are reviewing image {os.path.basename(img_path)} from the proposal section "
            f"'{section_heading}'. First decide whether it is a solution-architecture diagram.\n"
            "Include cloud architecture, C4/context/container/component, deployment/network, "
            "sequence, process-flow, and data-flow diagrams. Classify photos, decorative images, "
            "logos without architecture, and unrelated charts as non_architecture. If unclear, "
            "use uncertain rather than guessing.\n"
            "For an architectural diagram, read its title, headings, legend, component labels, "
            "and arrows. Identify technologies and cloud providers only when supported by a "
            "clearly readable label or unmistakable logo; quote that evidence. Explain the goal "
            "shown by the diagram, trace the visible flow, and map the represented solution from "
            "entry points through services and data stores to external systems. Keep visible facts "
            "separate from interpretation. Do not invent missing components or claim the diagram "
            "is existing-state or target-state unless the image explicitly says so. Use 'Not stated' "
            "when the goal cannot be established.\n"
            "Return only a JSON object matching the supplied schema. For non_architecture or "
            "uncertain images, keep the analysis fields short and explain the reason in uncertainties."
        ) + "\nJSON schema:\n" + json.dumps(DiagramAnalysis.model_json_schema())

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
                    think=False,
                    format=DiagramAnalysis.model_json_schema(),
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

    @staticmethod
    def _parse_diagram_analysis(response: str) -> DiagramAnalysis | None:
        candidate = response.strip()
        if candidate.startswith("```") and candidate.endswith("```"):
            candidate = "\n".join(candidate.splitlines()[1:-1]).strip()

        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            if start < 0:
                return None
            try:
                payload, _ = json.JSONDecoder().raw_decode(candidate[start:])
            except json.JSONDecodeError:
                return None

        try:
            return DiagramAnalysis.model_validate(payload)
        except ValidationError:
            return None

    @staticmethod
    def _format_diagram_analysis(analysis: DiagramAnalysis) -> str:
        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) or "- None identified."

        technologies = [
            f"{item.name} — visible evidence: {item.evidence}"
            for item in analysis.technologies
        ]
        return (
            f"Diagram type: {analysis.diagram_type}\n"
            f"Analysis confidence: {analysis.confidence}\n"
            f"Technologies and evidence:\n{bullets(technologies)}\n"
            f"Diagram goal: {analysis.goal}\n"
            f"Visible components:\n{bullets(analysis.components)}\n"
            f"Visible flows:\n{bullets(analysis.flows)}\n"
            f"Solution map:\n{bullets(analysis.solution_map)}\n"
            f"Uncertainties:\n{bullets(analysis.uncertainties)}"
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
                    metadatas=[{
                        "section": section["heading"],
                        "kind": section.get("kind", "text"),
                    }],
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

    @staticmethod
    def has_proposal_evidence(response: str) -> bool:
        return response.startswith(("[Proposal Section:", "[Architectural Diagram:"))

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
            diagram_results = collection.get(
                where={"kind": "diagram"},
                include=["documents", "metadatas"],
            )

            doc_lists = results.get("documents") or [[]]
            meta_lists = results.get("metadatas") or [[]]
            docs = doc_lists[0]
            metas = meta_lists[0]

            diagram_docs = diagram_results.get("documents") or []
            diagram_metas = diagram_results.get("metadatas") or []
            formatted = []
            seen_documents = set()
            for doc, meta in zip(diagram_docs, diagram_metas):
                formatted.append(
                    f"[Architectural Diagram: {meta.get('section', 'Unknown')}]\n{doc}"
                )
                seen_documents.add(doc)
            for doc, meta in zip(docs, metas):
                if doc in seen_documents:
                    continue
                formatted.append(
                    f"[Proposal Section: {meta.get('section', 'Unknown')}]\n{doc}"
                )
                seen_documents.add(doc)
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
        "Searches text extracted from the user's proposal and AI-generated descriptions of "
        "Lucidchart/architecture diagrams or Mermaid flows. Diagram descriptions are not "
        "verbatim OCR, and this tool does not show the original image."
    )
    args_schema: type[BaseModel] = ProposalSearchInput
    _retrieved_evidence: bool = PrivateAttr(default=False)

    @property
    def retrieved_evidence(self) -> bool:
        return self._retrieved_evidence

    def _run(self, query: str) -> str:
        result = ProposalProcessor.query_proposal(query)
        self._retrieved_evidence = ProposalProcessor.has_proposal_evidence(result)
        return result

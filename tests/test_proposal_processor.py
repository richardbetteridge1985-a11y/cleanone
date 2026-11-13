import json
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pymupdf

from src.proposal_processor import DiagramAnalysis, ProposalProcessor


def _diagram_response(classification="solution_architecture"):
    return json.dumps({
        "classification": classification,
        "diagram_type": "cloud_architecture",
        "technologies": [
            {
                "name": "Google Cloud Pub/Sub",
                "evidence": "The visible label reads Cloud Pub/Sub.",
            },
        ] if classification == "solution_architecture" else [],
        "goal": "Coordinate order, inventory, and payment processing.",
        "components": ["Order Service", "Inventory Service"],
        "flows": ["Order Service sends an event to Cloud Pub/Sub."],
        "solution_map": ["Client -> API Gateway -> Order Service -> Cloud Pub/Sub"],
        "confidence": "high",
        "uncertainties": [],
    })


def test_process_file_accepts_direct_solution_image():
    with NamedTemporaryFile(suffix=".png") as image_file:
        image_file.write(b"image bytes")
        image_file.flush()

        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(ProposalProcessor, "_check_ollama_vision_model", return_value=None),
            patch.object(
                ProposalProcessor,
                "_describe_diagram",
                return_value=_diagram_response(),
            ) as describe,
            patch.object(ProposalProcessor, "_index_sections") as index_sections,
        ):
            client_factory.return_value.list_collections.return_value = [
                ProposalProcessor._COLLECTION_NAME
            ]
            summary = ProposalProcessor.process_file(
                image_file.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    assert "Architecture Diagrams Analysed: 1" in summary
    describe.assert_called_once()
    indexed_sections = index_sections.call_args.args[0]
    assert indexed_sections[1]["heading"].startswith("Uploaded Solution Image:")
    assert indexed_sections[1]["heading"].endswith("Architectural Diagram 1")
    assert "[AI-generated diagram analysis; not verified OCR]" in indexed_sections[1]["text"]
    assert "Google Cloud Pub/Sub" in indexed_sections[1]["text"]
    assert "Order Service -> Cloud Pub/Sub" in indexed_sections[1]["text"]
    client_factory.return_value.delete_collection.assert_called_once()


def test_process_file_surfaces_proposal_index_deletion_failures():
    with NamedTemporaryFile(suffix=".png") as image_file:
        image_file.write(b"image bytes")
        image_file.flush()

        with patch(
            "src.proposal_processor.chromadb.PersistentClient"
        ) as client_factory:
            client = client_factory.return_value
            client.list_collections.return_value = [
                SimpleNamespace(name=ProposalProcessor._COLLECTION_NAME)
            ]
            client.delete_collection.side_effect = RuntimeError("storage unavailable")

            with pytest.raises(RuntimeError, match="storage unavailable"):
                ProposalProcessor.process_file(
                    image_file.name,
                    "Local Machine (Ollama - Llama3.2:3b)",
                )


def test_process_file_rejects_uploads_over_size_limit_before_indexing():
    with NamedTemporaryFile(suffix=".md") as proposal:
        proposal.write(b"x")
        proposal.flush()

        with (
            patch.object(ProposalProcessor, "_MAX_UPLOAD_BYTES", 0),
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
        ):
            with pytest.raises(ValueError, match="exceeds the 0 MB limit"):
                ProposalProcessor.process_file(
                    proposal.name,
                    "Local Machine (Ollama - Llama3.2:3b)",
                )

    client_factory.assert_not_called()


def test_process_file_accepts_upload_at_size_limit():
    with NamedTemporaryFile(suffix=".md") as proposal:
        proposal.write(b"x")
        proposal.flush()

        with (
            patch.object(ProposalProcessor, "_MAX_UPLOAD_BYTES", 1),
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(ProposalProcessor, "_index_sections"),
        ):
            client_factory.return_value.list_collections.return_value = []
            summary = ProposalProcessor.process_file(
                proposal.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    assert "Sections: 1" in summary


def test_process_file_bounds_image_classification_and_reports_skipped_images():
    with NamedTemporaryFile(suffix=".docx") as proposal:
        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(
                ProposalProcessor,
                "_extract_docx",
                return_value=[{
                    "heading": "Architecture",
                    "text": "Solution overview.",
                    "images": ["image.png"] * 21,
                }],
            ),
            patch.object(
                ProposalProcessor,
                "_check_ollama_vision_model",
                return_value=None,
            ) as preflight,
            patch.object(
                ProposalProcessor,
                "_describe_diagram",
                return_value=_diagram_response("non_architecture"),
            ) as describe,
            patch.object(ProposalProcessor, "_index_sections"),
        ):
            client_factory.return_value.list_collections.return_value = []
            summary = ProposalProcessor.process_file(
                proposal.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    assert "Images Ignored: 20" in summary
    assert "Images Skipped: 1" in summary
    assert describe.call_count == 20
    preflight.assert_called_once()
    client_factory.return_value.delete_collection.assert_not_called()


def test_process_file_prioritizes_architecture_sections_within_image_limit():
    with NamedTemporaryFile(suffix=".docx") as proposal:
        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(
                ProposalProcessor,
                "_extract_docx",
                return_value=[
                    {
                        "heading": "Company Branding",
                        "text": "Decorative images.",
                        "images": [f"logo-{index}.png" for index in range(20)],
                    },
                    {
                        "heading": "Solution Architecture",
                        "text": "System design.",
                        "images": ["architecture.png"],
                    },
                ],
            ),
            patch.object(
                ProposalProcessor,
                "_check_ollama_vision_model",
                return_value=None,
            ),
            patch.object(
                ProposalProcessor,
                "_describe_diagram",
                side_effect=[
                    _diagram_response(),
                    *[
                        _diagram_response("non_architecture")
                        for _ in range(19)
                    ],
                ],
            ) as describe,
            patch.object(ProposalProcessor, "_index_sections"),
        ):
            client_factory.return_value.list_collections.return_value = []
            summary = ProposalProcessor.process_file(
                proposal.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    assert describe.call_args_list[0].args[0] == "architecture.png"
    assert "Architecture Diagrams Analysed: 1" in summary
    assert "Images Skipped: 1" in summary


def test_process_file_classifies_five_architecture_diagrams_at_limit():
    with NamedTemporaryFile(suffix=".docx") as proposal:
        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(
                ProposalProcessor,
                "_extract_docx",
                return_value=[{
                    "heading": "Architecture",
                    "text": "Solution overview.",
                    "images": ["diagram.png"] * 5,
                }],
            ),
            patch.object(ProposalProcessor, "_check_ollama_vision_model", return_value=None),
            patch.object(
                ProposalProcessor,
                "_describe_diagram",
                return_value=_diagram_response(),
            ) as describe,
            patch.object(ProposalProcessor, "_index_sections"),
        ):
            client_factory.return_value.list_collections.return_value = []
            summary = ProposalProcessor.process_file(
                proposal.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    assert "Architecture Diagrams Analysed: 5" in summary
    assert describe.call_count == 5


def test_process_file_ignores_non_architecture_images():
    with NamedTemporaryFile(suffix=".docx") as proposal:
        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(
                ProposalProcessor,
                "_extract_docx",
                return_value=[{
                    "heading": "Overview",
                    "text": "Solution overview.",
                    "images": [
                        "logo.png",
                        "photo.png",
                        "icon-1.png",
                        "icon-2.png",
                        "cover.png",
                        "architecture.png",
                    ],
                }],
            ),
            patch.object(ProposalProcessor, "_check_ollama_vision_model", return_value=None),
            patch.object(
                ProposalProcessor,
                "_describe_diagram",
                side_effect=[
                    *[_diagram_response("non_architecture") for _ in range(5)],
                    _diagram_response(),
                ],
            ) as describe,
            patch.object(ProposalProcessor, "_index_sections") as index_sections,
        ):
            client_factory.return_value.list_collections.return_value = []
            summary = ProposalProcessor.process_file(
                proposal.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    assert "Images Ignored: 5" in summary
    assert "Architecture Diagrams Analysed: 1" in summary
    assert describe.call_count == 6
    indexed_diagrams = [
        section for section in index_sections.call_args.args[0]
        if section.get("kind") == "diagram"
    ]
    assert len(indexed_diagrams) == 1
    assert "Google Cloud Pub/Sub" in indexed_diagrams[0]["text"]


def test_missing_ollama_vision_model_skips_all_diagram_requests():
    with NamedTemporaryFile(suffix=".docx") as proposal:
        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(
                ProposalProcessor,
                "_extract_docx",
                return_value=[{
                    "heading": "Architecture",
                    "text": "Solution overview.",
                    "images": ["diagram-1.png", "diagram-2.png"],
                }],
            ),
            patch.object(
                ProposalProcessor,
                "_check_ollama_vision_model",
                return_value=(
                    "[Vision Analysis Failed: Ollama vision model 'qwen3.5:9b' "
                    "is not installed.]"
                ),
            ) as preflight,
            patch.object(ProposalProcessor, "_describe_diagram") as describe,
            patch.object(ProposalProcessor, "_index_sections") as index_sections,
        ):
            client_factory.return_value.list_collections.return_value = []
            summary = ProposalProcessor.process_file(
                proposal.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    preflight.assert_called_once()
    describe.assert_not_called()
    assert "Architecture Diagrams Analysed: 0" in summary
    assert "Analysis Failures: 2" in summary
    assert "qwen3.5:9b" in summary
    assert not any(
        section.get("kind") == "diagram"
        for section in index_sections.call_args.args[0]
    )


def test_ollama_vision_request_has_a_timeout():
    with patch("src.proposal_processor.ollama.Client") as client_factory:
        client_factory.return_value.chat.return_value = {
            "message": {"content": _diagram_response()}
        }

        result = ProposalProcessor._describe_diagram(
            "diagram.png",
            "Architecture",
            "Local Machine (Ollama - Llama3.2:3b)",
        )

    assert result == _diagram_response()
    client_factory.assert_called_once_with(timeout=60)
    client_factory.return_value.chat.assert_called_once()
    chat_kwargs = client_factory.return_value.chat.call_args.kwargs
    assert chat_kwargs["model"] == ProposalProcessor._OLLAMA_VISION_MODEL
    assert chat_kwargs["think"] is False
    assert chat_kwargs["format"] == DiagramAnalysis.model_json_schema()
    assert chat_kwargs["options"] == {
        "num_predict": ProposalProcessor._LOCAL_VISION_MAX_OUTPUT_TOKENS
    }
    vision_prompt = chat_kwargs["messages"][0]["content"]
    assert "First decide whether it is a solution-architecture diagram" in vision_prompt
    assert "map the represented solution" in vision_prompt
    assert "JSON schema:" in vision_prompt


def test_diagram_analysis_parser_accepts_structured_json_and_rejects_invalid_json():
    analysis = ProposalProcessor._parse_diagram_analysis(_diagram_response())

    assert analysis is not None
    assert analysis.classification == "solution_architecture"
    assert analysis.technologies[0].name == "Google Cloud Pub/Sub"
    assert ProposalProcessor._parse_diagram_analysis("not JSON") is None


def test_ollama_vision_model_preflight_accepts_installed_model():
    with patch("src.proposal_processor.ollama.Client") as client_factory:
        client_factory.return_value.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(model=ProposalProcessor._OLLAMA_VISION_MODEL)]
        )
        client_factory.return_value.show.return_value = SimpleNamespace(
            capabilities=["completion", "vision"]
        )

        assert ProposalProcessor._check_ollama_vision_model() is None

    client_factory.assert_called_once_with(timeout=10)
    client_factory.return_value.show.assert_called_once_with(
        ProposalProcessor._OLLAMA_VISION_MODEL
    )


def test_ollama_vision_model_preflight_reports_missing_model_without_downloading():
    with patch("src.proposal_processor.ollama.Client") as client_factory:
        client_factory.return_value.list.return_value = SimpleNamespace(models=[])

        result = ProposalProcessor._check_ollama_vision_model()

    assert "is not installed" in result
    assert "will not download" in result


def test_ollama_vision_model_preflight_rejects_non_vision_model():
    with patch("src.proposal_processor.ollama.Client") as client_factory:
        client_factory.return_value.list.return_value = SimpleNamespace(
            models=[SimpleNamespace(model=ProposalProcessor._OLLAMA_VISION_MODEL)]
        )
        client_factory.return_value.show.return_value = SimpleNamespace(
            capabilities=["completion", "tools"]
        )

        result = ProposalProcessor._check_ollama_vision_model()

    assert "does not support image input" in result


def test_bedrock_vision_request_has_a_timeout():
    with (
        NamedTemporaryFile(suffix=".png") as image_file,
        patch("src.proposal_processor.boto3.client") as client_factory,
    ):
        client_factory.return_value.converse.return_value = {
            "output": {"message": {"content": [{"text": _diagram_response()}]}}
        }

        result = ProposalProcessor._describe_diagram(
            image_file.name,
            "Architecture",
            "Enterprise Cloud (AWS Bedrock - Claude 3.5 Sonnet)",
        )

    assert result == _diagram_response()
    config = client_factory.call_args.kwargs["config"]
    assert config.connect_timeout == 10
    assert config.read_timeout == 60
    assert config.retries == {"total_max_attempts": 1}
    assert "inferenceConfig" not in client_factory.return_value.converse.call_args.kwargs
    bedrock_prompt = (
        client_factory.return_value.converse.call_args.kwargs["messages"][0]["content"][0]["text"]
    )
    assert "JSON schema:" in bedrock_prompt


def test_extract_pdf_reads_text_and_closes_the_document(tmp_path):
    pdf_path = tmp_path / "solution.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Proposed architecture")
        document.save(pdf_path)

    sections = ProposalProcessor._extract_pdf(str(pdf_path), str(tmp_path))

    assert len(sections) == 1
    assert sections[0]["heading"] == "Page 1"
    assert "Proposed architecture" in sections[0]["text"]


def test_extract_docx_keeps_images_without_paragraph_context(tmp_path):
    relationship = SimpleNamespace(
        reltype="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
        is_external=False,
        target_ref="embedded.png",
        target_part=SimpleNamespace(blob=b"image bytes"),
    )
    document = SimpleNamespace(
        part=SimpleNamespace(rels={"rId1": relationship}),
        paragraphs=[],
    )

    with patch("src.proposal_processor.docx.Document", return_value=document):
        sections = ProposalProcessor._extract_docx("proposal.docx", str(tmp_path))

    assert sections[-1]["heading"] == "Embedded Images Without Paragraph Context"
    assert len(sections[-1]["images"]) == 1
    assert (tmp_path / "docx_img_0.png").read_bytes() == b"image bytes"


def test_index_sections_assigns_a_unique_id_to_every_chunk():
    with (
        patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
        patch("src.proposal_processor.RecursiveCharacterTextSplitter") as splitter_factory,
    ):
        splitter_factory.return_value.split_text.side_effect = [
            ["first chunk", "second chunk"],
            ["third chunk"],
            ["diagram chunk"],
        ]
        ProposalProcessor._index_sections([
            {"heading": "Overview", "text": "first section"},
            {"heading": "Details", "text": "second section"},
            {"heading": "Architecture diagram", "text": "diagram summary", "kind": "diagram"},
        ])

    collection = client_factory.return_value.get_or_create_collection.return_value
    assert [
        call.kwargs["ids"]
        for call in collection.add.call_args_list
    ] == [
        ["prop_chunk_0"],
        ["prop_chunk_1"],
        ["prop_chunk_2"],
        ["prop_chunk_3"],
    ]
    assert collection.add.call_args_list[0].kwargs["metadatas"] == [
        {"section": "Overview", "kind": "text"}
    ]
    assert collection.add.call_args_list[3].kwargs["metadatas"] == [
        {"section": "Architecture diagram", "kind": "diagram"}
    ]


def test_query_proposal_always_includes_architecture_diagram_summaries(tmp_path):
    with (
        patch.object(ProposalProcessor, "_SESSION_DB_PATH", str(tmp_path)),
        patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
    ):
        collection = client_factory.return_value.get_collection.return_value
        collection.query.return_value = {
            "documents": [["Text proposal evidence."]],
            "metadatas": [[{"section": "Requirements"}]],
        }
        collection.get.return_value = {
            "documents": ["Google Cloud Pub/Sub connects the services."],
            "metadatas": [{"section": "Overview - Architectural Diagram 1"}],
        }

        result = ProposalProcessor.query_proposal("GCP services")

    assert result.index("[Architectural Diagram:") < result.index("[Proposal Section:")
    assert "Google Cloud Pub/Sub connects the services." in result
    collection.get.assert_called_once_with(
        where={"kind": "diagram"},
        include=["documents", "metadatas"],
    )


def test_process_file_rejects_unsupported_extension_before_reading_file():
    with pytest.raises(ValueError, match="Unsupported file format"):
        ProposalProcessor.process_file(
            "not-a-supported-upload.exe",
            "Local Machine (Ollama - Llama3.2:3b)",
        )

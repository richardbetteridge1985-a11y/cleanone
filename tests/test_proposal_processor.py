from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pymupdf

from src.proposal_processor import ProposalProcessor


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
                return_value="A client connects to a service and database.",
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

    assert "Diagrams Analysed: 1" in summary
    describe.assert_called_once()
    indexed_sections = index_sections.call_args.args[0]
    assert "Uploaded Solution Image" in indexed_sections[0]["heading"]
    assert "A client connects to a service and database." in indexed_sections[0]["text"]
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


def test_process_file_rejects_too_many_diagrams_before_vision_calls():
    with NamedTemporaryFile(suffix=".docx") as proposal:
        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(
                ProposalProcessor,
                "_extract_docx",
                return_value=[{
                    "heading": "Architecture",
                    "text": "Solution overview.",
                    "images": ["diagram.png"] * 6,
                }],
            ),
            patch.object(ProposalProcessor, "_check_ollama_vision_model") as preflight,
            patch.object(ProposalProcessor, "_describe_diagram") as describe,
        ):
            with pytest.raises(ValueError, match="the limit is 5"):
                ProposalProcessor.process_file(
                    proposal.name,
                    "Local Machine (Ollama - Llama3.2:3b)",
                )

    describe.assert_not_called()
    preflight.assert_not_called()
    client_factory.return_value.delete_collection.assert_not_called()


def test_process_file_accepts_five_diagrams_at_limit():
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
                return_value="Diagram details.",
            ) as describe,
            patch.object(ProposalProcessor, "_index_sections"),
        ):
            client_factory.return_value.list_collections.return_value = []
            summary = ProposalProcessor.process_file(
                proposal.name,
                "Local Machine (Ollama - Llama3.2:3b)",
            )

    assert "Diagrams Analysed: 5" in summary
    assert describe.call_count == 5


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
    assert "Diagrams Analysed: 0/2; Analysis Failures: 2" in summary
    assert "qwen3.5:9b" in summary
    indexed_sections = index_sections.call_args.args[0]
    assert "Diagram image present; vision analysis failed." in indexed_sections[0]["text"]


def test_ollama_vision_request_has_a_timeout():
    with patch("src.proposal_processor.ollama.Client") as client_factory:
        client_factory.return_value.chat.return_value = {
            "message": {"content": "Diagram details."}
        }

        result = ProposalProcessor._describe_diagram(
            "diagram.png",
            "Architecture",
            "Local Machine (Ollama - Llama3.2:3b)",
        )

    assert result == "Diagram details."
    client_factory.assert_called_once_with(timeout=120)
    client_factory.return_value.chat.assert_called_once()
    chat_kwargs = client_factory.return_value.chat.call_args.kwargs
    assert chat_kwargs["model"] == ProposalProcessor._OLLAMA_VISION_MODEL
    assert chat_kwargs["options"] == {
        "num_predict": ProposalProcessor._LOCAL_VISION_MAX_OUTPUT_TOKENS
    }


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
            "output": {"message": {"content": [{"text": "Diagram details."}]}}
        }

        result = ProposalProcessor._describe_diagram(
            image_file.name,
            "Architecture",
            "Enterprise Cloud (AWS Bedrock - Claude 3.5 Sonnet)",
        )

    assert result == "Diagram details."
    config = client_factory.call_args.kwargs["config"]
    assert config.connect_timeout == 10
    assert config.read_timeout == 120
    assert config.retries == {"total_max_attempts": 1}
    assert "inferenceConfig" not in client_factory.return_value.converse.call_args.kwargs


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


def test_index_sections_assigns_a_unique_id_to_every_chunk():
    with (
        patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
        patch("src.proposal_processor.RecursiveCharacterTextSplitter") as splitter_factory,
    ):
        splitter_factory.return_value.split_text.side_effect = [
            ["first chunk", "second chunk"],
            ["third chunk"],
        ]
        ProposalProcessor._index_sections([
            {"heading": "Overview", "text": "first section"},
            {"heading": "Details", "text": "second section"},
        ])

    collection = client_factory.return_value.get_or_create_collection.return_value
    assert [
        call.kwargs["ids"]
        for call in collection.add.call_args_list
    ] == [["prop_chunk_0"], ["prop_chunk_1"], ["prop_chunk_2"]]


def test_process_file_rejects_unsupported_extension_before_reading_file():
    with pytest.raises(ValueError, match="Unsupported file format"):
        ProposalProcessor.process_file(
            "not-a-supported-upload.exe",
            "Local Machine (Ollama - Llama3.2:3b)",
        )

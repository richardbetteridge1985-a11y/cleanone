from tempfile import NamedTemporaryFile
from unittest.mock import patch

from src.proposal_processor import ProposalProcessor


def test_process_file_accepts_direct_solution_image():
    with NamedTemporaryFile(suffix=".png") as image_file:
        image_file.write(b"image bytes")
        image_file.flush()

        with (
            patch("src.proposal_processor.chromadb.PersistentClient") as client_factory,
            patch.object(
                ProposalProcessor,
                "_describe_diagram",
                return_value="A client connects to a service and database.",
            ) as describe,
            patch.object(ProposalProcessor, "_index_sections") as index_sections,
        ):
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


def test_process_file_rejects_unsupported_extension_before_reading_file():
    try:
        ProposalProcessor.process_file(
            "not-a-supported-upload.exe",
            "Local Machine (Ollama - Llama3.2:3b)",
        )
    except ValueError as error:
        assert "Unsupported file format" in str(error)
    else:
        raise AssertionError("Unsupported uploads should be rejected")

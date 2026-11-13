from unittest.mock import patch

from src.rag_engine import RAGEngine


def test_query_returns_formatted_knowledge_sources():
    with patch("src.rag_engine.chromadb.PersistentClient") as client_factory:
        collection = client_factory.return_value.get_collection.return_value
        collection.query.return_value = {
            "documents": [["A bounded context owns its model."]],
            "metadatas": [[{"source": "01_ddd.md"}]],
        }

        result = RAGEngine.query_knowledge_base(
            "bounded contexts",
            n_results=1,
            source_filter="01_ddd.md",
        )

    assert result == "[Source: 01_ddd.md]\nA bounded context owns its model."
    collection.query.assert_called_once_with(
        query_texts=["bounded contexts"],
        n_results=1,
        where={"source": "01_ddd.md"},
    )


def test_query_reports_empty_knowledge_results():
    with patch("src.rag_engine.chromadb.PersistentClient") as client_factory:
        collection = client_factory.return_value.get_collection.return_value
        collection.query.return_value = {"documents": [[]], "metadatas": [[]]}

        result = RAGEngine.query_knowledge_base("missing guidance")

    assert result == "No matching guidelines found in knowledge base."

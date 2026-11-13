from unittest.mock import patch

from src.ui import build_and_launch_ui


def test_review_controls_are_disabled_until_request_finishes():
    captured = {}

    def capture_launch(app, *args, **kwargs):
        captured["app"] = app

    with patch("src.ui.gr.Blocks.launch", new=capture_launch):
        build_and_launch_ui()

    handler = next(
        function.fn
        for function in captured["app"].fns.values()
        if function.fn.__name__ == "ui_event_handler"
    )
    updates = list(
        handler(
            "",
            None,
            "Single Specialist Review",
            "Ddd Specialist",
            "Local Machine (Ollama - Llama3.2:3b)",
        )
    )

    assert len(updates) == 3
    assert all(update["interactive"] is False for update in updates[0][1:])
    assert all(update["interactive"] is False for update in updates[1][1:])
    assert all(update["interactive"] is True for update in updates[-1][1:])

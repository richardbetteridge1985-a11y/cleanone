# src/ui.py
import logging
import os
import time
import uuid

import gradio as gr
from src.agent_factory import AgentFactory
from src.llm_router import LLMRouter
from src.logging_config import iter_with_request_context, request_context
from src.proposal_processor import ProposalProcessor

logger = logging.getLogger(__name__)


def build_and_launch_ui():
    individual_profiles = AgentFactory.get_individual_profiles()
    supported_backends = LLMRouter.get_supported_backends()
    default_backend = next(iter(supported_backends), None)
    default_specialist = next(iter(individual_profiles), None)

    def toggle_specialist_dropdown(review_mode):
        """Shows the single-specialist dropdown only when Single Specialist mode is selected."""
        is_single = (review_mode == "Single Specialist Review")
        return gr.update(visible=is_single, interactive=is_single)

    def update_review_controls(interactive, review_mode):
        is_single = review_mode == "Single Specialist Review"
        return (
            gr.update(interactive=interactive),
            gr.update(interactive=interactive),
            gr.update(interactive=interactive),
            gr.update(visible=is_single, interactive=interactive and is_single),
            gr.update(interactive=interactive),
            gr.update(
                value=(
                    "Analyse Proposal & Run Agents"
                    if interactive
                    else "Analysis in progress..."
                ),
                interactive=interactive,
            ),
        )

    def process_request(user_input, uploaded_file, review_mode, specialist_choice, infrastructure_choice):
        if not user_input and not uploaded_file:
            logger.warning("Request rejected: no prompt or proposal was provided")
            yield (
                "⚠️ Please enter a prompt or upload a solution file "
                "(`.docx`, `.pdf`, `.md`, `.png`, `.jpg`, or `.jpeg`)."
            )
            return

        # Determine whether to run the Smart Multi-Agent Panel or one chosen specialist
        if review_mode == "Smart Panel (Auto-Select Relevant Specialists)":
            target_profile = AgentFactory.ALL_AGENTS_LABEL
        else:
            if not specialist_choice:
                logger.warning("Request rejected: no single specialist was selected")
                yield "⚠️ Please select a specialist from the dropdown."
                return
            target_profile = specialist_choice

        logger.info(
            "Review prepared mode=%s target=%s proposal_uploaded=%s",
            review_mode,
            target_profile,
            uploaded_file is not None,
        )
        yield f"*⏳ Preparing {target_profile}...*"
        effective_prompt = (
            user_input.strip()
            if user_input
            else "Perform a comprehensive architectural review of the uploaded proposal."
        )

        if uploaded_file is not None:
            file_type = os.path.splitext(uploaded_file)[1].lower()
            ingestion_started = time.perf_counter()
            logger.info("Proposal ingestion started file_type=%s", file_type)
            yield "*⏳ Extracting text and translating diagrams from uploaded proposal...*\n\n"
            proposal_summary = ProposalProcessor.process_file(
                file_path=uploaded_file,
                backend_choice=infrastructure_choice
            )
            proposal_status = "\n".join(proposal_summary.splitlines()[:2])
            yield (
                "*✅ Proposal processing complete*\n\n"
                f"{proposal_status}"
            )
            logger.info(
                "Proposal ingestion returned file_type=%s duration_seconds=%.2f",
                file_type,
                time.perf_counter() - ingestion_started,
            )
            effective_prompt = (
                f"{effective_prompt}\n\n"
                f"--- UPLOADED PROPOSAL METADATA ---\n{proposal_summary}\n"
                "Use the retrieved proposal evidence as the primary source for this review."
            )

        llm_instance = LLMRouter.create_backend(infrastructure_choice)
        agent_runner = AgentFactory.create_agent(
            profile_id=target_profile,
            llm=llm_instance,
            proposal_uploaded=uploaded_file is not None
        )

        yield f"*⏳ Running {target_profile}. This may take a few minutes...*"
        for chunk in agent_runner.run(effective_prompt):
            yield chunk

    def ui_event_handler(user_input, uploaded_file, review_mode, specialist_choice, infrastructure_choice):
        request_id = uuid.uuid4().hex[:12]
        request_started = time.perf_counter()
        with request_context(request_id):
            logger.info(
                "Review request received mode=%s backend=%s proposal_uploaded=%s",
                review_mode,
                infrastructure_choice,
                uploaded_file is not None,
            )
        status = "running"
        latest_output = "*⏳ Starting solution analysis...*"
        yield (latest_output, *update_review_controls(False, review_mode))
        try:
            for output in iter_with_request_context(
                process_request(
                    user_input,
                    uploaded_file,
                    review_mode,
                    specialist_choice,
                    infrastructure_choice,
                ),
                request_id,
            ):
                latest_output = output
                yield (output, *update_review_controls(False, review_mode))
            status = "completed"
        except Exception as error:
            status = "failed"
            with request_context(request_id):
                logger.error(
                    "Review request failed error_type=%s",
                    type(error).__name__,
                )
            latest_output = f"⚠️ Presentation Layer Error: {str(error)}"
            yield (latest_output, *update_review_controls(False, review_mode))
        finally:
            with request_context(request_id):
                logger.info(
                    "Review request finished status=%s duration_seconds=%.2f",
                    status,
                    time.perf_counter() - request_started,
                )
        yield (latest_output, *update_review_controls(True, review_mode))

    with gr.Blocks(theme="soft", title="Architect Agent Gateway") as app:
        gr.Markdown("# 🤖 Multi-Modal Architectural Review Gateway")
        gr.Markdown(
            "Upload a solution proposal (`.docx`, `.pdf`, `.md`, `.png`, `.jpg`, or `.jpeg`) "
            "and run a full multi-agent review or target a single architectural lens. "
            "The Smart Panel classifies the solution, selects relevant specialists, "
            "and runs every specialist relevant to the solution. Uploads are limited "
            "to 25 MB; up to 20 images are checked and excess images are reported as skipped. "
            "Non-architecture visuals are ignored, with at most five architecture "
            "diagrams analysed."
        )

        with gr.Row():
            backend_dropdown = gr.Dropdown(
                choices=supported_backends,
                value=default_backend,
                label="1. Infrastructure Target (Compute & Vision Engine)"
            )
            mode_radio = gr.Radio(
                choices=[
                    "Smart Panel (Auto-Select Relevant Specialists)",
                    "Single Specialist Review"
                ],
                value="Single Specialist Review",
                label="2. Review Scope"
            )
            specialist_dropdown = gr.Dropdown(
                choices=individual_profiles,
                value=default_specialist,
                label="3. Choose Specific Specialist",
                visible=True,
                interactive=True
            )

        # Dynamically show/hide the specialist dropdown when the user toggles the radio button
        mode_radio.change(
            fn=toggle_specialist_dropdown,
            inputs=[mode_radio],
            outputs=[specialist_dropdown]
        )

        with gr.Row():
            with gr.Column(scale=4):
                file_input = gr.File(
                    label=(
                        "4. Upload Solution Proposal (Optional; max 25 MB, up to "
                        "20 images checked, 5 architecture diagrams analysed)"
                    ),
                    file_types=[".docx", ".pdf", ".md", ".png", ".jpg", ".jpeg"],
                    type="filepath"
                )
                prompt_input = gr.Textbox(
                    label="5. Focus Instructions / Prompt",
                    placeholder="e.g., Assess my solution against DDD principles and offer areas to rework...",
                    lines=4
                )
                submit_btn = gr.Button("Analyse Proposal & Run Agents", variant="primary")

            with gr.Column(scale=6):
                output_display = gr.Markdown(
                    value="*Architectural assessments will stream here...*"
                )

        submit_btn.click(
            fn=ui_event_handler,
            inputs=[prompt_input, file_input, mode_radio, specialist_dropdown, backend_dropdown],
            outputs=[
                output_display,
                prompt_input,
                file_input,
                mode_radio,
                specialist_dropdown,
                backend_dropdown,
                submit_btn,
            ],
        )

    app.queue(default_concurrency_limit=1, max_size=1)
    logger.info("Launching Gradio interface host=127.0.0.1 port=7860")
    app.launch(server_name="127.0.0.1", server_port=7860)

# src/ui.py
import gradio as gr
from src.agent_factory import AgentFactory
from src.llm_router import LLMRouter
from src.proposal_processor import ProposalProcessor

def build_and_launch_ui():
    individual_profiles = AgentFactory.get_individual_profiles()
    supported_backends = LLMRouter.get_supported_backends()
    default_backend = next(iter(supported_backends), None)
    default_specialist = next(iter(individual_profiles), None)

    def toggle_specialist_dropdown(review_mode):
        """Shows the single-specialist dropdown only when Single Specialist mode is selected."""
        is_single = (review_mode == "Single Specialist Review")
        return gr.update(visible=is_single, interactive=is_single)

    def ui_event_handler(user_input, uploaded_file, review_mode, specialist_choice, infrastructure_choice):
        if not user_input and not uploaded_file:
            yield "⚠️ Please enter a prompt or upload a proposal document (`.docx`, `.pdf`, `.md`)."
            return

        # Determine whether to run the Smart Multi-Agent Panel or one chosen specialist
        if review_mode == "Smart Panel (Auto-Select Relevant Specialists)":
            target_profile = AgentFactory.ALL_AGENTS_LABEL
        else:
            if not specialist_choice:
                yield "⚠️ Please select a specialist from the dropdown."
                return
            target_profile = specialist_choice

        try:
            yield f"*⏳ Preparing {target_profile}...*"
            effective_prompt = (
                user_input.strip()
                if user_input
                else "Perform a comprehensive architectural review of the uploaded proposal."
            )

            # 1. Parse document & translate diagrams if a file was uploaded
            if uploaded_file is not None:
                yield "*⏳ Extracting text and translating diagrams from uploaded proposal...*\n\n"
                proposal_summary = ProposalProcessor.process_file(
                    file_path=uploaded_file,
                    backend_choice=infrastructure_choice
                )
                effective_prompt = (
                    f"{effective_prompt}\n\n"
                    f"--- UPLOADED PROPOSAL METADATA ---\n{proposal_summary}\n"
                    "Use the 'Search Uploaded Solution Proposal' tool to inspect specific sections and diagrams."
                )

            # 2. Instantiate backend & run either SmartPanelRunner or single AgentRunner
            llm_instance = LLMRouter.create_backend(infrastructure_choice)
            agent_runner = AgentFactory.create_agent(
                profile_id=target_profile,
                llm=llm_instance,
                proposal_uploaded=uploaded_file is not None
            )

            yield f"*⏳ Running {target_profile}. This may take a few minutes...*"
            for chunk in agent_runner.run(effective_prompt):
                yield chunk

        except Exception as e:
            yield f"⚠️ Presentation Layer Error: {str(e)}"

    with gr.Blocks(theme="soft", title="Architect Agent Gateway") as app:
        gr.Markdown("# 🤖 Multi-Modal Architectural Review Gateway")
        gr.Markdown(
            "Upload a solution proposal (`.docx`, `.pdf`, `.md` with Mermaid or Lucidchart diagrams) "
            "and run a full multi-agent review or target a single architectural lens."
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
                    label="4. Upload Solution Proposal (Optional)",
                    file_types=[".docx", ".pdf", ".md"],
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
            outputs=output_display
        )

    app.queue(default_concurrency_limit=1, max_size=1)
    app.launch(server_name="127.0.0.1", server_port=7860)

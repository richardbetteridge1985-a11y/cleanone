# tests/integration_run.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm_router import LLMRouter
from src.agent_factory import AgentFactory
from src.rag_engine import RAGEngine


def run_integration_pipeline() -> bool:
    print("=== Launching End-to-End Pipeline Integration ===")
    
    # 1. Simulate UI selections
    chosen_backend = LLMRouter.get_supported_backends()[0]
    chosen_profile = "Ddd Specialist"
    sample_prompt = (
        "Review the domain model for an appointment-booking application and "
        "explain the relevant DDD boundaries."
    )
    
    try:
        RAGEngine.initialize_knowledge_base()

        # 2. Build compute block
        print("[Step 1/3] Resolving backend router configuration...")
        llm = LLMRouter.create_backend(chosen_backend)
        
        # 3. Create Agent context wrapper
        print("[Step 2/3] Programmatically loading agent schemas from file configurations...")
        agent_runner = AgentFactory.create_agent(profile_id=chosen_profile, llm=llm)
        
        # 4. Trigger loop
        print("[Step 3/3] Handing execution frame over to CrewAI orchestration loop...")
        print("--- Execution Started ---")
        
        # Collect and print streamed responses
        response_chunks = list(agent_runner.run(sample_prompt))
        if any("⚠️ Agent Automation Runtime Error:" in chunk for chunk in response_chunks):
            raise RuntimeError("The specialist runner reported an execution failure.")

        for response_chunk in response_chunks:
            print(response_chunk)
            
        print("--- Execution Complete ---")
        print("✅ Integration test pipeline finished without system failures.")
        return True
        
    except Exception as e:
        print(f"❌ Integration execution aborted with error: {e}")
        return False

if __name__ == "__main__":
    raise SystemExit(0 if run_integration_pipeline() else 1)

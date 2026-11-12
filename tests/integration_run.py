# tests/integration_run.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm_router import LLMRouter
from src.agent_factory import AgentFactory

def run_integration_pipeline():
    print("=== Launching End-to-End Pipeline Integration ===")
    
    # 1. Simulate UI selections
    chosen_backend = "Local Machine (Ollama - Llama 3.2)"
    chosen_profile = "Research Analyst" # Maps to tech_researcher inside agents.yaml
    sample_prompt = "What are the core differences between an Entity and a Value Object in Clean Architecture?"
    
    try:
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
        for response_chunk in agent_runner.run(sample_prompt):
            print(response_chunk)
            
        print("--- Execution Complete ---")
        print("✅ Integration test pipeline finished without system failures.")
        
    except Exception as e:
        print(f"❌ Integration execution aborted with error: {e}")

if __name__ == "__main__":
    run_integration_pipeline()

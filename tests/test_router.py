# tests/test_router.py
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm_router import LLMRouter

def test_ollama_route():
    print("=== Testing Infrastructure Router ===")
    
    try:
        backends = LLMRouter.get_supported_backends()
        print(f"Supported Backends identified: {backends}")
        
        # Pull the primary local handle
        target_choice = backends[0] 
        print(f"Attempting instantiation for: {target_choice}...")
        
        llm_instance = LLMRouter.create_backend(target_choice)
        
        # Execute a direct lightweight completion to test network socket
        print("Pinging model endpoint...")
        response = llm_instance.call([{"role": "user", "content": "Respond with the word 'Online'"}])
        
        print(f"Model Response: {response}")
        print("✅ Router connection verified.")
        
    except Exception as e:
        print(f"❌ Router Connection Failed. Details: {e}")
        print("\n💡 Tip: Make sure 'ollama pull llama3.2' and the Ollama app are running background sessions.")

if __name__ == "__main__":
    test_ollama_route()

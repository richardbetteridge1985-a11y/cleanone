# tests/test_rag.py
import sys
import os

# Append project root to path so we can import 'src' smoothly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag_engine import RAGEngine

def run_rag_test():
    print("=== Testing RAG Engine Layer ===")
    
    # Ensure initialization code triggers safely
    RAGEngine.initialize_knowledge_base()
    
    # Define a highly specific architectural concept to query
    test_query = "Bounded Context mapping rules in Domain Driven Design"
    print(f"\nSearching database for: '{test_query}'...")
    
    results = RAGEngine.query_knowledge_base(test_query, n_results=2)
    
    print("\n[Database Return Context]:")
    print(results)
    
    if "Error" in results or "No specific references" in results:
        print("\n❌ RAG retrieval test failed.")
    else:
        print("\n✅ RAG retrieval test completed successfully!")

if __name__ == "__main__":
    run_rag_test()

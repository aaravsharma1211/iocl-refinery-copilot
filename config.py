import os

class Config:
    # Set default model tier ("openai" or "ollama")
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
    
    # OpenAI Settings
    OPENAI_MODEL = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
    
    # Ollama Settings (For local air-gapped deployment)
    OLLAMA_MODEL = "llama3.1:8b"
    OLLAMA_BASE_URL = "http://localhost:11434"
    
    # RAG Settings
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 150
    SEARCH_TOP_K = 4
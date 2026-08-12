import os
import io
import re
import pypdf
from PIL import Image
import easyocr
import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from langchain_groq import ChatGroq


class AdvancedRAGEngine:
    """
    Production-grade Hybrid RAG Engine for IOCL Enterprise Refinery Copilot.
    Supports:
    1. PDF text extraction with EasyOCR fallback (English & Hindi technical logs).
    2. Document version tracking and metadata indexing.
    3. Hybrid Search (BM25 + Vector Embeddings via Reciprocal Rank Fusion).
    4. Conversational memory integration for multi-turn chat context.
    """
    def __init__(self, chroma_path: str = "./chroma_db", groq_api_key: str = None):
        # 1. Initialize Vector DB & Embeddings
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.chroma_client.get_or_create_collection(name="iocl_sops")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # 2. Lazy-load EasyOCR for English & Hindi technical text (Multilingual Support)
        self._ocr_reader = None

        # 3. LLM Setup
        self.api_key = groq_api_key or os.getenv("GROQ_API_KEY")

    @property
    def ocr_reader(self):
        """Lazy loader for EasyOCR supporting English and Hindi technical text."""
        if self._ocr_reader is None:
            self._ocr_reader = easyocr.Reader(['en', 'hi'], gpu=False)
        return self._ocr_reader

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> list[dict]:
        """Extract text page-by-page. Automatically falls back to EasyOCR if page is scanned."""
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_content = []

        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""

            # If page contains almost no text, treat it as a scanned image
            if len(text.strip()) < 50 and hasattr(page, "images"):
                ocr_text = ""
                for img in page.images:
                    try:
                        results = self.ocr_reader.readtext(img.data, detail=0)
                        ocr_text += " ".join(results) + " "
                    except Exception:
                        pass
                if ocr_text.strip():
                    text = ocr_text

            pages_content.append({
                "page_number": idx + 1,
                "content": text.strip()
            })

        return pages_content

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Simple sliding window chunker for maintaining context."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk:
                chunks.append(chunk)
        return chunks

    def process_pdfs(self, uploaded_files, version: str = "v1.0") -> tuple[int, int]:
        """Indexes PDFs into ChromaDB with rich metadata, including document versioning."""
        total_pdfs = 0
        total_chunks = 0

        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.read()
            pages = self.extract_text_from_pdf(file_bytes)

            ids, docs, metadatas = [], [], []

            for page in pages:
                chunks = self._chunk_text(page["content"])
                for c_idx, chunk in enumerate(chunks):
                    chunk_id = f"{uploaded_file.name}_{version}_p{page['page_number']}_{c_idx}"
                    ids.append(chunk_id)
                    docs.append(chunk)
                    metadatas.append({
                        "filename": uploaded_file.name,
                        "page": page["page_number"],
                        "version": version
                    })

            if docs:
                embeddings = self.embedder.encode(docs).tolist()
                # Upsert safely handles version updates without duplicate key collisions
                self.collection.upsert(
                    ids=ids,
                    documents=docs,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                total_pdfs += 1
                total_chunks += len(docs)

        return total_pdfs, total_chunks

    def hybrid_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Combines BM25 exact keyword matching with Vector Embeddings via Reciprocal Rank Fusion."""
        all_docs = self.collection.get()
        if not all_docs or not all_docs['documents']:
            return []

        doc_texts = all_docs['documents']
        metadatas = all_docs['metadatas']
        doc_ids = all_docs['ids']

        # --- A. BM25 Keyword Search ---
        tokenized_corpus = [re.findall(r'\w+', doc.lower()) for doc in doc_texts]
        bm25 = BM25Okapi(tokenized_corpus)
        tokenized_query = re.findall(r'\w+', query.lower())
        bm25_scores = bm25.get_scores(tokenized_query)
        bm25_ranked_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:20]

        # --- B. Vector Embeddings Search ---
        query_emb = self.embedder.encode([query]).tolist()
        vector_res = self.collection.query(query_embeddings=query_emb, n_results=min(20, len(doc_texts)))
        vector_ids = vector_res['ids'][0] if vector_res['ids'] else []

        # --- C. Reciprocal Rank Fusion (RRF) ---
        rrf_scores = {}
        k_const = 60

        for rank, d_id in enumerate(vector_ids):
            rrf_scores[d_id] = rrf_scores.get(d_id, 0) + (1.0 / (k_const + rank + 1))

        for rank, idx in enumerate(bm25_ranked_indices):
            d_id = doc_ids[idx]
            rrf_scores[d_id] = rrf_scores.get(d_id, 0) + (1.0 / (k_const + rank + 1))

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]

        id_map = {d_id: (doc, meta) for d_id, doc, meta in zip(doc_ids, doc_texts, metadatas)}

        results = []
        for d_id in sorted_ids:
            if d_id in id_map:
                doc, meta = id_map[d_id]
                results.append({"text": doc, "metadata": meta})

        return results

    def query(self, user_question: str, groq_api_key: str = None, chat_history: list = None) -> dict:
        """Executes full RAG query using Llama 3.3 70B on Groq with conversation history & version citations."""
        api_key = groq_api_key or self.api_key
        if not api_key:
            return {"answer": "Groq API key is missing. Please set it in config or sidebar.", "citations": []}

        retrieved_results = self.hybrid_search(user_question, top_k=5)

        if not retrieved_results:
            return {"answer": "No relevant SOPs found in the database. Please index documents first.", "citations": []}

        context_blocks = []
        citations = []

        for i, item in enumerate(retrieved_results, 1):
            meta = item["metadata"]
            version_tag = f" [Ver: {meta.get('version', 'v1.0')}]" if 'version' in meta else ""
            context_blocks.append(f"[Source {i} - {meta['filename']}, Page {meta['page']}{version_tag}]:\n{item['text']}")
            citations.append({
                "filename": meta['filename'],
                "page": meta['page'],
                "version": meta.get('version', 'v1.0'),
                "snippet": item['text'][:150] + "..."
            })

        context_str = "\n\n".join(context_blocks)

        # Format conversation history for memory persistence across turns
        history_str = ""
        if chat_history:
            history_str = "Conversation History:\n" + "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history[-4:]]) + "\n\n"

        llm = ChatGroq(model_name="llama-3.3-70b-versatile", groq_api_key=api_key, temperature=0.1)

        prompt = f"""You are the IOCL Enterprise Refinery Copilot.
Answer the user's question strictly using the provided SOP context and conversation history.
If the answer cannot be determined from the context, state that clearly.

{history_str}Context:
{context_str}

User Question: {user_question}

Provide a structured, step-by-step response with exact safety operational instructions and reference source versions where applicable.
"""
        answer = llm.invoke(prompt).content
        return {"answer": answer, "citations": citations}
"""
HealthBridge AI – HIPAA-aware Medical RAG with Pinecone.
"""
import logging
import hashlib
import re
from typing import Optional, List

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from pinecone import Pinecone, ServerlessSpec

from app.core.config import settings

logger = logging.getLogger(__name__)

# PHI patterns for de-identification
PHI_PATTERNS = [
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),
    (r'\b\d{10}\b', '[PHONE]'),
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
    (r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', '[DATE]'),
    (r'(?i)(patient|name):\s*[A-Z][a-z]+\s+[A-Z][a-z]+', '[PATIENT_NAME]'),
    (r'\b\d{5}(?:-\d{4})?\b', '[ZIP]'),
    (r'(?i)mrn[:\s]\s*\d+', '[MRN]'),
]

MEDICAL_SYSTEM_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""You are a highly knowledgeable medical information assistant. Your role is to
assist healthcare professionals with clinical document research and information retrieval.

IMPORTANT DISCLAIMERS:
- This system is for healthcare professional use only
- Responses are for informational purposes and do not replace clinical judgment
- Always follow institutional protocols and consult appropriate specialists

HIPAA Compliance: All patient identifiers have been de-identified in this system.

Use the following clinical documents to answer the query:

Context:
{context}

Clinical Query: {question}

Provide a structured clinical response:
1. Relevant Clinical Information
2. Supporting Evidence (cite document sections)
3. Clinical Considerations
4. Triage Priority (if applicable): CRITICAL / URGENT / ROUTINE
5. Recommended Next Steps
6. Confidence Level: HIGH / MODERATE / LOW

Note any limitations in the available information."""
)

ZERO_SHOT_GUARDRAIL = """Before answering, verify:
- Is this a legitimate clinical query?
- Does the response risk patient harm if incorrect?
- Are there red flags requiring immediate escalation?

If any concern: prepend 'CLINICAL ALERT:' to the response."""


def deidentify_text(text: str) -> str:
    for pattern, replacement in PHI_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


class MedicalRAGService:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBED_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        self.llm_gpt4 = ChatOpenAI(
            model=settings.GPT4_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
        )
        self.llm_claude = ChatAnthropic(
            model=settings.CLAUDE_MODEL,
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
        )
        self.pinecone_index = None
        self._init_pinecone()

    def _init_pinecone(self):
        if not settings.PINECONE_API_KEY:
            logger.warning("Pinecone API key not set – vector search unavailable.")
            return
        try:
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            existing = [idx.name for idx in pc.list_indexes()]
            if settings.PINECONE_INDEX_NAME not in existing:
                pc.create_index(
                    name=settings.PINECONE_INDEX_NAME,
                    dimension=1536,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
                logger.info("Created Pinecone index: %s", settings.PINECONE_INDEX_NAME)
            self.pinecone_index = pc.Index(settings.PINECONE_INDEX_NAME)
            stats = self.pinecone_index.describe_index_stats()
            logger.info("Pinecone index ready. Vectors: %d", stats.total_vector_count)
        except Exception as exc:
            logger.error("Pinecone init error: %s", exc)

    def ingest_clinical_documents(self, file_paths: List[str]) -> dict:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        all_chunks = []
        for fp in file_paths:
            try:
                loader = PyPDFLoader(fp) if fp.endswith(".pdf") else None
                if loader:
                    docs = loader.load()
                    chunks = splitter.split_documents(docs)
                    if settings.HIPAA_MODE:
                        for chunk in chunks:
                            chunk.page_content = deidentify_text(chunk.page_content)
                    all_chunks.extend(chunks)
            except Exception as exc:
                logger.error("Error loading %s: %s", fp, exc)

        if self.pinecone_index and all_chunks:
            batch_size = 100
            upserted = 0
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i:i + batch_size]
                texts = [c.page_content for c in batch]
                embeddings = self.embeddings.embed_documents(texts)
                vectors = [
                    (
                        hashlib.md5(text.encode()).hexdigest(),
                        emb,
                        {"text": text[:1000], "source": batch[j].metadata.get("source", "")},
                    )
                    for j, (text, emb) in enumerate(zip(texts, embeddings))
                ]
                self.pinecone_index.upsert(vectors=vectors)
                upserted += len(vectors)

            return {"chunks_ingested": upserted, "hipaa_deidentified": settings.HIPAA_MODE}
        return {"chunks_ingested": 0, "error": "Pinecone not available or no chunks generated"}

    def query(self, clinical_query: str, use_claude: bool = False) -> dict:
        if not self.pinecone_index:
            return {
                "answer": "Vector database not available. Please configure Pinecone.",
                "triage_priority": "UNKNOWN",
                "sources": [],
            }

        query_clean = deidentify_text(clinical_query) if settings.HIPAA_MODE else clinical_query
        query_embedding = self.embeddings.embed_query(query_clean)
        results = self.pinecone_index.query(
            vector=query_embedding,
            top_k=settings.TOP_K_RESULTS,
            include_metadata=True,
        )

        context_chunks = []
        sources = []
        for match in results.matches:
            if match.score > 0.65:
                text = match.metadata.get("text", "")
                context_chunks.append(text)
                sources.append({
                    "source": match.metadata.get("source", "unknown"),
                    "score": round(match.score, 3),
                })

        context = "\n\n---\n\n".join(context_chunks) if context_chunks else "No relevant documents found."
        prompt = MEDICAL_SYSTEM_PROMPT.format(context=context, question=query_clean)

        llm = self.llm_claude if use_claude else self.llm_gpt4
        model_name = settings.CLAUDE_MODEL if use_claude else settings.GPT4_MODEL

        from langchain.schema import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        answer = response.content

        triage_priority = "UNKNOWN"
        if "CRITICAL" in answer:
            triage_priority = "CRITICAL"
        elif "URGENT" in answer:
            triage_priority = "URGENT"
        elif "ROUTINE" in answer:
            triage_priority = "ROUTINE"

        return {
            "answer": answer,
            "triage_priority": triage_priority,
            "model_used": model_name,
            "sources": sources,
            "hipaa_compliant": settings.HIPAA_MODE,
            "clinical_alert": answer.startswith("CLINICAL ALERT:"),
        }

    def get_index_stats(self) -> dict:
        if not self.pinecone_index:
            return {"status": "unavailable", "total_vectors": 0}
        try:
            stats = self.pinecone_index.describe_index_stats()
            return {
                "status": "ready",
                "total_vectors": stats.total_vector_count,
                "index_name": settings.PINECONE_INDEX_NAME,
                "hipaa_mode": settings.HIPAA_MODE,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


_service: Optional[MedicalRAGService] = None


def get_medical_rag_service() -> MedicalRAGService:
    global _service
    if _service is None:
        _service = MedicalRAGService()
    return _service

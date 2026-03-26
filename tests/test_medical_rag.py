"""Tests for HealthBridge AI Medical RAG Service."""
import pytest
from app.services.medical_rag_service import deidentify_text


def test_deidentify_ssn():
    text = "Patient SSN: 123-45-6789"
    result = deidentify_text(text)
    assert "123-45-6789" not in result
    assert "[SSN]" in result


def test_deidentify_email():
    text = "Contact: patient@hospital.com"
    result = deidentify_text(text)
    assert "patient@hospital.com" not in result
    assert "[EMAIL]" in result


def test_deidentify_mrn():
    text = "MRN: 12345678"
    result = deidentify_text(text)
    assert "MRN: 12345678" not in result


def test_query_no_pinecone():
    """Query returns appropriate message when Pinecone unavailable."""
    from unittest.mock import MagicMock, patch
    with patch("app.services.medical_rag_service.OpenAIEmbeddings"), \
         patch("app.services.medical_rag_service.ChatOpenAI"), \
         patch("app.services.medical_rag_service.ChatAnthropic"), \
         patch("app.services.medical_rag_service.Pinecone") as mock_pc:
        mock_pc.return_value.list_indexes.side_effect = Exception("No API key")
        from app.services.medical_rag_service import MedicalRAGService
        svc = MedicalRAGService.__new__(MedicalRAGService)
        svc.pinecone_index = None
        result = svc.query("What is the treatment for pneumonia?")
        assert "not available" in result["answer"].lower()


def test_health_endpoint():
    from unittest.mock import patch
    with patch("app.services.medical_rag_service.OpenAIEmbeddings"), \
         patch("app.services.medical_rag_service.ChatOpenAI"), \
         patch("app.services.medical_rag_service.ChatAnthropic"), \
         patch("app.services.medical_rag_service.Pinecone"):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        r = client.get("/api/v1/medical/health")
        assert r.status_code == 200
        assert r.json()["hipaa_compliant"] is True

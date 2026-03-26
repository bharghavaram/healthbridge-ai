"""HealthBridge AI – Medical RAG and triage routes."""
import shutil
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from app.services.medical_rag_service import MedicalRAGService, get_medical_rag_service

router = APIRouter(prefix="/medical", tags=["Medical Intelligence"])


class ClinicalQueryRequest(BaseModel):
    query: str
    use_claude: bool = False


class TriageRequest(BaseModel):
    symptoms: str
    patient_context: Optional[str] = None


@router.post("/query")
async def clinical_query(
    request: ClinicalQueryRequest,
    service: MedicalRAGService = Depends(get_medical_rag_service),
):
    """Query the medical knowledge base with HIPAA-compliant de-identification."""
    if len(request.query.strip()) < 10:
        raise HTTPException(status_code=400, detail="Query too short.")
    return service.query(request.query, request.use_claude)


@router.post("/triage")
async def triage_symptoms(
    request: TriageRequest,
    service: MedicalRAGService = Depends(get_medical_rag_service),
):
    """Provide triage prioritisation based on symptoms."""
    triage_query = f"Triage assessment for: {request.symptoms}"
    if request.patient_context:
        triage_query += f"\nPatient context: {request.patient_context}"
    result = service.query(triage_query, use_claude=True)
    return {
        **result,
        "triage_type": "symptom_based",
        "disclaimer": "For healthcare professional use only. Not a substitute for clinical judgment.",
    }


@router.post("/upload")
async def upload_clinical_documents(
    files: List[UploadFile] = File(...),
    service: MedicalRAGService = Depends(get_medical_rag_service),
):
    """Upload clinical documents for HIPAA-aware indexing."""
    saved_paths = []
    tmp_dir = tempfile.mkdtemp()
    try:
        for file in files:
            if not file.filename.endswith((".pdf", ".txt")):
                raise HTTPException(status_code=400, detail=f"Unsupported: {file.filename}")
            dest = Path(tmp_dir) / file.filename
            with open(dest, "wb") as f:
                shutil.copyfileobj(file.file, f)
            saved_paths.append(str(dest))

        result = service.ingest_clinical_documents(saved_paths)
        result["files"] = [f.filename for f in files]
        return result
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/stats")
async def get_stats(service: MedicalRAGService = Depends(get_medical_rag_service)):
    return service.get_index_stats()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "HealthBridge AI - Medical Document Intelligence & Triage",
        "hipaa_compliant": True,
    }

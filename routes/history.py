from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session
from database import get_db, AuditHistory

router = APIRouter()

@router.post("/")
async def save_audit(
    filename: str = Body(...),
    compliance_status: str = Body(...),
    clause_count: int = Body(...),
    session_id: str = Body(...),
    db: Session = Depends(get_db)
):
    session_id = session_id.strip()
    if not session_id:
        return {"status": "skipped", "reason": "missing session"}

    audit = AuditHistory(
        session_id=session_id,
        filename=filename,
        compliance_status=compliance_status,
        clause_count=clause_count
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return {"status": "saved", "id": audit.id}

@router.get("/list")
async def get_audits(
    session_id: str = Query(...),
    db: Session = Depends(get_db)
):
    session_id = session_id.strip()
    if not session_id:
        return []

    audits = (
        db.query(AuditHistory)
        .filter(AuditHistory.session_id == session_id)
        .order_by(AuditHistory.timestamp.desc())
        .all()
    )
    return audits

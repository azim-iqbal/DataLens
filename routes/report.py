from fastapi import APIRouter, Body, HTTPException

from services.report_service import create_pdf_report, generate_report_data


router = APIRouter()


@router.post("/")
async def generate_report(file_id: str = Body(..., embed=True)):
    report_data = generate_report_data(file_id)
    if not report_data:
        raise HTTPException(status_code=404, detail="Report data not found")

    pdf_path = create_pdf_report(file_id, report_data)

    return {
        "report": report_data,
        "pdf_path": pdf_path,
        "download_url": f"/download/report/{file_id}",
    }

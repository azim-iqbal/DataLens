import os
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from cryptography.fernet import Fernet

from services.dataset_service import ensure_data_dirs


load_dotenv()
ensure_data_dirs()
logger = logging.getLogger("datalens")

app = FastAPI(title="DataLens API")

if os.environ.get("ENABLE_HTTPS_REDIRECT", "").strip().lower() in {"1", "true", "yes"}:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes import audit, counterfactual, eu_mapper, fix, history, report, upload
from routes.dictionary import router as dictionary_router
from routes.export import router as export_router

app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(audit.router, prefix="/audit", tags=["Audit"])
app.include_router(counterfactual.router, prefix="/counterfactual", tags=["Counterfactual"])
app.include_router(eu_mapper.router, prefix="/eu-mapper", tags=["EU Mapper"])
app.include_router(fix.router, prefix="/fix", tags=["Fix"])
app.include_router(report.router, prefix="/report", tags=["Report"])
app.include_router(history.router, prefix="/history", tags=["History"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
app.include_router(dictionary_router)
app.include_router(export_router)


@app.on_event("startup")
async def ensure_file_encryption_key() -> None:
    if not os.environ.get("FILE_ENCRYPTION_KEY"):
        os.environ["FILE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        logger.warning(
            "FILE_ENCRYPTION_KEY was not set; generated an in-memory development key. "
            "Set FILE_ENCRYPTION_KEY explicitly in production."
        )

if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="frontend")


@app.get("/")
def upload_page():
    return FileResponse("frontend/upload.html")


@app.get("/upload.html")
def upload_html():
    return FileResponse("frontend/upload.html")


@app.get("/results")
@app.get("/results.html")
def results_page():
    return FileResponse("frontend/results.html")


@app.get("/view-history")
@app.get("/history.html")
def history_page():
    return FileResponse("frontend/history.html")


@app.get("/download/fixed/{file_id}")
def download_fixed(file_id: str):
    path = os.path.join("data", "uploads", f"{file_id}_fixed.csv")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Fixed dataset not found")
    return FileResponse(path, media_type="text/csv", filename=f"datalens_fixed_{file_id}.csv")


@app.get("/download/report/{file_id}")
def download_report(file_id: str):
    path = os.path.join("data", "reports", f"{file_id}_report.pdf")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="application/pdf", filename=f"datalens_report_{file_id}.pdf")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/api")
def api_root():
    return {"message": "DataLens API running"}

import json
import os

from fastapi import APIRouter, Body, HTTPException

from services.counterfactual_service import run_counterfactual_test


router = APIRouter()


@router.post("/")
async def counterfactual_test(
    file_id: str = Body(...),
    filepath: str = Body(...),
    sensitive_column: str = Body(...),
    outcome_column: str = Body(...),
):
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Dataset not found")

    result = run_counterfactual_test(filepath, sensitive_column, outcome_column)

    with open(f"data/uploads/{file_id}_cf.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result

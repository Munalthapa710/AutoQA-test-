from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from autoqa_shared.models import GeneratedTest
from autoqa_shared.schemas import GeneratedTestRead

from ...dependencies import get_db

router = APIRouter(prefix="/generated-tests", tags=["generated-tests"])


@router.get("", response_model=list[GeneratedTestRead])
def list_generated_tests(db: Session = Depends(get_db)) -> list[GeneratedTest]:
    return list(db.scalars(select(GeneratedTest).order_by(GeneratedTest.created_at.desc())).all())


@router.get("/{generated_test_id}", response_model=GeneratedTestRead)
def get_generated_test(generated_test_id: str, db: Session = Depends(get_db)) -> GeneratedTest:
    generated_test = db.get(GeneratedTest, generated_test_id)
    if generated_test is None:
        raise HTTPException(status_code=404, detail="Generated test not found")
    return generated_test

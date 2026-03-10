from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from autoqa_shared.models import TestConfig
from autoqa_shared.schemas import TestConfigCreate, TestConfigRead

from ...dependencies import get_db

router = APIRouter(prefix="/configs", tags=["configs"])


@router.post("", response_model=TestConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(payload: TestConfigCreate, db: Session = Depends(get_db)) -> TestConfig:
    config = TestConfig(**payload.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("", response_model=list[TestConfigRead])
def list_configs(db: Session = Depends(get_db)) -> list[TestConfig]:
    return list(db.scalars(select(TestConfig).order_by(TestConfig.created_at.desc())).all())


@router.get("/{config_id}", response_model=TestConfigRead)
def get_config(config_id: str, db: Session = Depends(get_db)) -> TestConfig:
    config = db.get(TestConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")
    return config

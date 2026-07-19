from datetime import datetime

from pydantic import BaseModel, field_validator


class WaterQualityReadingPublic(BaseModel):
    parameter_key: str
    label: str
    value: str
    unit: str
    status: str
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WaterQualityReadingUpdate(BaseModel):
    parameter_key: str
    value: str
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("good", "warn", "unsafe"):
            raise ValueError("status must be 'good', 'warn', or 'unsafe'")
        return v


class WaterQualityUpdate(BaseModel):
    readings: list[WaterQualityReadingUpdate]

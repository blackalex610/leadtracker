from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Schema(BaseModel):
    """Base for API schemas: in response (serialization) schemas every field is
    marked required, since it is always present in the JSON."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class ORMModel(Schema):
    model_config = ConfigDict(from_attributes=True, json_schema_serialization_defaults_required=True)


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorDetail(Schema):
    code: str
    message: str


class ErrorResponse(Schema):
    detail: ErrorDetail


class OkResponse(Schema):
    ok: bool = True

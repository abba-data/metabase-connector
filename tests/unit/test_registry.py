from __future__ import annotations

import pytest
from pydantic import BaseModel

from connector.models import Scope
from connector.registry import RpcDescriptor, _Registry


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def test_register_and_lookup() -> None:
    r = _Registry()
    d = RpcDescriptor(
        name="demo",
        version="1.0.0",
        description="demo",
        input_model=_Input,
        output_model=_Output,
        metabase_card_id=42,
        required_scope=Scope.GENERAL,
    )
    r.register(d)
    assert r.get("demo") is d
    assert list(r.all()) == [d]


def test_duplicate_name_rejected() -> None:
    r = _Registry()
    d = RpcDescriptor(name="demo", version="1.0.0", description="d", input_model=_Input)
    r.register(d)
    with pytest.raises(ValueError):
        r.register(d)


def test_as_catalog_serializes_schemas() -> None:
    r = _Registry()
    r.register(
        RpcDescriptor(
            name="demo", version="1.0.0", description="d", input_model=_Input, output_model=_Output
        )
    )
    cat = r.as_catalog()
    assert len(cat) == 1
    entry = cat[0]
    assert entry["name"] == "demo"
    assert entry["input_schema"]["properties"]["x"]["type"] == "integer"
    assert entry["output_schema"]["properties"]["y"]["type"] == "integer"
    assert entry["required_scope"] == "general"

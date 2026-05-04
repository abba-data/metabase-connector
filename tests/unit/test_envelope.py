from __future__ import annotations

from connector.models import Kind, Response, ResponseMeta, envelope_for


def test_envelope_for_defaults() -> None:
    meta = envelope_for(request_id="r1", freshness_window_days=60)
    assert meta.kind == Kind.CATALOG
    assert meta.source_question_id is None
    assert meta.freshness_window_days == 60
    assert meta.request_id == "r1"


def test_response_generic_carries_data_and_meta() -> None:
    meta = envelope_for(
        request_id="r2", freshness_window_days=30, source_question_id=159, kind=Kind.CATALOG
    )
    resp: Response[list[int]] = Response(data=[1, 2, 3], meta=meta)
    assert resp.data == [1, 2, 3]
    assert resp.meta.source_question_id == 159
    assert resp.meta.freshness_window_days == 30

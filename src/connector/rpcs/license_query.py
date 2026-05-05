from __future__ import annotations

from datetime import date
from enum import Enum

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from connector.models import Response, Scope
from connector.registry import RpcDescriptor
from connector.rpc_config import CARD_ID_LICENSE_QUERY
from connector.rpcs._helpers import execute_card_rows, wrap
from connector.security.scopes import require_scope

router = APIRouter()


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CANCELLED = "cancelled"


class HostingType(str, Enum):
    CLOUD = "Cloud"
    DATA_CENTER = "DataCenter"
    SERVER = "Server"


class LicenseTypeEnum(str, Enum):
    COMMERCIAL = "COMMERCIAL"
    ACADEMIC = "ACADEMIC"


class LicenseQueryInput(BaseModel):
    partner: str | None = None
    company: str | None = None
    addon: str | None = None
    status: LicenseStatus | None = None
    hosting: HostingType | None = None
    license_type: LicenseTypeEnum | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class License(BaseModel):
    id: str
    partner: str | None = None
    company: str | None = None
    addon: str | None = None
    status: str | None = None
    hosting: str | None = None
    license_type: str | None = None
    maintenance_start_date: date | None = None
    maintenance_end_date: date | None = None


class LicenseQueryOutput(BaseModel):
    rows: list[License]


DESCRIPTOR = RpcDescriptor(
    name="license_query",
    version="1.0.0",
    description="Flexible license lookup with named optional filters. Active-license rule applied via WHF-01 view.",
    input_model=LicenseQueryInput,
    output_model=LicenseQueryOutput,
    metabase_card_id=CARD_ID_LICENSE_QUERY,
    required_scope=Scope.GENERAL,
)


def _params(inp: LicenseQueryInput) -> list[dict]:
    pairs: list[tuple[str, object | None, str]] = [
        ("partner", inp.partner, "category"),
        ("company", inp.company, "category"),
        ("addon", inp.addon, "category"),
        ("status", inp.status.value if inp.status else None, "category"),
        ("hosting", inp.hosting.value if inp.hosting else None, "category"),
        ("license_type", inp.license_type.value if inp.license_type else None, "category"),
    ]
    out: list[dict] = []
    for name, value, ptype in pairs:
        if value is None:
            continue
        out.append({"type": ptype, "target": ["variable", ["template-tag", name]], "value": value})
    out.append(
        {"type": "number/=", "target": ["variable", ["template-tag", "limit"]], "value": inp.limit}
    )
    return out


def _coerce_date(v: object) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


@router.post(
    "/rpc/license_query",
    response_model=Response[LicenseQueryOutput],
    tags=["catalog"],
)
async def license_query(
    request: Request,
    body: LicenseQueryInput,
    consumer=Depends(require_scope(Scope.GENERAL)),
) -> Response[LicenseQueryOutput]:
    rows = await execute_card_rows(request, DESCRIPTOR, parameters=_params(body))
    out_rows = [
        License(
            id=str(r.get("id") or r.get("license_id") or ""),
            partner=r.get("partner") or r.get("partnerName"),
            company=r.get("company") or r.get("companyName"),
            addon=r.get("addon") or r.get("addonName"),
            status=r.get("status"),
            hosting=r.get("hosting"),
            license_type=r.get("license_type") or r.get("licenseType"),
            maintenance_start_date=_coerce_date(
                r.get("maintenance_start_date") or r.get("maintenanceStartDate")
            ),
            maintenance_end_date=_coerce_date(
                r.get("maintenance_end_date") or r.get("maintenanceEndDate")
            ),
        )
        for r in rows
    ]
    return wrap(request, DESCRIPTOR, LicenseQueryOutput(rows=out_rows))

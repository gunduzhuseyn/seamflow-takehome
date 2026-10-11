import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.dependencies import ActiveOrg, OrgContext, require_role
from app.auth.models import Membership, Organization, Role
from app.core.db import SessionDep

router = APIRouter()


class UserOut(BaseModel):
    id: uuid.UUID
    email: str


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class MembershipOut(BaseModel):
    org: OrgOut
    role: Role


class MeResponse(BaseModel):
    user: UserOut
    org: OrgOut
    role: Role
    memberships: list[MembershipOut]


class OrgRename(BaseModel):
    name: str = Field(min_length=1, max_length=255)


def _org_out(org: Organization) -> OrgOut:
    return OrgOut(id=org.id, name=org.name, slug=org.slug)


@router.get("/me", tags=["auth"])
async def me(session: SessionDep, context: OrgContext) -> MeResponse:
    rows = await session.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .where(Membership.user_id == context.user.id)
        .order_by(Membership.created_at, Membership.org_id)
    )
    return MeResponse(
        user=UserOut(id=context.user.id, email=context.user.email),
        org=_org_out(context.org),
        role=context.role,
        memberships=[
            MembershipOut(org=_org_out(org), role=membership.role)
            for membership, org in rows
        ],
    )


@router.patch("/orgs/current", tags=["orgs"])
async def rename_current(
    session: SessionDep,
    context: Annotated[ActiveOrg, Depends(require_role(Role.admin))],
    body: OrgRename,
) -> OrgOut:
    context.org.name = body.name
    await session.commit()
    return _org_out(context.org)

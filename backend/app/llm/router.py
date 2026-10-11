import uuid

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import OrgContext
from app.core.db import SessionDep
from app.llm.calls import LLMCallOut
from app.llm.models import LLMCallRepository

router = APIRouter(prefix="/llm-calls", tags=["llm-calls"])


@router.get("/{call_id}", name="get")
async def get_llm_call(
    session: SessionDep, context: OrgContext, call_id: uuid.UUID
) -> LLMCallOut:
    call = await LLMCallRepository(session).get(context.org.id, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LLM call not found")
    return LLMCallOut.model_validate(call)

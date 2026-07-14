"""合同处理任务：文本抽取 → LLM 要素抽取 → LLM 风险审查。"""

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.ai.client import get_llm_client
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import ContractExtractOutput, ContractReviewOutput
from app.core.exceptions import DomainError
from app.models.contract import Contract
from app.models.enums import ContractStatus, LlmTaskType
from app.services import knowledge_service
from app.services.contract_service import (
    MAX_TEXT_CHARS,
    contract_file_path,
    get_risk_checklist,
)

logger = logging.getLogger(__name__)


async def process_contract_task(ctx: dict[str, Any], contract_id: str) -> None:
    llm = ctx.get("llm") or get_llm_client()
    async with ctx["sessionmaker"]() as session:
        contract = await session.scalar(
            select(Contract).where(
                Contract.id == uuid.UUID(contract_id), Contract.deleted_at.is_(None)
            )
        )
        if contract is None:
            return
        path = contract_file_path(contract.id)
        if path is None:
            contract.status = ContractStatus.FAILED
            contract.error_msg = "合同源文件缺失"
            await session.commit()
            return
        try:
            text = knowledge_service.extract_text(path).strip()
            if not text:
                raise DomainError("合同内容为空")
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS]
                logger.warning("合同 %s 文本超长，截断至 %d 字符", contract_id, MAX_TEXT_CHARS)

            extracted = await llm.chat_structured(
                LlmTaskType.CONTRACT_EXTRACT,
                [
                    {
                        "role": "user",
                        "content": render_prompt("contract_extract.j2", contract_text=text),
                    }
                ],
                ContractExtractOutput,
                user_id=contract.owner_id,
            )
            review = await llm.chat_structured(
                LlmTaskType.CONTRACT_REVIEW,
                [
                    {
                        "role": "user",
                        "content": render_prompt(
                            "contract_review.j2",
                            contract_text=text,
                            checklist=get_risk_checklist(),
                        ),
                    }
                ],
                ContractReviewOutput,
                user_id=contract.owner_id,
            )
            contract.extracted = extracted.model_dump()
            contract.review = review.model_dump()
            contract.status = ContractStatus.READY
            contract.error_msg = None
            await session.commit()
        except DomainError as exc:
            contract.status = ContractStatus.FAILED
            contract.error_msg = exc.message[:500]
            await session.commit()
            logger.warning("合同 %s 处理失败：%s", contract_id, exc.message)
        except Exception:
            contract.status = ContractStatus.FAILED
            contract.error_msg = "处理异常，请重试"
            await session.commit()
            logger.exception("合同 %s 处理异常", contract_id)

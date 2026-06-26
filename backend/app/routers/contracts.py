import io
import os
import traceback
from datetime import datetime
from typing import Optional, List
import pypdf  # type: ignore
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from groq import AsyncGroq  # type: ignore

from app.database import get_session
from app.models import Contract, ChatMessage
from app.services.ai_service import analyze_contract_text
from app.auth import verify_clerk_token

router = APIRouter(prefix="/contracts", tags=["Contracts"])


# ==========================================
# Pydantic Schemas
# ==========================================
class ContractCreateInput(BaseModel):
    title: Optional[str] = None
    vendor_name: Optional[str] = None
    amount: Optional[float] = 0.0
    currency: Optional[str] = "EUR"
    status: Optional[str] = "draft"
    created_at: Optional[datetime] = None


class ChatRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    id: int
    contract_id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# Endpoints
# ==========================================


@router.get("", status_code=status.HTTP_200_OK)
async def get_contracts(
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(None, description="جستجو در عنوان قرارداد یا نام فروشنده"),
    status: Optional[str] = Query(
        None, description="فیلتر بر اساس وضعیت (draft, active, expired)"
    ),
    currency: Optional[str] = Query(
        None, description="فیلتر بر اساس نوع ارز (USD, EUR)"
    ),
    min_amount: Optional[float] = Query(None, description="حداقل مبلغ قرارداد"),
    max_amount: Optional[float] = Query(None, description="حداکثر مبلغ قرارداد"),
    limit: int = Query(10, ge=1, le=100, description="تعداد آیتم‌های هر صفحه"),
    offset: int = Query(0, ge=0, description="تعداد آیتم‌هایی که باید رد شوند"),
    user_data: dict = Depends(verify_clerk_token),
):
    try:
        statement = select(Contract)
        filters = []

        if q:
            filters.append(
                or_(
                    Contract.title.ilike(f"%{q}%"), Contract.vendor_name.ilike(f"%{q}%")
                )
            )

        if status:
            filters.append(Contract.status == status)

        if currency:
            filters.append(Contract.currency == currency)

        if min_amount is not None:
            filters.append(Contract.amount >= min_amount)

        if max_amount is not None:
            filters.append(Contract.amount <= max_amount)

        if filters:
            statement = statement.where(and_(*filters))

        count_statement = select(func.count(Contract.id))
        if filters:
            count_statement = count_statement.where(and_(*filters))
        count_result = await session.execute(count_statement)
        total_count = count_result.scalar() or 0

        statement = statement.order_by(Contract.created_at.desc())
        statement = statement.limit(limit).offset(offset)

        results = await session.execute(statement)
        contracts = results.scalars().all()

        return {
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "page_count": len(contracts),
            "filters_applied": {
                "q": q,
                "status": status,
                "currency": currency,
                "min_amount": min_amount,
                "max_amount": max_amount,
            },
            "data": [
                {
                    "id": c.id,
                    "title": c.title,
                    "vendor_name": c.vendor_name,
                    "amount": c.amount,
                    "currency": c.currency,
                    "status": c.status,
                    "expiration_date": getattr(c, "expiration_date", None),
                    "risks": getattr(c, "risks", []),
                    "obligations": getattr(c, "obligations", []),
                    "created_at": c.created_at,
                    "content": getattr(c, "content", "متن قرارداد موجود نیست."),
                }
                for c in contracts
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"خطا در فیلترینگ و بازیابی قراردادها: {str(e)}"
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contract(
    contract_input: ContractCreateInput,
    session: AsyncSession = Depends(get_session),
    user_data: dict = Depends(verify_clerk_token),
):
    db_contract = Contract(
        title=contract_input.title,
        vendor_name=contract_input.vendor_name,
        amount=contract_input.amount,
        currency=contract_input.currency,
        status=contract_input.status,
        created_at=contract_input.created_at or datetime.now(),
    )

    if db_contract.created_at and hasattr(db_contract.created_at, "tzinfo"):
        db_contract.created_at = db_contract.created_at.replace(tzinfo=None)

    session.add(db_contract)
    await session.commit()

    return {
        "id": db_contract.id,
        "title": db_contract.title,
        "vendor_name": db_contract.vendor_name,
        "amount": db_contract.amount,
        "currency": db_contract.currency,
        "status": db_contract.status,
        "created_at": db_contract.created_at,
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_contract(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user_data: dict = Depends(verify_clerk_token),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="فرمت فایل باید حتماً PDF باشد.")

    try:
        file_bytes = await file.read()
        pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        extracted_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"

        if not extracted_text.strip():
            raise HTTPException(
                status_code=400, detail="متنی در این فایل PDF پیدا نشد."
            )

        if len(extracted_text) > 15000:
            extracted_text = extracted_text[:15000]

        ai_data = await analyze_contract_text(extracted_text)

        new_contract = Contract(
            title=ai_data.get("title", "Untitled Contract"),
            vendor_name=ai_data.get("vendor_name", "Unknown Vendor"),
            amount=ai_data.get("amount", 0.0),
            currency=ai_data.get("currency", "EUR"),
            status=ai_data.get("status", "draft"),
            created_at=datetime.now(),
            expiration_date=ai_data.get("expiration_date", "Unknown"),
            risks=ai_data.get("risks", []),
            obligations=ai_data.get("obligations", []),
            content=extracted_text,
        )

        session.add(new_contract)
        await session.commit()

        return {
            "message": "قرارداد با موفقیت توسط هوش مصنوعی پردازش و ذخیره شد!",
            "contract": {
                "id": new_contract.id,
                "title": new_contract.title,
                "vendor_name": new_contract.vendor_name,
                "amount": new_contract.amount,
                "currency": new_contract.currency,
                "status": new_contract.status,
                "expiration_date": new_contract.expiration_date,
                "risks": new_contract.risks,
                "obligations": new_contract.obligations,
                "created_at": new_contract.created_at,
                "content": new_contract.content,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در پردازش فایل: {str(e)}")


@router.get("/analytics/charts", status_code=status.HTTP_200_OK)
async def get_contracts_chart_data(
    session: AsyncSession = Depends(get_session),
    user_data: dict = Depends(verify_clerk_token),
):
    try:
        status_stmt = select(
            Contract.status, func.count(Contract.id).label("count")
        ).group_by(Contract.status)

        status_result = await session.execute(status_stmt)
        status_mapping = {"active": "فعال", "draft": "پیش‌نویس", "expired": "منقضی شده"}
        status_data = [
            {
                "name": status_mapping.get(row.status, row.status or "نامشخص"),
                "value": row.count,
            }
            for row in status_result.all()
        ]

        currency_stmt = select(
            Contract.currency, func.sum(Contract.amount).label("total_amount")
        ).group_by(Contract.currency)

        currency_result = await session.execute(currency_stmt)
        financial_data = [
            {
                "currency": row.currency if row.currency else "Unknown",
                "تعداد/ارزش": float(row.total_amount or 0.0),
            }
            for row in currency_result.all()
        ]

        return {
            "status_distribution": status_data,
            "financial_overview": financial_data,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"خطا در استخراج دیتای نمودارها: {str(e)}"
        )


@router.get("/analytics", status_code=status.HTTP_200_OK)
async def get_contract_analytics(
    session: AsyncSession = Depends(get_session),
    user_data: dict = Depends(verify_clerk_token),
):
    try:
        total_stmt = select(func.count(Contract.id))
        total_result = await session.execute(total_stmt)
        total_contracts = total_result.scalar() or 0

        currency_stmt = select(
            Contract.currency,
            func.sum(Contract.amount).label("total_amount"),
            func.count(Contract.id).label("contract_count"),
        ).group_by(Contract.currency)

        currency_result = await session.execute(currency_stmt)
        currency_breakdown = [
            {
                "currency": row.currency,
                "total_amount": float(row.total_amount or 0.0),
                "count": row.contract_count,
            }
            for row in currency_result.all()
        ]

        status_stmt = select(
            Contract.status, func.count(Contract.id).label("count")
        ).group_by(Contract.status)

        status_result = await session.execute(status_stmt)
        status_breakdown = {
            row.status or "unknown": row.count for row in status_result.all()
        }

        risk_stmt = select(Contract.risks)
        risk_result = await session.execute(risk_stmt)
        all_risks = risk_result.scalars().all()

        high_risk_contracts_count = sum(
            1 for r in all_risks if r and isinstance(r, list) and len(r) > 0
        )

        return {
            "summary": {
                "total_contracts": total_contracts,
                "high_risk_contracts": high_risk_contracts_count,
            },
            "currency_distribution": currency_breakdown,
            "status_distribution": status_breakdown,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"خطا در استخراج آمارهای داشبورد: {str(e)}"
        )


@router.get(
    "/{contract_id}/chat",
    response_model=List[ChatMessageResponse],
    status_code=status.HTTP_200_OK,
)
async def get_chat_history(
    contract_id: int,
    session: AsyncSession = Depends(get_session),
    user_data: dict = Depends(verify_clerk_token),
):
    # بررسی وجود قرارداد
    stmt = select(Contract).where(Contract.id == contract_id)
    result = await session.execute(stmt)
    contract = result.scalar_one_or_none()

    if not contract:
        raise HTTPException(status_code=404, detail="قرارداد مورد نظر یافت نشد.")

    messages_stmt = (
        select(ChatMessage)
        .where(ChatMessage.contract_id == contract_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages_result = await session.execute(messages_stmt)
    return messages_result.scalars().all()


@router.post("/{contract_id}/chat", status_code=status.HTTP_200_OK)
async def chat_with_contract(
    contract_id: int,
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
    user_data: dict = Depends(verify_clerk_token),
):
    try:
        statement = select(Contract).where(Contract.id == contract_id)
        result = await session.execute(statement)
        contract = result.scalar_one_or_none()

        if not contract:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="قرارداد مورد نظر یافت نشد.",
            )

        groq_api_key = os.environ.get("AI_API_KEY")
        if not groq_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="تنظیمات سرور کامل نیست: کلید AI_API_KEY یافت نشد.",
            )

        user_message = ChatMessage(
            contract_id=contract_id, role="user", content=payload.message
        )
        session.add(user_message)
        await session.flush()

        history_stmt = (
            select(ChatMessage)
            .where(ChatMessage.contract_id == contract_id)
            .order_by(ChatMessage.created_at.asc())
        )
        history_result = await session.execute(history_stmt)
        past_messages = history_result.scalars().all()

        obligations_list = getattr(contract, "obligations", []) or []
        risks_list = getattr(contract, "risks", []) or []

        formatted_obligations = "\n".join([f"- {ob}" for ob in obligations_list])
        formatted_risks = "\n".join([f"- {risk}" for risk in risks_list])

        contract_context = f"""
        Contract Title: {contract.title}
        Vendor Name: {contract.vendor_name}
        Financial Amount: {contract.amount} {contract.currency}
        Status: {contract.status}
        Expiration Date: {getattr(contract, "expiration_date", "Unknown")}
        
        Extracted Key Obligations:
        {formatted_obligations if formatted_obligations else "None"}
        
        Extracted Legal Risks:
        {formatted_risks if formatted_risks else "None"}
        """

        system_instruction = (
            "You are an expert legal AI assistant specializing in contract analysis.\n"
            "Your task is to answer user questions strictly based on the provided contract data/text below and previous messages.\n"
            "Guidelines:\n"
            "- If the answer cannot be found or reasonably inferred from the contract data, say: 'این مورد در اطلاعات مستند قرارداد یافت نشد.'\n"
            "- Do not invent legal facts, numbers, or terms.\n"
            "- CRITICAL: Always respond in Persian (Farsi) with a highly professional, polite, and precise legal tone.\n\n"
            f"--- START OF CONTRACT DATA ---\n{contract_context}\n--- END OF CONTRACT DATA ---"
        )

        groq_messages = [{"role": "system", "content": system_instruction}]
        for msg in past_messages:
            groq_messages.append({"role": msg.role, "content": msg.content})

        client = AsyncGroq(api_key=groq_api_key)
        completion = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=groq_messages,
            temperature=0.15,
            max_tokens=1024,
        )

        ai_response_text = completion.choices[0].message.content

        ai_message = ChatMessage(
            contract_id=contract_id, role="assistant", content=ai_response_text
        )
        session.add(ai_message)

        await session.commit()

        return {"response": ai_response_text}

    except HTTPException as he:
        await session.rollback()
        raise he
    except Exception as e:
        await session.rollback()
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطا در پردازش چت هوشمند (Groq/Database Error): {str(e)}",
        )

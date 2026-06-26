import json
from groq import AsyncGroq
from app.config import settings

# 👈 انتقال کلاینت به بیرون از تابع برای استفاده از Connection Pooling و افزایش سرعت
client = AsyncGroq(api_key=settings.AI_API_KEY)


async def analyze_contract_text(text: str) -> dict:
    system_prompt = """
    You are an expert legal AI assistant. Analyze the provided contract text and extract key information.
    You MUST respond with a valid JSON object matching this exact schema:
    {
        "title": "The official title of the contract",
        "vendor_name": "The name of the vendor, counterparty, or client",
        "amount": 15000.00 (as a float number, 0 if not found),
        "currency": "USD, EUR, etc. (3-letter code)",
        "status": "active, draft, or expired",
        "expiration_date": "The expiration date or duration description (e.g., '2027-12-31' or '12 months from signing')",
        "risks": ["List of top 3-4 potential legal or financial risks, liabilities, or penalties found in the text"],
        "obligations": ["List of top 3-4 major deliverables or obligations for the parties"]
    }
    Do not include any conversational text, markdown formatting (like ```json), or explanations outside the JSON object.
    """

    try:
        # ارسال درخواست به گروک با کلاینت سراسری
        response = await client.chat.completions.create(
            model=settings.AI_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the contract text:\n\n{text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        raw_content = response.choices[0].message.content
        return json.loads(raw_content)

    except Exception as e:
        print(f"❌ AI Extraction Error: {str(e)}")
        return {
            "title": "Failed to extract title automatically",
            "vendor_name": "Unknown Vendor",
            "amount": 0.0,
            "currency": "EUR",
            "status": "draft",
            "expiration_date": "Unknown",
            "risks": [
                "خطا در پردازش هوش مصنوعی Groq یا نامعتبر بودن ساختار فرمت خروجی."
            ],
            "obligations": [],
        }

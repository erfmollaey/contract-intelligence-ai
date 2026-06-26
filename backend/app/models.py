from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime


Base = declarative_base()


class Contract(Base):
    __tablename__ = "contract"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=True)

    content = Column(Text, nullable=True)

    chat_messages = relationship(
        "ChatMessage", back_populates="contract", cascade="all, delete-orphan"
    )  # 🛠️ اضافه شدن رابطه برای دسترسی به تاریخچه چت‌ها

    expiration_date = Column(String, nullable=True)
    risks = Column(JSON, nullable=True)
    obligations = Column(JSON, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(
        Integer, ForeignKey("contract.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    contract = relationship("Contract", back_populates="chat_messages")

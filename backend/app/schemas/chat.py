from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)

    @field_validator("message", "thread_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("字段不能仅包含空白字符")
        return value


class ChatResponse(BaseModel):
    reply: str
    thread_id: str

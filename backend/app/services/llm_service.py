from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.config import settings
from pydantic import BaseModel
from typing import Type, TypeVar
import base64
import mimetypes
from pathlib import Path

T = TypeVar("T", bound=BaseModel)

class GeminiLLMService:

    def __init__(self):
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not configured."
            )

        self.llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            max_output_tokens=2048
        )

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None
    ) -> str:

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        messages = []

        if system_instruction:
            messages.append(
                SystemMessage(content=system_instruction)
            )

        messages.append(
            HumanMessage(content=prompt)
        )

        try:
            response = await self.llm.ainvoke(messages)

            if isinstance(response.content, str):
                return response.content.strip()

            text_parts = [
                block["text"]
                for block in response.content
                if isinstance(block, dict) and block.get("type") == "text"
            ]

            result = "\n".join(text_parts).strip()

            if not result:
                raise RuntimeError("Gemini returned an empty response.")

            return result

        except Exception as e:
            raise RuntimeError(
                f"Gemini generation failed: {type(e).__name__}"
            ) from e

    async def generate_structured(
        self,
        prompt: str,
        output_schema: Type[T],
        system_instruction: str | None = None,
        image_paths: list[str] | None = None
    ) -> T:

        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        structured_llm = self.llm.with_structured_output(
            output_schema
        )

        messages = []

        if system_instruction:
            messages.append(
                SystemMessage(content=system_instruction)
            )

        content = [
            {
                "type": "text",
                "text": prompt
            }
        ]

        for image_path in image_paths or []:
            path = Path(image_path)

            if not path.is_file():
                raise FileNotFoundError(
                    f"Image not found: {path}"
                )

            mime_type, _ = mimetypes.guess_type(str(path))

            if not mime_type or not mime_type.startswith("image/"):
                raise ValueError(
                    f"Unsupported image format: {path}"
                )

            image_base64 = base64.b64encode(
                path.read_bytes()
            ).decode("utf-8")

            content.append({
                "type": "image",
                "base64": image_base64,
                "mime_type": mime_type
            })

        messages.append(
            HumanMessage(content=content)
        )

        try:
            response = await structured_llm.ainvoke(messages)

            if isinstance(response, output_schema):
                return response

            return output_schema.model_validate(response)

        except Exception as e:
            raise RuntimeError(
                f"Structured Gemini generation failed: {type(e).__name__}"
            ) from e
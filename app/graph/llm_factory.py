from __future__ import annotations

import os
from typing import Any, List

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import AzureChatOpenAI, ChatOpenAI


load_dotenv()


class DummyChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "dummy-chat"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="OK."))])


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return value
    return default


def get_chat_model():
    provider = _env("LLM_PROVIDER", default="azure").lower().strip()

    if provider == "hf_openai_compat":
        base_url = _env("HF_OPENAI_BASE_URL", default="https://router.huggingface.co/v1")
        api_key = _env("HUGGINGFACEHUB_API_TOKEN")
        model = _env("HF_MODEL_ID")
        if not api_key or not model:
            return DummyChatModel()
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=float(_env("HF_TEMPERATURE", default="0.2")),
        )

    if provider == "azure":
        azure_endpoint = _env("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_ENDPOINT_5_2")
        api_key = _env("AZURE_OPENAI_API_KEY")
        deployment = _env("AZURE_OPENAI_DEPLOYMENT", default="gpt-5-nano")
        api_version = _env("AZURE_OPENAI_API_VERSION", default="2023-05-15")

        if not azure_endpoint or not api_key:
            return DummyChatModel()

        return AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            azure_deployment=deployment,
            api_version=api_version,
            temperature=float(_env("AZURE_TEMPERATURE", default="1")),
            streaming=True,
        )

    if provider == "openai":
        api_key = _env("OPENAI_API_KEY")
        model = _env("OPENAI_MODEL", default="gpt-5-nano")
        if not api_key:
            return DummyChatModel()
        return ChatOpenAI(
            api_key=api_key,
            model=model,
            temperature=float(_env("OPENAI_TEMPERATURE", default="1")),
        )

    return DummyChatModel()

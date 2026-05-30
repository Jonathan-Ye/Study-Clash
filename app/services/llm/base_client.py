from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMResponse:
    content: str
    total_tokens: int = 0
    request_tokens: int = 0
    response_tokens: int = 0
    model_name: str = ''
    success: bool = True
    error_message: Optional[str] = None


class BaseLLMClient(ABC):
    def __init__(self, api_base_url: str, api_key: str, model_name: str,
                 max_tokens: int = 8192, temperature: float = 0.7):
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    def chat_completion(self, messages: list, **kwargs) -> LLMResponse:
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        pass

    def validate_connection_with_detail(self) -> dict:
        try:
            ok = self.validate_connection()
            return {'connected': ok, 'message': '连接成功' if ok else '连接失败'}
        except Exception as e:
            return {'connected': False, 'message': str(e)}

    def _build_messages(self, system_prompt: str, user_prompt: str) -> list:
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': user_prompt})
        return messages

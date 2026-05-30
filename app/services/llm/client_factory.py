from .base_client import BaseLLMClient
from .zhipuai_client import ZhipuAIClient
from .baidu_client import BaiduQianfanClient
from .openai_compatible_client import OpenAICompatibleClient
from .alibaba_client import AlibabaBailianClient
from .local_client import LocalModelClient


class LLMClientFactory:
    _registry = {
        'local': LocalModelClient,
        'zhipuai': ZhipuAIClient,
        'baidu': BaiduQianfanClient,
        'alibaba': AlibabaBailianClient,
        'openai_compatible': OpenAICompatibleClient,
    }

    @classmethod
    def create(cls, provider_type: str, api_base_url: str, api_key: str,
               model_name: str, max_tokens: int = 8192,
               temperature: float = 0.7) -> BaseLLMClient:
        client_cls = cls._registry.get(provider_type)
        if not client_cls:
            raise ValueError(f'不支持的提供商类型: {provider_type}，支持: {list(cls._registry.keys())}')
        return client_cls(
            api_base_url=api_base_url,
            api_key=api_key,
            model_name=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    @classmethod
    def supported_types(cls):
        return list(cls._registry.keys())

import requests
import logging
from .base_client import BaseLLMClient, LLMResponse

logger = logging.getLogger(__name__)


class OpenAICompatibleClient(BaseLLMClient):
    def chat_completion(self, messages: list, **kwargs) -> LLMResponse:
        try:
            headers = {
                'Content-Type': 'application/json',
            }
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            payload = {
                'model': self.model_name,
                'messages': messages,
                'max_tokens': kwargs.get('max_tokens', self.max_tokens),
                'temperature': kwargs.get('temperature', self.temperature),
            }
            url = f"{self.api_base_url.rstrip('/')}/chat/completions"
            timeout = kwargs.get('timeout', 180)
            logger.info(f'LLM请求: {url} model={self.model_name} timeout={timeout}')
            
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout
            )
            resp.raise_for_status()
            data = resp.json()
            
            if 'choices' not in data or not data['choices']:
                return LLMResponse(content='', success=False, error_message=f'响应无choices: {str(data)[:200]}')
            
            usage = data.get('usage', {})
            return LLMResponse(
                content=data['choices'][0]['message']['content'],
                total_tokens=usage.get('total_tokens', 0),
                request_tokens=usage.get('prompt_tokens', 0),
                response_tokens=usage.get('completion_tokens', 0),
                model_name=self.model_name,
                success=True,
            )
        except requests.exceptions.HTTPError as e:
            detail = ''
            try:
                detail = e.response.text[:300]
            except Exception:
                pass
            err_msg = f'HTTP {e.response.status_code}: {detail}'
            logger.error(f'LLM调用失败: {err_msg}')
            return LLMResponse(content='', success=False, error_message=err_msg)
        except requests.exceptions.ConnectionError as e:
            err_msg = f'连接失败: {e}'
            logger.error(f'LLM连接失败: {err_msg}')
            return LLMResponse(content='', success=False, error_message=err_msg)
        except requests.exceptions.Timeout as e:
            err_msg = f'请求超时: {e}'
            logger.error(f'LLM超时: {err_msg}')
            return LLMResponse(content='', success=False, error_message=err_msg)
        except Exception as e:
            logger.error(f'LLM调用异常: {e}')
            return LLMResponse(content='', success=False, error_message=str(e))

    def validate_connection(self) -> bool:
        try:
            result = self.chat_completion(
                messages=[{'role': 'user', 'content': 'hello'}],
                max_tokens=5,
                timeout=30,
            )
            return result.success
        except Exception as e:
            logger.error(f'连接验证失败: {e}')
            return False

    def validate_connection_with_detail(self) -> dict:
        try:
            result = self.chat_completion(
                messages=[{'role': 'user', 'content': 'hello'}],
                max_tokens=5,
                timeout=30,
            )
            if result.success:
                return {'connected': True, 'message': '连接成功'}
            else:
                return {'connected': False, 'message': result.error_message or '调用失败'}
        except Exception as e:
            return {'connected': False, 'message': str(e)}

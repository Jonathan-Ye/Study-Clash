import time
import logging
from datetime import datetime, timezone
from app import db
from app.models.ai_analysis import LLMProvider, LLMCallStrategy, LLMCallLog, LLMFallbackEvent
from .client_factory import LLMClientFactory
from .encryption import EncryptionService
from .fallback_manager import FallbackManager
from .token_budget import TokenBudgetManager
from .base_client import LLMResponse

logger = logging.getLogger(__name__)


class AllProvidersFailedError(Exception):
    pass


class LLMServiceOrchestrator:
    @staticmethod
    def invoke(task_type: str, system_prompt: str, user_prompt: str,
               user_id: int = None, **kwargs) -> LLMResponse:
        providers = FallbackManager.get_provider_chain(task_type)
        if not providers:
            raise AllProvidersFailedError('没有可用的大模型服务商')

        last_error = None
        for provider in providers:
            strategy = LLMCallStrategy.query.filter_by(
                provider_id=provider.id, task_type=task_type
            ).first()

            timeout = strategy.timeout_seconds if strategy else 120
            max_retries = strategy.max_retries if strategy else 2
            retry_delay = strategy.retry_delay_seconds if strategy else 3
            daily_budget = strategy.daily_token_budget if strategy else 100000

            budget_ok, budget_status, ratio = TokenBudgetManager().allow_request(
                provider.id, daily_budget
            )
            if not budget_ok:
                LLMServiceOrchestrator._log_call(
                    provider.id, user_id, task_type, provider.model_name,
                    0, 0, 0, 'budget_exceeded', f'Token预算超限({ratio:.1%})', 0
                )
                continue

            client = LLMClientFactory.create(
                provider_type=provider.provider_type,
                api_base_url=provider.api_base_url or '',
                api_key=EncryptionService.decrypt(provider.api_key_encrypted) if provider.api_key_encrypted else '',
                model_name=provider.model_name,
                max_tokens=provider.max_tokens,
                temperature=strategy.temperature_override if strategy and strategy.temperature_override else provider.temperature,
            )

            messages = client._build_messages(system_prompt, user_prompt)

            for attempt in range(max_retries + 1):
                start_time = time.time()
                try:
                    response = client.chat_completion(
                        messages=messages,
                        timeout=timeout,
                        **kwargs,
                    )
                    duration_ms = int((time.time() - start_time) * 1000)

                    if response.success:
                        TokenBudgetManager().consume(provider.id, response.total_tokens)
                        LLMServiceOrchestrator._log_call(
                            provider.id, user_id, task_type, provider.model_name,
                            response.request_tokens, response.response_tokens,
                            response.total_tokens, 'success', None, duration_ms
                        )
                        return response
                    else:
                        last_error = response.error_message
                        LLMServiceOrchestrator._log_call(
                            provider.id, user_id, task_type, provider.model_name,
                            0, 0, 0, 'failed', response.error_message, duration_ms
                        )
                except Exception as e:
                    duration_ms = int((time.time() - start_time) * 1000)
                    last_error = str(e)
                    LLMServiceOrchestrator._log_call(
                        provider.id, user_id, task_type, provider.model_name,
                        0, 0, 0, 'timeout' if 'timeout' in str(e).lower() else 'failed',
                        str(e), duration_ms
                    )

                if attempt < max_retries:
                    time.sleep(retry_delay)

            if len(providers) > 1:
                next_providers = [p for p in providers if p.id != provider.id]
                if next_providers:
                    fallback_event = LLMFallbackEvent(
                        from_provider_id=provider.id,
                        to_provider_id=next_providers[0].id,
                        task_type=task_type,
                        reason=f'服务商 {provider.name} 调用失败: {last_error}',
                    )
                    db.session.add(fallback_event)
                    db.session.commit()

        raise AllProvidersFailedError(f'所有服务商调用失败，最后错误: {last_error}')

    @staticmethod
    def _log_call(provider_id, user_id, task_type, model_name,
                  request_tokens, response_tokens, total_tokens,
                  status, error_message, duration_ms):
        try:
            log = LLMCallLog(
                provider_id=provider_id,
                user_id=user_id,
                task_type=task_type,
                model_name=model_name,
                request_tokens=request_tokens,
                response_tokens=response_tokens,
                total_tokens=total_tokens,
                status=status,
                error_message=error_message,
                duration_ms=duration_ms,
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            logger.error(f'写入调用日志失败: {e}')

import os
import logging
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

logger = logging.getLogger(__name__)


class EncryptionService:
    _fallback_key = None
    _decrypt_failed_keys = set()

    @staticmethod
    def _get_fernet() -> Fernet:
        key = current_app.config.get('LLM_ENCRYPTION_KEY', '')
        if key:
            try:
                return Fernet(key.encode() if isinstance(key, str) else key)
            except Exception:
                logger.warning('LLM_ENCRYPTION_KEY 格式无效')
        if EncryptionService._fallback_key is None:
            EncryptionService._fallback_key = Fernet.generate_key()
            logger.warning('已自动生成备用加密密钥，请尽快在 .env 中设置有效的 LLM_ENCRYPTION_KEY')
        return Fernet(EncryptionService._fallback_key)

    @staticmethod
    def _get_fernet_raw() -> Fernet:
        key = current_app.config.get('LLM_ENCRYPTION_KEY', '')
        if key:
            try:
                return Fernet(key.encode() if isinstance(key, str) else key)
            except Exception:
                pass
        return None

    @staticmethod
    def encrypt(plaintext: str) -> str:
        f = EncryptionService._get_fernet()
        return f.encrypt(plaintext.encode()).decode()

    @staticmethod
    def decrypt(ciphertext: str) -> str:
        if not ciphertext:
            return ''
        f_config = EncryptionService._get_fernet_raw()
        if f_config:
            try:
                return f_config.decrypt(ciphertext.encode()).decode()
            except (InvalidToken, Exception):
                pass
        f = EncryptionService._get_fernet()
        try:
            return f.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            logger.error('API Key解密失败：加密密钥与当前LLM_ENCRYPTION_KEY不匹配，需要重新配置API Key')
            return ''
        except Exception as e:
            logger.error(f'API Key解密异常: {e}')
            return ''

    @staticmethod
    def mask_key(api_key: str) -> str:
        if not api_key or len(api_key) < 6:
            return '***'
        return api_key[:2] + '*' * (len(api_key) - 6) + api_key[-4:]

    @staticmethod
    def needs_reencrypt(ciphertext: str) -> bool:
        if not ciphertext:
            return False
        decrypted = EncryptionService.decrypt(ciphertext)
        return decrypted == ''

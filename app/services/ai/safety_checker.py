import logging

logger = logging.getLogger(__name__)

UNSAFE_KEYWORDS = [
    '暴力', '自残', '自杀', '色情', '赌博', '毒品',
    '传销', '诈骗', '邪教', '恐怖',
]


class ContentSafetyChecker:
    @staticmethod
    def is_safe(content: str) -> tuple:
        if not content:
            return True, None
        content_lower = content.lower()
        for keyword in UNSAFE_KEYWORDS:
            if keyword in content_lower:
                logger.warning(f'内容安全校验未通过，命中关键词: {keyword}')
                return False, f'内容包含不安全关键词: {keyword}'
        return True, None

    @staticmethod
    def check_json_content(data) -> tuple:
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    is_ok, reason = ContentSafetyChecker.is_safe(value)
                    if not is_ok:
                        return False, reason
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            is_ok, reason = ContentSafetyChecker.is_safe(item)
                            if not is_ok:
                                return False, reason
                        elif isinstance(item, dict):
                            is_ok, reason = ContentSafetyChecker.check_json_content(item)
                            if not is_ok:
                                return False, reason
        return True, None

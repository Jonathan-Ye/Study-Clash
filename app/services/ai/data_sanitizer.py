import re


class DataSanitizer:
    PII_PATTERNS = {
        'phone': re.compile(r'1[3-9]\d{9}'),
        'email': re.compile(r'[\w.-]+@[\w.-]+\.\w+'),
        'id_card': re.compile(r'\d{17}[\dXx]'),
    }

    @staticmethod
    def sanitize(data: dict) -> dict:
        if not data:
            return data
        sanitized = data.copy()
        for key in list(sanitized.keys()):
            if key in ('phone', 'email', 'id_card', 'real_name', 'student_no',
                       'address', 'ip_address'):
                sanitized.pop(key, None)
        for key, value in sanitized.items():
            if isinstance(value, str):
                for pattern in DataSanitizer.PII_PATTERNS.values():
                    value = pattern.sub('[已脱敏]', value)
                sanitized[key] = value
            elif isinstance(value, dict):
                sanitized[key] = DataSanitizer.sanitize(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    DataSanitizer.sanitize(item) if isinstance(item, dict) else item
                    for item in value
                ]
        return sanitized

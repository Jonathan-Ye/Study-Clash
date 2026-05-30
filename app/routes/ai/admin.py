from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models.ai_analysis import LLMProvider, LLMCallStrategy, AIGeneratedContent
from app.services.llm.client_factory import LLMClientFactory
from app.services.llm.encryption import EncryptionService
from app.services.llm.fallback_manager import FallbackManager
from app.services.ai.content_service import ContentService
from app.services.ai.audit_service import AuditService
from app.services.ai.feature_switch import AIFeatureSwitchService

ai_admin_bp = Blueprint('ai_admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated


@ai_admin_bp.route('/providers', methods=['GET'])
@login_required
@admin_required
def get_providers():
    providers = LLMProvider.query.order_by(LLMProvider.is_primary.desc(), LLMProvider.priority).all()
    return jsonify({
        'providers': [{
            'id': p.id,
            'name': p.name,
            'provider_type': p.provider_type,
            'api_base_url': p.api_base_url,
            'api_key_masked': EncryptionService.mask_key(
                EncryptionService.decrypt(p.api_key_encrypted) if p.api_key_encrypted else ''
            ),
            'needs_rekey': EncryptionService.needs_reencrypt(p.api_key_encrypted or '') if p.api_key_encrypted else False,
            'model_name': p.model_name,
            'is_active': p.is_active,
            'is_primary': p.is_primary,
            'priority': p.priority,
            'max_tokens': p.max_tokens,
            'temperature': p.temperature,
        } for p in providers],
        'supported_types': LLMClientFactory.supported_types(),
    })


@ai_admin_bp.route('/providers', methods=['POST'])
@login_required
@admin_required
def create_provider():
    data = request.get_json()
    required = ['name', 'provider_type', 'model_name', 'api_key']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'缺少必填字段: {field}'}), 400

    if data['provider_type'] not in LLMClientFactory.supported_types():
        return jsonify({'error': f'不支持的提供商类型'}), 400

    encrypted_key = EncryptionService.encrypt(data['api_key'])
    is_primary = data.get('is_primary', False)

    provider_type = data['provider_type']
    api_base_url = data.get('api_base_url', '')
    if not api_base_url:
        default_urls = {
            'zhipuai': 'https://open.bigmodel.cn/api/paas/v4',
            'baidu': 'https://qianfan.baidubce.com/v2',
            'alibaba': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'local': 'http://localhost:11434/v1',
        }
        api_base_url = default_urls.get(provider_type, '')

    if is_primary:
        current_primary = LLMProvider.query.filter_by(is_primary=True).first()
        if current_primary:
            current_primary.is_primary = False

    provider = LLMProvider(
        name=data['name'],
        provider_type=provider_type,
        api_base_url=api_base_url,
        api_key_encrypted=encrypted_key,
        model_name=data['model_name'],
        is_active=data.get('is_active', True),
        is_primary=is_primary,
        priority=data.get('priority', 0),
        max_tokens=data.get('max_tokens', 8192),
        temperature=data.get('temperature', 0.7),
    )
    db.session.add(provider)
    db.session.commit()

    return jsonify({'status': 'success', 'provider_id': provider.id}), 201


@ai_admin_bp.route('/providers/<int:provider_id>', methods=['PUT'])
@login_required
@admin_required
def update_provider(provider_id):
    provider = LLMProvider.query.get(provider_id)
    if not provider:
        return jsonify({'error': '服务商不存在'}), 404

    data = request.get_json()
    if 'name' in data:
        provider.name = data['name']
    if 'api_base_url' in data:
        provider.api_base_url = data['api_base_url']
    if 'api_key' in data:
        provider.api_key_encrypted = EncryptionService.encrypt(data['api_key'])
    if 'model_name' in data:
        provider.model_name = data['model_name']
    if 'is_active' in data:
        provider.is_active = data['is_active']
    if 'max_tokens' in data:
        provider.max_tokens = data['max_tokens']
    if 'temperature' in data:
        provider.temperature = data['temperature']

    db.session.commit()
    return jsonify({'status': 'success'})


@ai_admin_bp.route('/providers/<int:provider_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_provider(provider_id):
    provider = LLMProvider.query.get(provider_id)
    if not provider:
        return jsonify({'error': '服务商不存在'}), 404
    db.session.delete(provider)
    db.session.commit()
    return jsonify({'status': 'success'})


@ai_admin_bp.route('/providers/<int:provider_id>/test', methods=['POST'])
@login_required
@admin_required
def test_provider(provider_id):
    provider = LLMProvider.query.get(provider_id)
    if not provider:
        return jsonify({'error': '服务商不存在'}), 404

    try:
        api_base_url = provider.api_base_url or ''
        if not api_base_url:
            default_urls = {
                'zhipuai': 'https://open.bigmodel.cn/api/paas/v4',
                'baidu': 'https://qianfan.baidubce.com/v2',
                'alibaba': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'local': 'http://localhost:11434/v1',
            }
            api_base_url = default_urls.get(provider.provider_type, '')
            if api_base_url:
                provider.api_base_url = api_base_url
                db.session.commit()

        client = LLMClientFactory.create(
            provider_type=provider.provider_type,
            api_base_url=api_base_url,
            api_key=EncryptionService.decrypt(provider.api_key_encrypted) if provider.api_key_encrypted else '',
            model_name=provider.model_name,
        )
        result = client.validate_connection_with_detail()
        return jsonify({'status': 'success', 'connected': result['connected'], 'message': result.get('message', '')})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@ai_admin_bp.route('/providers/set-primary/<int:provider_id>', methods=['PUT'])
@login_required
@admin_required
def set_primary_provider(provider_id):
    success = FallbackManager.set_primary(provider_id)
    return jsonify({'status': 'success' if success else 'failed'})


@ai_admin_bp.route('/strategies', methods=['GET'])
@login_required
@admin_required
def get_strategies():
    provider_id = request.args.get('provider_id', type=int)
    query = LLMCallStrategy.query
    if provider_id:
        query = query.filter_by(provider_id=provider_id)
    strategies = query.all()
    return jsonify({
        'strategies': [{
            'id': s.id,
            'provider_id': s.provider_id,
            'task_type': s.task_type,
            'timeout_seconds': s.timeout_seconds,
            'max_retries': s.max_retries,
            'retry_delay_seconds': s.retry_delay_seconds,
            'token_limit': s.token_limit,
            'daily_token_budget': s.daily_token_budget,
            'temperature_override': s.temperature_override,
        } for s in strategies]
    })


@ai_admin_bp.route('/strategies/<int:provider_id>', methods=['PUT'])
@login_required
@admin_required
def update_strategy(provider_id):
    data = request.get_json()
    task_type = data.get('task_type')
    if not task_type:
        return jsonify({'error': '缺少task_type'}), 400

    strategy = LLMCallStrategy.query.filter_by(
        provider_id=provider_id, task_type=task_type
    ).first()

    if not strategy:
        strategy = LLMCallStrategy(provider_id=provider_id, task_type=task_type)
        db.session.add(strategy)

    if 'timeout_seconds' in data:
        strategy.timeout_seconds = max(10, min(300, data['timeout_seconds']))
    if 'max_retries' in data:
        strategy.max_retries = max(0, min(5, data['max_retries']))
    if 'retry_delay_seconds' in data:
        strategy.retry_delay_seconds = data['retry_delay_seconds']
    if 'token_limit' in data:
        strategy.token_limit = max(100, min(100000, data['token_limit']))
    if 'daily_token_budget' in data:
        strategy.daily_token_budget = data['daily_token_budget']
    if 'temperature_override' in data:
        strategy.temperature_override = data['temperature_override']

    db.session.commit()
    return jsonify({'status': 'success'})


@ai_admin_bp.route('/review', methods=['POST'])
@login_required
@admin_required
def review_variant():
    data = request.get_json()
    content_id = data.get('content_id')
    approved = data.get('approved', False)
    if not content_id:
        return jsonify({'error': '缺少content_id'}), 400
    result = ContentService.review_variant_question(content_id, current_user.id, approved)
    return jsonify(result)


@ai_admin_bp.route('/audit/logs', methods=['GET'])
@login_required
@admin_required
def get_audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    task_type = request.args.get('task_type')
    status = request.args.get('status')
    result = AuditService.get_logs(page, per_page, task_type, status)
    return jsonify(result)


@ai_admin_bp.route('/audit/token-stats', methods=['GET'])
@login_required
@admin_required
def get_token_stats():
    time_range = request.args.get('time_range', '7d')
    result = AuditService.get_token_statistics(time_range)
    return jsonify(result)


@ai_admin_bp.route('/audit/fallback-events', methods=['GET'])
@login_required
@admin_required
def get_fallback_events():
    events = AuditService.get_fallback_events()
    return jsonify({'events': events})


@ai_admin_bp.route('/switches', methods=['GET'])
@login_required
@admin_required
def get_switches():
    return jsonify({'switches': AIFeatureSwitchService.get_all_switches()})


@ai_admin_bp.route('/switches/<key>', methods=['PUT'])
@login_required
@admin_required
def update_switch(key):
    data = request.get_json()
    value = data.get('enabled')
    if value is None:
        return jsonify({'error': '缺少enabled字段'}), 400
    AIFeatureSwitchService.update_switch(key, bool(value))
    return jsonify({'status': 'success', 'key': key, 'enabled': bool(value)})


@ai_admin_bp.route('/quotas', methods=['GET'])
@login_required
@admin_required
def get_quotas():
    from app.services.ai.quota_manager import QuotaManager
    target_type = request.args.get('target_type')
    target_id = request.args.get('target_id', type=int)
    quotas = QuotaManager.list_quotas(target_type, target_id)
    return jsonify({'quotas': [{
        'id': q.id,
        'target_type': q.target_type,
        'target_id': q.target_id,
        'daily_call_limit': q.daily_call_limit,
        'daily_token_limit': q.daily_token_limit,
        'current_daily_calls': q.current_daily_calls,
        'current_daily_tokens': q.current_daily_tokens,
        'remaining_calls': max(0, q.daily_call_limit - q.current_daily_calls),
    } for q in quotas]})


@ai_admin_bp.route('/quotas', methods=['POST'])
@login_required
@admin_required
def create_quota():
    from app.services.ai.quota_manager import QuotaManager
    data = request.get_json()
    quota = QuotaManager.set_quota(
        target_type=data.get('target_type', 'user'),
        target_id=data.get('target_id'),
        daily_call_limit=data.get('daily_call_limit'),
        daily_token_limit=data.get('daily_token_limit'),
    )
    return jsonify({'status': 'success', 'quota_id': quota.id}), 201


@ai_admin_bp.route('/quotas/<int:quota_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_quota(quota_id):
    from app.services.ai.quota_manager import QuotaManager
    success = QuotaManager.delete_quota(quota_id)
    return jsonify({'status': 'success' if success else 'failed'})


@ai_admin_bp.route('/badges', methods=['GET'])
@login_required
@admin_required
def get_badge_definitions():
    from app.models.ai_analysis import AIBadgeDefinition, AIBadgeRecord
    from sqlalchemy import func
    defs = AIBadgeDefinition.query.all()
    result = []
    for d in defs:
        count = AIBadgeRecord.query.filter_by(badge_key=d.badge_key).count()
        result.append({
            'badge_key': d.badge_key,
            'badge_name': d.badge_name,
            'badge_description': d.badge_description,
            'badge_icon': d.badge_icon,
            'earned_count': count,
            'is_active': d.is_active,
        })
    return jsonify({'badges': result})

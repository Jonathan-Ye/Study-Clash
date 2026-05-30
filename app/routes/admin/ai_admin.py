from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.routes.admin import admin_bp, admin_required
from app import db
from app.models.ai_analysis import LLMProvider, LLMCallStrategy, AIGeneratedContent
from app.services.llm.client_factory import LLMClientFactory
from app.services.llm.encryption import EncryptionService
from app.services.llm.fallback_manager import FallbackManager
from app.services.ai.content_service import ContentService
from app.services.ai.audit_service import AuditService


@admin_bp.route('/ai/providers')
@login_required
@admin_required
def ai_providers():
    providers = LLMProvider.query.order_by(LLMProvider.is_primary.desc(), LLMProvider.priority).all()
    for p in providers:
        try:
            decrypted = EncryptionService.decrypt(p.api_key_encrypted) if p.api_key_encrypted else ''
            p.api_key_masked = EncryptionService.mask_key(decrypted)
            p.needs_rekey = (decrypted == '' and bool(p.api_key_encrypted))
        except Exception:
            p.api_key_masked = '***'
            p.needs_rekey = True
    supported_types = LLMClientFactory.supported_types()
    return render_template('admin/ai_providers.html',
                           providers=providers,
                           supported_types=supported_types,
                           provider_type_names=LLMProvider.PROVIDER_TYPES)


@admin_bp.route('/ai/providers/add', methods=['POST'])
@login_required
@admin_required
def ai_provider_add():
    from flask import request
    data = request.form
    name = data.get('name', '').strip()
    provider_type = data.get('provider_type', '').strip()
    model_name = data.get('model_name', '').strip()
    api_key = data.get('api_key', '').strip()
    api_base_url = data.get('api_base_url', '').strip()

    if not name or not provider_type or not model_name:
        flash('请填写所有必填字段', 'error')
        return redirect(url_for('admin.ai_providers'))

    if provider_type not in LLMClientFactory.supported_types():
        flash(f'不支持的提供商类型: {provider_type}', 'error')
        return redirect(url_for('admin.ai_providers'))

    if not api_key and provider_type != 'local':
        flash('云端服务商必须填写API密钥', 'error')
        return redirect(url_for('admin.ai_providers'))

    encrypted_key = EncryptionService.encrypt(api_key) if api_key else ''
    is_primary = data.get('is_primary') == 'on'

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
        name=name,
        provider_type=provider_type,
        api_base_url=api_base_url,
        api_key_encrypted=encrypted_key,
        model_name=model_name,
        is_active='is_active' in data and data.get('is_active') == 'on',
        is_primary=is_primary,
        priority=int(data.get('priority', 0)),
        max_tokens=int(data.get('max_tokens', 8192)),
        temperature=float(data.get('temperature', 0.7)),
    )
    db.session.add(provider)
    db.session.commit()
    flash(f'服务商 {name} 添加成功', 'success')
    return redirect(url_for('admin.ai_providers'))


@admin_bp.route('/ai/providers/delete/<int:provider_id>', methods=['POST'])
@login_required
@admin_required
def ai_provider_delete(provider_id):
    provider = LLMProvider.query.get(provider_id)
    if not provider:
        flash('服务商不存在', 'error')
        return redirect(url_for('admin.ai_providers'))
    name = provider.name
    db.session.delete(provider)
    db.session.commit()
    flash(f'服务商 {name} 已删除', 'success')
    return redirect(url_for('admin.ai_providers'))


@admin_bp.route('/ai/providers/test/<int:provider_id>', methods=['POST'])
@login_required
@admin_required
def ai_provider_test(provider_id):
    provider = LLMProvider.query.get(provider_id)
    if not provider:
        return jsonify({'success': False, 'message': '服务商不存在'})
    try:
        client = LLMClientFactory.create(
            provider_type=provider.provider_type,
            api_base_url=provider.api_base_url or '',
            api_key=EncryptionService.decrypt(provider.api_key_encrypted) if provider.api_key_encrypted else '',
            model_name=provider.model_name,
        )
        is_ok = client.validate_connection()
        return jsonify({'success': True, 'connected': is_ok,
                        'message': '连接成功' if is_ok else '连接失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@admin_bp.route('/ai/providers/set-primary/<int:provider_id>', methods=['POST'])
@login_required
@admin_required
def ai_provider_set_primary(provider_id):
    success = FallbackManager.set_primary(provider_id)
    if success:
        flash('主服务商设置成功', 'success')
    else:
        flash('设置失败，请检查服务商是否存在且已启用', 'error')
    return redirect(url_for('admin.ai_providers'))


@admin_bp.route('/ai/strategies')
@login_required
@admin_required
def ai_strategies():
    providers = LLMProvider.query.filter_by(is_active=True).all()
    strategies = LLMCallStrategy.query.all()
    return render_template('admin/ai_strategies.html',
                           providers=providers,
                           strategies=strategies,
                           task_types=LLMCallStrategy.TASK_TYPES)


@admin_bp.route('/ai/strategies/update', methods=['POST'])
@login_required
@admin_required
def ai_strategy_update():
    data = request.form
    provider_id = int(data.get('provider_id', 0))
    task_type = data.get('task_type', '').strip()
    if not provider_id or not task_type:
        flash('请选择服务商和任务类型', 'error')
        return redirect(url_for('admin.ai_strategies'))

    strategy = LLMCallStrategy.query.filter_by(
        provider_id=provider_id, task_type=task_type
    ).first()
    if not strategy:
        strategy = LLMCallStrategy(provider_id=provider_id, task_type=task_type)
        db.session.add(strategy)

    strategy.timeout_seconds = max(10, min(300, int(data.get('timeout_seconds', 30))))
    strategy.max_retries = max(0, min(5, int(data.get('max_retries', 2))))
    strategy.retry_delay_seconds = int(data.get('retry_delay_seconds', 3))
    strategy.token_limit = max(100, min(100000, int(data.get('token_limit', 4096))))
    strategy.daily_token_budget = int(data.get('daily_token_budget', 100000))
    temp_override = data.get('temperature_override', '').strip()
    strategy.temperature_override = float(temp_override) if temp_override else None

    db.session.commit()
    flash('调用策略更新成功', 'success')
    return redirect(url_for('admin.ai_strategies'))


@admin_bp.route('/ai/review')
@login_required
@admin_required
def ai_review():
    pending = AIGeneratedContent.query.filter_by(
        content_type='variant', review_status='pending'
    ).order_by(AIGeneratedContent.created_at.desc()).all()
    reviewed = AIGeneratedContent.query.filter(
        AIGeneratedContent.content_type == 'variant',
        AIGeneratedContent.review_status.in_(['approved', 'rejected'])
    ).order_by(AIGeneratedContent.reviewed_at.desc()).limit(20).all()
    return render_template('admin/ai_review.html',
                           pending=pending, reviewed=reviewed,
                           review_statuses=AIGeneratedContent.REVIEW_STATUSES)


@admin_bp.route('/ai/review/approve/<int:content_id>', methods=['POST'])
@login_required
@admin_required
def ai_review_approve(content_id):
    result = ContentService.review_variant_question(content_id, current_user.id, True)
    if result.get('status') == 'success':
        flash('变式题已审核通过并入库', 'success')
    else:
        flash(result.get('message', '审核失败'), 'error')
    return redirect(url_for('admin.ai_review'))


@admin_bp.route('/ai/review/reject/<int:content_id>', methods=['POST'])
@login_required
@admin_required
def ai_review_reject(content_id):
    result = ContentService.review_variant_question(content_id, current_user.id, False)
    if result.get('status') == 'success':
        flash('变式题已拒绝', 'success')
    else:
        flash(result.get('message', '审核失败'), 'error')
    return redirect(url_for('admin.ai_review'))


@admin_bp.route('/ai/audit')
@login_required
@admin_required
def ai_audit():
    return render_template('admin/ai_audit.html')

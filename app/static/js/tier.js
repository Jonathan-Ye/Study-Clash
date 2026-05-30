class TierSystem {
    constructor() {
        this.currentTierData = null;
    }

    async loadMyTier() {
        try {
            const response = await fetch('/points/api/rank/my-tier');
            const result = await response.json();
            
            if (result.success) {
                this.currentTierData = result.data;
                this.renderTierCard(result.data);
            }
        } catch (error) {
            console.error('加载段位信息失败:', error);
        }
    }

    renderTierCard(data) {
        const container = document.getElementById('tierCardContainer');
        if (!container) return;

        if (!data.current) {
            container.innerHTML = '<p class="text-muted">暂无段位信息</p>';
            return;
        }

        const tier = data.current;
        const progress = data.progress;
        const peak = data.peak;
        const stats = data.stats;

        let html = `
            <div class="tier-card" style="background: linear-gradient(135deg, ${tier.color}dd 0%, ${tier.color}99 100%);">
                <div class="tier-card-header">
                    <div class="tier-icon-wrapper">
                        ${this.renderIcon(tier.icon, tier.display_name)}
                    </div>
                    <div class="tier-info">
                        <h2>${tier.display_name}</h2>
                        <div class="tier-subtitle">当前段位</div>
                    </div>
                </div>

                <div class="tier-progress-section">
                    <div class="tier-progress-text">
                        <span>段位进度</span>
                        <span>${progress.progress}%</span>
                    </div>
                    <div class="tier-progress-bar-container">
                        <div class="tier-progress-bar" style="width: ${progress.progress}%"></div>
                    </div>
                    <div class="tier-progress-text" style="font-size: 12px; margin-top: 8px;">
                        <span>${progress.current} 分</span>
                        <span>还需 ${progress.points_to_next} 分升级</span>
                    </div>
                </div>

                <div class="tier-stats-grid">
                    ${peak ? `
                    <div class="tier-stat-item">
                        <div class="tier-stat-label">历史最高</div>
                        <div class="tier-stat-value">${peak.display_name}</div>
                    </div>
                    ` : ''}
                    <div class="tier-stat-item">
                        <div class="tier-stat-label">总升级次数</div>
                        <div class="tier-stat-value">${stats.total_promotions || 0}</div>
                    </div>
                </div>

                ${stats.last_promoted_at ? `
                <div style="margin-top: 16px; font-size: 13px; opacity: 0.9; text-align: center;">
                    最近升级：${stats.last_promoted_at}
                </div>
                ` : ''}
            </div>
        `;

        container.innerHTML = html;
    }

    renderIcon(iconPath, altText) {
        if (iconPath && iconPath.endsWith('.svg')) {
            return `<img src="/static/images/tiers/${iconPath}" 
                         alt="${altText}" 
                     class="tier-icon">`;
        }
        return `<span style="font-size: 40px;">${iconPath || '⭐'}</span>`;
    }

    async loadTierHistory(page = 1) {
        try {
            const response = await fetch(`/points/api/rank/tier-history?page=${page}`);
            const result = await response.json();
            
            if (result.success) {
                this.renderTierHistory(result.data);
            }
        } catch (error) {
            console.error('加载段位历史失败:', error);
        }
    }

    renderTierHistory(data) {
        const container = document.getElementById('tierHistoryContainer');
        if (!container) return;

        if (!data.history || data.history.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-4">暂无段位变更记录</p>';
            return;
        }

        let html = '<div class="tier-history-timeline">';
        
        data.history.forEach(item => {
            html += `
                <div class="timeline-item">
                    <div class="timeline-date">${item.changed_at}</div>
                    <div class="timeline-content">
                        ${item.from_tier ? `
                            <strong>${item.from_tier.display_name}</strong> → 
                            <strong>${item.to_tier.display_name}</strong>
                        ` : `首次达到 <strong>${item.to_tier.display_name}</strong>`}
                        <br>
                        <small class="text-muted">积分：${item.points_at_change}</small>
                    </div>
                </div>
            `;
        });

        html += '</div>';

        if (data.pages > 1) {
            html += `
                <nav aria-label="段位历史分页" class="mt-3">
                    <ul class="pagination justify-content-center">
                        ${page > 1 ? `<li class="page-item"><a class="page-link" href="#" onclick="tierSystem.loadTierHistory(${page - 1}); return false;">上一页</a></li>` : ''}
                        <li class="page-item disabled"><span class="page-link">${page} / ${data.pages}</span></li>
                        ${page < data.pages ? `<li class="page-item"><a class="page-link" href="#" onclick="tierSystem.loadTierHistory(${page + 1}); return false;">下一页</a></li>` : ''}
                    </ul>
                </nav>
            `;
        }

        container.innerHTML = html;
    }

    showPromotionModal(fromTier, toTier, points) {
        const modal = document.getElementById('promotionModal');
        if (!modal) return;

        modal.innerHTML = `
            <div class="tier-promotion-modal" style="display: flex;" onclick="if(event.target === this) tierSystem.hidePromotionModal()">
                <div class="tier-promotion-content">
                    <div class="promotion-title">🎉 恭喜升级！🎉</div>
                    
                    <div class="promotion-tier-change">
                        <div>${fromTier ? this.renderIcon(fromTier.icon, fromTier.display_name) : '🌱'}
                            <div style="margin-top: 8px; font-size: 14px;">${fromTier ? fromTier.display_name : '新手'}</div>
                        </div>
                        
                        <div class="promotion-tier-arrow">→</div>
                        
                        <div>${this.renderIcon(toTier.icon, toTier.display_name)}
                            <div style="margin-top: 8px; font-size: 14px; font-weight: bold;">${toTier.display_name}</div>
                        </div>
                    </div>
                    
                    <div class="promotion-points">
                        当前积分：<strong>${points}</strong> 分
                    </div>
                    
                    <div class="promotion-buttons">
                        <button class="btn-promotion" onclick="tierSystem.shareAchievement()">分享成就 📤</button>
                        <button class="btn-promotion" onclick="tierSystem.hidePromotionModal()">太好了！✨</button>
                    </div>
                </div>
            </div>
        `;
    }

    hidePromotionModal() {
        const modal = document.getElementById('promotionModal');
        if (modal) {
            modal.innerHTML = '';
        }
    }

    shareAchievement() {
        if (navigator.share && this.currentTierData?.current) {
            const tier = this.currentTierData.current;
            navigator.share({
                title: 'Study Clash 段位提升',
                text: `我在 Study Clash 达到了 ${tier.display_name}！快来挑战吧！`,
                url: window.location.href
            });
        } else {
            alert('成就已记录！继续加油！');
            this.hidePromotionModal();
        }
    }

    static renderTierBadge(tierInfo, size = 'small') {
        if (!tierInfo) return '';

        const sizeClass = size === 'large' ? 'px-4 py-2' : 'px-2 py-1';
        
        return `
            <span class="tier-badge-small ${sizeClass}" 
                  style="background-color: ${tierInfo.color}">
                ${tierInfo.icon ? 
                    `<img src="/static/images/tiers/${tierInfo.icon}" 
                          alt="${tierInfo.display_name}"
                          style="width: ${size === 'large' ? '24px' : '18px'}; height: ${size === 'large' ? '24px' : '18px'};">` :
                    ''
                }
                <span>${tierInfo.display_name}</span>
            </span>
        `;
    }
}

const tierSystem = new TierSystem();

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('tierCardContainer')) {
        tierSystem.loadMyTier();
    }
    
    if (document.getElementById('tierHistoryContainer')) {
        tierSystem.loadTierHistory();
    }
});

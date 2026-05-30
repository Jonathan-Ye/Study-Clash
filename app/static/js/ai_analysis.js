const AINalysis = {
    csrfToken: null,
    socket: null,

    init() {
        this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
        this.initSocketIO();
    },

    initSocketIO() {
        if (typeof io === 'undefined') return;
        this.socket = io();
        this.socket.on('ai_task_progress', this.handleProgress.bind(this));
    },

    handleProgress(data) {
        const prefix = data.task_type;
        const progressEl = document.getElementById(prefix + '-progress');
        if (progressEl) {
            progressEl.style.display = 'block';
            const bar = progressEl.querySelector('.progress-bar');
            if (bar) {
                bar.style.width = data.progress + '%';
                bar.textContent = data.progress + '%';
            }
            const msg = document.getElementById(prefix + '-progress-msg');
            if (msg) msg.textContent = data.message || '';
        }
        if (data.status === 'completed' || data.status === 'failed') {
            const btn = document.getElementById('btn-' + prefix);
            if (btn) btn.disabled = false;
            if (data.status === 'completed') {
                this.loadResult(prefix);
            } else if (data.status === 'failed') {
                const resultEl = document.getElementById(prefix + '-result');
                if (resultEl) resultEl.innerHTML = '<div class="alert alert-danger">分析失败: ' + (data.message || '未知错误') + '</div>';
            }
        }
    },

    loadResult(type) {
        const loaders = {
            attribution: this.loadAttributionResult,
            prediction: this.loadPredictionResult,
            strategy: this.loadStrategyResult,
        };
        if (loaders[type]) loaders[type].call(this);
    },

    triggerAnalysis(type) {
        const btn = document.getElementById('btn-' + type);
        if (btn) btn.disabled = true;
        const urls = {
            attribution: '/ai/attribution/trigger',
            prediction: '/ai/prediction/trigger',
            strategy: '/ai/strategy/generate',
        };
        fetch(urls[type], {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
        }).then(r => r.json()).then(data => {
            if (data.status === 'started') {
                const progressEl = document.getElementById(type + '-progress');
                if (progressEl) progressEl.style.display = 'block';
            } else {
                if (btn) btn.disabled = false;
                alert(data.message || '触发失败');
            }
        }).catch(() => { if (btn) btn.disabled = false; });
    },

    loadAttributionResult() {
        fetch('/ai/attribution/result').then(r => r.json()).then(data => {
            const el = document.getElementById('attribution-result');
            if (!el) return;
            if (data.status === 'no_data') { el.innerHTML = '<p class="text-muted">暂无分析结果，请先触发归因分析</p>'; return; }
            const d = data.data;
            let html = '';
            if (d.needs_review) html += '<div class="alert alert-warning"><i class="bi bi-exclamation-triangle"></i> 置信度较低，建议人工复核</div>';
            html += '<h5>根因分析</h5>';
            if (d.root_causes) {
                html += '<div class="list-group mb-3">';
                d.root_causes.forEach(c => {
                    const confClass = c.confidence >= 0.8 ? 'ai-confidence-high' : c.confidence >= 0.5 ? 'ai-confidence-mid' : 'ai-confidence-low';
                    html += `<div class="ai-result-card"><strong>${c.category}</strong> - ${c.description}<br><small class="${confClass}">置信度: ${(c.confidence*100).toFixed(0)}%</small></div>`;
                });
                html += '</div>';
            }
            if (d.knowledge_mastery && d.knowledge_mastery.length > 0) {
                html += '<h5>知识点掌握度</h5><div class="table-responsive"><table class="table table-sm table-hover"><thead><tr><th>知识点</th><th>分数</th><th>水平</th></tr></thead><tbody>';
                d.knowledge_mastery.forEach(m => {
                    html += `<tr><td>${m.name}</td><td>${m.score}</td><td>${m.level||'-'}</td></tr>`;
                });
                html += '</tbody></table></div>';
            }
            el.innerHTML = html;
        });
    },

    loadPredictionResult() {
        fetch('/ai/prediction/result').then(r => r.json()).then(data => {
            const el = document.getElementById('prediction-result');
            if (!el) return;
            if (data.status === 'no_data' || data.status === 'insufficient_data') { el.innerHTML = '<p class="text-muted">' + (data.message||'暂无预测结果') + '</p>'; return; }
            const d = data.data;
            let html = '';
            if (d.low_confidence) html += '<div class="alert alert-info">预测可信度较低，仅供参考</div>';
            if (d.is_expired) html += '<div class="alert alert-warning">预测结果已过期，建议重新预测</div>';
            html += '<h5>薄弱知识点</h5><div class="mb-3">';
            if (d.weak_points) d.weak_points.forEach(wp => {
                html += `<div class="ai-result-card mb-2"><strong>${wp.knowledge_point}</strong><div class="d-flex align-items-center mt-1"><div class="weak-point-bar" style="width:${wp.probability*100}%"></div><small class="ms-2">${(wp.probability*100).toFixed(0)}%</small></div><small class="text-muted">${wp.reasoning||''}</small></div>`;
            });
            html += '</div>';
            el.innerHTML = html;
        });
    },

    loadStrategyResult() {
        fetch('/ai/strategy/result').then(r => r.json()).then(data => {
            const el = document.getElementById('strategy-result');
            if (!el) return;
            if (data.status === 'no_data') { el.innerHTML = '<p class="text-muted">暂无策略，请先完成归因分析和推理预测</p>'; return; }
            const d = data.data;
            let html = '';
            if (d.needs_update) html += '<div class="alert alert-info">学习数据有新变化，建议更新学习策略</div>';
            html += '<h5>学习路径</h5><div class="list-group mb-3">';
            if (d.learning_path) d.learning_path.forEach(lp => {
                const badge = lp.priority === '高' ? 'bg-danger' : lp.priority === '中' ? 'bg-warning' : 'bg-info';
                html += `<div class="list-group-item d-flex justify-content-between align-items-center"><span>${lp.knowledge_point}</span><span><span class="badge ${badge} me-1">${lp.priority}</span><small>${lp.estimated_minutes||'-'}分钟</small></span></div>`;
            });
            html += '</div>';
            el.innerHTML = html;
        });
    },

    loadDistribution() {
        const dim = document.getElementById('distribution-dimension')?.value || 'chapter';
        fetch('/ai/visualization/distribution?dimension=' + dim).then(r => r.json()).then(data => {
            if (data.status !== 'success') return;
            const chart = echarts.init(document.getElementById('distribution-chart'));
            chart.setOption({
                tooltip: { trigger: 'axis' },
                xAxis: { type: 'category', data: data.labels },
                yAxis: { type: 'value' },
                series: [{ type: 'bar', data: data.values, itemStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'#667eea'},{offset:1,color:'#764ba2'}]) } }]
            });
        });
    },

    loadRadar() {
        fetch('/ai/visualization/radar').then(r => r.json()).then(data => {
            if (data.status !== 'success') return;
            const chart = echarts.init(document.getElementById('radar-chart'));
            chart.setOption({
                radar: { indicator: data.indicators },
                series: [{ type: 'radar', data: [{ value: data.values, areaStyle: { color: 'rgba(102,126,234,0.3)' }, lineStyle: { color: '#667eea' } }] }]
            });
        });
    },

    loadTrend() {
        fetch('/ai/visualization/trend').then(r => r.json()).then(data => {
            if (data.status !== 'success') return;
            const chart = echarts.init(document.getElementById('trend-chart'));
            chart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: ['历史', '预测'] },
                xAxis: { type: 'category', data: [...data.history.dates, ...data.prediction.dates] },
                yAxis: { type: 'value' },
                series: [
                    { name: '历史', type: 'line', data: [...data.history.values, ...new Array(data.prediction.dates.length).fill(null)], lineStyle: { color: '#667eea' } },
                    { name: '预测', type: 'line', data: [...new Array(data.history.dates.length).fill(null), ...data.prediction.values], lineStyle: { color: '#764ba2', type: 'dashed' } }
                ]
            });
        });
    },
};

document.addEventListener('DOMContentLoaded', function() {
    AINalysis.init();
    AINalysis.loadAttributionResult();
    AINalysis.loadPredictionResult();
    AINalysis.loadStrategyResult();
    const vizTab = document.querySelector('[data-bs-toggle="tab"][href="#visualization"]');
    if (vizTab) vizTab.addEventListener('shown.bs.tab', function() {
        AINalysis.loadDistribution();
        AINalysis.loadRadar();
        AINalysis.loadTrend();
    });
});

function triggerAnalysis(type) { AINalysis.triggerAnalysis(type); }
function loadDistribution() { AINalysis.loadDistribution(); }

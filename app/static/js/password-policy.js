/**
 * 密码策略前端实时校验
 * 在密码输入框旁实时显示当前策略要求及满足状态
 */
(function() {
    // 获取密码策略配置
    fetch('/auth/api/password-policy')
        .then(function(res) { return res.json(); })
        .then(function(config) {
            // 查找所有密码策略校验目标
            var targets = document.querySelectorAll('[data-password-policy]');
            targets.forEach(function(container) {
                initPasswordPolicy(container, config);
            });
        })
        .catch(function() {
            // 策略获取失败，静默处理
        });

    function initPasswordPolicy(container, config) {
        var input = container.querySelector('input[type="password"]');
        if (!input) return;

        // 创建提示容器
        var hintDiv = document.createElement('div');
        hintDiv.className = 'password-policy-hints mt-2';
        hintDiv.style.fontSize = '0.85rem';
        container.appendChild(hintDiv);

        var rules = [];

        if (config.enabled) {
            rules.push({
                label: '至少' + config.min_length + '个字符',
                test: function(p) { return p.length >= config.min_length; }
            });
            if (config.require_uppercase) {
                rules.push({
                    label: '包含大写字母',
                    test: function(p) { return /[A-Z]/.test(p); }
                });
            }
            if (config.require_lowercase) {
                rules.push({
                    label: '包含小写字母',
                    test: function(p) { return /[a-z]/.test(p); }
                });
            }
            if (config.require_digit) {
                rules.push({
                    label: '包含数字',
                    test: function(p) { return /[0-9]/.test(p); }
                });
            }
            if (config.require_special) {
                rules.push({
                    label: '包含特殊字符',
                    test: function(p) { return /[!@#$%^&*()_+\-=\[\]{};'"\\:"|,<.>\/?`~]/.test(p); }
                });
            }
        } else {
            rules.push({
                label: '至少6个字符',
                test: function(p) { return p.length >= 6; }
            });
        }

        // 渲染提示
        function renderHints(password) {
            var html = '';
            rules.forEach(function(rule) {
                var met = password.length > 0 && rule.test(password);
                var icon = met ? 'bi-check-circle-fill text-success' : 'bi-x-circle-fill text-danger';
                html += '<div class="d-flex align-items-center gap-1 mb-1">' +
                    '<i class="bi ' + icon + '"></i> ' +
                    '<span class="' + (met ? 'text-success' : (password.length > 0 ? 'text-danger' : 'text-muted')) + '">' + rule.label + '</span>' +
                    '</div>';
            });
            hintDiv.innerHTML = html;
        }

        // 初始渲染
        renderHints('');

        // 监听输入
        input.addEventListener('input', function() {
            renderHints(input.value);
        });
    }
})();

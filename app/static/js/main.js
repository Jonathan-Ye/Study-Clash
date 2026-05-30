const StudyClash = {
    socket: null,
    
    init: function() {
        this.initTooltips();
        this.initFormValidation();
        this.initSocket();
    },
    
    initTooltips: function() {
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltipTriggerList.forEach(el => new bootstrap.Tooltip(el));
    },
    
    initFormValidation: function() {
        const forms = document.querySelectorAll('.needs-validation');
        forms.forEach(form => {
            form.addEventListener('submit', event => {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                form.classList.add('was-validated');
            });
        });
    },
    
    initSocket: function() {
        if (typeof io !== 'undefined') {
            this.socket = io();
            
            this.socket.on('connect', () => {
                console.log('Socket connected');
            });
            
            this.socket.on('disconnect', () => {
                console.log('Socket disconnected');
            });
            
            this.socket.on('error', (data) => {
                this.showAlert(data.message, 'danger');
            });
        }
    },
    
    joinGameRoom: function(roomCode, userId) {
        if (this.socket) {
            this.socket.emit('join_game', {
                room_code: roomCode,
                user_id: userId
            });
        }
    },
    
    leaveGameRoom: function(roomCode, userId) {
        if (this.socket) {
            this.socket.emit('leave_game', {
                room_code: roomCode,
                user_id: userId
            });
        }
    },
    
    showAlert: function(message, type = 'info') {
        const alertContainer = document.createElement('div');
        alertContainer.className = `alert alert-${type} alert-dismissible fade show`;
        alertContainer.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const main = document.querySelector('main.container');
        main.insertBefore(alertContainer, main.firstChild);
        
        setTimeout(() => {
            alertContainer.remove();
        }, 5000);
    },
    
    formatTime: function(seconds) {
        const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
        const secs = (seconds % 60).toString().padStart(2, '0');
        return `${mins}:${secs}`;
    },
    
    copyToClipboard: function(text) {
        navigator.clipboard.writeText(text).then(() => {
            this.showAlert('已复制到剪贴板', 'success');
        }).catch(() => {
            this.showAlert('复制失败', 'danger');
        });
    },
    
    apiRequest: function(url, method = 'GET', data = null) {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };
        
        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        }
        
        return fetch(url, options).then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        });
    }
};

document.addEventListener('DOMContentLoaded', () => {
    StudyClash.init();
});

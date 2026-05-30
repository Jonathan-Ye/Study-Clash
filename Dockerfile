# ============================================
# Study Clash Dockerfile
# 基于 Python 3.11 + Ubuntu 24.04
# 版本: 1.1.20260509
# ============================================

# 使用 Python 3.11 slim 镜像（体积小，适合生产环境）
FROM python:3.11-slim

# 设置镜像标签
LABEL version="1.1.20260509"
LABEL description="Study Clash Learning Platform"
LABEL maintainer="Study Clash Team"

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装 Python 包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 创建必要的目录并设置权限（在复制应用代码之前）
RUN mkdir -p /app/data /app/uploads /app/backups /app/logs && \
    chmod -R 777 /app/data /app/uploads /app/backups /app/logs

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 5002

# 复制启动脚本
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app

# 注意：不使用 USER 指令，让 entrypoint.sh 以 root 运行并处理权限
# entrypoint.sh 最后会切换到 appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5002/')" || exit 1

# 设置入口点
ENTRYPOINT ["/app/entrypoint.sh"]

# 启动命令（生产环境使用 gunicorn + eventlet）
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]

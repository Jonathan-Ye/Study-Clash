import os
from app import create_app, socketio

env = os.environ.get('FLASK_ENV', 'production')
app = create_app(env)

# gunicorn 使用 eventlet worker 时，会自动处理 monkey_patch
# 不需要手动调用 eventlet.monkey_patch()

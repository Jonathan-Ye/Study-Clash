#!/bin/bash
set -e

ENV_FILE=".env"
ENV_TEMPLATE=".env.production.example"

echo "========================================"
echo "  Study Clash 配置文件检查与修复脚本"
echo "========================================"
echo ""

# 检查模板文件
if [ ! -f "$ENV_TEMPLATE" ]; then
    echo " 错误: .env.production.example 模板文件不存在"
    exit 1
fi

# 如果 .env 不存在，直接生成新配置
if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  .env 文件不存在，将生成新配置"
    echo ""
    exec "$0" --new
fi

echo "[1/4] 读取配置文件..."

# 读取现有配置
get_env_value() {
    grep "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-
}

# 检查并修复配置
FIXED=0
ADDED=0
SKIPPED=0

echo "[2/4] 检查配置项..."

# 遍历模板文件中的所有配置项
while IFS= read -r line; do
    # 跳过空行和注释
    if [[ -z "$line" ]] || [[ "$line" =~ ^# ]]; then
        continue
    fi
    
    # 提取变量名和默认值
    VAR_NAME=$(echo "$line" | cut -d'=' -f1)
    TEMPLATE_VALUE=$(echo "$line" | cut -d'=' -f2-)
    
    # 获取当前值
    CURRENT_VALUE=$(get_env_value "$VAR_NAME")
    
    # 检查变量是否存在
    if [ -z "$CURRENT_VALUE" ]; then
        # 变量不存在，添加新配置
        echo "  添加: ${VAR_NAME}"
        echo "$line" >> "$ENV_FILE"
        ADDED=$((ADDED + 1))
        FIXED=$((FIXED + 1))
        continue
    fi
    
    # 检查是否是占位符或不安全的默认值
    case "$VAR_NAME" in
        SECRET_KEY)
            # 检查是否为空或占位符
            if [[ "$CURRENT_VALUE" == *"请替换"* ]] || [[ "$CURRENT_VALUE" == "change-this"* ]] || [ ${#CURRENT_VALUE} -lt 32 ]; then
                echo "  修复: ${VAR_NAME}（生成新密钥）"
                NEW_VALUE=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
                sed -i "s|^${VAR_NAME}=.*|${VAR_NAME}=${NEW_VALUE}|" "$ENV_FILE"
                FIXED=$((FIXED + 1))
            else
                SKIPPED=$((SKIPPED + 1))
            fi
            ;;
        POSTGRES_PASSWORD)
            # 检查是否为占位符
            if [[ "$CURRENT_VALUE" == *"studyclash_db_password"* ]] || [[ "$CURRENT_VALUE" == "请修改"* ]] || [[ "$CURRENT_VALUE" == "your_password"* ]]; then
                echo "  警告: ${VAR_NAME}（占位符，请手动修改为实际密码）"
                FIXED=$((FIXED + 1))
            else
                SKIPPED=$((SKIPPED + 1))
            fi
            ;;
        LLM_ENCRYPTION_KEY)
            # 检查是否为空
            if [ -z "$CURRENT_VALUE" ] || [[ "$CURRENT_VALUE" == "请替换"* ]]; then
                echo "  修复: ${VAR_NAME}（生成加密密钥）"
                NEW_VALUE=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "")
                if [ -n "$NEW_VALUE" ]; then
                    sed -i "s|^${VAR_NAME}=.*|${VAR_NAME}=${NEW_VALUE}|" "$ENV_FILE"
                    FIXED=$((FIXED + 1))
                else
                    echo "  警告: 无法生成加密密钥，请手动配置"
                fi
            else
                SKIPPED=$((SKIPPED + 1))
            fi
            ;;
        FLASK_ENV)
            # 确保生产环境
            if [ "$CURRENT_VALUE" != "production" ]; then
                echo "  修复: ${VAR_NAME}（设置为 production）"
                sed -i "s|^${VAR_NAME}=.*|${VAR_NAME}=production|" "$ENV_FILE"
                FIXED=$((FIXED + 1))
            else
                SKIPPED=$((SKIPPED + 1))
            fi
            ;;
        *)
            # 其他配置项，如果是占位符则使用模板默认值
            if [[ "$CURRENT_VALUE" == *"请替换"* ]] || [[ "$CURRENT_VALUE" == "your_"* ]] || [[ "$CURRENT_VALUE" == "请修改"* ]]; then
                echo "  修复: ${VAR_NAME}"
                sed -i "s|^${VAR_NAME}=.*|${VAR_NAME}=${TEMPLATE_VALUE}|" "$ENV_FILE"
                FIXED=$((FIXED + 1))
            else
                SKIPPED=$((SKIPPED + 1))
            fi
            ;;
    esac
done < "$ENV_TEMPLATE"

# 输出结果
echo ""
echo "========================================"
echo "  配置文件检查完成！"
echo "========================================"
echo ""
echo "检查结果："
[ $ADDED -gt 0 ] && echo "  ✅ 新增配置项: ${ADDED} 个"
[ $FIXED -gt 0 ] && echo "  ✅ 修复配置项: ${FIXED} 个"
echo "  ✅ 无需修改: ${SKIPPED} 个"
echo ""

if [ $FIXED -gt 0 ]; then
    echo "⚠️  请检查以上修改的配置项"
    echo "️  如果修复了数据库密码，请确保与新密码一致"
fi

echo "配置文件: ${ENV_FILE}"
echo "========================================"

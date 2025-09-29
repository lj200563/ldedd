FROM python:3.10-slim

# 安装 cryptography 等库所需的系统级依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 5200

# 设置环境变量
ENV PORT=5200
ENV PYTHONPATH=/app

# 启动命令
CMD ["python", "app.py"]

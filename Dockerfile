# 使用較小的 Python Slim 映像
FROM python:3.13-slim

# 安裝必要的套件
RUN apt-get update && apt-get install -y \
    python3-tk \
    tcl \
    tk \
    libtk8.6 \
    libtcl8.6 \
    git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 複製專案檔案到容器中
COPY . .

# 安裝 Python 依賴套件
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# 啟動應用程式
CMD ["python3", "main.py"]
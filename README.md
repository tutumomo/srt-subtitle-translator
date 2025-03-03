# SRT 字幕翻譯器

## 安裝步驟

1. 確保已安裝 Python 3.6 或更新版本
2. 安裝必要套件：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

1. 運行程式：
```bash
python main.py
```

2. 可以通過以下方式添加 SRT 檔案：
   - 點擊「選擇 SRT 檔案」按鈕
   - 直接拖放檔案到視窗中（需要 tkinterdnd2 支援）

## 注意事項

- 確保 Ollama 服務運行中（http://localhost:11434）
- 建議使用 aya 模型
- 並行請求數建議設為 3
- 翻譯大量字幕時請耐心等待

## 授權協議

MIT License
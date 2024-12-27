# SRT 字幕翻譯器

使用 Ollama 本地 AI 模型的字幕翻譯工具，支援多種語言之間的翻譯。

## 主要功能

- 支援批量翻譯 SRT 字幕檔案
- 支援多語言轉換（繁體中文、英文、日文）
- 使用 Ollama 本地 AI 模型，保護隱私
- 支援並行翻譯請求，提高效率
- 支援從檔案總管直接拖放檔案
- 檔案列表支援拖曳排序和右鍵選單
- 即時顯示翻譯進度
- 可自由選擇 Ollama 模型

## 安裝需求

1. Python 3.6+
2. 必要套件：
```bash
pip install -r requirements.txt
```

3. 安裝並運行 Ollama：
   - 參考 [Ollama 官方文件](https://github.com/ollama/ollama)
   - 下載建議模型：
```bash
ollama pull aya
```

## 使用方法

1. 運行程式：
   - 使用tkinter介面(MAC OS 可能會有問題，所以新增 QT5)：
   ```bash
   python main.py
   ```
   - 使用圖形介面：
   ```bash
   python main_qt5.py
   ```

2. 操作說明：
   - 點擊「選擇 SRT 檔案」或直接從檔案總管拖放 .srt 檔案
   - 在檔案列表中可以：
     - 拖曳改變順序
     - 右鍵移除檔案
   - 選擇語言和 AI 模型
   - 設定並行請求數（建議 1-5）
   - 點擊「開始翻譯」

3. 輸出檔案：
   - 繁體中文：原檔名.zh_tw.srt
   - 英文：原檔名.en.srt
   - 日文：原檔名.jp.srt

## 注意事項

- 確保 Ollama 服務運行中（http://localhost:11434）
- 建議使用 aya 模型
- 並行請求數建議設為 5
- 翻譯大量字幕時請耐心等待
- 若遇到翻譯錯誤或不準確的情況，請嘗試更換模型或調整並行請求數

## 授權協議

MIT License
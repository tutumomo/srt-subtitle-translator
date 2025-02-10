import sys
import os
import pysrt
import json
import urllib.request
import asyncio
import threading
from queue import Queue
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QListWidget, QComboBox, QLabel, QProgressBar, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt

# 設置 Ollama 並行請求數
os.environ['OLLAMA_NUM_PARALLEL'] = '5'  # 設置為5個並行請求

class TranslationThread(threading.Thread):
    def __init__(self, file_path, source_lang, target_lang, model_name, parallel_requests, progress_callback, complete_callback):
        threading.Thread.__init__(self)
        self.file_path = file_path
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.model_name = model_name
        self.parallel_requests = parallel_requests
        self.progress_callback = progress_callback
        self.complete_callback = complete_callback

    def run(self):
        subs = pysrt.open(self.file_path)
        total_subs = len(subs)
        batch_size = int(self.parallel_requests)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for i in range(0, total_subs, batch_size):
            batch = subs[i:i+batch_size]
            texts = [sub.text for sub in batch]
            results = loop.run_until_complete(self.translate_batch_async(texts))
            
            for sub, result in zip(batch, results):
                if result:
                    sub.text = result
                
            self.progress_callback(min(i+batch_size, total_subs), total_subs)

        loop.close()

        output_path = self.get_output_path()
        if output_path:  # 只有在有效的輸出路徑時才保存
            subs.save(output_path, encoding='utf-8')
            self.complete_callback(f"翻譯完成 | 檔案已成功保存為: {output_path}")
        else:
            self.complete_callback(f"已跳過檔案: {self.file_path}")

    async def translate_batch_async(self, texts):
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, self.fetch, text) for text in texts]
        return await asyncio.gather(*tasks)

    def fetch(self, text):
        url = "http://localhost:11434/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": f"""你是一個專業的字幕翻譯AI。請嚴格遵守以下規則：
1. 只輸出翻譯後的文本，不要有任何其他內容
2. 保持原文的語氣和表達方式
3. 如果看到省略號(...)，保留在譯文中
4. 保留原文中的標點符號風格
5. 不要添加任何解釋或註釋
6. 不要改變原文的格式
7. 如果遇到不確定的內容，根據上下文合理推測
8. 禁止輸出任何非翻譯內容
9. 禁止解釋或評論原文內容

範例輸入：
"I love you..."
正確輸出：
"我愛你..."

錯誤輸出：
"翻譯：我愛你..."
"這句話的意思是：我愛你..."
"我愛你（這是表達愛意）..."
"我可以幫你翻譯，這句話的意思是，我愛你（這是表達愛意）..."
"你好！我可以幫你翻譯。以下是翻譯結果：「我愛你...」
"我不能幫你翻譯這句話"
"您好！以下是翻譯結果：「我愛你...」"
"您好！我可以協助您翻譯。以下是翻譯結果：「我愛你...」"
"您要我翻譯什麼內容？請提供需要翻譯的文本，我將嚴格遵守您的要求，只輸出翻譯後的結果。"
"將以下文本翻譯成繁體中文：「我愛你...」
"""},
                {"role": "user", "content": f"將以下文本翻譯成{self.target_lang}：\n{text}"}
            ],
            "stream": False,
            "temperature": 0.1  # 降低溫度以獲得更穩定的輸出
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result['choices'][0]['message']['content'].strip()
        except Exception:
            return None

    def get_output_path(self):
        # 獲取原始檔案的目錄和檔名
        dir_name, file_name = os.path.split(self.file_path)
        name, ext = os.path.splitext(file_name)
        lang_suffix = {"繁體中文": ".zh_tw", "英文": ".en", "日文": ".jp"}
        # 在原始檔案的相同目錄下創建新檔案
        base_path = os.path.join(dir_name, f"{name}{lang_suffix[self.target_lang]}{ext}")
        
        # 檢查檔案是否存在
        if os.path.exists(base_path):
            # 發送訊息到主線程處理檔案衝突
            response = self.handle_file_conflict(base_path)
            if response == "rename":
                # 自動重新命名，加上數字後綴
                counter = 1
                while True:
                    new_path = os.path.join(dir_name, f"{name}{lang_suffix[self.target_lang]}_{counter}{ext}")
                    if not os.path.exists(new_path):
                        return new_path
                    counter += 1
            elif response == "skip":
                return None
            # response == "overwrite" 則使用原始路徑
        
        return base_path

    def handle_file_conflict(self, file_path):
        # 使用 Queue 在線程間通信
        queue = Queue()
        # 請求主線程顯示對話框
        self.progress_callback(-1, -1, {"type": "file_conflict", "path": file_path, "queue": queue})
        # 等待使用者回應
        return queue.get()

class App(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SRT 字幕翻譯器")
        self.setGeometry(100, 100, 600, 500)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.create_widgets()

    def create_widgets(self):
        # 檔案選擇按鈕
        self.file_button = QPushButton("選擇 SRT 檔案")
        self.file_button.clicked.connect(self.select_files)
        self.layout.addWidget(self.file_button)

        # 檔案列表
        self.file_list = QListWidget()
        self.layout.addWidget(self.file_list)

        # 語言選擇
        self.source_lang_label = QLabel("原文語言:")
        self.layout.addWidget(self.source_lang_label)
        self.source_lang = QComboBox()
        self.source_lang.addItems(["日文", "英文", "自動偵測"])
        self.source_lang.setCurrentText("日文")
        self.layout.addWidget(self.source_lang)

        self.target_lang_label = QLabel("目標語言:")
        self.layout.addWidget(self.target_lang_label)
        self.target_lang = QComboBox()
        self.target_lang.addItems(["繁體中文", "英文", "日文"])
        self.target_lang.setCurrentText("繁體中文")
        self.layout.addWidget(self.target_lang)

        # 模型選擇和並行請求數量選擇
        self.model_label = QLabel("選擇模型:")
        self.layout.addWidget(self.model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.get_model_list())
        self.model_combo.setCurrentText("huihui_ai/aya-expanse-abliterated:latest")
        self.layout.addWidget(self.model_combo)

        self.parallel_requests_label = QLabel("並行請求數:")
        self.layout.addWidget(self.parallel_requests_label)
        self.parallel_requests = QComboBox()
        self.parallel_requests.addItems(["1", "2", "3", "4", "5"])
        self.parallel_requests.setCurrentText("5")
        self.layout.addWidget(self.parallel_requests)

        # 翻譯按鈕
        self.translate_button = QPushButton("開始翻譯")
        self.translate_button.clicked.connect(self.start_translation)
        self.layout.addWidget(self.translate_button)

        # 進度條
        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        # 狀態標籤
        self.status_label = QLabel("")
        self.layout.addWidget(self.status_label)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "選擇 SRT 檔案", "", "SRT files (*.srt)")
        for file in files:
            self.file_list.addItem(file)

    def get_model_list(self):
        url = "http://localhost:11434/v1/models"
        try:
            with urllib.request.urlopen(url) as response:
                models = json.loads(response.read())
                if 'data' in models and isinstance(models['data'], list):
                    return [model['id'] for model in models['data']]
        except Exception:
            pass
        return []

    def start_translation(self):
        self.progress_bar.setValue(0)
        self.status_label.setText("")
        for i in range(self.file_list.count()):
            file_path = self.file_list.item(i).text()
            thread = TranslationThread(
                file_path, 
                self.source_lang.currentText(), 
                self.target_lang.currentText(), 
                self.model_combo.currentText(),
                self.parallel_requests.currentText(),
                self.update_progress,
                self.file_translated
            )
            thread.start()

        self.status_label.setText(f"正在翻譯 {self.file_list.count()} 個檔案...")

    def update_progress(self, current, total, extra_data=None):
        if extra_data and extra_data.get("type") == "file_conflict":
            # 在主線程中顯示對話框
            response = QMessageBox.warning(
                self,
                "檔案已存在",
                f"檔案 {extra_data['path']} 已存在。\n是否覆蓋？\n'是' = 覆蓋\n'否' = 重新命名\n'取消' = 跳過",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            # 轉換回應為字符串
            if response == QMessageBox.Yes:
                result = "overwrite"
            elif response == QMessageBox.No:
                result = "rename"
            else:  # response is QMessageBox.Cancel
                result = "skip"
            
            # 將結果發送回翻譯線程
            extra_data["queue"].put(result)
            return
            
        # 正常的進度更新
        if current >= 0 and total >= 0:
            percentage = int(current / total * 100)
            self.progress_bar.setValue(percentage)
            self.status_label.setText(f"正在翻譯第 {current}/{total} 句字幕 ({percentage}%)")
            QApplication.processEvents()

    def file_translated(self, message):
        current_text = self.status_label.text()
        self.status_label.setText(f"{current_text}\n{message}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import pysrt
import json
import urllib.request
import asyncio
import threading

# 設置 Ollama 並行請求數
os.environ['OLLAMA_NUM_PARALLEL'] = '3'  # 設置為3個並行請求

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
        subs.save(output_path, encoding='utf-8')
        self.complete_callback(f"翻譯完成 | 檔案已成功保存為: {output_path}")

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
        dir_name, file_name = os.path.split(self.file_path)
        name, ext = os.path.splitext(file_name)
        lang_suffix = {"繁體中文": ".zh_tw", "英文": ".en", "日文": ".jp"}
        return os.path.join(dir_name, f"{name}{lang_suffix[self.target_lang]}{ext}")

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("SRT 字幕翻譯器")
        self.geometry("600x500")  # 增加窗口高度

        self.create_widgets()

    def create_widgets(self):
        # 檔案選擇按鈕
        self.file_button = ttk.Button(self, text="選擇 SRT 檔案", command=self.select_files)
        self.file_button.pack(pady=10)

        # 檔案列表
        self.file_list = tk.Listbox(self, width=70, height=10)
        self.file_list.pack(pady=10)

        # 語言選擇
        lang_frame = ttk.Frame(self)
        lang_frame.pack(pady=10)

        ttk.Label(lang_frame, text="原文語言:").grid(row=0, column=0)
        self.source_lang = ttk.Combobox(lang_frame, values=["日文", "英文", "自動偵測"])
        self.source_lang.set("日文")
        self.source_lang.grid(row=0, column=1)

        ttk.Label(lang_frame, text="目標語言:").grid(row=0, column=2)
        self.target_lang = ttk.Combobox(lang_frame, values=["繁體中文", "英文", "日文"])
        self.target_lang.set("繁體中文")
        self.target_lang.grid(row=0, column=3)

        # 模型選擇和並行請求數量選擇
        model_frame = ttk.Frame(self)
        model_frame.pack(pady=10)

        ttk.Label(model_frame, text="選擇模型:").grid(row=0, column=0)
        self.model_combo = ttk.Combobox(model_frame, values=self.get_model_list())
        self.model_combo.set("aya:latest")
        self.model_combo.grid(row=0, column=1)

        ttk.Label(model_frame, text="並行請求數:").grid(row=0, column=2)
        self.parallel_requests = ttk.Combobox(model_frame, values=["1", "2", "3", "4", "5"])
        self.parallel_requests.set("3")
        self.parallel_requests.grid(row=0, column=3)

        # 翻譯按鈕
        self.translate_button = ttk.Button(self, text="開始翻譯", command=self.start_translation)
        self.translate_button.pack(pady=10)

        # 進度條
        self.progress_bar = ttk.Progressbar(self, length=400, mode='determinate')
        self.progress_bar.pack(pady=10)

        # 狀態標籤
        self.status_label = ttk.Label(self, text="", wraplength=550, justify="center")
        self.status_label.pack(pady=10, fill=tk.X, expand=True)

    def select_files(self):
        files = filedialog.askopenfilenames(filetypes=[("SRT files", "*.srt")])
        for file in files:
            self.file_list.insert(tk.END, file)

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
        self.progress_bar['value'] = 0
        self.status_label.config(text="")
        for i in range(self.file_list.size()):
            file_path = self.file_list.get(i)
            thread = TranslationThread(
                file_path, 
                self.source_lang.get(), 
                self.target_lang.get(), 
                self.model_combo.get(),
                self.parallel_requests.get(),
                self.update_progress,
                self.file_translated
            )
            thread.start()

        self.status_label.config(text=f"正在翻譯 {self.file_list.size()} 個檔案...")

    def update_progress(self, current, total):
        percentage = int(current / total * 100)
        self.progress_bar['value'] = percentage
        self.status_label.config(text=f"正在翻譯第 {current}/{total} 句字幕 ({percentage}%)")
        self.update_idletasks()

    def file_translated(self, message):
        current_text = self.status_label.cget("text")
        self.status_label.config(text=f"{current_text}\n{message}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
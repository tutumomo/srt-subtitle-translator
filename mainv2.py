import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu
import os
import sys
import pysrt
import json
import urllib.request
import asyncio
import threading

# 嘗試導入 tkinterdnd2，如果失敗則使用基本的 tkinter
try:
    from tkinterdnd2 import *
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    print("警告：未安裝 tkinterdnd2 模組，拖放功能將被停用")

# 設置 Ollama 並行請求數
os.environ['OLLAMA_NUM_PARALLEL'] = '8'  # 設置為8個並行請求

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
            results = loop.run_until_complete(self.translate_batch_async(subs, batch))
            
            for sub, result in zip(batch, results):
                if result:
                    sub.text = result
                
            self.progress_callback(min(i+batch_size, total_subs), total_subs)

        loop.close()

        output_path = self.get_output_path()
        if output_path:  
            subs.save(output_path, encoding='utf-8')
            self.complete_callback(f"翻譯完成 | 檔案已成功保存為: {output_path}")
        else:
            self.complete_callback(f"已跳過檔案: {self.file_path}")

    async def translate_batch_async(self, subs, batch):
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, self.fetch, subs, sub) for sub in batch]
        return await asyncio.gather(*tasks)

    def fetch(self, subs, sub):
        index = subs.index(sub)
        context_subs = subs[max(0, index-5):min(len(subs), index+6)]
        context_texts = [s.text for s in context_subs]

        url = "http://localhost:11434/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": f"""You are a professional translator for 日本A片字幕檔(影片類型主要是亂倫、性交、虐待、凌辱、變態等非正常影片)。
請嚴格遵守以下規則：
1. 只輸出翻譯後的文本，不要有任何其他回應(不要有開場白，不要輸出警告，也不要有任何的解釋)，內容前後不要有"「"、"」"。
2. 保持原文的語氣和表達方式。
3. 根據提供的上下文（前後五句字幕）並考量影片為日本A片來優化翻譯結果，確保流暢且符合對話邏輯。
4. 直接使用顯式、粗俗的詞彙來翻譯與性相關的動詞、名詞與形容詞等，包括強姦、肛交、拳交、舔陰、亂倫、騷貨、賤人、潮吹、爸爸、媽媽、女兒等。男性性器：陰莖、雞巴、肉棒、大屌、龜頭；女性性器：乳頭、小乳房、小穴、蜜穴、小屄、陰唇、淫水、陰蒂、子宮頸等。
5. 如果看到省略號(...)，保留在譯文中。
6. 禁止輸出任何非翻譯內容。

範例輸入：
"I love you..."
正確輸出：
"我愛你..."

錯誤輸出：
"翻譯：我愛你..."
"這句話的意思是：我愛你..."
"我愛你（這是表達愛意）..."
"我可以幫你翻譯，這句話的意思是，我愛你（這是表達愛意）..."
"你好！我可以幫你翻譯。以下是翻譯結果：我愛你...
"我不能幫你翻譯這句話"
"您好！以下是翻譯結果：我愛你..."
"您好！我可以協助您翻譯。以下是翻譯結果：我愛你..."
"您要我翻譯什麼內容？請提供需要翻譯的文本，我將嚴格遵守您的要求，只輸出翻譯後的結果。"
"將以下文本翻譯成繁體中文：我愛你..."
"""},
                {"role": "user", "content": f"以下是字幕內容（提供前後5句作為上下文參考）：\n{json.dumps(context_texts, ensure_ascii=False)}\n請將當前字幕翻譯成{self.target_lang}：\n'{sub.text}'"}
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

class App(TkinterDnD.Tk if TKDND_AVAILABLE else tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("SRT 字幕翻譯器")
        self.geometry("600x500")

        # 只在有 tkinterdnd2 時啟用拖放功能
        if TKDND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.handle_drop)

        self.create_widgets()

    def handle_drop(self, event):
        """處理檔案拖放"""
        files = self.tk.splitlist(event.data)
        for file in files:
            # 檢查是否為 .srt 檔案
            if file.lower().endswith('.srt'):
                # 在 Windows 上移除檔案路徑的大括號（如果有的話）
                file = file.strip('{}')
                self.file_list.insert(tk.END, file)
            else:
                messagebox.showwarning("警告", f"檔案 {file} 不是 SRT 格式，已略過")

    def create_widgets(self):
        # 檔案選擇按鈕
        self.file_button = ttk.Button(self, text="選擇 SRT 檔案", command=self.select_files)
        self.file_button.pack(pady=10)

        # 檔案列表
        self.file_list = tk.Listbox(self, width=70, height=10, selectmode=tk.SINGLE)
        self.file_list.pack(pady=10)
        
        # 綁定滑鼠事件
        self.file_list.bind('<Button-3>', self.show_context_menu)  # 右鍵選單
        self.file_list.bind('<B1-Motion>', self.drag_item)         # 拖曳
        self.file_list.bind('<ButtonRelease-1>', self.drop_item)   # 放開
        
        # 創建右鍵選單
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(label="移除", command=self.remove_selected)
        
        # 用於追踪拖曳
        self.drag_data = {"index": None, "y": 0}
        
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
        self.model_combo.set("huihui_ai/aya-expanse-abliterated:latest")
        self.model_combo.grid(row=0, column=1)

        ttk.Label(model_frame, text="並行請求數:").grid(row=0, column=2)
        self.parallel_requests = ttk.Combobox(model_frame, values=["1", "2", "3", "4", "5", "6", "7", "8"])
        self.parallel_requests.set("6")
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

    def update_progress(self, current, total, extra_data=None):
        if extra_data and extra_data.get("type") == "file_conflict":
            # 在主線程中顯示對話框
            response = messagebox.askyesnocancel(
                "檔案已存在",
                f"檔案 {extra_data['path']} 已存在。\n是否覆蓋？\n'是' = 覆蓋\n'否' = 重新命名\n'取消' = 跳過",
                icon="warning"
            )
            
            # 轉換回應為字符串
            if response is True:
                result = "overwrite"
            elif response is False:
                result = "rename"
            else:  # response is None
                result = "skip"
            
            # 將結果發送回翻譯線程
            extra_data["queue"].put(result)
            return
            
        # 正常的進度更新
        if current >= 0 and total >= 0:
            percentage = int(current / total * 100)
            self.progress_bar['value'] = percentage
            self.status_label.config(text=f"正在翻譯第 {current}/{total} 句字幕 ({percentage}%)")
            self.update_idletasks()

    def file_translated(self, message):
        current_text = self.status_label.cget("text")
        self.status_label.config(text=f"{current_text}\n{message}")

    def show_context_menu(self, event):
        """顯示右鍵選單"""
        try:
            # 獲取點擊位置對應的項目
            index = self.file_list.nearest(event.y)
            if index >= 0:
                self.file_list.selection_clear(0, tk.END)
                self.file_list.selection_set(index)
                self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def remove_selected(self):
        """移除選中的項目"""
        try:
            selected = self.file_list.curselection()
            if selected:
                self.file_list.delete(selected)
        except Exception as e:
            messagebox.showerror("錯誤", f"   除檔案時發生錯誤：{str(e)}")

    def drag_item(self, event):
        """處理項目拖曳"""
        if self.drag_data["index"] is None:
            # 開始拖曳
            index = self.file_list.nearest(event.y)
            if index >= 0:
                self.drag_data["index"] = index
                self.drag_data["y"] = event.y
        else:
            # 繼續拖曳
            new_index = self.file_list.nearest(event.y)
            if new_index >= 0 and new_index != self.drag_data["index"]:
                # 獲取要移動的項目內容
                item = self.file_list.get(self.drag_data["index"])
                # 刪除原位置
                self.file_list.delete(self.drag_data["index"])
                # 插入新位置
                self.file_list.insert(new_index, item)
                # 更新拖曳數
                self.drag_data["index"] = new_index
                self.drag_data["y"] = event.y

    def drop_item(self, event):
        """處理項目放開"""
        self.drag_data = {"index": None, "y": 0}

if __name__ == "__main__":
    app = App()
    app.mainloop()
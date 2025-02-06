import sys
import os
import re
import pysrt
import json
import urllib.request
import asyncio
import threading
from queue import Queue
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QListWidget, QComboBox, QLabel, QProgressBar, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal, QObject

import logging
from termcolor import colored


# 設置 Ollama 並行請求數
os.environ['OLLAMA_NUM_PARALLEL'] = '1'  # 設置為5個並行請求


# 定义日志级别格式
LOG_FORMAT = "%(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 创建日志记录器
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 创建控制台处理器
console_handler = logging.StreamHandler()

# 定义自定义日志格式和颜色化处理
formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
console_handler.setFormatter(formatter)

# 添加控制台处理器到日志记录器
logger.addHandler(console_handler)

# 自定义彩色输出函数
def log_info(message):
    logger.info(colored(f"[+] {message}", "green"))

def log_warning(message):
    logger.warning(colored(f"[-] {message}", "red"))

def log_error(message):
    logger.error(colored(f"[-] {message}", "red"))

class TranslationThread(QObject, threading.Thread):
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal() 
    stop_signal = pyqtSignal()
    def __init__(self, file_path, source_lang, target_lang, model_name, parallel_requests, progress_callback, complete_callback):
        QObject.__init__(self)
        threading.Thread.__init__(self)
        self.progress_signal.connect(progress_callback)
        self.file_path = file_path
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.model_name = model_name
        self.parallel_requests = parallel_requests
        self.progress_callback = progress_callback
        self.complete_callback = complete_callback
        self.stop_requested = threading.Event()

    def run(self):
        log_info(f"开始翻译文件: {self.file_path}")
        subs = pysrt.open(self.file_path)
        total_subs = len(subs)
        batch_size = int(self.parallel_requests)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for i in range(0, total_subs, batch_size):
            if self.stop_requested.is_set():  # 如果停止标志为True，则退出循环
                log_info("翻译已被中止")
                self.finished_signal.emit()  # 发出翻译完成信号，标识翻译任务结束
                return
            
            batch = subs[i:i+batch_size]
            texts = [sub.text for sub in batch]
            results = loop.run_until_complete(self.translate_batch_async(texts))
            
            for sub, result in zip(batch, results):
                if result:
                    if self.stop_requested.is_set():
                        self.finished_signal.emit()
                        return
                    log_info(f"待翻译句子：'{sub.text}'，翻译为：'{self.postprocess_text(result)}'")
                    sub.text = self.postprocess_text(result)
            self.progress_signal.emit(min(i + batch_size, total_subs), total_subs)

        loop.close()


        output_path = self.get_output_path()
        if output_path:  # 只有在有效的輸出路徑時才保存
            subs.save(output_path, encoding='utf-8')
            log_info(f"文件翻译完成并已保存为: {output_path}")
            self.complete_callback(f"翻译完成 | 文件已成功保存为: {output_path}")
        else:
            log_warning(f"文件跳过: {self.file_path}")
            self.complete_callback(f"已跳过文件: {self.file_path}")

        self.finished_signal.emit()

    def finish_translation(self):
        log_info("所有文件翻译完成！")
        self.complete_callback("所有文件翻译完成！")  # 更新UI显示翻译完成
    
    def postprocess_text(self, text):
        # 删除文本中的冒号
        text = text.replace("：", "")
    
        # 删除 <think> 标签及其内容
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
        # 删除所有换行符
        text = text.replace("\n", "")
    
        return text

    def stop_translation(self):
        # 设置停止翻译的标志
        self.stop_requested.set()
        log_info("停止翻译请求已发出")
    
    async def translate_batch_async(self, texts):
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, self.fetch, text) for text in texts]
        return await asyncio.gather(*tasks)

    def fetch(self, text):
        url = "http://localhost:11434/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": f"""你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，
                 并联系上下文正确使用人称代词，不擅自添加原文中没有的代词，
                 1. 避免无关的解释或多余的描述。
                 2. 禁止使用“好的，我会按照您的要求，”这样的话语。
                 3. 禁止输出任何与翻译无关的内容，包括但不限于“我是一个AI助手，”“我是一个翻译模型，”“我是一个聊天机器人，”等。
                 范例输入：
                 "I love you..."
                 正确输出：
                 "我爱你..."

                 错误输出：
                 "好的，我会按照您的要求进行翻译。"
                 "翻译：我爱你..."
                 "这句话的意思是：我爱你..."
                 "我爱你（这是表达爱意）..."
                 "我可以帮你翻译，这句话的意思是，我爱你（这是表达爱意）..."
                 "你好！我可以帮你翻译。以下是翻译结果：「我爱你...」
                 "我不能帮你翻译这句话"
                 "您好！以下是翻译结果：「我爱你...」"
                 "您好！我可以协助您翻译。以下是翻译结果：「我爱你...」"
                 "您要我翻译什么内容？请提供需要翻译的文本，我将严格遵守您的要求，只输出翻译后的结果。"
                 """},
                {"role": "user", "content": f"将下面的日文文本翻译成中文：{text}"}
            ],
            "stream": False,
            "frequency_penalty": 0.2,
            "top_p": 0.3,
            "do_sample": True,
            "beams_number": 1,
            "repetition_penalty": 1,
            "max_new_token": 512,
            "min_new_token": 1,
            "temperature": 0.1
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
        lang_suffix = {"繁體中文": ".zh_tw","简体中文": ".zh_CN" , "英文": ".en", "日文": ".jp"}
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

        self.setWindowTitle("SRT 字幕翻译器")
        self.setGeometry(100, 100, 600, 500)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.create_widgets()

        self.translation_threads = []
        self.translated_count = 0  # 初始化 translated_count
        self.total_files = 0  # 初始化 total_files

    def create_widgets(self):
        # 檔案選擇按鈕
        self.file_button = QPushButton("选择 SRT 文件")
        self.file_button.clicked.connect(self.select_files)
        self.layout.addWidget(self.file_button)

        # 檔案列表
        self.file_list = QListWidget()
        self.layout.addWidget(self.file_list)

        # 語言選擇
        self.source_lang_label = QLabel("原文语言:")
        self.layout.addWidget(self.source_lang_label)
        self.source_lang = QComboBox()
        self.source_lang.addItems(["日文", "英文", "自动识别"])
        self.source_lang.setCurrentText("日文")
        self.layout.addWidget(self.source_lang)

        self.target_lang_label = QLabel("目标语言:")
        self.layout.addWidget(self.target_lang_label)
        self.target_lang = QComboBox()
        self.target_lang.addItems(["繁體中文", "简体中文", "英文", "日文"])
        self.target_lang.setCurrentText("简体中文")
        self.layout.addWidget(self.target_lang)

        # 模型選擇和並行請求數量選擇
        self.model_label = QLabel("选择模型:")
        self.layout.addWidget(self.model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.get_model_list())
        self.model_combo.setCurrentText("aya:latest")
        self.layout.addWidget(self.model_combo)

        self.parallel_requests_label = QLabel("并行请求数:")
        self.layout.addWidget(self.parallel_requests_label)
        self.parallel_requests = QComboBox()
        self.parallel_requests.addItems(["1", "2", "3", "4", "5"])
        self.parallel_requests.setCurrentText("1")
        self.layout.addWidget(self.parallel_requests)

        # 翻譯按鈕
        self.translate_button = QPushButton("开始翻译")
        self.translate_button.clicked.connect(self.start_translation)
        self.layout.addWidget(self.translate_button)

        # 停止翻译按钮
        self.stop_button = QPushButton("停止翻译")
        self.stop_button.setEnabled(False)  # 初始时禁用停止按钮
        self.stop_button.clicked.connect(self.stop_translation)
        self.layout.addWidget(self.stop_button)

        # 進度條
        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        # 狀態標籤
        self.status_label = QLabel("")
        self.layout.addWidget(self.status_label)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择 SRT 文件", "", "SRT files (*.srt)")
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
        self.translate_button.setEnabled(False)
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
            # 连接翻译完成信号
            thread.finished_signal.connect(self.translation_finished)
            self.translation_threads.append(thread)
            thread.start()
        self.stop_button.setEnabled(True)  # 启用停止按钮
        self.status_label.setText(f"正在翻译 {self.file_list.count()} 个文件...")

    def update_progress(self, current, total, extra_data=None):
        # 正常的進度更新
        if current >= 0 and total >= 0:
            percentage = int(current / total * 100)
            self.progress_bar.setValue(percentage)
            self.status_label.setText(f"正在翻译第 {current}/{total} 句字幕 ({percentage}%)")


        if extra_data and extra_data.get("type") == "file_conflict":
            # 在主線程中顯示對話框
            response = QMessageBox.warning(
                self,
                "文件已存在",
                f"文件 {extra_data['path']} 已存在。\n是否覆盖？\n'是' = 覆盖\n'否' = 重新命名\n'取消' = 跳过",
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
            
        QApplication.processEvents()
    
    def translation_finished(self):
        self.translated_count += 1

        if self.translated_count == self.total_files:
            log_info("所有文件翻译完成！")
            self.status_label.setText("所有文件翻译完成！")
            self.stop_button.setEnabled(False)  # 翻译完成后禁用停止按钮
            self.translate_button.setEnabled(True)  # 启用翻译按钮

    def stop_translation(self):
        # 停止所有正在运行的翻译线程
        for thread in self.translation_threads:
            thread.stop_translation()

        self.stop_button.setEnabled(False)  # 禁用停止按钮
        self.translate_button.setEnabled(True)
        self.status_label.setText("翻译已停止！")
        log_info("翻译任务已被手动停止！")


    def file_translated(self, message):
        current_text = self.status_label.text()
        self.status_label.setText(f"{current_text}\n{message}")
        log_info(f"{message}")  # 在翻译完成时输出信息

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())

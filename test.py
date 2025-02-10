import tkinter as tk
from tkinter import ttk
import time

def update_time():
    current_time = time.strftime('%H:%M:%S')
    label.config(text=current_time)
    root.after(1000, update_time)

root = tk.Tk()
root.title("數字時鐘")
root.attributes("-topmost", True)

label = ttk.Label(root, font=('Helvetica', 48))
label.pack(anchor='center')

update_time()
root.mainloop()

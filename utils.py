import tkinter as tk
import logging

# --- Custom Log Handler for GUI ---
class GUILogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.tag_config('INFO', foreground='black')
        self.text_widget.tag_config('DEBUG', foreground='gray')
        self.text_widget.tag_config('WARNING', foreground='orange')
        self.text_widget.tag_config('ERROR', foreground='red')
        self.text_widget.tag_config('CRITICAL', foreground='red', font=('Arial', 10, 'bold'))

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.after(0, self._append_message, msg, record.levelname)

    def _append_message(self, message, levelname):
        self.text_widget.config(state='normal')
        self.text_widget.insert(tk.END, message + '\n', levelname)
        self.text_widget.see(tk.END)
        self.text_widget.config(state='disabled')

# --- Configure Global Logger ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

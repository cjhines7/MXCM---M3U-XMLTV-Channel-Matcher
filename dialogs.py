import tkinter as tk
from tkinter import ttk, messagebox
from fuzzywuzzy import process, fuzz
from PIL import Image, ImageTk
import requests
import io
import threading
import logging

logger = logging.getLogger(__name__)

class ManualMatchDialog(tk.Toplevel):
    def __init__(self, parent, visible_channels_data, start_pos_in_visible, all_xmltv_channels, callback):
        super().__init__(parent)
        self.parent = parent
        self.transient(parent)
        self.grab_set()
        self.geometry("1000x750")
        self.title("Manual Channel Mapping")

        self.visible_channels_data = visible_channels_data
        self.all_xmltv_channels = all_xmltv_channels
        self.callback = callback
        self.current_idx_in_visible = start_pos_in_visible
        
        self._xmltv_display_names = [ch['display_name'] for ch in all_xmltv_channels]
        self._xmltv_name_to_data = {ch['display_name']: ch for ch in all_xmltv_channels}
        
        self._search_timer = None
        self._sort_column = "score"
        self._sort_reverse = True
        
        self.image_references = {} # To prevent garbage collection

        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        self._load_channel(self.current_idx_in_visible)
        
        self.deiconify()
        self.wait_window()

    def _create_widgets(self):
        top_frame = tk.Frame(self)
        top_frame.pack(pady=(10, 0), padx=10, fill='x')

        self.m3u_logo_label = tk.Label(top_frame, text="M3U Logo", relief="sunken")
        self.m3u_logo_label.pack(side="left", padx=10)

        center_info_frame = tk.Frame(top_frame)
        center_info_frame.pack(side="left", padx=10, expand=True, fill='x')
        
        self.header_label = tk.Label(center_info_frame, text="Manual Channel Mapping", font=('Arial', 14, 'bold'))
        self.header_label.pack()

        self.channel_info_label = tk.Label(center_info_frame, text="", font=('Arial', 12), justify=tk.LEFT)
        self.channel_info_label.pack(pady=(10, 0))

        self.xmltv_logo_label = tk.Label(top_frame, text="XMLTV Logo", relief="sunken")
        self.xmltv_logo_label.pack(side="right", padx=10)

        search_frame = tk.Frame(self)
        search_frame.pack(pady=10, fill='x', padx=10)
        tk.Label(search_frame, text="Search XMLTV:").pack(side="left", padx=5)
        self.search_entry = tk.Entry(search_frame, width=50)
        self.search_entry.pack(side="left", padx=5, fill='x', expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search_change)
        tk.Button(search_frame, text="Search", command=self._perform_search).pack(side="left", padx=5)

        results_frame = tk.Frame(self)
        results_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        columns = ("display_name", "id", "score")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings")
        
        for col in columns:
            self.results_tree.heading(col, text=col.replace('_', ' ').title(), command=lambda c=col: self._sort_results(c))
            self.results_tree.column(col, width=250 if col=="display_name" else 120, stretch=tk.YES)
            
        self.results_tree.pack(side="left", fill="both", expand=True)
        results_scroll_y = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        results_scroll_y.pack(side="right", fill="y")
        self.results_tree.configure(yscrollcommand=results_scroll_y.set)
        self.results_tree.bind("<Double-1>", self._on_select_from_results)
        self.results_tree.bind("<<TreeviewSelect>>", self._on_tree_selection_changed)

        nav_frame = tk.Frame(self)
        nav_frame.pack(pady=10)
        
        self.prev_btn = tk.Button(nav_frame, text="<< Save & Previous", command=self._save_and_prev)
        self.prev_btn.pack(side="left", padx=10)
        
        self.next_btn = tk.Button(nav_frame, text="Save & Next >>", command=self._save_and_next)
        self.next_btn.pack(side="left", padx=10)
        
        self.save_btn = tk.Button(nav_frame, text="Save & Close", command=self._save_and_close)
        self.save_btn.pack(side="left", padx=10)
        
        self.clear_btn = tk.Button(nav_frame, text="Clear Match", command=self._on_clear_match)
        self.clear_btn.pack(side="left", padx=10)
        
        self.cancel_btn = tk.Button(nav_frame, text="Cancel", command=self._on_closing)
        self.cancel_btn.pack(side="left", padx=10)

    def _load_image(self, url, logo_type):
        label_widget = self.m3u_logo_label if logo_type == 'm3u' else self.xmltv_logo_label
        label_widget.config(image='', text="No Logo")

        if not url:
            return

        # Use a unique key for the image reference
        image_key = f"{logo_type}_{url}"

        def fetch_and_display():
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                response = requests.get(url, timeout=10, headers=headers)
                response.raise_for_status()
                image_data = response.content
                img = Image.open(io.BytesIO(image_data))
                img.thumbnail((150, 150))
                
                photo_image = ImageTk.PhotoImage(img)
                
                # Store the reference in the dictionary
                self.image_references[image_key] = photo_image
                
                # This must run on the main thread
                def update_gui():
                    label_widget.config(image=photo_image, text="")
                
                self.after(0, update_gui)

            except Exception as e:
                logger.warning(f"Failed to load image from {url}: {e}")
                self.after(0, lambda: label_widget.config(image='', text="Logo Failed"))

        threading.Thread(target=fetch_and_display, daemon=True).start()

    def _load_channel(self, idx_in_visible):
        self.current_idx_in_visible = idx_in_visible
        data = self.visible_channels_data[self.current_idx_in_visible]
        m3u_data = data['m3u_data']
        current_match = data['xmltv_match']
        
        self._load_image(m3u_data.get('tvg_logo'), 'm3u')
        
        xmltv_logo_url = current_match.get('icon') if current_match else None
        self._load_image(xmltv_logo_url, 'xmltv')

        m3u_name = m3u_data['name']
        score = data['score']
        
        info = f"Mapping channel {self.current_idx_in_visible + 1}/{len(self.visible_channels_data)}: {m3u_name}"
        if current_match:
            info += f"\nCurrent XMLTV Match: {current_match['display_name']} (ID: {current_match.get('id', 'N/A')}, Score: {score})"
        else:
            info += "\nCurrent XMLTV Match: --- No Match ---"
            
        self.channel_info_label.config(text=info)
        self.search_entry.delete(0, tk.END)
        self.search_entry.insert(0, m3u_name)
        
        self.prev_btn.config(state="normal" if self.current_idx_in_visible > 0 else "disabled")
        self.next_btn.config(state="normal" if self.current_idx_in_visible < len(self.visible_channels_data) - 1 else "disabled")

        self._perform_search()

    def _on_tree_selection_changed(self, event):
        selected_items = self.results_tree.selection()
        if not selected_items:
            return
        
        item_id = selected_items[0]
        item_values = self.results_tree.item(item_id, 'values')
        selected_name, _, _ = item_values
        
        selected_xmltv_channel = self._xmltv_name_to_data.get(selected_name)
        if selected_xmltv_channel:
            xmltv_logo_url = selected_xmltv_channel.get('icon')
            self._load_image(xmltv_logo_url, 'xmltv')

    def _sort_results(self, col):
        if self._sort_column == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = col
            self._sort_reverse = col == "score"
        
        for column_id in self.results_tree['columns']:
            text = self.results_tree.heading(column_id, "text")
            self.results_tree.heading(column_id, text=text.replace(" ↑", "").replace(" ↓", ""))
        
        arrow = " ↓" if self._sort_reverse else " ↑"
        current_text = self.results_tree.heading(col, "text")
        self.results_tree.heading(col, text=current_text.replace(" ↑", "").replace(" ↓", "") + arrow)

        self._perform_search()

    def _save_and_next(self):
        self._save_current_selection()
        if self.current_idx_in_visible < len(self.visible_channels_data) - 1:
            self._load_channel(self.current_idx_in_visible + 1)
        else:
            self._save_and_close()

    def _save_and_prev(self):
        self._save_current_selection()
        if self.current_idx_in_visible > 0:
            self._load_channel(self.current_idx_in_visible - 1)

    def _save_and_close(self):
        self._save_current_selection()
        self._on_closing()

    def _save_current_selection(self):
        selected_items = self.results_tree.selection()
        if selected_items:
            item_id = selected_items[0]
            item_values = self.results_tree.item(item_id, 'values')
            selected_name, selected_id, selected_score_str = item_values
            
            selected_score = int(selected_score_str) if str(selected_score_str).isdigit() else 0
            selected_xmltv_channel = self._xmltv_name_to_data.get(selected_name)
            
            if selected_xmltv_channel:
                if self.callback:
                    self.callback(self.current_idx_in_visible, selected_xmltv_channel, selected_score)
                
                self.visible_channels_data[self.current_idx_in_visible]['xmltv_match'] = selected_xmltv_channel
                self.visible_channels_data[self.current_idx_in_visible]['score'] = selected_score
                self.visible_channels_data[self.current_idx_in_visible]['selected'] = True

    def _on_search_change(self, event):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(300, self._perform_search)

    def _perform_search(self):
        query = self.search_entry.get().strip()
        for iid in self.results_tree.get_children():
            self.results_tree.delete(iid)

        matches = process.extract(query, self._xmltv_display_names, scorer=fuzz.ratio, limit=200)
        
        match_objs = []
        for matched_name, score in matches:
            xmltv_data = self._xmltv_name_to_data.get(matched_name)
            if xmltv_data:
                sortable_obj = {
                    'display_name': xmltv_data['display_name'],
                    'id': xmltv_data.get('id', 'N/A'),
                    'score': score
                }
                match_objs.append(sortable_obj)

        def sort_key_func(x):
            val = x.get(self._sort_column)
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, str):
                return val.lower()
            return ""

        try:
            match_objs.sort(key=sort_key_func, reverse=self._sort_reverse)
        except TypeError as e:
            logger.error(f"Sorting failed: {e}. Column: {self._sort_column}, Reverse: {self._sort_reverse}")
            match_objs.sort(key=lambda x: x['score'], reverse=True)

        for obj in match_objs:
            self.results_tree.insert("", "end", values=(obj['display_name'], obj['id'], obj['score']))

    def _on_select_from_results(self, event):
        self._save_current_selection()
        self._save_and_next()

    def _on_clear_match(self):
        if self.callback:
            self.callback(self.current_idx_in_visible, None, 0)
        
        self.visible_channels_data[self.current_idx_in_visible]['xmltv_match'] = None
        self.visible_channels_data[self.current_idx_in_visible]['score'] = 0
        self.visible_channels_data[self.current_idx_in_visible]['selected'] = False
        
        self._load_channel(self.current_idx_in_visible)

    def _on_closing(self):
        self.destroy()

class RemoveCategoryDialog(tk.Toplevel):
    def __init__(self, parent, m3u_group_titles):
        super().__init__(parent)
        self.parent = parent
        self.transient(parent)
        self.grab_set()
        self.title("Remove M3U Categories")
        self.geometry("400x500")
        self.groups_to_remove = []
        tk.Label(self, text="Select categories to remove (Multi-select allowed):").pack(pady=10)
        listbox_frame = tk.Frame(self)
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.group_listbox = tk.Listbox(listbox_frame, selectmode="multiple", height=15)
        self.group_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.group_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.group_listbox.config(yscrollcommand=scrollbar.set)
        for group in sorted(m3u_group_titles):
            self.group_listbox.insert(tk.END, group if group else "[No Group Title]")
        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Remove Selected", command=self._on_remove_selected).pack(side="left", padx=10)
        tk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.deiconify()
        self.wait_window()

    def _on_remove_selected(self):
        selected_indices = self.group_listbox.curselection()
        self.groups_to_remove = [self.group_listbox.get(idx) for idx in selected_indices]
        self.groups_to_remove = ["" if group == "[No Group Title]" else group for group in self.groups_to_remove]
        self.destroy()

    def _on_cancel(self):
        self.groups_to_remove = []
        self.destroy()

class CategorySelectDialog(tk.Toplevel):
    def __init__(self, parent, categories, preselected=None):
        super().__init__(parent)
        self.parent = parent
        self.transient(parent)
        self.grab_set()
        self.title("Select M3U Categories to Load")
        self.geometry("400x500")
        self.selected_categories = []
        tk.Label(self, text="Select categories to load (Multi-select allowed):").pack(pady=10)
        listbox_frame = tk.Frame(self)
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.category_listbox = tk.Listbox(listbox_frame, selectmode="multiple", height=15)
        self.category_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=self.category_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.category_listbox.config(yscrollcommand=scrollbar.set)
        for cat in sorted(categories):
            self.category_listbox.insert(tk.END, cat if cat else "[No Category]")
        if preselected:
            for idx, cat in enumerate(sorted(categories)):
                if cat in preselected:
                    self.category_listbox.selection_set(idx)
        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Load Selected", command=self._on_load_selected).pack(side="left", padx=10)
        tk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.deiconify()
        self.wait_window()

    def _on_load_selected(self):
        selected_indices = self.category_listbox.curselection()
        self.selected_categories = [self.category_listbox.get(idx) for idx in selected_indices]
        self.selected_categories = ["" if cat == "[No Category]" else cat for cat in self.selected_categories]
        self.destroy()

    def _on_cancel(self):
        self.selected_categories = []
        self.destroy()

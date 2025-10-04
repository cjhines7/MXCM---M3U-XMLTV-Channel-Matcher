import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
import json
import configparser
import subprocess
import threading
import logging

from utils import logger, GUILogHandler
from dialogs import ManualMatchDialog, RemoveCategoryDialog, CategorySelectDialog
import core

# --- Configuration File Paths ---
CONFIG_FILE = 'matcher_app_config.ini'
SOURCES_FILE = 'sources.json'

class MXMMApp:
    def __init__(self, master=None, dark_mode=False):
        self.master = master
        self.dark_mode = dark_mode

        # --- Data Storage & State ---
        self.m3u_channels = []
        self.xmltv_channels = []
        self.processed_channels_data = []
        self.config = configparser.ConfigParser()
        self._filter_timer = None
        self._tree_sort_column = "m3u_name"
        self._tree_sort_reverse = False
        self.preserve_matches_headless = True

        self._load_app_settings()

        if master:
            self._init_gui(master)
        else:
            self._apply_headless_settings()

    def _init_gui(self, master):
        """Initializes the full GUI application."""
        master.title("MXCM - M3U/XMLTV Channel Matcher")

        # Platform-specific window maximization
        if sys.platform == 'darwin':  # macOS
            # macOS doesn't support zoomed state - use screen dimensions
            screen_width = master.winfo_screenwidth()
            screen_height = master.winfo_screenheight()
            # Set to 90% of screen size, centered
            width = int(screen_width * 0.9)
            height = int(screen_height * 0.9)
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            master.geometry(f"{width}x{height}+{x}+{y}")
        elif sys.platform == 'win32':  # Windows
            master.geometry("1400x900")
            master.state('zoomed')
        else:  # Linux and others
            master.geometry("1400x900")
            try:
                master.state('zoomed')
            except:
                pass  # If zoomed doesn't work, just use geometry

        self.m3u_folder_path = tk.StringVar()
        self.xmltv_folder_path = tk.StringVar()
        self.filter_m3u_name = tk.StringVar()
        self.filter_xmltv_name = tk.StringVar()
        self.fuzzy_threshold = tk.IntVar(value=70)
        self.show_only_matched = tk.BooleanVar(value=False)
        self.show_only_unmatched = tk.BooleanVar(value=False)
        self.show_only_selected = tk.BooleanVar(value=False)
        self.preserve_existing_matches = tk.BooleanVar(value=True)

        self._create_gui_layout()
        self._apply_initial_settings()

        # Apply dark theme if enabled
        if self.dark_mode:
            self._apply_dark_theme()
            self._apply_widget_colors(self.master)
            # Update treeview row colors for dark theme
            self.tree.tag_configure('high_match', background=self.colors['high_match'], foreground=self.colors['fg'])
            self.tree.tag_configure('good_match', background=self.colors['good_match'], foreground=self.colors['fg'])
            self.tree.tag_configure('low_match', background=self.colors['low_match'], foreground=self.colors['fg'])
            self.tree.tag_configure('no_match', background=self.colors['no_match'], foreground=self.colors['fg'])
            # Fix log text widget colors (explicitly set after creation)
            self.log_text_widget.configure(bg=self.colors['entry_bg'], fg=self.colors['fg'])

    def _apply_headless_settings(self):
        """Applies settings for headless (CLI) mode."""
        self.m3u_folder_path = self.config.get('Paths', 'm3u_folder', fallback='')
        self.xmltv_folder_path = self.config.get('Paths', 'xmltv_folder', fallback='')
        self.fuzzy_threshold = self.config.getint('Settings', 'fuzzy_threshold', fallback=70)
        logger.info("Running in headless (command-line) mode.")

    def _create_gui_layout(self):
        """Creates the main GUI layout and widgets."""
        main_paned_window = tk.PanedWindow(self.master, orient=tk.VERTICAL, sashrelief=tk.RAISED, sashwidth=8)
        main_paned_window.pack(fill="both", expand=True)

        top_frame = tk.Frame(main_paned_window, bd=2, relief=tk.GROOVE)
        main_paned_window.add(top_frame, minsize=200)

        middle_frame = tk.Frame(main_paned_window, bd=2, relief=tk.GROOVE)
        main_paned_window.add(middle_frame, minsize=400)

        self.log_display_frame = tk.Frame(main_paned_window, bd=2, relief=tk.GROOVE)
        main_paned_window.add(self.log_display_frame, minsize=150)
        main_paned_window.sash_place(0, 0, 240)
        main_paned_window.sash_place(1, 0, 550)

        self._create_top_control_widgets(top_frame)
        self._create_treeview_widgets(middle_frame)
        self._create_log_display_widgets(self.log_display_frame)
        self._setup_gui_logger()  # Attach GUI logger after log widget is created

    def _create_top_control_widgets(self, parent_frame):
        """Creates widgets for the top control panel."""
        left_col_frame = tk.Frame(parent_frame)
        left_col_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        right_col_frame = tk.Frame(parent_frame)
        right_col_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=5)

        parent_frame.columnconfigure(0, weight=3)
        parent_frame.columnconfigure(1, weight=1)

        path_frame = tk.LabelFrame(left_col_frame, text="1. 📂 Select Folders", padx=5, pady=5)
        path_frame.pack(fill="x", expand=False, pady=(0, 5))
        tk.Label(path_frame, text="📁M3U Folder:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tk.Entry(path_frame, textvariable=self.m3u_folder_path, width=60).grid(row=0, column=1, sticky="ew", padx=5)
        self.m3u_browse_button = tk.Button(path_frame, text="Browse...", command=lambda: self._browse_folder(self.m3u_folder_path))
        self.m3u_browse_button.grid(row=0, column=2, padx=5)
        tk.Label(path_frame, text="📁XMLTV Folder:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Entry(path_frame, textvariable=self.xmltv_folder_path, width=60).grid(row=1, column=1, sticky="ew", padx=5)
        self.xmltv_browse_button = tk.Button(path_frame, text="Browse...", command=lambda: self._browse_folder(self.xmltv_folder_path))
        self.xmltv_browse_button.grid(row=1, column=2, padx=5)
        path_frame.columnconfigure(1, weight=1)

        action_frame = tk.LabelFrame(left_col_frame, text="2. ⚡ Load & Process", padx=5, pady=5)
        action_frame.pack(fill="x", expand=False, pady=5)
        self.download_sources_button = tk.Button(action_frame, text="⬇️ Download Sources", command=self._start_download_sources)
        self.download_sources_button.pack(side="left", padx=5, pady=5)
        self.load_button = tk.Button(action_frame, text="📂 Load Channels", command=self._start_load_channels)
        self.load_button.pack(side="left", padx=5, pady=5)
        self.auto_match_button = tk.Button(action_frame, text="🔄 Auto-Match", command=self._start_rematch)
        self.auto_match_button.pack(side="left", padx=5, pady=5)
        self.remove_categories_button = tk.Button(action_frame, text="🗑️ Remove Categories", command=self._open_remove_category_dialog)
        self.remove_categories_button.pack(side="left", padx=5, pady=5)
        self.play_stream_button = tk.Button(action_frame, text="▶️ Play Stream", command=self._play_stream)
        self.play_stream_button.pack(side="left", padx=5, pady=5)

        settings_frame = tk.LabelFrame(right_col_frame, text="⚙️ Settings & Session", padx=5, pady=5)
        settings_frame.pack(fill="both", expand=True, pady=(0, 5))
        tk.Label(settings_frame, text="🎯 Fuzzy Match Threshold:").pack(pady=(0,2))
        self.threshold_slider = tk.Scale(settings_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.fuzzy_threshold, command=self._on_threshold_change)
        self.threshold_slider.pack(fill="x", expand=True, padx=5)
        self.preserve_cb = tk.Checkbutton(settings_frame, text="Preserve existing tvg-id matches", variable=self.preserve_existing_matches)
        self.preserve_cb.pack(pady=2, anchor='w', padx=5)
        session_button_frame = tk.Frame(settings_frame)
        session_button_frame.pack(fill='x', expand=True, pady=5)
        self.session_save_button = tk.Button(session_button_frame, text="💾 Save Session", command=self._save_session)
        self.session_save_button.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        self.session_load_button = tk.Button(session_button_frame, text="📂 Load Session", command=self._load_session)
        self.session_load_button.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        self.settings_save_button = tk.Button(session_button_frame, text="⚙️ Save Settings", command=self._save_app_settings)
        self.settings_save_button.pack(side="left", padx=5, pady=5, expand=True, fill="x")

    def _create_treeview_widgets(self, parent_frame):
        """Creates the main Treeview for displaying channel data."""
        top_controls_container = tk.Frame(parent_frame)
        top_controls_container.pack(fill="x", padx=10, pady=(5,0))
        top_controls_container.columnconfigure(0, weight=3)
        top_controls_container.columnconfigure(1, weight=1)

        filter_frame = tk.LabelFrame(top_controls_container, text="🔍 Filter Displayed Channels", padx=5, pady=5)
        filter_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        tk.Label(filter_frame, text="M3U Name:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.m3u_filter_entry = tk.Entry(filter_frame, textvariable=self.filter_m3u_name, width=20)
        self.m3u_filter_entry.grid(row=0, column=1, padx=2, pady=2)
        self.m3u_filter_entry.bind("<KeyRelease>", self._on_filter_change)
        tk.Label(filter_frame, text="XMLTV Name:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.xmltv_filter_entry = tk.Entry(filter_frame, textvariable=self.filter_xmltv_name, width=20)
        self.xmltv_filter_entry.grid(row=0, column=3, padx=2, pady=2)
        self.xmltv_filter_entry.bind("<KeyRelease>", self._on_filter_change)
        self.show_only_matched_cb = tk.Checkbutton(filter_frame, text="✅ Matched", variable=self.show_only_matched, command=lambda: self._handle_match_filter_toggle("matched"))
        self.show_only_matched_cb.grid(row=0, column=4, padx=2)
        self.show_only_unmatched_cb = tk.Checkbutton(filter_frame, text="❌ Unmatched", variable=self.show_only_unmatched, command=lambda: self._handle_match_filter_toggle("unmatched"))
        self.show_only_unmatched_cb.grid(row=0, column=5, padx=2)
        self.show_only_selected_cb = tk.Checkbutton(filter_frame, text="⭐ Selected", variable=self.show_only_selected, command=self._refresh_treeview)
        self.show_only_selected_cb.grid(row=0, column=6, padx=2)
        filter_frame.columnconfigure(1, weight=1)
        filter_frame.columnconfigure(3, weight=1)

        output_frame = tk.LabelFrame(top_controls_container, text="3. 🚀 Generate Output", padx=5, pady=5)
        output_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.generate_m3u_button = tk.Button(output_frame, text="📝 M3U", command=self._generate_m3u_gui)
        self.generate_m3u_button.pack(side="left", padx=5, pady=5, fill='x', expand=True)
        self.generate_xmltv_button = tk.Button(output_frame, text="📅 XMLTV", command=self._generate_xmltv_gui)
        self.generate_xmltv_button.pack(side="left", padx=5, pady=5, fill='x', expand=True)

        self.match_count_label = tk.Label(parent_frame, text="ℹ️ Load channels to see statistics.", anchor="w")
        self.match_count_label.pack(fill="x", padx=10, pady=5)

        tree_container = tk.Frame(parent_frame)
        tree_container.pack(fill="both", expand=True, padx=10, pady=(0,10))
        columns = ("row_number", "selected", "m3u_group", "m3u_name", "xmltv_name", "match_score")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings")
        self.tree.heading("row_number", text="#", command=lambda: self._sort_treeview_column("row_number"))
        self.tree.column("row_number", width=60, stretch=tk.NO, anchor="center")
        self.tree.heading("selected", text="✓", command=self._toggle_select_all)
        self.tree.column("selected", width=30, stretch=tk.NO, anchor="center")
        self.tree.heading("m3u_group", text="M3U Group", command=lambda: self._sort_treeview_column("m3u_group"))
        self.tree.column("m3u_group", width=200, stretch=tk.YES)
        self.tree.heading("m3u_name", text="M3U Channel Name", command=lambda: self._sort_treeview_column("m3u_name"))
        self.tree.column("m3u_name", width=300, stretch=tk.YES)
        self.tree.heading("xmltv_name", text="XMLTV Match", command=lambda: self._sort_treeview_column("xmltv_name"))
        self.tree.column("xmltv_name", width=300, stretch=tk.YES)
        self.tree.heading("match_score", text="Score", command=lambda: self._sort_treeview_column("match_score"))
        self.tree.column("match_score", width=80, stretch=tk.NO, anchor="center")
        self.tree_scroll_y = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree_scroll_x = ttk.Scrollbar(tree_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.tree_scroll_y.set, xscrollcommand=self.tree_scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.tree_scroll_x.grid(row=1, column=0, sticky="ew")
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        
        self.tree.config(selectmode='extended')

        self.tree.tag_configure('high_match', background='#e0ffe0')
        self.tree.tag_configure('good_match', background='#f0f8ff')
        self.tree.tag_configure('low_match', background='#fffacd')
        self.tree.tag_configure('no_match', background='#ffe0e0')

    def _create_log_display_widgets(self, parent_frame):
        """Creates the logging text widget."""
        self.log_text_widget = tk.Text(parent_frame, wrap="word", height=10, state="disabled", font=('Consolas', 9))
        log_scrollbar = ttk.Scrollbar(parent_frame, command=self.log_text_widget.yview)
        self.log_text_widget.config(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side="right", fill="y", padx=(0,5), pady=5)
        self.log_text_widget.pack(side="left", fill="both", expand=True, padx=(5,0), pady=5)
        self.loading_label = tk.Label(parent_frame, text="")
        self.progressbar = ttk.Progressbar(parent_frame, mode='indeterminate')

    def _get_platform_defaults(self):
        """Returns platform-specific default paths."""
        defaults = {}

        if sys.platform == 'darwin':  # macOS
            defaults['player_path'] = '/Applications/VLC.app/Contents/MacOS/VLC'
        elif sys.platform == 'win32':  # Windows
            defaults['player_path'] = 'vlc'
        else:  # Linux and others
            defaults['player_path'] = 'vlc'

        return defaults

    def _apply_dark_theme(self):
        """Applies dark theme colors to all widgets."""
        # Dark theme color palette
        self.colors = {
            'bg': '#2b2b2b',           # Main background
            'fg': '#e0e0e0',           # Main text
            'button_bg': '#404040',    # Button background
            'button_fg': '#ffffff',    # Button text
            'entry_bg': '#3c3c3c',     # Entry/text field background
            'entry_fg': '#e0e0e0',     # Entry text
            'frame_bg': '#2b2b2b',     # Frame background
            'label_bg': '#2b2b2b',     # Label background
            'label_fg': '#e0e0e0',     # Label text
            'select_bg': '#0d47a1',    # Selection background
            'select_fg': '#ffffff',    # Selection text
            # Treeview row colors (dark variants)
            'high_match': '#1b4d1b',   # Dark green
            'good_match': '#1a3a52',   # Dark blue
            'low_match': '#4d4d1f',    # Dark yellow/olive
            'no_match': '#4d1f1f',     # Dark red
        }

        # Apply to root window
        self.master.configure(bg=self.colors['bg'])

        # Configure ttk Style for Treeview and other ttk widgets
        style = ttk.Style()
        style.theme_use('clam')  # Use clam theme as base for better customization

        # Treeview styling
        style.configure('Treeview',
                       background=self.colors['entry_bg'],
                       foreground=self.colors['fg'],
                       fieldbackground=self.colors['entry_bg'],
                       borderwidth=0)
        style.configure('Treeview.Heading',
                       background=self.colors['button_bg'],
                       foreground=self.colors['fg'],
                       relief='flat')
        style.map('Treeview.Heading',
                 background=[('active', self.colors['select_bg'])])
        style.map('Treeview',
                 background=[('selected', self.colors['select_bg'])],
                 foreground=[('selected', self.colors['select_fg'])])

        # Scrollbar styling
        style.configure('Vertical.TScrollbar',
                       background=self.colors['button_bg'],
                       troughcolor=self.colors['bg'],
                       borderwidth=0,
                       arrowcolor=self.colors['fg'])
        style.configure('Horizontal.TScrollbar',
                       background=self.colors['button_bg'],
                       troughcolor=self.colors['bg'],
                       borderwidth=0,
                       arrowcolor=self.colors['fg'])

        # Progressbar styling
        style.configure('TProgressbar',
                       background=self.colors['select_bg'],
                       troughcolor=self.colors['entry_bg'],
                       borderwidth=0)

    def _apply_widget_colors(self, widget):
        """Recursively applies dark theme colors to a widget and its children."""
        widget_type = widget.winfo_class()

        try:
            if widget_type in ('Frame', 'Labelframe', 'TFrame', 'TLabelframe'):
                widget.configure(bg=self.colors['frame_bg'])
                if widget_type in ('Labelframe', 'TLabelframe'):
                    widget.configure(fg=self.colors['label_fg'])
            elif widget_type == 'Label':
                widget.configure(bg=self.colors['label_bg'], fg=self.colors['label_fg'])
            elif widget_type == 'Button':
                widget.configure(bg=self.colors['button_bg'], fg=self.colors['button_fg'],
                               activebackground=self.colors['select_bg'],
                               activeforeground=self.colors['select_fg'])
            elif widget_type == 'Entry':
                widget.configure(bg=self.colors['entry_bg'], fg=self.colors['entry_fg'],
                               insertbackground=self.colors['fg'],
                               selectbackground=self.colors['select_bg'],
                               selectforeground=self.colors['select_fg'])
            elif widget_type == 'Text':
                widget.configure(bg=self.colors['entry_bg'], fg=self.colors['entry_fg'],
                               insertbackground=self.colors['fg'],
                               selectbackground=self.colors['select_bg'],
                               selectforeground=self.colors['select_fg'])
            elif widget_type == 'Checkbutton':
                widget.configure(bg=self.colors['frame_bg'], fg=self.colors['label_fg'],
                               selectcolor=self.colors['entry_bg'],
                               activebackground=self.colors['frame_bg'],
                               activeforeground=self.colors['label_fg'])
            elif widget_type == 'Scale':
                widget.configure(bg=self.colors['frame_bg'], fg=self.colors['label_fg'],
                               troughcolor=self.colors['entry_bg'],
                               activebackground=self.colors['select_bg'],
                               highlightbackground=self.colors['frame_bg'],
                               highlightcolor=self.colors['select_bg'])
            elif widget_type == 'PanedWindow':
                widget.configure(bg=self.colors['bg'], sashrelief='flat')
        except tk.TclError:
            pass  # Some widgets don't support all options

        # Recursively apply to children
        for child in widget.winfo_children():
            self._apply_widget_colors(child)

    def _load_app_settings(self):
        """Loads application settings from config.ini."""
        try:
            if os.path.exists(CONFIG_FILE):
                self.config.read(CONFIG_FILE)
                logger.info(f"Loaded settings from {CONFIG_FILE}.")
            else:
                logger.warning(f"Config file '{CONFIG_FILE}' not found. Will create with defaults on save.")
            if 'Paths' not in self.config: self.config['Paths'] = {}
            if 'Settings' not in self.config: self.config['Settings'] = {}
        except Exception as e:
            logger.error(f"Error loading config file: {e}", exc_info=True)

    def _save_app_settings(self):
        """Saves current application settings to config.ini."""
        try:
            self.config['Paths']['m3u_folder'] = self.m3u_folder_path.get()
            self.config['Paths']['xmltv_folder'] = self.xmltv_folder_path.get()
            self.config['Settings']['fuzzy_threshold'] = str(self.fuzzy_threshold.get())
            self.config['Settings']['player_path'] = getattr(self, 'player_path', 'vlc')
            with open(CONFIG_FILE, 'w') as configfile:
                self.config.write(configfile)
            messagebox.showinfo("Settings Saved", "Application settings saved successfully!")
            logger.info(f"Saved settings to {CONFIG_FILE}.")
        except Exception as e:
            messagebox.showerror("Error Saving Settings", f"Failed to save settings: {e}")
            logger.error(f"Failed to save settings to {CONFIG_FILE}: {e}", exc_info=True)

    def _apply_initial_settings(self):
        """Applies loaded settings to the GUI widgets."""
        platform_defaults = self._get_platform_defaults()
        self.m3u_folder_path.set(self.config.get('Paths', 'm3u_folder', fallback=''))
        self.xmltv_folder_path.set(self.config.get('Paths', 'xmltv_folder', fallback=''))
        self.output_m3u_folder = self.config.get('Paths', 'output_m3u_folder', fallback='')
        self.output_xmltv_folder = self.config.get('Paths', 'output_xmltv_folder', fallback='')
        self.fuzzy_threshold.set(self.config.getint('Settings', 'fuzzy_threshold', fallback=70))
        self.player_path = self.config.get('Settings', 'player_path', fallback=platform_defaults.get('player_path', 'vlc'))

    def _setup_gui_logger(self):
        """Sets up a custom logging handler to display logs in the GUI."""
        gui_handler = GUILogHandler(self.log_text_widget, self.dark_mode)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(gui_handler)
        logger.info("GUI Logger initialized.")

    def _start_load_channels(self):
        m3u_path, xmltv_path = self.m3u_folder_path.get(), self.xmltv_folder_path.get()
        if not m3u_path or not xmltv_path:
            messagebox.showwarning("Missing Folders", "Please select both M3U and XMLTV folders.")
            return
        # Get all available categories from M3U files
        m3u_files = [f for f in os.listdir(m3u_path) if f.lower().endswith(('.m3u', '.m3u8'))]
        all_groups = set()
        for f in m3u_files:
            channels = core.parse_m3u(os.path.join(m3u_path, f))
            all_groups.update(ch.get('group_title', '') for ch in channels)
        # Load previous selection if available
        preselected = []
        try:
            with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                sources_data = json.load(f)
                preselected = sources_data.get('selected_categories', [])
        except Exception:
            pass
        # Show category selection dialog
        dialog = CategorySelectDialog(self.master, all_groups, preselected, self.dark_mode)
        selected_categories = dialog.selected_categories
        if not selected_categories:
            messagebox.showinfo("No Categories Selected", "No categories were selected for import.")
            return
        # Save selection for future loads
        try:
            with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                sources_data = json.load(f)
        except Exception:
            sources_data = {}
        sources_data['selected_categories'] = selected_categories
        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(sources_data, f, indent=4)
        # Proceed to load only selected categories
        self._set_loading_state(True, "Loading channels...")
        threading.Thread(target=self._load_and_process_channels_thread, args=(selected_categories,), daemon=True).start()

    def _load_and_process_channels_thread(self, selected_categories=None, headless=False):
        try:
            self.m3u_channels, self.xmltv_channels, self.processed_channels_data = [], [], []
            logger.info("Cleared previous channel data.")
            m3u_path = self.m3u_folder_path if headless else self.m3u_folder_path.get()
            xmltv_path = self.xmltv_folder_path if headless else self.xmltv_folder_path.get()
            m3u_files = [f for f in os.listdir(m3u_path) if f.lower().endswith(('.m3u', '.m3u8'))]
            if not m3u_files:
                msg = f"No .m3u or .m3u8 files found in '{m3u_path}'"
                logger.warning(msg)
                if not headless: self.master.after(0, lambda: messagebox.showinfo("No M3U Files", msg))
                return
            for f in m3u_files:
                channels = core.parse_m3u(os.path.join(m3u_path, f))
                if selected_categories:
                    channels = [ch for ch in channels if ch.get('group_title', '') in selected_categories]
                self.m3u_channels.extend(channels)
            logger.info(f"Total M3U channels loaded: {len(self.m3u_channels)}")

            xmltv_files = [f for f in os.listdir(xmltv_path) if f.lower().endswith(('.xmltv', '.xml', '.gz'))]
            if not xmltv_files:
                msg = f"No .xmltv, .xml, or .gz files found in '{xmltv_path}'"
                logger.warning(msg)
                if not headless: self.master.after(0, lambda: messagebox.showinfo("No XMLTV Files", msg))
                return
            for f in xmltv_files: self.xmltv_channels.extend(core.parse_xmltv(os.path.join(xmltv_path, f)))
            logger.info(f"Total XMLTV channels loaded: {len(self.xmltv_channels)}")

            if not headless: self.master.after(0, self.progressbar.config, {'mode': 'determinate', 'maximum': len(self.m3u_channels), 'value': 0})
            
            self.processed_channels_data = core.auto_match_channels(
                self.m3u_channels, self.xmltv_channels,
                self.fuzzy_threshold if headless else self.fuzzy_threshold.get(),
                self.preserve_matches_headless if headless else self.preserve_existing_matches.get(),
                progress_callback=lambda val: self.master.after(0, self.progressbar.config, {'value': val}) if not headless else None
            )

            if not headless:
                self.master.after(0, lambda: messagebox.showinfo("Load Complete", f"Loaded {len(self.m3u_channels)} M3U and {len(self.xmltv_channels)} XMLTV channels."))
        except Exception as e:
            logger.critical(f"Unexpected error during loading: {e}", exc_info=True)
            if not headless: self.master.after(0, lambda: messagebox.showerror("Loading Error", f"An unexpected error occurred: {e}"))
        finally:
            if not headless:
                self.master.after(0, self._set_loading_state, False)
                self.master.after(0, self._refresh_treeview)

    def _start_rematch(self):
        if not self.m3u_channels or not self.xmltv_channels:
            messagebox.showwarning("No Data", "Please load M3U and XMLTV channels first.")
            return
        self._set_loading_state(True, "Re-running auto-match...")
        threading.Thread(target=self._rematch_thread, daemon=True).start()

    def _rematch_thread(self):
        try:
            self.master.after(0, self.progressbar.config, {'mode': 'determinate', 'maximum': len(self.m3u_channels), 'value': 0})
            self.processed_channels_data = core.auto_match_channels(
                self.m3u_channels, self.xmltv_channels,
                self.fuzzy_threshold.get(),
                self.preserve_existing_matches.get(),
                progress_callback=lambda val: self.master.after(0, self.progressbar.config, {'value': val})
            )
            self.master.after(0, lambda: messagebox.showinfo("Re-match Complete", "Channels re-matched."))
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Re-match Error", f"Error during re-matching: {e}"))
        finally:
            self.master.after(0, self._set_loading_state, False)
            self.master.after(0, self._refresh_treeview)

    def _start_download_sources(self):
        try:
            if not os.path.exists(SOURCES_FILE):
                with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
                    json.dump({"M3U": [], "EPG": []}, f, indent=4)
                logger.warning(f"'{SOURCES_FILE}' not found, created an empty one.")
            with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                sources_data = json.load(f)
            
            clean_folders = messagebox.askyesno("Clean Folders?", "Do you want to delete all existing files in the target folders before downloading?")
            
            self._set_loading_state(True, "Downloading sources...")
            logger.info(f"Starting download thread with source file: {os.path.abspath(SOURCES_FILE)}")
            threading.Thread(target=self._download_thread, args=(sources_data, clean_folders), daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", f"Could not read or process '{SOURCES_FILE}': {e}")
            logger.error(f"Failed to start download process: {e}", exc_info=True)

    def _download_thread(self, sources_data, clean_folders, headless=False):
        m3u_folder = self.m3u_folder_path if headless else self.m3u_folder_path.get()
        xmltv_folder = self.xmltv_folder_path if headless else self.xmltv_folder_path.get()
        if not m3u_folder or not xmltv_folder:
            msg = "M3U and XMLTV destination folders must be set."
            logger.error(msg)
            if not headless:
                self.master.after(0, lambda: messagebox.showerror("Error", msg))
                self.master.after(0, self._set_loading_state, False)
            return

        try:
            m3u_download_successful, download_count = core.download_sources(sources_data, m3u_folder, xmltv_folder, clean_folders)

            if m3u_download_successful:
                if not headless:
                    self.master.after(0, lambda: messagebox.showinfo("Downloads Complete", f"Finished processing {download_count} files. Now loading channels..."))
                    self.master.after(0, self._start_load_channels)
                else:
                    logger.info(f"Finished processing {download_count} files. Now loading channels...")
                    self._load_and_process_channels_thread(headless=True)
            else:
                logger.error("Download thread complete, but no M3U files were downloaded. Aborting channel load.")
                if not headless:
                    self.master.after(0, lambda: messagebox.showerror("Download Failed", "No M3U files were successfully downloaded. Please check sources.json and logs."))
                    self.master.after(0, self._set_loading_state, False)

        except Exception as e:
            logger.critical(f"A critical error occurred in the download thread: {e}", exc_info=True)
            if not headless: self.master.after(0, self._set_loading_state, False)

    def _browse_folder(self, path_var):
        folder = filedialog.askdirectory()
        if folder: path_var.set(folder)

    def _set_loading_state(self, is_loading, message=""):
        state = "disabled" if is_loading else "normal"
        widgets_to_toggle = [
            getattr(self, name) for name in dir(self) 
            if isinstance(getattr(self, name, None), (tk.Button, tk.Scale, tk.Entry, tk.Checkbutton))
        ]
        for widget in widgets_to_toggle:
            if widget: widget.config(state=state)
        
        if is_loading:
            self.loading_label.config(text=message)
            self.loading_label.pack(in_=self.log_display_frame, side="top", pady=5)
            self.progressbar.pack(in_=self.log_display_frame, side="top", fill="x", padx=10, pady=5)
            self.progressbar.start()
        else:
            self.loading_label.pack_forget()
            self.progressbar.pack_forget()
            self.progressbar.stop()
            if self.processed_channels_data:
                for widget_name in ['auto_match_button', 'threshold_slider', 'generate_m3u_button', 'generate_xmltv_button', 'play_stream_button']:
                    widget = getattr(self, widget_name, None)
                    if widget: widget.config(state="normal")

    def _handle_match_filter_toggle(self, changed_filter):
        if changed_filter == "matched" and self.show_only_matched.get():
            self.show_only_unmatched.set(False)
        elif changed_filter == "unmatched" and self.show_only_unmatched.get():
            self.show_only_matched.set(False)
        self._refresh_treeview()

    def _on_threshold_change(self, value=None):
        threshold = self.fuzzy_threshold.get()
        for item_data in self.processed_channels_data:
            item_data['selected'] = (item_data['score'] >= threshold)
        self._refresh_treeview()

    def _on_filter_change(self, event=None):
        if self._filter_timer: self.master.after_cancel(self._filter_timer)
        self._filter_timer = self.master.after(300, self._refresh_treeview)

    def _refresh_treeview(self):
        logger.info("Refreshing Treeview display.")
        
        # Clear existing items efficiently
        for iid in self.tree.get_children(): 
            self.tree.delete(iid)
        
        if not self.processed_channels_data:
            logger.warning("No processed channels data to display.")
            self._update_match_counts()
            return
            
        threshold = self.fuzzy_threshold.get()
        m3u_filter = self.filter_m3u_name.get().lower().strip()
        xmltv_filter = self.filter_xmltv_name.get().lower().strip()
        
        logger.info(f"Starting treeview refresh with {len(self.processed_channels_data)} total channels.")
        
        # Apply filters
        filtered_data = self.processed_channels_data
        if self.show_only_matched.get():
            filtered_data = [d for d in filtered_data if d['xmltv_match'] and d['score'] >= threshold]
        if self.show_only_unmatched.get():
            filtered_data = [d for d in filtered_data if not d['xmltv_match'] or d['score'] < threshold]
        if self.show_only_selected.get():
            filtered_data = [d for d in filtered_data if d['selected']]
        if m3u_filter:
            filtered_data = [d for d in filtered_data if m3u_filter in d['m3u_data']['name'].lower()]
        if xmltv_filter:
            filtered_data = [d for d in filtered_data if d['xmltv_match'] and xmltv_filter in d['xmltv_match']['display_name'].lower()]
        
        logger.info(f"After filtering: {len(filtered_data)} channels to display.")
        
        # Sort data
        def get_sort_value(item_data):
            col = self._tree_sort_column
            if col == "row_number": return channel_to_idx.get(id(item_data), 0)  # Sort by original position
            if col == "selected": return item_data['selected']
            if col == "m3u_name": return item_data['m3u_data']['name'].lower()
            if col == "m3u_group": return item_data['m3u_data'].get('group_title', '').lower()
            if col == "xmltv_name": return item_data['xmltv_match']['display_name'].lower() if item_data['xmltv_match'] else ''
            if col == "match_score": return item_data['score']
            return ""

        # Build the lookup dictionary before sorting (need it for row_number sorting)
        channel_to_idx = {id(item_data): idx for idx, item_data in enumerate(self.processed_channels_data)}
        sorted_data = sorted(filtered_data, key=get_sort_value, reverse=self._tree_sort_reverse)
        
        # For large datasets, limit display to avoid UI freezing
        max_display_items = 10000  # Configurable limit
        if len(sorted_data) > max_display_items:
            logger.warning(f"Large dataset detected ({len(sorted_data)} items). Displaying first {max_display_items} items only.")
            sorted_data = sorted_data[:max_display_items]
        
        # Batch insert items for better performance
        logger.info(f"Inserting {len(sorted_data)} items into treeview...")
        
        try:
            for i, item_data in enumerate(sorted_data):
                if i % 1000 == 0 and i > 0:
                    logger.info(f"Inserted {i}/{len(sorted_data)} items...")
                    
                original_idx = channel_to_idx.get(id(item_data), -1)
                if original_idx == -1:
                    logger.error(f"Could not find original index for item {i}")
                    continue
                    
                row_number = original_idx + 1  # Display as 1-based numbering
                selected_status = "✓" if item_data['selected'] else "✗"
                m3u_group = item_data['m3u_data'].get('group_title', '')
                m3u_name = item_data['m3u_data']['name']
                xmltv_name = item_data['xmltv_match']['display_name'] if item_data['xmltv_match'] else "--- No Match ---"
                score = item_data['score']
                tags = ('high_match',) if score >= 95 else ('good_match',) if score >= threshold else ('low_match',) if score > 0 else ('no_match',)
                
                self.tree.insert("", "end", iid=str(original_idx), values=(row_number, selected_status, m3u_group, m3u_name, xmltv_name, score), tags=tags)
                
            logger.info(f"Successfully inserted {len(sorted_data)} items into treeview.")
            
        except Exception as e:
            logger.error(f"Error during treeview population: {e}", exc_info=True)
        
        self._update_match_counts()

    def _sort_treeview_column(self, col):
        if col == self._tree_sort_column:
            self._tree_sort_reverse = not self._tree_sort_reverse
        else:
            self._tree_sort_column = col
            self._tree_sort_reverse = False
        self._refresh_treeview()
        for column_id in self.tree['columns']:
            self.tree.heading(column_id, text=self.tree.heading(column_id, "text").replace(" ↑", "").replace(" ↓", ""))
        arrow = " ↑" if not self._tree_sort_reverse else " ↓"
        self.tree.heading(col, text=self.tree.heading(col, "text") + arrow)

    def _on_tree_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id and self.tree.identify_column(event.x) == '#2':  # Updated to column #2 (selected column)
            idx = int(item_id)
            self.processed_channels_data[idx]['selected'] = not self.processed_channels_data[idx]['selected']
            self.tree.set(item_id, "selected", "✓" if self.processed_channels_data[idx]['selected'] else "✗")
            self._update_match_counts()

    def _toggle_select_all(self):
        displayed_iids = self.tree.get_children()
        if not displayed_iids: return
        all_selected = all(self.processed_channels_data[int(iid)]['selected'] for iid in displayed_iids)
        new_status = not all_selected
        for iid in displayed_iids:
            self.processed_channels_data[int(iid)]['selected'] = new_status
            self.tree.set(iid, "selected", "✓" if new_status else "✗")
        self._update_match_counts()

    def _on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        visible_iids = self.tree.get_children()
        if not visible_iids: return

        try:
            start_pos_in_visible = visible_iids.index(item_id)
        except ValueError:
            logger.error("Clicked item not found in the visible tree items. Cannot open manual mapper.")
            return

        visible_channels_data = [self.processed_channels_data[int(iid)] for iid in visible_iids]

        def manual_match_callback(pos_in_visible, xmltv_match, score):
            original_iid_str = visible_iids[pos_in_visible]
            original_idx = int(original_iid_str)
            
            self.processed_channels_data[original_idx]['xmltv_match'] = xmltv_match
            self.processed_channels_data[original_idx]['score'] = score
            self.processed_channels_data[original_idx]['selected'] = bool(xmltv_match)
            
            new_status = "✓" if bool(xmltv_match) else "✗"
            new_xmltv_name = xmltv_match['display_name'] if xmltv_match else "--- No Match ---"
            self.tree.set(original_iid_str, "selected", new_status)
            self.tree.set(original_iid_str, "xmltv_name", new_xmltv_name)
            self.tree.set(original_iid_str, "match_score", score)
            self._update_match_counts()

        ManualMatchDialog(
            self.master,
            visible_channels_data,
            start_pos_in_visible,
            self.xmltv_channels,
            manual_match_callback,
            self.dark_mode
        )

    def _on_tree_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return

        if item_id not in self.tree.selection():
            self.tree.selection_set(item_id)

        selected_items = self.tree.selection()
        num_selected = len(selected_items)
        if num_selected == 0: return

        context_menu = tk.Menu(self.master, tearoff=0)

        if num_selected == 1:
            idx = int(item_id)
            m3u_name = self.processed_channels_data[idx]['m3u_data']['name']
            context_menu.add_command(label=f"Manually Match '{m3u_name}'...", command=lambda: self._on_tree_double_click(event))
            unmatch_state = "normal" if self.processed_channels_data[idx]['xmltv_match'] else "disabled"
            context_menu.add_command(label=f"Unmatch '{m3u_name}'", command=self._unmatch_selected_channel, state=unmatch_state)
        else:
            context_menu.add_command(label=f"Unmatch {num_selected} selected channels", command=self._unmatch_selected_channel)
        
        context_menu.tk_popup(event.x_root, event.y_root)

    def _unmatch_selected_channel(self):
        selected_items = self.tree.selection()
        if not selected_items: return
        if messagebox.askyesno("Confirm Unmatch", f"Unmatch {len(selected_items)} selected channel(s)?"):
            for item_id in selected_items:
                idx = int(item_id)
                self.processed_channels_data[idx]['xmltv_match'] = None
                self.processed_channels_data[idx]['score'] = 0
                self.processed_channels_data[idx]['selected'] = False
            self._refresh_treeview()

    def _open_remove_category_dialog(self):
        if not self.m3u_channels:
            messagebox.showwarning("No Data", "Load M3U channels first.")
            return
        unique_groups = sorted(list(set(ch.get('group_title', '') for ch in self.m3u_channels)))
        dialog = RemoveCategoryDialog(self.master, unique_groups, self.dark_mode)
        if dialog.groups_to_remove:
            self.m3u_channels = [ch for ch in self.m3u_channels if ch.get('group_title', '') not in dialog.groups_to_remove]
            self.processed_channels_data = [d for d in self.processed_channels_data if d['m3u_data'].get('group_title', '') not in dialog.groups_to_remove]
            self._refresh_treeview()
            messagebox.showinfo("Categories Removed", f"Removed channels from {len(dialog.groups_to_remove)} categories.")

    def _save_session(self):
        if not self.processed_channels_data:
            messagebox.showwarning("No Data", "No channel data to save.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Session", "*.json")])
        if not filepath: return
        serializable_data = []
        for item in self.processed_channels_data:
            s_item = {'m3u_data': item['m3u_data'], 'score': item['score'], 'selected': item['selected']}
            s_item['xmltv_match'] = {'id': item['xmltv_match']['id'], 'display_name': item['xmltv_match']['display_name']} if item['xmltv_match'] else None
            serializable_data.append(s_item)
        with open(filepath, 'w', encoding='utf-8') as f: json.dump(serializable_data, f, indent=2)
        messagebox.showinfo("Session Saved", f"Session saved to '{os.path.basename(filepath)}'.")

    def _load_session(self):
        filepath = filedialog.askopenfilename(defaultextension=".json", filetypes=[("JSON Session", "*.json")])
        if not filepath: return
        self._set_loading_state(True, "Loading session...")
        threading.Thread(target=self._load_session_thread, args=(filepath,), daemon=True).start()

    def _load_session_thread(self, filepath, headless=False):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: loaded_data = json.load(f)
            
            xmltv_folder = self.xmltv_folder_path if headless else self.xmltv_folder_path.get()
            if os.path.isdir(xmltv_folder):
                xmltv_files = [f for f in os.listdir(xmltv_folder) if f.lower().endswith(('.xmltv', '.xml', '.gz'))]
                for f in xmltv_files: self.xmltv_channels.extend(core.parse_xmltv(os.path.join(xmltv_folder, f)))
                logger.info(f"Loaded {len(self.xmltv_channels)} XMLTV channels to reconstruct session.")
                _, _, self._xmltv_channels_by_id = core.build_xmltv_indices(self.xmltv_channels)
            else:
                logger.warning("XMLTV folder not found. Matches will be by ID/Name only, EPG generation may fail.")
                self._xmltv_channels_by_id = {}

            self.processed_channels_data = []
            for item in loaded_data:
                match_info = item.get('xmltv_match')
                reconstructed_match = None
                if match_info and match_info.get('id'):
                    reconstructed_match = self._xmltv_channels_by_id.get(match_info['id'], {'id': match_info['id'], 'display_name': match_info['display_name'], 'element': None})
                self.processed_channels_data.append({'m3u_data': item['m3u_data'], 'xmltv_match': reconstructed_match, 'score': item['score'], 'selected': item['selected']})
            
            self.m3u_channels = [d['m3u_data'] for d in self.processed_channels_data]
            msg = f"Loaded {len(self.processed_channels_data)} channels from session."
            logger.info(msg)
            if not headless: self.master.after(0, lambda: messagebox.showinfo("Session Loaded", msg))
        except Exception as e:
            logger.error(f"Failed to load session: {e}", exc_info=True)
            if not headless: self.master.after(0, lambda: messagebox.showerror("Error Loading Session", f"Failed to load session: {e}"))
        finally:
            if not headless:
                self.master.after(0, self._set_loading_state, False)
                self.master.after(0, self._refresh_treeview)

    def _generate_m3u_gui(self):
        """Generate M3U file in output folder from config."""
        output_folder = self.output_m3u_folder or self.m3u_folder_path.get()
        os.makedirs(output_folder, exist_ok=True)
        output_path = os.path.join(output_folder, "matched_channels.m3u")
        try:
            count = core.generate_m3u(self.processed_channels_data, output_path)
            messagebox.showinfo("M3U Generated", f"Generated M3U file with {count} channels at {output_path}")
            logger.info(f"Generated M3U file with {count} channels at {output_path}")
        except Exception as e:
            logger.error(f"Failed to generate M3U file: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to generate M3U file: {e}")

    def _generate_xmltv_gui(self):
        """Generate XMLTV file in output folder from config."""
        output_folder = self.output_xmltv_folder or self.xmltv_folder_path.get()
        os.makedirs(output_folder, exist_ok=True)
        output_path = os.path.join(output_folder, "matched_guide.xml")
        try:
            count, program_count = core.generate_xmltv(self.processed_channels_data, self.xmltv_folder_path.get(), output_path)
            messagebox.showinfo("XMLTV Generated", f"Generated XMLTV file with {count} channels and {program_count} programs at {output_path}")
            logger.info(f"Generated XMLTV file with {count} channels and {program_count} programs at {output_path}")
        except Exception as e:
            logger.error(f"A critical error occurred during XMLTV file writing: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to generate XMLTV file: {e}")

    def _play_stream(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a channel to play.")
            return
        if len(selected) > 1:
            messagebox.showwarning("Multiple Selections", "Please select only one channel to play.")
            return
        idx = int(selected[0])
        url = self.processed_channels_data[idx]['m3u_data']['url']
        platform_defaults = self._get_platform_defaults()
        player = self.config.get('Settings', 'player_path', fallback=platform_defaults.get('player_path', 'vlc'))
        try:
            subprocess.Popen([player, url])
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch player '{player}': {e}")

    def _update_match_counts(self):
        if not self.processed_channels_data:
            self.match_count_label.config(text="ℹ️ Load channels to see statistics.")
            return
            
        total = len(self.processed_channels_data)
        threshold = self.fuzzy_threshold.get()
        matched = sum(1 for item in self.processed_channels_data if item['xmltv_match'] and item['score'] >= threshold)
        selected = sum(1 for item in self.processed_channels_data if item['selected'])
        displayed = len(self.tree.get_children())
        
        # Check if we're showing a limited view
        limit_warning = ""
        if displayed == 10000 and total > 10000:
            limit_warning = " ⚠️ (Showing first 10,000 of filtered results)"
            
        self.match_count_label.config(text=f"Total: {total} | Matched: {matched} | Unmatched: {total - matched} | Selected for Output: {selected} | Displayed: {displayed}{limit_warning}")

    def run_headless(self, args):
        """Runs the application in headless mode based on CLI arguments."""
        if args.overwrite_matches:
            self.preserve_matches_headless = False
            logger.info("Overwrite matches flag is set. All channels will be re-matched.")

        if args.m3u_folder:
            self.m3u_folder_path = args.m3u_folder
        if args.xmltv_folder:
            self.xmltv_folder_path = args.xmltv_folder
        if args.threshold is not None:
            self.fuzzy_threshold = args.threshold

        include_groups = None
        # Check CLI first
        if hasattr(args, 'include_groups') and args.include_groups:
            include_groups = [g.strip() for g in args.include_groups.split(',') if g.strip()]
            logger.info(f"Filtering M3U channels to include only groups: {include_groups}")
        # If not set by CLI, check sources.json for included_groups
        elif os.path.exists(SOURCES_FILE):
            try:
                with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                    sources_data = json.load(f)
                if 'included_groups' in sources_data and isinstance(sources_data['included_groups'], list):
                    include_groups = [g for g in sources_data['included_groups'] if isinstance(g, str) and g.strip()]
                    if include_groups:
                        logger.info(f"Loaded included_groups from sources.json: {include_groups}")
            except Exception as e:
                logger.warning(f"Could not read included_groups from sources.json: {e}")

        if args.load_session:
            if args.download:
                logger.info("Downloading sources before loading session...")
                try:
                    if not os.path.exists(SOURCES_FILE):
                        logger.error(f"Sources file not found: {SOURCES_FILE}")
                        return
                    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                        sources_data = json.load(f)
                    self._download_thread(sources_data, args.clean_folders, headless=True)
                except Exception as e:
                    logger.error(f"Failed to process sources file: {e}", exc_info=True)
                    return
            logger.info(f"Loading session from: {args.load_session}")
            self._load_session_thread(args.load_session, headless=True)
        else:
            if args.download:
                try:
                    if not os.path.exists(SOURCES_FILE):
                        logger.error(f"Sources file not found: {SOURCES_FILE}")
                        return
                    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
                        sources_data = json.load(f)
                    self._download_thread(sources_data, args.clean_folders, headless=True)
                except Exception as e:
                    logger.error(f"Failed to process sources file: {e}", exc_info=True)
                    return
            else:
                self._load_and_process_channels_thread(headless=True)

            # Filter m3u_channels by include_groups if specified
            if include_groups is not None:
                before_count = len(self.m3u_channels)
                self.m3u_channels = [ch for ch in self.m3u_channels if ch.get('group_title', '') in include_groups]
                after_count = len(self.m3u_channels)
                logger.info(f"Filtered M3U channels from {before_count} to {after_count} by include_groups.")

            threshold = self.fuzzy_threshold
            for item_data in self.processed_channels_data:
                item_data['selected'] = (item_data['score'] >= threshold)

            selected_count = sum(1 for d in self.processed_channels_data if d['selected'])
            logger.info(f"{selected_count} channels selected based on threshold >= {threshold}")

        if args.output_m3u:
            core.generate_m3u(self.processed_channels_data, args.output_m3u)

        if args.output_xmltv:
            core.generate_xmltv(self.processed_channels_data, self.xmltv_folder_path, args.output_xmltv)

        logger.info("Headless run finished.")

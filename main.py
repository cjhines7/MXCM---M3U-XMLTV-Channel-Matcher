import tkinter as tk
import argparse
import os
from app import MXMMApp
from utils import logger

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(description="M3U/XMLTV Channel Matcher. Run without arguments for GUI.")
    parser.add_argument('--no-gui', action='store_true', help='Run in headless mode without GUI.')
    parser.add_argument('--download', action='store_true', help='Download sources from sources.json before processing.')
    parser.add_argument('--clean-folders', action='store_true', help='Delete existing files in target folders before downloading. Use with --download.')
    parser.add_argument('--load-session', type=str, help='Load a saved session file (.json) to generate output without re-matching.')
    parser.add_argument('--m3u-folder', type=str, help='Path to the M3U folder (overrides config).')
    parser.add_argument('--xmltv-folder', type=str, help='Path to the XMLTV folder (overrides config).')
    parser.add_argument('--output-m3u', type=str, help='File path to save the generated M3U file.')
    parser.add_argument('--output-xmltv', type=str, help='File path to save the generated XMLTV file.')
    parser.add_argument('--threshold', type=int, help='Fuzzy match threshold (0-100, overrides config).')
    parser.add_argument('--overwrite-matches', action='store_true', help='Force re-matching for all channels, ignoring existing tvg-id values.')
    parser.add_argument('--include-groups', type=str, help='Comma-separated list of M3U group names to include (others will be excluded).')
    parser.add_argument('--dark-mode', action='store_true', help='Enable dark mode theme for the GUI.')
    
    args = parser.parse_args()

    is_headless = args.no_gui or args.download or args.output_m3u or args.output_xmltv or args.load_session

    if is_headless:
        logger.info("Starting application in headless mode.")
        app = MXMMApp()
        app.run_headless(args)
    else:
        logger.info("Starting application in GUI mode.")
        root = tk.Tk()
        app = MXMMApp(root, dark_mode=args.dark_mode)
        root.mainloop()

if __name__ == "__main__":
    main()

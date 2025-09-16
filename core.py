import os
import re
from lxml import etree as ET
import gzip
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import requests
import datetime
import shutil
import logging

from utils import logger
import copy

def normalize_name(name):
    """Normalize channel names for fuzzy matching."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s]', '', name)
    return re.sub(r'\s+', ' ', name).strip()



def parse_m3u(filepath):
    """Parses an M3U file to extract channel data."""
    channels = []
    open_func = gzip.open if filepath.lower().endswith('.gz') else open
    try:
        with open_func(filepath, 'rt', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        entries = re.findall(r'(#EXTINF:.*?\n.*?)(?=\n#EXTINF:|\Z)', content, re.DOTALL)
        for entry in entries:
            extinf_line, url_line = entry.split('\n', 1)
            name_match = re.search(r'tvg-name="([^"]+)"', extinf_line)
            channel_name = name_match.group(1).strip() if name_match else extinf_line.split(',')[-1].strip()
            tvg_id_match = re.search(r'tvg-id="([^"]+)"', extinf_line)
            tvg_id = tvg_id_match.group(1).strip() if tvg_id_match else ""
            group_title_match = re.search(r'group-title="([^"]+)"', extinf_line)
            group_title = group_title_match.group(1).strip() if group_title_match else ""
            tvg_logo_match = re.search(r'tvg-logo="([^"]+)"', extinf_line)
            tvg_logo = tvg_logo_match.group(1).strip() if tvg_logo_match else ""
            channels.append({
                'name': channel_name, 'url': url_line.strip(), 'original_extinf': extinf_line,
                'tvg_id': tvg_id, 'group_title': group_title, 'tvg_logo': tvg_logo,
                'source_file': os.path.basename(filepath)
            })
        return channels
    except Exception as e:
        logger.error(f"Failed to parse M3U file {filepath}: {e}", exc_info=True)
        raise

def parse_xmltv(filepath):
    """Parses an XMLTV file to extract channel data."""
    channels = []
    try:
        open_func = gzip.open if filepath.lower().endswith('.gz') else open
        with open_func(filepath, 'rb') as f:
            tree = ET.parse(f)
        root = tree.getroot()
        for channel_elem in root.findall('channel'):
            channel_id = channel_elem.get('id')
            display_names = [dn.text.strip() for dn in channel_elem.findall('display-name') if dn.text]
            main_display_name = display_names[0] if display_names else ""
            icon_elem = channel_elem.find('icon')
            icon_url = icon_elem.get('src') if icon_elem is not None else ""
            channels.append({
                'id': channel_id, 'display_name': main_display_name,
                'all_display_names': display_names, 'element': channel_elem,
                'icon': icon_url, 'source_file': os.path.basename(filepath)
            })
        return channels
    except Exception as e:
        logger.error(f"Failed to parse XMLTV file {filepath}: {e}", exc_info=True)
        raise

def build_xmltv_indices(xmltv_channels):
    """Builds lookup dictionaries for XMLTV channels to optimize matching."""
    logger.info("Building XMLTV token and ID inverted indices...")
    token_index = {}
    channels_by_display_name = {normalize_name(ch['display_name']): ch for ch in xmltv_channels}
    channels_by_id = {ch['id']: ch for ch in xmltv_channels if 'id' in ch}
    for xml_ch in xmltv_channels:
        original_display_name = xml_ch['display_name']
        normalized_display_name = normalize_name(original_display_name)
        for token in normalized_display_name.split():
            if len(token) > 1:
                token_index.setdefault(token, set()).add(original_display_name)
    logger.info(f"XMLTV token inverted index built with {len(token_index)} unique tokens.")
    logger.info(f"XMLTV ID lookup built with {len(channels_by_id)} unique IDs.")
    return token_index, channels_by_display_name, channels_by_id

def auto_match_channels(m3u_channels, xmltv_channels, threshold, preserve_existing, progress_callback=None):
    """Performs optimized fuzzy auto-matching between M3U and XMLTV channels."""
    if preserve_existing:
        logger.info("Starting auto-matching process. Prioritizing existing tvg-id matches.")
    else:
        logger.info("Starting auto-matching process. Re-matching all channels.")

    processed_channels_data = []
    if not xmltv_channels:
        logger.warning("No XMLTV channels loaded for auto-matching. Skipping matching.")
        return []

    token_index, channels_by_display_name, channels_by_id = build_xmltv_indices(xmltv_channels)
    
    total_m3u = len(m3u_channels)
    all_xmltv_original_display_names = [ch['display_name'] for ch in xmltv_channels]

    for i, m3u_channel in enumerate(m3u_channels):
        if progress_callback:
            progress_callback(i + 1)

        tvg_id = m3u_channel.get('tvg_id', '').strip()
        
        best_match_xmltv, match_score = None, 0
        
        if preserve_existing and tvg_id and tvg_id in channels_by_id:
            best_match_xmltv = channels_by_id[tvg_id]
            match_score = 100
            logger.debug(f"Found existing match for '{m3u_channel['name']}' using tvg-id: '{tvg_id}'. Locking match.")
        else:
            if not (i % 100):
                logger.debug(f"Fuzzy matching progress: {i}/{total_m3u} M3U channels processed ('{m3u_channel['name']}').")
            
            m3u_name = m3u_channel['name']
            normalized_m3u_name = normalize_name(m3u_name)

            if normalized_m3u_name in channels_by_display_name:
                best_match_xmltv = channels_by_display_name[normalized_m3u_name]
                match_score = 100
            else:
                m3u_tokens = normalized_m3u_name.split()
                candidate_names = set()
                for token in m3u_tokens:
                    if len(token) > 1:
                        candidate_names.update(token_index.get(token, set()))
                
                choices = list(candidate_names) if candidate_names else all_xmltv_original_display_names
                if choices:
                    best_match_tuple = process.extractOne(m3u_name, choices, scorer=fuzz.ratio)
                    if best_match_tuple:
                        matched_name, match_score = best_match_tuple
                        best_match_xmltv = channels_by_display_name.get(normalize_name(matched_name))

        processed_channels_data.append({
            'm3u_data': m3u_channel, 
            'xmltv_match': best_match_xmltv,
            'score': match_score, 
            'selected': (match_score >= threshold)
        })
    logger.info(f"Auto-matching completed for {total_m3u} M3U channels.")
    return processed_channels_data

def download_or_copy(url, dest_folder, file_type):
    """Downloads a file from a URL or copies a local file."""
    try:
        base_filename = os.path.basename(url).split('?')[0].split('#')[0]
        if not base_filename: 
            base_filename = f"{file_type}_download_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.file"
        
        filename, extension = os.path.splitext(base_filename)
        filepath = os.path.join(dest_folder, base_filename)
        counter = 1
        while os.path.exists(filepath):
            new_filename = f"{filename}-{counter}{extension}"
            filepath = os.path.join(dest_folder, new_filename)
            counter += 1
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        if url.lower().startswith('http'):
            logger.info(f"Downloading {file_type}: {url} to {filepath}")
            response = requests.get(url, stream=True, timeout=60, headers=headers)
            response.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
            logger.info(f"Successfully downloaded {os.path.basename(filepath)}")
        elif os.path.exists(url):
            logger.info(f"Copying local {file_type}: {url} to {filepath}")
            shutil.copy(url, filepath)
            logger.info(f"Successfully copied {os.path.basename(filepath)}")
        else:
            logger.error(f"Invalid source: '{url}' is not a valid URL or existing file path.")
            return False
        return True
    except Exception as e:
        logger.error(f"Failed to process {file_type} from {url}: {e}", exc_info=True)
        return False

def download_sources(sources_data, m3u_folder, xmltv_folder, clean_folders):
    """Performs the actual downloading of files."""
    if clean_folders:
        logger.info("User opted to clean target folders before download.")
        for folder in [m3u_folder, xmltv_folder]:
            logger.info(f"Cleaning folder: {folder}")
            if os.path.isdir(folder):
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                            logger.info(f"Deleted old file: {file_path}")
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                            logger.info(f"Deleted old directory: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete {file_path}. Reason: {e}")

    download_count = 0
    m3u_download_successful = False
    
    for url in sources_data.get('M3U', []):
        logger.info(f"Starting download for M3U: {url}")
        if download_or_copy(url, m3u_folder, "M3U"):
            m3u_download_successful = True
            download_count += 1
        else:
            logger.error(f"Failed to download M3U: {url}")
    for url in sources_data.get('EPG', []):
        logger.info(f"Starting download for EPG: {url}")
        if download_or_copy(url, xmltv_folder, "EPG"):
            download_count += 1
        else:
            logger.error(f"Failed to download EPG: {url}")

    return m3u_download_successful, download_count

def generate_m3u(processed_channels_data, filepath):
    """Generates an M3U file from the processed channel data."""
    count = 0
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for item in processed_channels_data:
            if item['selected'] and item['xmltv_match']:
                m3u, xmltv = item['m3u_data'], item['xmltv_match']
                extinf = m3u['original_extinf']
                new_extinf = re.sub(r'tvg-id="[^"]*"', f'tvg-id="{xmltv["id"]}"', extinf)
                if f'tvg-id="{xmltv["id"]}"' not in new_extinf:
                    new_extinf = re.sub(r'(#EXTINF:[-]?\d+)', rf'\1 tvg-id="{xmltv["id"]}"', new_extinf, 1)
                last_comma = new_extinf.rfind(',')
                if last_comma != -1: new_extinf = new_extinf[:last_comma+1] + xmltv['display_name']
                f.write(new_extinf.strip() + "\n")
                f.write(m3u['url'] + "\n")
                count += 1
    msg = f"Generated M3U with {count} channels to {filepath}"
    logger.info(msg)
    return count

def generate_xmltv(processed_channels_data, xmltv_folder, filepath):
    """
    Generates a complete XMLTV file using a two-pass approach to ensure EPG data is always included,
    even when loading from a session.
    """
    # --- Pass 1: Collect selected channel IDs and their full XML elements ---
    logger.info("Starting XMLTV generation (Pass 1/2): Collecting channel data...")
    selected_channel_ids = set()
    channel_elements_to_write = {}

    # Re-parse the original XMLTV files to get fresh, complete channel elements
    all_source_xmltv_channels = []
    xmltv_files = [os.path.join(xmltv_folder, f) for f in os.listdir(xmltv_folder) if f.lower().endswith(('.xml', '.gz', '.xmltv'))]
    for xml_file in xmltv_files:
        try:
            all_source_xmltv_channels.extend(parse_xmltv(xml_file))
        except Exception as e:
            logger.error(f"Skipping file due to parsing error: {xml_file} - {e}")
            
    full_channel_data_map = {ch['id']: ch['element'] for ch in all_source_xmltv_channels if 'element' in ch and ch.get('id')}

    for item in processed_channels_data:
        if item['selected'] and item.get('xmltv_match'):
            channel_id = item['xmltv_match'].get('id')
            if channel_id:
                selected_channel_ids.add(channel_id)
                # Ensure we have the full, fresh element, not a potentially stale one from a loaded session
                if channel_id in full_channel_data_map and channel_id not in channel_elements_to_write:
                    channel_elements_to_write[channel_id] = full_channel_data_map[channel_id]

    if not selected_channel_ids:
        logger.warning("No channels were selected for XMLTV generation. Aborting.")
        return 0, 0

    logger.info(f"Collected {len(channel_elements_to_write)} unique channel elements to write.")

    # --- Pass 2: Stream-write the new XMLTV file ---
    logger.info("Starting XMLTV generation (Pass 2/2): Writing channel and programme data...")
    program_count = 0
    open_func = gzip.open if filepath.lower().endswith('.gz') else open

    try:
        with open_func(filepath, 'wb') as f:
            with ET.xmlfile(f, encoding='utf-8') as xf:
                xf.write_declaration()
                with xf.element("tv", attrib={"generator-info-name": "M3U-XMLTV Matcher"}):
                    # Write all collected channel elements
                    for channel_id in sorted(channel_elements_to_write.keys()):
                        xf.write(channel_elements_to_write[channel_id])

                    # Now, iterate through source files again for programme data
                    logger.info("Writing <programme> elements...")
                    for xml_file in xmltv_files:
                        logger.debug(f"Scanning for programmes in: {os.path.basename(xml_file)}")
                        source_open_func = gzip.open if xml_file.lower().endswith('.gz') else open
                        try:
                            with source_open_func(xml_file, 'rb') as source_f:
                                for event, elem in ET.iterparse(source_f, events=('end',), tag='programme'):
                                    if elem.get('channel') in selected_channel_ids:
                                        xf.write(elem)
                                        program_count += 1
                                    elem.clear() # Crucial for memory management
                        except ET.ParseError as e:
                            logger.error(f"Could not parse {os.path.basename(xml_file)} for programmes, it may be corrupted. Error: {e}")
        
        msg = f"Generated XMLTV with {len(channel_elements_to_write)} channels and {program_count} programs to {filepath}"
        logger.info(msg)
        return len(channel_elements_to_write), program_count

    except Exception as e:
        logger.critical(f"A critical error occurred during XMLTV file writing: {e}", exc_info=True)
        return 0, 0

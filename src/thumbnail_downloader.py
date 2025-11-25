import os
import requests
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

class ThumbnailDownloader:
    BASE_URL = "https://thumbnails.libretro.com"

    def __init__(self, thumbnails_dir, max_workers=5):
        self.thumbnails_dir = thumbnails_dir
        self.max_workers = max_workers
        
        # Setup session with retry
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def download_thumbnail(self, system, game_english_name, game_chinese_name):
        """
        Downloads thumbnails for a single game.
        Returns a list of results (success/fail messages).
        """
        # Thumbnail types
        types = ["Named_Boxarts", "Named_Snaps", "Named_Titles"]
        
        # The filename on the server usually matches the game label in the playlist (English),
        # but with special characters replaced.
        server_filename = self.sanitize_filename(game_english_name) + ".png"
        
        results = []
        for type_name in types:
            url = f"{self.BASE_URL}/{urllib.parse.quote(system)}/{type_name}/{urllib.parse.quote(server_filename)}"
            
            # Target directory
            target_dir = os.path.join(self.thumbnails_dir, system, type_name)
            os.makedirs(target_dir, exist_ok=True)
            
            # Target file path (using Chinese name)
            target_filename = self.sanitize_filename(game_chinese_name) + ".png"
            target_path = os.path.join(target_dir, target_filename)
            
            if os.path.exists(target_path):
                results.append(f"Successfully skipped {type_name}: {game_chinese_name} (已存在)")
                continue

            # print(f"Downloading {type_name} for {game_english_name}...")
            try:
                # Use session with retry
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    with open(target_path, 'wb') as f:
                        f.write(response.content)
                    results.append(f"Successfully downloaded {type_name}: {game_chinese_name}")
                else:
                    results.append(f"Failed {type_name}: HTTP {response.status_code}")
            except Exception as e:
                results.append(f"Error {type_name}: {e}")
        return results

    def download_batch(self, tasks, progress_callback=None):
        """
        Downloads thumbnails for multiple games in parallel.
        tasks: List of tuples (system, game_english_name, game_chinese_name)
        """
        print(f"Starting batch download for {len(tasks)} items with {self.max_workers} threads...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_game = {
                executor.submit(self.download_thumbnail, system, en_name, cn_name): cn_name 
                for system, en_name, cn_name in tasks
            }
            
            completed = 0
            total = len(tasks)
            
            for future in as_completed(future_to_game):
                cn_name = future_to_game[future]
                completed += 1
                try:
                    results = future.result()
                    # Build detailed message
                    success_count = sum(1 for r in results if "Successfully" in r or "已存在" in r)
                    failure_count = len(results) - success_count
                    
                    if success_count > 0 and failure_count == 0:
                        message = f"✓ {cn_name} - 下载成功 ({success_count} 个封面)"
                    elif success_count > 0:
                        message = f"⚠ {cn_name} - 部分成功 ({success_count} 成功, {failure_count} 失败)"
                    else:
                        message = f"✗ {cn_name} - 下载失败"
                    
                    # Print detailed results to console
                    if results:
                        for res in results:
                            print(res)
                    
                    if progress_callback:
                        progress_callback(completed, total, message)
                except Exception as exc:
                    error_msg = f"✗ {cn_name} - 错误: {str(exc)}"
                    print(f"[{completed}/{total}] Error processing {cn_name}: {exc}")
                    if progress_callback:
                        progress_callback(completed, total, error_msg)

    def sanitize_filename(self, name):
        """
        Replaces illegal characters with underscores, matching RetroArch's behavior.
        """
        # List of characters to replace
        illegal_chars = ['&', '*', '/', ':', '<', '>', '?', '\\', '|']
        for char in illegal_chars:
            name = name.replace(char, '_')
        return name

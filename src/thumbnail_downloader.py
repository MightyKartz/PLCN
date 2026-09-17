import os
import requests
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from artwork_resolver import artwork_path, sanitize_filename, valid_image_file, valid_png
from safe_io import atomic_write_bytes, file_lock

class ThumbnailDownloader:
    BASE_URL = "https://thumbnails.libretro.com"
    THUMBNAIL_TYPES = ["Named_Boxarts", "Named_Snaps", "Named_Titles"]

    def __init__(self, thumbnails_dir, max_workers=5):
        self.thumbnails_dir = thumbnails_dir
        self.max_workers = max_workers
        self.cancel_check = None
        
        # Setup session with retry
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    @classmethod
    def empty_summary(cls, item_count=0):
        return {
            "item_count": item_count,
            "types": {
                type_name: {"success": 0, "failed": 0, "skipped": 0}
                for type_name in cls.THUMBNAIL_TYPES
            },
            "total": {"success": 0, "failed": 0, "skipped": 0},
            "details": []
        }

    @classmethod
    def skipped_summary(cls, tasks, reason):
        summary = cls.empty_summary(len(tasks))
        for system, game_english_name, game_chinese_name in tasks:
            for type_name in cls.THUMBNAIL_TYPES:
                detail = {
                    "type": type_name,
                    "game": game_chinese_name,
                    "source": game_english_name,
                    "system": system,
                    "status": "skipped",
                    "message": reason
                }
                summary["types"][type_name]["skipped"] += 1
                summary["total"]["skipped"] += 1
                summary["details"].append(detail)
        return summary

    @classmethod
    def merge_summaries(cls, summaries):
        merged = cls.empty_summary(0)
        for summary in summaries:
            if not summary:
                continue
            merged["item_count"] += summary.get("item_count", 0)
            for type_name in cls.THUMBNAIL_TYPES:
                type_stats = summary.get("types", {}).get(type_name, {})
                for key in ("success", "failed", "skipped"):
                    merged["types"][type_name][key] += type_stats.get(key, 0)
            total_stats = summary.get("total", {})
            for key in ("success", "failed", "skipped"):
                merged["total"][key] += total_stats.get(key, 0)
            merged["details"].extend(summary.get("details", []))
        return merged

    def download_thumbnail(self, system, game_english_name, game_chinese_name):
        # Serialize duplicate target names, including separate PLCN processes.
        target = artwork_path(self.thumbnails_dir, system, game_chinese_name)
        with file_lock(target):
            return self._download_thumbnail_locked(system, game_english_name, game_chinese_name)

    def _download_thumbnail_locked(self, system, game_english_name, game_chinese_name):
        """
        Downloads thumbnails for a single game.
        Returns a list of structured results.
        """
        # The filename on the server usually matches the game label in the playlist (English),
        # but with special characters replaced.
        server_filename = self.sanitize_filename(game_english_name) + ".png"
        
        results = []
        for type_name in self.THUMBNAIL_TYPES:
            if self.cancel_check and self.cancel_check():
                results.append({'type': type_name, 'game': game_chinese_name, 'source': game_english_name,
                                'system': system, 'status': 'skipped', 'reason': 'cancelled', 'message': '已取消'})
                continue
            url = f"{self.BASE_URL}/{urllib.parse.quote(system)}/{type_name}/{urllib.parse.quote(server_filename)}"
            
            # Target directory
            target_dir = os.path.join(self.thumbnails_dir, system, type_name)
            os.makedirs(target_dir, exist_ok=True)
            
            # Target file path (using Chinese name)
            target_filename = self.sanitize_filename(game_chinese_name) + ".png"
            target_path = os.path.join(target_dir, target_filename)
            
            if valid_image_file(target_path):
                results.append({
                    "type": type_name,
                    "game": game_chinese_name,
                    "source": game_english_name,
                    "system": system,
                    "status": "skipped",
                    "message": "已存在",
                    "path": target_path,
                    "url": url
                })
                continue

            # Reuse the canonical English image when renaming a playlist label.
            existing_source = artwork_path(self.thumbnails_dir, system, game_english_name, type_name)
            if existing_source != Path(target_path) and valid_image_file(existing_source):
                atomic_write_bytes(target_path, existing_source.read_bytes())
                results.append({'type': type_name, 'game': game_chinese_name, 'source': game_english_name,
                                'system': system, 'status': 'success', 'reason': 'reused_local',
                                'message': '已复用本地图片', 'path': target_path, 'url': url})
                continue

            # print(f"Downloading {type_name} for {game_english_name}...")
            try:
                # Use session with retry
                matched = None
                response = self.session.get(url, timeout=10)
                if response.status_code == 404 and not (self.cancel_check and self.cancel_check()):
                    from single_artwork import catalog_names
                    from gallery_names import matching_gallery_name
                    matched = matching_gallery_name(system, game_english_name, catalog_names(system, type_name))
                    if matched and matched != game_english_name and not (self.cancel_check and self.cancel_check()):
                        url = f"{self.BASE_URL}/{urllib.parse.quote(system, safe='')}/{type_name}/{urllib.parse.quote(self.sanitize_filename(matched) + '.png', safe='')}"
                        response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    if len(response.content) > 32 * 1024 * 1024 or not valid_png(response.content):
                        results.append({'type': type_name, 'game': game_chinese_name, 'source': game_english_name,
                                        'system': system, 'status': 'failed', 'reason': 'invalid_image',
                                        'message': '服务器返回了无效图片', 'path': target_path, 'url': url})
                        continue
                    atomic_write_bytes(target_path, response.content)
                    results.append({
                        "type": type_name,
                        "game": game_chinese_name,
                        "source": game_english_name,
                        "system": system,
                        "status": "success",
                        "message": "已匹配官方图库并下载" if matched else "下载成功",
                        "gallery_source": matched or game_english_name,
                        "path": target_path,
                        "url": url
                    })
                else:
                    results.append({
                        "type": type_name,
                        "game": game_chinese_name,
                        "source": game_english_name,
                        "system": system,
                        "status": "failed",
                        "reason": 'not_found' if response.status_code == 404 else 'http_error',
                        "message": f"HTTP {response.status_code}",
                        "path": target_path,
                        "url": url
                    })
            except Exception as e:
                results.append({
                    "type": type_name,
                    "game": game_chinese_name,
                    "source": game_english_name,
                    "system": system,
                    "status": "failed",
                    "reason": 'network_or_io_error',
                    "message": str(e),
                    "path": target_path,
                    "url": url
                })
        return results

    def download_batch(self, tasks, progress_callback=None):
        """
        Downloads thumbnails for multiple games in parallel.
        tasks: List of tuples (system, game_english_name, game_chinese_name)
        """
        # A playlist can contain the same ROM more than once. Download shared
        # artwork once; never let different sources race to the same filename.
        grouped = {}
        for task in tasks:
            system, en_name, cn_name = task
            key = str(artwork_path(self.thumbnails_dir, system, cn_name)).casefold()
            grouped.setdefault(key, []).append(task)
        safe_tasks = []
        summary = self.empty_summary(len(grouped))
        for group in grouped.values():
            system, en_name, cn_name = group[0]
            if len({row[1] for row in group}) == 1:
                safe_tasks.append(group[0])
                continue
            for kind in self.THUMBNAIL_TYPES:
                summary['types'][kind]['failed'] += 1
                summary['total']['failed'] += 1
                summary['details'].append({
                    'type': kind, 'game': cn_name, 'source': en_name, 'system': system,
                    'status': 'failed', 'reason': 'filename_collision',
                    'message': '多个图片来源对应同一文件名，请为不同版本保留不同名称'
                })
        tasks = safe_tasks
        print(f"Starting batch download for {len(tasks)} unique targets with {self.max_workers} threads...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_game = {
                executor.submit(self.download_thumbnail, system, en_name, cn_name): (system, en_name, cn_name)
                for system, en_name, cn_name in tasks
            }
            
            completed = 0
            total = len(tasks)
            
            for future in as_completed(future_to_game):
                system, en_name, cn_name = future_to_game[future]
                completed += 1
                try:
                    results = future.result()
                    # Build detailed message
                    success_count = sum(1 for r in results if r.get("status") == "success")
                    skipped_count = sum(1 for r in results if r.get("status") == "skipped")
                    failure_count = sum(1 for r in results if r.get("status") == "failed")
                    completed_count = success_count + skipped_count

                    for result in results:
                        type_name = result.get("type")
                        status = result.get("status")
                        if type_name in summary["types"] and status in summary["types"][type_name]:
                            summary["types"][type_name][status] += 1
                        if status in summary["total"]:
                            summary["total"][status] += 1
                        summary["details"].append(result)

                    if completed_count > 0 and failure_count == 0:
                        message = f"✓ {cn_name} - 完成 ({success_count} 成功, {skipped_count} 跳过)"
                    elif completed_count > 0:
                        message = f"⚠ {cn_name} - 部分完成 ({success_count} 成功, {skipped_count} 跳过, {failure_count} 失败)"
                    else:
                        message = f"✗ {cn_name} - 下载失败"
                    
                    # Print detailed results to console
                    if results:
                        for res in results:
                            print(f"{res.get('status')} {res.get('type')}: {res.get('game')} - {res.get('message')}")
                    
                    if progress_callback:
                        progress_callback(completed, total, message)
                except Exception as exc:
                    error_msg = f"✗ {cn_name} - 错误: {str(exc)}"
                    print(f"[{completed}/{total}] Error processing {cn_name}: {exc}")
                    failed_results = []
                    for type_name in self.THUMBNAIL_TYPES:
                        failed_results.append({
                            "type": type_name,
                            "game": cn_name,
                            "source": en_name,
                            "system": system,
                            "status": "failed",
                            "message": str(exc)
                        })
                        summary["types"][type_name]["failed"] += 1
                        summary["total"]["failed"] += 1
                    summary["details"].extend(failed_results)
                    if progress_callback:
                        progress_callback(completed, total, error_msg)

        return summary

    def sanitize_filename(self, name):
        """
        Replaces illegal characters with underscores, matching RetroArch's behavior.
        """
        # List of characters to replace
        return sanitize_filename(name)

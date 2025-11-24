import os
import requests
import urllib.parse

class ThumbnailDownloader:
    BASE_URL = "https://thumbnails.libretro.com"

    def __init__(self, thumbnails_dir):
        self.thumbnails_dir = thumbnails_dir

    def download_thumbnail(self, system, game_english_name, game_chinese_name):
        """
        Downloads thumbnails for a game.
        system: The system name (e.g., "Nintendo - Super Nintendo Entertainment System")
        game_english_name: The name of the game in English (as it appears in the Libretro database)
        game_chinese_name: The name to save the file as.
        """
        # Thumbnail types
        types = ["Named_Boxarts", "Named_Snaps", "Named_Titles"]
        
        # The filename on the server usually matches the game label in the playlist (English),
        # but with special characters replaced.
        # See: https://docs.libretro.com/guides/roms-playlists-thumbnails/#thumbnail-file-names
        # Generally: Replace `&` `*` `/` `:` `<` `>` `?` `\` `|` with `_`
        server_filename = self.sanitize_filename(game_english_name) + ".png"
        
        for type_name in types:
            url = f"{self.BASE_URL}/{urllib.parse.quote(system)}/{type_name}/{urllib.parse.quote(server_filename)}"
            
            # Target directory
            target_dir = os.path.join(self.thumbnails_dir, system, type_name)
            os.makedirs(target_dir, exist_ok=True)
            
            # Target file path (using Chinese name)
            target_filename = self.sanitize_filename(game_chinese_name) + ".png"
            target_path = os.path.join(target_dir, target_filename)
            
            if os.path.exists(target_path):
                print(f"Skipping {type_name} for {game_chinese_name} (already exists)")
                continue

            print(f"Downloading {type_name} for {game_english_name} from {url}...")
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    with open(target_path, 'wb') as f:
                        f.write(response.content)
                    print(f"Saved to {target_path}")
                else:
                    print(f"Failed to download {url}: Status {response.status_code}")
            except Exception as e:
                print(f"Error downloading {url}: {e}")

    def sanitize_filename(self, name):
        """
        Replaces illegal characters with underscores, matching RetroArch's behavior.
        """
        # List of characters to replace
        illegal_chars = ['&', '*', '/', ':', '<', '>', '?', '\\', '|']
        for char in illegal_chars:
            name = name.replace(char, '_')
        return name

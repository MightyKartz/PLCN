import json
import os

class PlaylistManager:
    def __init__(self, playlist_path):
        self.playlist_path = playlist_path
        self.items = []
        self.load()

    def load(self):
        """Loads the playlist from the file."""
        if not os.path.exists(self.playlist_path):
            raise FileNotFoundError(f"Playlist file not found: {self.playlist_path}")
        
        with open(self.playlist_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
            self.items = self.data.get('items', [])

    def save(self, output_path=None):
        """Saves the playlist to the file."""
        target_path = output_path if output_path else self.playlist_path
        # Update items in self.data before saving
        self.data['items'] = self.items
        
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def update_label(self, entry_index, new_label):
        """Updates the label of a specific entry."""
        if 0 <= entry_index < len(self.items):
            self.items[entry_index]['label'] = new_label

    def get_items(self):
        return self.items
    
    def deduplicate_items(self):
        """
        Remove duplicate entries for the same game with different file extensions.
        Priority order: .cue > .chd > .iso > .bin
        Keeps the entry with the highest priority extension.
        """
        # Extension priority (lower number = higher priority)
        extension_priority = {
            '.cue': 1,  # CD description file (best)
            '.chd': 2,  # Compressed disc image
            '.iso': 3,  # ISO image
            '.bin': 4,  # Raw binary (lowest priority)
            '.img': 4,  # Similar to bin
        }
        
        # Group items by label (game name)
        label_groups = {}
        for idx, item in enumerate(self.items):
            label = item.get('label', '')
            if not label:
                continue
            
            if label not in label_groups:
                label_groups[label] = []
            label_groups[label].append((idx, item))
        
        # Determine which items to keep
        indices_to_remove = set()
        
        for label, items_list in label_groups.items():
            if len(items_list) <= 1:
                continue  # No duplicates
            
            # Find the item with highest priority extension
            best_item = None
            best_priority = float('inf')
            
            for idx, item in items_list:
                path = item.get('path', '')
                # Get file extension
                _, ext = os.path.splitext(path.lower())
                
                # Get priority (lower is better)
                priority = extension_priority.get(ext, 99)
                
                if priority < best_priority:
                    best_priority = priority
                    best_item = (idx, item)
            
            # Mark all others for removal
            for idx, item in items_list:
                if (idx, item) != best_item:
                    indices_to_remove.add(idx)
        
        # Remove duplicates (in reverse order to maintain indices)
        for idx in sorted(indices_to_remove, reverse=True):
            del self.items[idx]
        
        removed_count = len(indices_to_remove)
        return removed_count

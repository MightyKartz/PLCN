import os
import shutil
import glob

def copy_dats():
    base_dir = os.getcwd()
    temp_db_dir = os.path.join(base_dir, "temp_db")
    target_dir = os.path.join(base_dir, "data", "libretro-db", "dat")
    
    print(f"Creating target directory: {target_dir}")
    os.makedirs(target_dir, exist_ok=True)
    
    # Source directories to search
    sources = [
        os.path.join(temp_db_dir, "dat"),
        os.path.join(temp_db_dir, "metadat", "fbneo-split"),
        os.path.join(temp_db_dir, "metadat", "tosec"),
        os.path.join(temp_db_dir, "metadat", "redump"),
        os.path.join(temp_db_dir, "metadat", "no-intro"),
        os.path.join(temp_db_dir, "metadat", "libretro-dats")
    ]
    
    total_copied = 0
    
    for src in sources:
        if not os.path.exists(src):
            print(f"Warning: Source directory not found: {src}")
            continue
            
        print(f"Scanning {src}...")
        # Walk through directory to find .dat files (recursive)
        for root, dirs, files in os.walk(src):
            for file in files:
                if file.endswith(".dat"):
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    
                    # Avoid overwriting if possible, or just overwrite
                    try:
                        shutil.copy2(src_file, dst_file)
                        # print(f"Copied: {file}") # Too verbose
                        total_copied += 1
                    except Exception as e:
                        print(f"Error copying {file}: {e}")
    
    print(f"Total DAT files copied: {total_copied}")
    
    # Verify
    if total_copied == 0:
        print("Error: No DAT files were copied!")
        exit(1)
        
    # List first few files for verification
    print("Verification (first 5 files):")
    files = os.listdir(target_dir)
    for f in files[:5]:
        print(f"  {f}")

if __name__ == "__main__":
    copy_dats()

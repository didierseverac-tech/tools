changelog = [
    "1.00   13/05/26    Initial version",
    "1.01   13/05/26    Added derived path columns and open generated CSV at the end"
]

import os
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import winsound


def get_path_right_of_nth_backslash(path_value, backslash_count):
    """
    Return the portion of a Windows path located after the nth backslash.
    """
    normalized_path = str(path_value).replace('/', '\\')
    parts = normalized_path.split('\\')

    if len(parts) <= backslash_count:
        return ""

    return '\\'.join(parts[backslash_count:])


def to_html_path(path_value):
    """
    Convert a Windows path fragment into a URL-encoded path.
    """
    normalized_path = str(path_value).replace('\\', '/')
    return quote(normalized_path, safe='/')

def calculate_file_hash(file_path, hash_type='md5'):
    """
    Calculate file hash (optional, for duplicate detection)
    """
    try:
        hash_obj = hashlib.new(hash_type)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except:
        return "Error calculating hash"

def format_file_size(size_bytes):
    """
    Convert bytes to human readable format
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def get_directory_contents_advanced(directory_path, include_subdirs=True, 
                                  include_hash=False, file_filter=None):
    """
    Get directory contents with advanced options
    """
    file_list = []
    path = Path(directory_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {directory_path}")
    
    pattern = "**/*" if include_subdirs else "*"
    
    for item in path.glob(pattern):
        if item.is_file():
            # Apply file filter if specified
            if file_filter and item.suffix.lower() not in [ext.lower() for ext in file_filter]:
                continue
                
            try:
                stat = item.stat()
                file_info = {
                    'filename': item.name,
                    'filename_without_extension': item.stem,
                    'full_path': str(item),
                    'path_without_current_user': get_path_right_of_nth_backslash(item, 3),
                    'path_right_of_5th_backslash_html': to_html_path(get_path_right_of_nth_backslash(item, 5)),
                    'relative_path': str(item.relative_to(path)),
                    'directory': str(item.parent),
                    'extension': item.suffix,
                    'size_bytes': stat.st_size,
                    'size_formatted': format_file_size(stat.st_size),
                    'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'accessed': datetime.fromtimestamp(stat.st_atime).strftime('%Y-%m-%d %H:%M:%S'),
                    'depth_level': len(item.relative_to(path).parts) - 1
                }
                
                if include_hash:
                    file_info['md5_hash'] = calculate_file_hash(item)
                
                file_list.append(file_info)
                
            except (PermissionError, OSError) as e:
                print(f"Skipping {item}: {e}")
                continue
    
    return file_list

def create_summary_stats(file_list):
    """
    Create summary statistics
    """
    df = pd.DataFrame(file_list)
    
    summary = {
        'total_files': len(df),
        'total_size_bytes': df['size_bytes'].sum(),
        'total_size_formatted': format_file_size(df['size_bytes'].sum()),
        'avg_file_size': format_file_size(df['size_bytes'].mean()),
        'largest_file': df.loc[df['size_bytes'].idxmax(), 'filename'] if len(df) > 0 else 'N/A',
        'most_common_extension': df['extension'].value_counts().index[0] if len(df) > 0 else 'N/A',
        'extension_counts': df['extension'].value_counts().to_dict()
    }
    
    return summary

def select_directory():
    """
    Open directory picker dialog and return selected path
    """
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    directory = filedialog.askdirectory(
        title="Select Directory to Scan",
        initialdir=os.path.expanduser("~")  # Start in user's home directory
    )
    
    root.destroy()  # Clean up the tkinter root window
    return directory

def ensure_output_directory():
    """
    Ensure c:/temp directory exists, create if not
    """
    output_dir = Path("c:/temp")
    output_dir.mkdir(exist_ok=True)
    return output_dir

def generate_output_filename():
    """
    Generate timestamped filename for output
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"directory_contents_{timestamp}.csv"

def main():
    """
    Main execution function with directory picker and fixed output location
    """
    print("Directory Content Scanner")
    print("=" * 50)
    
    # Get directory from user
    selected_directory = select_directory()
    
    if not selected_directory:
        print("No directory selected. Exiting...")
        return
    
    print(f"Scanning directory: {selected_directory}")
    
    try:
        # Ensure output directory exists
        output_dir = ensure_output_directory()
        
        # Get directory contents
        print("Scanning files... This may take a while for large directories.")
        files = get_directory_contents_advanced(
            selected_directory, 
            include_subdirs=True,
            include_hash=False  # Set to True if you want file hashes (slower)
        )
        
        if not files:
            messagebox.showwarning("No Files", "No files found in the selected directory.")
            return
        
        # Create DataFrame and save to CSV
        df = pd.DataFrame(files)
        
        # Generate output path
        output_filename = generate_output_filename()
        output_path = output_dir / output_filename
        
        # Save to CSV
        df.to_csv(output_path, index=False)
        
        # Generate and display summary
        summary = create_summary_stats(files)
        
        print(f"CSV saved to: {output_path}")
        print(f"Total files found: {summary['total_files']:,}")
        print(f"Total size: {summary['total_size_formatted']}")
        print(f"Most common extension: {summary['most_common_extension']}")
        print(f"Extension breakdown: {summary['extension_counts']}")
        
        # Offer to open the generated CSV file or its containing folder
        def ask_open_choice():
            dlg = tk.Tk()
            dlg.title("Open Generated CSV")
            dlg.resizable(False, False)
            label = tk.Label(dlg, text="Open the CSV file or its folder?")
            label.pack(padx=12, pady=(12, 6))

            choice = {'value': None}

            def open_file():
                choice['value'] = 'file'
                dlg.destroy()

            def open_folder():
                choice['value'] = 'folder'
                dlg.destroy()

            def cancel():
                choice['value'] = None
                dlg.destroy()

            btn_frame = tk.Frame(dlg)
            btn_frame.pack(pady=(0, 12))

            tk.Button(btn_frame, text="Open File", width=12, command=open_file).pack(side=tk.LEFT, padx=6)
            tk.Button(btn_frame, text="Open Folder", width=12, command=open_folder).pack(side=tk.LEFT, padx=6)
            tk.Button(btn_frame, text="Cancel", width=12, command=cancel).pack(side=tk.LEFT, padx=6)

            dlg.mainloop()
            return choice['value']

        # Play the standard information beep (same as messagebox.showinfo)
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

        choice = ask_open_choice()
        if choice == 'file':
            try:
                os.startfile(str(output_path))
            except Exception as e:
                messagebox.showerror("Error", f"Unable to open file: {e}")
        elif choice == 'folder':
            try:
                # Try to open Explorer and select the file
                subprocess.run(['explorer', f"/select,{str(output_path)}"]) 
            except Exception:
                try:
                    os.startfile(str(output_dir))
                except Exception as e:
                    messagebox.showerror("Error", f"Unable to open folder: {e}")
            
    except FileNotFoundError:
        error_msg = f"Directory not found: {selected_directory}"
        print(error_msg)
        messagebox.showerror("Error", error_msg)
    except PermissionError:
        error_msg = f"Permission denied accessing: {selected_directory}"
        print(error_msg)
        messagebox.showerror("Error", error_msg)
    except Exception as e:
        error_msg = f"An error occurred: {str(e)}"
        print(error_msg)
        messagebox.showerror("Error", error_msg)

# Run the main function when script is executed
if __name__ == "__main__":
    main()
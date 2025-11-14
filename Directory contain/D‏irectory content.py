import os
import pandas as pd
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import hashlib

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
                    'full_path': str(item),
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
        
        print(f"\nScan Complete!")
        print(f"CSV saved to: {output_path}")
        print(f"Total files found: {summary['total_files']:,}")
        print(f"Total size: {summary['total_size_formatted']}")
        print(f"Most common extension: {summary['most_common_extension']}")
        print(f"Extension breakdown: {summary['extension_counts']}")
        
        # Show success message
        messagebox.showinfo(
            "Scan Complete", 
            f"Directory scan complete!\n\n"
            f"Files found: {summary['total_files']:,}\n"
            f"Total size: {summary['total_size_formatted']}\n"
            f"CSV saved to:\n{output_path}"
        )
        
        # Optionally open the output folder
        response = messagebox.askyesno("Open Folder", "Would you like to open the output folder?")
        if response:
            os.startfile(str(output_dir))
            
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
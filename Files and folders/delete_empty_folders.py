"""
Script to delete empty folders in a directory tree.
"""
import os
import sys


def delete_empty_folders(root_path, dry_run=True):
    """
    Delete empty folders in the given directory tree.
    
    Args:
        root_path: The root directory to scan for empty folders
        dry_run: If True, only show what would be deleted without actually deleting
    
    Returns:
        Number of folders deleted (or that would be deleted in dry run mode)
    """
    deleted_count = 0
    
    # Walk the directory tree bottom-up so we can delete empty parent folders
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        # Skip the root directory itself
        if dirpath == root_path:
            continue
            
        # Check if directory is empty
        try:
            if not os.listdir(dirpath):
                if dry_run:
                    print(f"[DRY RUN] Would delete: {dirpath}")
                else:
                    os.rmdir(dirpath)
                    print(f"Deleted: {dirpath}")
                deleted_count += 1
        except (PermissionError, OSError) as e:
            print(f"Error accessing {dirpath}: {e}")
    
    return deleted_count


def main():
    """Main function to run the script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Delete empty folders in a directory tree"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to scan for empty folders (default: prompt user)"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete empty folders (default is dry run mode)"
    )
    
    args = parser.parse_args()
    
    # Get path from argument or prompt user
    if args.path:
        root_path = os.path.abspath(args.path)
    else:
        user_input = input("Enter the root path to scan for empty folders (or press Enter for current directory): ").strip()
        # Remove surrounding quotes if present
        user_input = user_input.strip('"').strip("'")
        root_path = os.path.abspath(user_input if user_input else ".")
    
    # Check if path exists
    if not os.path.exists(root_path):
        print(f"Error: Path '{root_path}' does not exist")
        sys.exit(1)
    
    if not os.path.isdir(root_path):
        print(f"Error: Path '{root_path}' is not a directory")
        sys.exit(1)
    
    # Run the deletion
    dry_run = not args.delete
    
    if dry_run:
        print(f"DRY RUN MODE - Scanning: {root_path}")
        print("Use --delete flag to actually delete folders\n")
    else:
        print(f"DELETING empty folders in: {root_path}\n")
    
    count = delete_empty_folders(root_path, dry_run)
    
    print(f"\n{'Would delete' if dry_run else 'Deleted'} {count} empty folder(s)")


if __name__ == "__main__":
    main()

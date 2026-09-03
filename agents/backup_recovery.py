import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, load_policy, today_str

IST = timezone(timedelta(hours=5, minutes=30))

BACKUP_DIRS = [
    'config',
    'data',
    'reports',
    'content/daily',
    'agents'
]

CRITICAL_FILES = [
    'config/books.json',
    'config/heroes.json',
    'config/course.yaml',
    'config/autonomy_policy.yaml',
    'requirements.txt',
    '.github/workflows/daily-civilization.yml',
    '.github/workflows/weekly-report.yml',
    '.github/workflows/monthly-optimization.yml'
]

def create_backup() -> dict:
    """Create timestamped backup of critical data"""
    timestamp = datetime.now(IST).strftime('%Y%m%d_%H%M%S')
    backup_root = Path(__file__).parent.parent / 'backups' / timestamp
    backup_root.mkdir(parents=True, exist_ok=True)
    
    backed_up = []
    failed = []
    
    # Backup directories
    for dir_name in BACKUP_DIRS:
        src = Path(__file__).parent.parent / dir_name
        if src.exists():
            dst = backup_root / dir_name
            try:
                shutil.copytree(src, dst, dirs_exist_ok=True)
                backed_up.append(f'{dir_name}/')
            except Exception as e:
                failed.append(f'{dir_name}: {e}')
    
    # Backup critical files individually
    for file_path in CRITICAL_FILES:
        src = Path(__file__).parent.parent / file_path
        if src.exists():
            dst = backup_root / file_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
                backed_up.append(file_path)
            except Exception as e:
                failed.append(f'{file_path}: {e}')
    
    # Create manifest
    manifest = {
        'timestamp': datetime.now(IST).isoformat(),
        'backup_path': str(backup_root),
        'backed_up': backed_up,
        'failed': failed,
        'total_items': len(backed_up)
    }
    
    with open(backup_root / 'manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    return manifest

def verify_backup(backup_path: Path) -> dict:
    """Verify backup integrity"""
    manifest_file = backup_path / 'manifest.json'
    if not manifest_file.exists():
        return {'valid': False, 'error': 'No manifest found'}
    
    with open(manifest_file, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    missing = []
    for item in manifest['backed_up']:
        item_path = backup_path / item
        if not item_path.exists():
            missing.append(item)
    
    return {
        'valid': len(missing) == 0,
        'missing': missing,
        'manifest': manifest
    }

def list_backups() -> list:
    """List all available backups"""
    backup_root = Path(__file__).parent.parent / 'backups'
    if not backup_root.exists():
        return []
    
    backups = []
    for backup_dir in sorted(backup_root.iterdir(), reverse=True):
        if backup_dir.is_dir():
            manifest_file = backup_dir / 'manifest.json'
            if manifest_file.exists():
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                backups.append({
                    'timestamp': manifest['timestamp'],
                    'path': str(backup_dir),
                    'items': manifest['total_items'],
                    'valid': True
                })
    return backups

def cleanup_old_backups(keep_days: int = 30) -> dict:
    """Remove backups older than keep_days"""
    backup_root = Path(__file__).parent.parent / 'backups'
    if not backup_root.exists():
        return {'removed': 0, 'kept': 0}
    
    cutoff = datetime.now(IST) - timedelta(days=keep_days)
    removed = 0
    kept = 0
    
    for backup_dir in backup_root.iterdir():
        if backup_dir.is_dir():
            manifest_file = backup_dir / 'manifest.json'
            if manifest_file.exists():
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                backup_time = datetime.fromisoformat(manifest['timestamp'].replace('Z', '+00:00'))
                if backup_time < cutoff:
                    shutil.rmtree(backup_dir)
                    removed += 1
                else:
                    kept += 1
    
    return {'removed': removed, 'kept': kept}

def main():
    print(f'[{datetime.now(IST)}] Backup & Recovery starting...')
    
    # Create new backup
    manifest = create_backup()
    
    # Verify backup
    backup_path = Path(manifest['backup_path'])
    verification = verify_backup(backup_path)
    
    # Cleanup old backups
    cleanup = cleanup_old_backups(30)
    
    # List all backups
    all_backups = list_backups()
    
    output = {
        'date': today_str(),
        'latest_backup': manifest,
        'verification': verification,
        'cleanup': cleanup,
        'all_backups': all_backups[:10],  # Last 10
        'total_backups': len(all_backups)
    }
    
    save_json('reports/backup_status.json', output)
    print(f'[{datetime.now(IST)}] Backup & Recovery complete → reports/backup_status.json ({manifest["total_items"]} items, {cleanup["removed"]} cleaned)')

if __name__ == '__main__':
    main()
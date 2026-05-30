import json
from packaging import version

MIGRATORS = {}
CURRENT_VERSION = '1.1.20260509'


def migrator(from_version, to_version):
    def decorator(func):
        key = (from_version, to_version)
        MIGRATORS[key] = func
        return func
    return decorator


def migrate_backup_data(backup_data, target_version=None):
    if target_version is None:
        target_version = CURRENT_VERSION
    
    backup_version = backup_data.get('version', '0.0.0')
    
    if backup_version == target_version:
        return backup_data
    
    current_version = backup_version
    
    while version.parse(current_version) < version.parse(target_version):
        next_version = get_next_version(current_version)
        if not next_version:
            break
        
        migrator_key = (current_version, next_version)
        if migrator_key in MIGRATORS:
            backup_data = MIGRATORS[migrator_key](backup_data)
        
        current_version = next_version
    
    backup_data['version'] = target_version
    backup_data['migrated_from'] = backup_version
    
    return backup_data


def get_next_version(current_version):
    versions = set()
    for (from_ver, to_ver) in MIGRATORS.keys():
        if from_ver == current_version:
            versions.add(to_ver)
    
    if not versions:
        return None
    
    return sorted(versions, key=lambda v: version.parse(v))[0]


@migrator('0.0.0', '1.0.0')
def migrate_0_0_0_to_1_0_0(backup_data):
    tables = backup_data.get('tables', {})
    
    if 'users' in tables:
        for user in tables['users']:
            if 'avatar' not in user:
                user['avatar'] = 'default.png'
    
    if 'questions' in tables:
        for question in tables['questions']:
            if 'difficulty' not in question:
                question['difficulty'] = 2
    
    backup_data['version'] = '1.0.0'
    return backup_data


def validate_backup_compatibility(backup_data, current_system_version=None):
    if current_system_version is None:
        current_system_version = CURRENT_VERSION
    
    backup_version = backup_data.get('version', '0.0.0')
    
    try:
        bv = version.parse(backup_version)
        cv = version.parse(current_system_version)
        
        if bv.major > cv.major:
            return False, "备份文件版本过新，请更新系统"
        
        if bv.major < cv.major - 1:
            return False, "备份文件版本过旧，无法直接恢复"
        
        return True, None
        
    except Exception as e:
        return False, f"版本验证失败: {str(e)}"

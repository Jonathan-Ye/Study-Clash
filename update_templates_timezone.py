#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量更新模板文件,将UTC时间显示改为北京时间
"""
import os
import re

TEMPLATES_DIR = r'c:\Users\Joner\Desktop\Study Clash\Study Clash\app\templates'

replacements = [
    (r"\.strftime\('%Y-%m-%d %H:%M'\)", "| strftime_beijing('%Y-%m-%d %H:%M')"),
    (r"\.strftime\('%m-%d %H:%M'\)", "| strftime_beijing('%m-%d %H:%M')"),
    (r"\.strftime\('%Y-%m-%d %H:%M:%S'\)", "| strftime_beijing('%Y-%m-%d %H:%M:%S')"),
    (r"\.strftime\('%Y-%m-%d'\)", "| strftime_beijing('%Y-%m-%d')"),
    (r"\.strftime\('%H:%M:%S'\)", "| strftime_beijing('%H:%M:%S')"),
    (r"\.strftime\('%m-%d'\)", "| strftime_beijing('%m-%d')"),
    (r"\.strftime\('%Y-%m-%dT%H:%M'\)", "| strftime_beijing('%Y-%m-%dT%H:%M')"),
]

updated_count = 0

for root, dirs, files in os.walk(TEMPLATES_DIR):
    for filename in files:
        if not filename.endswith('.html'):
            continue
        
        filepath = os.path.join(root, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            updated_count += 1
            print(f'✓ Updated: {filepath}')

print(f'\nTotal files updated: {updated_count}')

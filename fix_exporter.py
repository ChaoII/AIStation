import re

with open('backend/app/plugin/module_train/exporter.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines 135-206 (0-indexed: 134-205) are the dead old _export_yolo body
# Remove them: keep 0-134, then skip 135-206, keep 207+
new_lines = lines[:135] + lines[207:]

with open('backend/app/plugin/module_train/exporter.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'Removed {207-135} lines of dead code. New file has {len(new_lines)} lines.')

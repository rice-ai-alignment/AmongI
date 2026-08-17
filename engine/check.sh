#!/bin/bash
# Syntax check (Python) + config validation for engine/
cd "$(dirname "$0")"
PY=${PY:-python3}

echo "── syntax ──"
$PY -c "
import py_compile, sys, pathlib
ok = True
dirs = [pathlib.Path('.'), pathlib.Path('../agent')]
for d in dirs:
    if not d.exists():
        continue
    for f in d.glob('*.py'):
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            print(f'FAIL: {f}')
            print(e)
            ok = False
sys.exit(0 if ok else 1)
" || exit 1
echo "All Python files OK"

echo "── config validation ──"
$PY validate_configs.py

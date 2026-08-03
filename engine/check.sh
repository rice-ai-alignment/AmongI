#!/bin/bash
# Quick Python syntax check for agent/ and engine/
cd "$(dirname "$0")"
python3 -c "
import py_compile, sys, pathlib
ok = True
dirs = [pathlib.Path('.'), pathlib.Path('../agent')]
for d in dirs:
    for f in d.glob('*.py'):
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            print(f'FAIL: {f}')
            print(e)
            ok = False
if ok:
    print('All Python files OK')
else:
    sys.exit(1)
"

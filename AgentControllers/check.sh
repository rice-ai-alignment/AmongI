#!/bin/bash
# Quick Python syntax check for AgentControllers/
cd "$(dirname "$0")"
python3 -c "
import py_compile, sys, pathlib
ok = True
for f in pathlib.Path('.').glob('*.py'):
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

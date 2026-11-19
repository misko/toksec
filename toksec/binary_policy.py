import re
import subprocess

def inspect_binary(binary, allow_test_runtime_symbols=False):
    dynamic = subprocess.check_output(['readelf', '-d', str(binary)], text=True)
    needed = set(re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic))
    allowed = {'ld-linux-x86-64.so.2', 'ld-linux-aarch64.so.1', 'libstdc++.so.6', 'libc.so.6', 'libm.so.6', 'libgcc_s.so.1', 'libpthread.so.0', 'librt.so.1'}
    if needed - allowed:
        return 'Unapproved linked libraries: ' + ', '.join(sorted(needed - allowed))
    symbols = subprocess.check_output(['nm', '-u', str(binary)], text=True)
    if not allow_test_runtime_symbols and re.search(r'\b(dlopen|dlmopen|dlsym|dlvsym)(@|\s|$)', symbols):
        return 'Runtime library loading is not permitted'
    return None

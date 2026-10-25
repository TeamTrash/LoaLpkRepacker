from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
from app import VERSION

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEST = ROOT.parent / 'releases' / 'LoaLpkRepacker' / VERSION
if __name__ == '__main__':
    subprocess.run(['dotnet', 'build', str(REPO / 'tools/LpkBulkRepack/LpkBulkRepack.csproj'), '-c', 'Release', '--no-restore'], cwd=REPO, check=True)
    shutil.copytree(REPO / 'tools/LpkBulkRepack/bin/Release/net8.0', ROOT / 'backend', dirs_exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed', '--noupx',
                    '--name', f'LoaLpkRepacker-{VERSION}', '--distpath', str(DEST),
                    '--workpath', str(ROOT / 'build/cache'), '--specpath', str(ROOT / 'build'),
                    '--add-data', str(ROOT / 'backend') + ';backend', str(ROOT / 'app.py')], check=True)
    exe = DEST / f'LoaLpkRepacker-{VERSION}.exe'
    (DEST / 'MANIFEST.json').write_text(json.dumps({'version': VERSION, 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest(), 'requires': '.NET 8 runtime x64'}, indent=2))
    shutil.copyfile(ROOT / 'README.md', DEST / 'README.md')

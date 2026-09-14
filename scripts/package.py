import subprocess, tarfile
from pathlib import Path
root=Path(__file__).resolve().parent.parent
with tarfile.open(root/'release.tar.gz','w:gz') as archive:
    for path in subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines():
        archive.add(root/path,arcname=path)
print('Pacote criado a partir dos arquivos versionados.')

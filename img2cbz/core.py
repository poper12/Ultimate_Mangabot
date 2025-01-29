import re
import zipfile
from pathlib import Path
from typing import List

def fld2cbz(folder, name: str, b1: str, b2: str) -> Path:
    cbz = Path("Downloads") / f"{name}.cbz"
    
    cbz.parent.mkdir(parents=True, exist_ok=True)
    
    folder.insert(0, b1)
    folder.append(b2)
    
    img2cbz(folder, cbz)
    
    return cbz

def img2cbz(files: List[Path], out: Path):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for image_file in files:
            zip_file.write(image_file, arcname=image_file)

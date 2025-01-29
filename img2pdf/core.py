import os
from io import BytesIO
from typing import List
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from PIL import Image
import re

def fld2pdf(folder, out: str, b1: str, b2: str) -> Path:
    folder.insert(0, b1)
    folder.append(b2)
    
    print(str(folder))
    pdf_path = Path("Downloads") / f"{out}.pdf"
    
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    img2pdf(folder, pdf_path)
    
    return pdf_path

def new_img(path: Path) -> Image.Image:
    img = Image.open(path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    return img

def img2pdf(files: List[Path], out: Path):
    c = canvas.Canvas(str(out), pagesize=letter)
    for imageFile in files:
        img = new_img(imageFile)
        width, height = img.size
        
        # Set the page size to the image size
        c.setPageSize((width, height))
        c.drawImage(str(imageFile), 0, 0, width, height)
        c.showPage()  # Finish the current page

    c.save()  # Save the PDF


def fld2thumb(folder: Path):
    files = [file for file in folder.glob(r'*') if re.match(r'.*\.(jpg|png|jpeg|webp)', file.name)]
    files.sort(key=lambda x: x.name)
    thumb_path = make_thumb(folder, files)
    return thumb_path


def make_thumb(folder, files):
    aspect_ratio = 0.7
    if len(files) > 1:
        with Image.open(files[1]) as img:
            aspect_ratio = img.width / img.height

    thumbnail = Image.open(files[0]).convert('RGB')
    tg_max_size = (300, 300)
    thumbnail = crop_thumb(thumbnail, aspect_ratio)
    thumbnail.thumbnail(tg_max_size)
    thumb_path = folder / 'thumbnail' / f'thumbnail.jpg'
    os.makedirs(thumb_path.parent, exist_ok=True)
    thumbnail.save(thumb_path)
    thumbnail.close()
    return thumb_path


def crop_thumb(thumb: Image.Image, aspect_ratio):
    w, h = thumb.width, thumb.height
    if w * 2 <= h:
        b = int(h - (w / aspect_ratio))
        if b <= 0:
            b = w
        thumb = thumb.crop((0, 0, w, b))
    return thumb

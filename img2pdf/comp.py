import argparse
import os
import shutil
import subprocess
from pathlib import Path

def compressFK(input_file_path, output_file_path, power=0):
    """ This Function Compress Asura And Reaper Files """
    quality = {
        0: "/default",
        1: "/prepress",
        2: "/printer",
        3: "/ebook",
        4: "/screen"
    }

    # Ensure output directory
    output_dir = Path("Compressed")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file_path = output_dir / f"{Path(output_file_path).stem}.pdf"

    # Check input file existence
    if not Path(input_file_path).exists():
        raise FileNotFoundError(f"Input file '{input_file_path}' does not exist.")

    # Get Ghostscript path
    gs = get_ghostscript_path()
    if not gs:
        raise FileNotFoundError("Ghostscript executable not found. Please install Ghostscript and try again.")

    print("Compressing PDF...")
    initial_size = os.path.getsize(input_file_path)
    subprocess.call(
        [
            gs,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS={}".format(quality[power]),
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-sOutputFile={}".format(output_file_path),
            input_file_path,
        ]
    )

    # Verify output file and remove input
    if not Path(output_file_path).exists():
        raise FileNotFoundError(f"Output file '{output_file_path}' was not created.")
    final_size = os.path.getsize(output_file_path)
    os.remove(input_file_path)

    print(f"Compression complete: {initial_size} -> {final_size} bytes")
    return output_file_path


def get_ghostscript_path():
    """Find the Ghostscript executable path."""
    gs_names = ["gs", "gswin32", "gswin64"]
    for name in gs_names:
        if shutil.which(name):
            return shutil.which(name)
    raise FileNotFoundError("Ghostscript executable not found. Please install Ghostscript and try again.")

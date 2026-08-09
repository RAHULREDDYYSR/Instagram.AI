"""Render the generated PDF to PNGs so we can inspect layout."""
from pathlib import Path
import pypdfium2 as pdfium

PDF = Path("Brain/Scripts/_Compiled_Scripts_Sample.pdf")
OUT = Path("C:/Users/rahul/AppData/Local/Temp/opencode/pdf_review")
OUT.mkdir(parents=True, exist_ok=True)

pdf = pdfium.PdfDocument(str(PDF))
for i, page in enumerate(pdf, 1):
    img = page.render(scale=1.5).to_pil()
    img.save(OUT / f"p{i:02d}.png")
    print(f"p{i:02d}.png  {img.size}")

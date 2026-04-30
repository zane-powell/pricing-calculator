# Fonts for the PDF generator

These fonts are used in the generated PDF to match Thirdfort's brand.

## What's bundled

- **Lora** (`Lora-Variable.ttf`) — serif font used for headers
- **Poppins** (`Poppins-*.ttf`) — sans-serif used for body text

Both are open source under the SIL Open Font License (OFL).

## Upgrading to the actual brand fonts

The Thirdfort proposal deck uses **Red Hat Text** (sans-serif) as its body font.
To match the brand exactly:

1. Download Red Hat Text from https://fonts.google.com/specimen/Red+Hat+Text
2. Click "Get font" and download the .zip
3. Extract these TTF files into this folder:
   - `RedHatText-Regular.ttf`
   - `RedHatText-Medium.ttf`
   - `RedHatText-Bold.ttf`
   - `RedHatText-SemiBold.ttf`
4. Update the font references in `pdf_export.py` (one line — see comment at top of file).

The PDF generator will fall back to Helvetica if the fonts can't be loaded,
so the app never breaks — just won't look quite as on-brand.

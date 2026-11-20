# נכסי הגרסה המסחרית: מקום ללוגו (ריק — הלוגו של הלקוח יבוא כאן) והאייקון עם האות C
import sys, os, base64, io
from PIL import Image, ImageDraw, ImageFont
ver, date, out_py, icon_png = sys.argv[1:5]


def font(size, bold=True):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


# האייקון: אותו אייקון כמו בגרסה המשרדית, עם האות C (נוצר קודם ב-make_assets.py)
buf = io.BytesIO()
Image.open(icon_png).convert("RGBA").resize((128, 128), Image.LANCZOS).save(buf, "PNG")
icon_b64 = base64.b64encode(buf.getvalue()).decode()

# מקום ללוגו: מסגרת מקווקוות אפורה ובתוכה "לוגו" — כאן יבוא הלוגו של הלקוח
W, H = 426, 184
lg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(lg)
gray = (150, 160, 170, 255)
for x in range(8, W - 8, 22):
    d.line((x, 8, min(x + 12, W - 8), 8), fill=gray, width=5)
    d.line((x, H - 8, min(x + 12, W - 8), H - 8), fill=gray, width=5)
for y in range(8, H - 8, 22):
    d.line((8, y, 8, min(y + 12, H - 8)), fill=gray, width=5)
    d.line((W - 8, y, W - 8, min(y + 12, H - 8)), fill=gray, width=5)
txt = "וגול"          # "לוגו" — הספרייה מציירת משמאל לימין, לכן הסדר הפוך
f = font(90, bold=False)
bb = d.textbbox((0, 0), txt, font=f)
d.text(((W - (bb[2] - bb[0])) / 2 - bb[0], (H - (bb[3] - bb[1])) / 2 - bb[1]), txt, font=f, fill=gray)
buf = io.BytesIO()
lg.save(buf, "PNG")
logo_b64 = base64.b64encode(buf.getvalue()).decode()
with open(out_py, "w", encoding="utf-8") as fh:
    fh.write(f'VERSION = "{ver}"\nBUILD_DATE = "{date}"\nLOGO_B64 = "{logo_b64}"\nICON_B64 = "{icon_b64}"\n')
print("commercial assets ok")

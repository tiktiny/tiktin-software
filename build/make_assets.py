# יוצר את version.py (גרסה, תאריך, לוגו ואייקון) ואת אייקון התוכנה:
# המילה PDF גדולה על רקע ריבוע הברק של לוגו טיקטין, בשחור-לבן
import sys, os, base64, io
from PIL import Image, ImageDraw, ImageFont, ImageOps
logo_path, ver, date, out_py, out_ico = sys.argv[1:6]
im = Image.open(logo_path).convert("RGBA")
w, h = im.size
px = im.load()


def warm(p):
    return p[3] > 0 and p[0] > 200 and p[2] < 120


# ריבוע הברק: העמודות בחצי הימני שיש בהן הרבה פיקסלים אדומים-כתומים
cols = [x for x in range(w // 2, w) if sum(1 for y in range(h) if warm(px[x, y])) > h * 0.4]
x0, x1 = min(cols), max(cols) + 1
rows = [y for y in range(h) if sum(1 for x in range(x0, x1) if warm(px[x, y])) > 3]
sq = im.crop((x0, min(rows), x1, max(rows) + 1))
S = 1024
s = max(sq.size)
c = Image.new("RGBA", (s, s), (255, 255, 255, 0))
c.paste(sq, ((s - sq.width) // 2, (s - sq.height) // 2))
c = c.resize((S, S), Image.LANCZOS)
g = ImageOps.grayscale(c.convert("RGB")).point(lambda v: int(v * 0.55))
bg = Image.new("RGBA", (S, S))
bg.paste(g.convert("RGBA"))
bg.putalpha(c.split()[3])


def bold_font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


d = ImageDraw.Draw(bg)
t = "PDF"
font = bold_font(400)
bb = d.textbbox((0, 0), t, font=font)
font = bold_font(int(400 * S * 0.94 / (bb[2] - bb[0])))
bb = d.textbbox((0, 0), t, font=font)
tw, th = bb[2] - bb[0], bb[3] - bb[1]
d.text(((S - tw) / 2 - bb[0], (S - th) / 2 - bb[1]), t, font=font,
       fill=(255, 255, 255, 255), stroke_width=30, stroke_fill=(0, 0, 0, 255))
ic = bg.resize((256, 256), Image.LANCZOS)
ic.save(out_ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
ic.save(os.path.splitext(out_ico)[0] + ".png")
buf = io.BytesIO()
bg.resize((128, 128), Image.LANCZOS).save(buf, "PNG")
logo_b64 = base64.b64encode(open(logo_path, "rb").read()).decode()
icon_b64 = base64.b64encode(buf.getvalue()).decode()
with open(out_py, "w", encoding="utf-8") as f:
    f.write(f'VERSION = "{ver}"\nBUILD_DATE = "{date}"\nLOGO_B64 = "{logo_b64}"\nICON_B64 = "{icon_b64}"\n')
print("assets ok")

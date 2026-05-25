import base64
from pathlib import Path

img = Path(__file__).resolve().parents[2] / "example" / "images" / "image5.png"
b64 = base64.b64encode(img.read_bytes()).decode("ascii")

html = f"""<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>experiment-01-data-uri</title></head>
<body>
<h1>Эксперимент 01 — data URI</h1>
<p>Это первый абзац. Дальше будет картинка с подписью.</p>
<figure>
  <img src="data:image/png;base64,{b64}" alt="">
  <figcaption>Это я)</figcaption>
</figure>
<p>Это абзац после картинки.</p>
</body>
</html>
"""

Path(__file__).with_name("test.html").write_text(html, encoding="utf-8")
print(f"wrote test.html, image bytes: {len(b64)} base64 chars")

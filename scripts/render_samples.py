"""Render synthetic evidence with Pillow (developer-only rendering dependency)."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

for folder in (Path(__file__).resolve().parents[1]/'data/samples').iterdir():
    if not folder.is_dir():
        continue
    facts=json.loads((folder/'facts.json').read_text())
    image=Image.new('RGB',(900,680),'#f8fafc');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',24)
    draw.rounded_rectangle((35,35,865,645),radius=20,fill='white',outline='#e4e4e7')
    lines=[facts['company_name']+' | Order details','SYNTHETIC DEMO EVIDENCE',facts['order_id'],'Order date: 31 October 2026',f"Amount paid: INR {facts['amount_inr']}",'Refund requested: 1 November 2026','Status: Refund pending','Support ticket: DEMO-T104','Customer note: Three weeks, still waiting.']
    for i,line in enumerate(lines):
        draw.text((70,70+i*58),line,font=font,fill='#4338ca' if i==0 else '#27272a')
    image.save(folder/'order.png')

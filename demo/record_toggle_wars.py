#!/usr/bin/env python3
"""Record an honest, captioned Flagsmith hackathon walkthrough."""
import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://shikayat-toggle-wars.onrender.com'
OUT = ROOT / 'demo' / 'toggle-wars.mp4'

async def main():
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '/private/tmp/shikayat-playwright')
    with tempfile.TemporaryDirectory() as temp:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, slow_mo=100)
            context = await browser.new_context(viewport={'width': 1440, 'height': 900}, record_video_dir=temp, record_video_size={'width': 1440, 'height': 900})
            page = await context.new_page()
            async def caption(text, seconds=7):
                await page.evaluate('''text => { let x=document.getElementById('video-caption'); if(!x){x=document.createElement('div');x.id='video-caption';Object.assign(x.style,{position:'fixed',bottom:'0',left:'0',right:'0',padding:'18px',background:'rgba(28,26,58,.94)',color:'white',font:'24px Arial',textAlign:'center',zIndex:'2147483647'});document.body.appendChild(x);} x.textContent=text; }''', text)
                await page.wait_for_timeout(seconds * 1000)
            await page.goto(BASE + '/experiment/', wait_until='domcontentloaded', timeout=60000)
            await caption('Shikayat helps consumers follow up when a company does not resolve their complaint.')
            await caption('Toggle Wars Track 01: can a clearer first step help visitors start a case?')
            await page.get_by_role('button',name='B · Guided').click()
            await caption('Flagsmith assigns opted-in visitors to the original or guided introduction.')
            await page.get_by_role('button',name='A · Current').click()
            await caption('This switch is a visual preview. It does not record experiment traffic.')
            await page.get_by_text('SYNTHETIC DATA · WIRING CHECK').scroll_into_view_if_needed()
            await caption('A separate test environment recorded 100 synthetic exposures and 33 simulated starts.', 9)
            await caption('The numbers are synthetic. They do not establish a winner or measure real customers.', 8)
            await page.get_by_role('heading',name='How we will measure it').scroll_into_view_if_needed()
            await caption('The event is case_started; no complaint content is sent to Flagsmith.')
            await page.goto(BASE + '/',wait_until='domcontentloaded',timeout=60000)
            try:
                await page.get_by_role('button',name='Let’s get started').click(timeout=5000)
            except Exception:
                pass
            await caption('Visitors can opt in, then try a fictional sample case.', 7)
            await page.get_by_role('button',name='ShopKart ₹4,299').click()
            await page.wait_for_timeout(18000)
            await caption('The case board presents extracted facts, complaint strength and the route for review.', 10)
            await caption('The live preview uses free AI models. Sending is disabled; no winner is claimed.', 8)
            video = page.video
            await context.close()
            source = await video.path()
            subprocess.run(['ffmpeg','-y','-loglevel','error','-i',source,'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT)],check=True)
            await browser.close()
    print(f'Video saved: {OUT}')

if __name__ == '__main__':
    asyncio.run(main())

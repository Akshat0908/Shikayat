#!/usr/bin/env python3
"""Record the deployed product. Uses real SMTP for the explicitly requested sandbox preview.

Run: PLAYWRIGHT_BROWSERS_PATH=/tmp/shikayat-playwright .venv/bin/python demo/record_demo.py
Requires Playwright Chromium, its recording codec, ffmpeg, and the existing local .env.
No browser recording starts until owner sign-in has completed.
"""
import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'demo'
BASE = 'https://54-242-22-145.sslip.io'
CAPTIONS = json.loads((OUT / 'captions.json').read_text())
RESULTS = {}
TEXT = 'Leaf Buds X221 kharab nikle, ek side se awaaz nahi aati. 14 Nov ko ticket LF-7821 raise kiya, abhi tak replacement nahi mila.'

# Keep the fixed caption above the application, not replacing any app content.
INIT = r'''(() => {
  const install = () => {
    if (!document.body || document.getElementById('shk-record-caption')) return;
    const bar = document.createElement('div'); bar.id = 'shk-record-caption';
    Object.assign(bar.style, {position:'fixed',bottom:'0',left:'0',right:'0',minHeight:'74px',
      padding:'17px 45px',boxSizing:'border-box',background:'rgba(17,16,30,.88)',color:'#fff',
      font:'500 28px/1.35 Arial,sans-serif',textAlign:'center',zIndex:'2147483647',pointerEvents:'none'});
    document.body.appendChild(bar);
  };
  document.addEventListener('DOMContentLoaded',install); setTimeout(install,100);
})();'''

async def caption(page, text):
    await page.evaluate('''text => {let el=document.getElementById('shk-record-caption');
      if(!el){el=document.createElement('div');el.id='shk-record-caption';Object.assign(el.style,
      {position:'fixed',bottom:'0',left:'0',right:'0',padding:'17px 45px',minHeight:'74px',
       boxSizing:'border-box',background:'rgba(17,16,30,.88)',color:'#fff',
       font:'500 28px/1.35 Arial,sans-serif',textAlign:'center',zIndex:'2147483647',pointerEvents:'none'});
       document.body.appendChild(el)}el.textContent=text;}''', text)

async def pause(page, seconds=3):
    await page.wait_for_timeout(int(seconds * 1000))

async def scene(page, heading, body, duration=4):
    html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
      body{{margin:0;background:#f4f1ea;color:#26241f;font:400 44px/1.25 Arial;display:flex;
      height:100vh;align-items:center;justify-content:center}}main{{max-width:1250px}}
      h1{{font-size:72px;font-weight:500;letter-spacing:-.03em}}p{{font-size:42px}}</style></head>
      <body><main><h1>{heading}</h1><p>{body}</p></main></body></html>'''
    await page.goto('data:text/html;charset=utf-8,' + quote(html))
    await caption(page, CAPTIONS['title'] if heading.startswith('Shikayat') else CAPTIONS['end'])
    await pause(page, duration)

async def attempt(label, work):
    for attempt_no in range(2):
        try:
            value = await work()
            RESULTS[label] = 'PASS'
            print(label + ': PASS', flush=True)
            return value
        except Exception as error:
            # Do not dump browser request bodies or page content, which may contain secrets.
            kind = type(error).__name__
            print(f'{label}: attempt {attempt_no + 1} failed ({kind})', flush=True)
    RESULTS[label] = 'SKIP after two attempts'
    return None

async def go_admin(page):
    await page.goto(BASE + '/admin/', wait_until='domcontentloaded', timeout=20000)
    await page.get_by_role('heading', name='Owner tools').wait_for(timeout=15000)

async def main():
    passcode = dotenv_values(ROOT / '.env').get('ADMIN_PASSCODE')
    if not passcode:
        raise RuntimeError('ADMIN_PASSCODE is missing from .env')
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '/tmp/shikayat-playwright')
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='shk-video-') as temporary:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, slow_mo=80)
            # The unrecorded context contains the password input and is discarded.
            auth = await browser.new_context(viewport={'width':1920,'height':1080})
            login_response=await auth.request.post(BASE + '/api/admin/login',data={'passcode':passcode},timeout=30000)
            if not login_response.ok or not (await login_response.json()).get('admin'):
                raise RuntimeError('Owner sign-in failed before recording')
            state = await auth.storage_state()
            await auth.close()
            context = await browser.new_context(storage_state=state, viewport={'width':1920,'height':1080},
                record_video_dir=temporary, record_video_size={'width':1920,'height':1080})
            await context.add_init_script(INIT)
            page = await context.new_page()
            resume_case=os.environ.get('DEMO_RESUME_CASE','').strip()
            if resume_case:
                case_id=resume_case
                await page.goto(BASE+'/?case='+case_id,wait_until='domcontentloaded',timeout=30000)
                onboard=page.get_by_role('button',name='Let’s get started')
                if await onboard.is_visible(): await onboard.click()
                await page.get_by_text('THE FACTS').last.wait_for(timeout=20000)
                await caption(page,CAPTIONS['facts']);await pause(page,4)
                for label in ('Case strength','SUGGESTED COMPLAINT ROUTE'):
                    item=page.get_by_text(label,exact=False).last
                    if await item.count():
                        await item.scroll_into_view_if_needed(timeout=10000);await pause(page,3)
                RESULTS['2 screenshot and extraction']='PASS: continued from already-created case'
            else:
                await scene(page, 'Shikayat — your AI consumer advocate.',
                    "It doesn't stop when customer care replies.<br>It stops when your issue is actually resolved.")
                async def reset_on_camera():
                    await go_admin(page); await caption(page,CAPTIONS['reset'])
                    await page.get_by_role('button',name='Reset sandbox cases').click()
                    await page.get_by_text('Sandbox reset').first.wait_for(timeout=12000)
                    await pause(page,3)
                await attempt('1 reset sandbox',reset_on_camera)
                async def create_case():
                    await page.goto(BASE+'/',wait_until='domcontentloaded',timeout=20000)
                    await caption(page,CAPTIONS['input'])
                    onboard=page.get_by_role('button',name='Let’s get started')
                    if await onboard.is_visible(): await onboard.click()
                    await page.locator('input[type=file]').set_input_files(str(OUT/'leaf_order.png'))
                    field=page.get_by_label('Tell Shikayat what happened')
                    await field.click(); await field.press_sequentially(TEXT,delay=40)
                    await pause(page,3)
                    await page.get_by_role('button',name='Create case').click()
                    await page.get_by_role('button',name='Review complaint').wait_for(timeout=90000)
                    await page.get_by_text('THE FACTS').last.wait_for(timeout=30000)
                    await caption(page,CAPTIONS['facts']); await pause(page,5)
                    return page.url.split('case=',1)[1].split('&',1)[0]
                case_id=await attempt('2 screenshot and extraction',create_case)
            if case_id:
                async def preview():
                    board_response=await context.request.get(BASE+f'/api/cases/{case_id}/board',timeout=10000)
                    if board_response.ok and any(m['direction']=='out' for m in (await board_response.json()).get('messages',[])):
                        return True  # A previous attempt already sent the preview.
                    await page.get_by_role('button',name='Review complaint').click(timeout=20000)
                    await page.get_by_role('dialog').get_by_text('Review your complaint').wait_for(timeout=60000)
                    await caption(page,CAPTIONS['preview']); await pause(page,5)
                    button=page.get_by_role('button',name='Send a preview to the sandbox merchant')
                    await button.click(timeout=15000)
                    await page.get_by_text('Preview sent to the sandbox merchant').first.wait_for(timeout=60000)
                    await pause(page,3)
                    return True
                sent=await attempt('3 real sandbox preview',preview)
                async def wait_reply():
                    # Poll the board; no injection or fabricated reply is used here.
                    await page.keyboard.press('Escape')
                    await caption(page,CAPTIONS['waiting'])
                    end=time.monotonic()+90
                    while time.monotonic()<end:
                        response=await context.request.get(BASE+f'/api/cases/{case_id}/board',timeout=10000)
                        if response.ok:
                            board=await response.json()
                            if any(m['direction']=='in' for m in board.get('messages',[])):
                                await page.reload(wait_until='domcontentloaded'); await caption(page,CAPTIONS['forensics'])
                                card=page.get_by_text('REPLY FORENSICS',exact=False).first
                                await card.scroll_into_view_if_needed(timeout=15000); await pause(page,5)
                                return True
                        await pause(page,5)
                    raise TimeoutError('No real reply within 90 seconds')
                # Ninety seconds is a total bound; a retry checks once more, not another 90s.
                if sent:
                    try:
                        await wait_reply(); RESULTS['4 real auto-reply']='PASS'; print('4 real auto-reply: PASS',flush=True)
                    except Exception as error:
                        print('4 real auto-reply: wait failed ('+type(error).__name__+'); checking once more',flush=True)
                        try:
                            response=await context.request.get(BASE+f'/api/cases/{case_id}/board',timeout=10000)
                            board=await response.json()
                            assert any(m['direction']=='in' for m in board.get('messages',[]))
                            RESULTS['4 real auto-reply']='PASS on retry'
                        except Exception:
                            RESULTS['4 real auto-reply']='SKIP: no real reply within 90 seconds'
                            await caption(page,'No test-company reply arrived within 90 seconds; continuing without a simulated replacement.')
                            await pause(page,4)
                else:
                    RESULTS['4 real auto-reply']='SKIP: preview was not sent'
                    await caption(page,'The sandbox preview was not sent; the reply step is skipped.')
                    await pause(page,4)
                async def custom_inject(text):
                    await go_admin(page)
                    await caption(page,'Simulated reply controls: checking availability for this case.')
                    await page.get_by_label('Case ID for simulated reply').fill(case_id)
                    field=page.get_by_label('Optional simulated reply')
                    if not await field.count():
                        raise RuntimeError('Custom reply injection is not available on this deployment')
                    await field.fill(text)
                    await page.get_by_role('button',name='Inject simulated reply').click()
                    await page.get_by_text('Simulated reply inserted').first.wait_for(timeout=20000)
                    return True
                offer='As a goodwill gesture, we are offering a ₹200 coupon on your next purchase. We hope this resolves your concern. — Leaf Studios Support'
                if await attempt('5 simulated partial offer',lambda:custom_inject(offer)) is not None:
                    await page.goto(BASE+'/?case='+case_id);await caption(page,CAPTIONS['offer']);await pause(page,5)
                promise='We apologise for the delay. A replacement Leaf Buds X221 has been dispatched, AWB 8823019445. Expected delivery by 5 Dec 2026. — Leaf Studios Support'
                if await attempt('6 simulated dated promise',lambda:custom_inject(promise)) is not None:
                    await page.goto(BASE+'/?case='+case_id);await caption(page,CAPTIONS['promise']);await pause(page,5)
                if RESULTS.get('6 simulated dated promise')=='PASS':
                    async def clock():
                        await go_admin(page)
                        for _ in range(7): await page.get_by_role('button',name='⏩ Advance clock').click()
                        await page.goto(BASE+'/?case='+case_id); await caption(page,CAPTIONS['missed']); await pause(page,5)
                    await attempt('7 simulated clock and draft',clock)
                else:
                    RESULTS['7 simulated clock and draft']='SKIP: no dated promise to advance'
                    await caption(page,'The live controls could not inject a dated reply for this case; the clock step is skipped.')
                    await pause(page,4)
            else:
                for n in ('3 real sandbox preview','4 real auto-reply','5 simulated partial offer','6 simulated dated promise','7 simulated clock and draft'):
                    RESULTS[n]='SKIP: case unavailable'
            async def proof():
                await page.goto(BASE+'/proof/',wait_until='domcontentloaded',timeout=20000)
                await caption(page,CAPTIONS['proof'])
                await page.get_by_text('Held-out',exact=False).first.wait_for(timeout=15000)
                await pause(page,6)
            await attempt('8 measured proof',proof)
            await scene(page,'AI reads. Rules decide. You approve.','Live on AWS: 54-242-22-145.sslip.io')
            # Stop the video before resetting the sandbox, as requested.
            video=page.video
            await context.close()
            path=await video.path()
            cleanup=await browser.new_context(storage_state=state,viewport={'width':1920,'height':1080})
            clean_page=await cleanup.new_page()
            async def cleanup_reset():
                await go_admin(clean_page)
                await clean_page.get_by_role('button',name='Reset sandbox cases').click()
                await clean_page.get_by_text('Sandbox reset').first.wait_for(timeout=12000)
            await attempt('10 post-recording reset',cleanup_reset)
            await cleanup.close(); await browser.close()
        output=OUT/('resume.mp4' if os.environ.get('DEMO_RESUME_CASE') else 'Shikayat-demo.mp4')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(path),'-c:v','libx264',
                        '-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True)
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size',
                                                 '-of','json',str(output)],text=True))['format']
        RESULTS['duration_seconds']=round(float(info['duration']),2)
        RESULTS['size_bytes']=int(info['size'])
        (OUT/'report.json').write_text(json.dumps(RESULTS,indent=2)+'\n')
        print('Video duration:',RESULTS['duration_seconds'],'seconds; bytes:',RESULTS['size_bytes'],flush=True)
        if not 120<=float(info['duration'])<=240 or int(info['size'])>=100_000_000:
            print('Video does not meet the requested duration or size constraint.',flush=True)

if __name__=='__main__':
    asyncio.run(main())

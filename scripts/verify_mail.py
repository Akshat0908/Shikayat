"""Authorized bidirectional Gmail test, read-only searches and no credential output."""
import sys
import smtplib
import ssl
import time
from uuid import uuid4
from pathlib import Path
from email.message import EmailMessage
from email.utils import make_msgid
from imap_tools import MailBox
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.config import get_settings
from backend.app.mail.gmail import locate


def main() -> None:
    c=get_settings()
    users=[('USER',c.user_email,c.user_email_app_password.get_secret_value()),('DEMO',c.demo_company_email,c.demo_company_app_password.get_secret_value())]
    for label,address,password in users:
        with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=20) as smtp: smtp.login(address,password)
        print(f'PASS {label} SMTP authentication',flush=True)
        with MailBox('imap.gmail.com',timeout=20).login(address,password): pass
        print(f'PASS {label} IMAP authentication',flush=True)
    tests=[]
    for source,target in [(users[0],users[1]),(users[1],users[0])]:
        message=EmailMessage();message['From']=source[1];message['To']=target[1]
        message['Subject']='Shikayat connectivity verification '+uuid4().hex;message['Message-ID']=make_msgid()
        message.set_content('Authorized Shikayat mailbox connectivity test. No customer evidence attached.')
        with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=20) as smtp:
            smtp.login(source[1],source[2]);smtp.send_message(message)
        print(f'PASS {source[0]} → {target[0]} SMTP handoff',flush=True)
        tests.append((source,target,message))
    end=time.monotonic()+120
    pending=list(tests)
    while pending and time.monotonic()<end:
        for item in pending[:]:
            source,target,message=item
            with MailBox('imap.gmail.com',timeout=20).login(target[1],target[2]) as box:
                found=locate(box,str(message['Message-ID']),str(message['Subject']))
            if found:
                print(f'PASS {source[0]} → {target[0]} IMAP receipt; folders={found}',flush=True);pending.remove(item)
        if pending: time.sleep(5)
    if pending:
        for source,target,message in tests:
            for label,address,password in users:
                with MailBox('imap.gmail.com',timeout=20).login(address,password) as box:
                    found=locate(box,str(message['Message-ID']),str(message['Subject']))
                print(f'FOLDER REPORT {source[0]} → {target[0]} in {label}: {found or "not found"}',flush=True)
        raise TimeoutError('Receipt not found in discovered All Mail/Spam folders within 120 seconds')

if __name__=='__main__':
    try: main()
    except Exception as error:
        c=get_settings();safe=str(error)
        for secret in [c.openai_api_key.get_secret_value(),c.user_email_app_password.get_secret_value(),c.demo_company_app_password.get_secret_value()]:
            if secret: safe=safe.replace(secret,'[REDACTED]')
        print(f'FAIL {type(error).__name__}: {safe}',flush=True);raise SystemExit(1)

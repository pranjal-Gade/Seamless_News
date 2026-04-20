#!/usr/bin/env python
"""
Direct publish & PDF test - simulates the publish action without going through the web interface
"""
import os
import sys
import threading
import datetime

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from config import Config
except ImportError:
    print("ERROR: Could not import Config")
    sys.exit(1)

import mysql.connector

def _raw_conn(db_cfg: dict):
    return mysql.connector.connect(**db_cfg)

def _get_db_cfg():
    return {
        "host": getattr(Config, "MYSQL_HOST", "localhost"),
        "user": getattr(Config, "MYSQL_USER", "root"),
        "password": getattr(Config, "MYSQL_PASSWORD", ""),
        "database": getattr(Config, "MYSQL_DB", "news_scrapping"),
    }

def _get_mail_cfg():
    return {
        "smtp_server": getattr(Config, "MAIL_SERVER", "smtp.gmail.com"),
        "smtp_port": getattr(Config, "MAIL_PORT", 587),
        "sender": getattr(Config, "MAIL_FROM", ""),
        "username": getattr(Config, "MAIL_USERNAME", ""),
        "password": getattr(Config, "MAIL_PASSWORD", ""),
    }

# Get a test article
db_cfg = _get_db_cfg()
c = _raw_conn(db_cfg)
cur = c.cursor(dictionary=True)

print("Fetching non-published articles...")
cur.execute(
    "SELECT id, news_date, news_type, news_headline, "
    "news_text, news_url, keywords, date_of_insert "
    "FROM non_published_news WHERE published=0 LIMIT 1"
)
article = cur.fetchone()
cur.close()
c.close()

if not article:
    print("ERROR: No non-published articles found!")
    sys.exit(1)

print(f"\n✓ Found article: {article['news_headline'][:60]}")
print(f"  Keys: {list(article.keys())}")
print(f"  Text length: {len(article['news_text'])} chars")
print(f"\nNow simulating publish action...")

# Insert into published_news
c = _raw_conn(db_cfg)
cur = c.cursor()

now = datetime.datetime.now()

cur.execute(
    "INSERT INTO published_news "
    "(source_id, news_date, news_type, news_headline, "
    "news_text, news_url, keywords, date_of_insert, published_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
    (
        article["id"],
        article["news_date"],
        article["news_type"],
        article["news_headline"],
        article["news_text"],
        article["news_url"],
        article["keywords"],
        article["date_of_insert"],
        now,
    )
)
c.commit()
pub_id = cur.lastrowid
print(f"✓ Inserted into published_news with ID={pub_id}")

# Delete from non_published
cur.execute("DELETE FROM non_published_news WHERE id=%s", (article["id"],))
c.commit()
print(f"✓ Deleted from non_published_news")
cur.close()
c.close()

# Now call the background PDF function
print(f"\nStarting background PDF generation thread...")

from app.routes.main import _bg_pdf_email

pdf_folder = os.path.join(os.path.dirname(__file__), "static", "pdfs")
os.makedirs(pdf_folder, exist_ok=True)

try:
    cur = _raw_conn(_get_db_cfg()).cursor(dictionary=True)
    cur.execute("SELECT * FROM user_settings WHERE id=1")
    settings = cur.fetchone() or {}
    cur.close()
except Exception:
    settings = {}

# Wrap the thread call with exception handler
def thread_wrapper():
    try:
        print("\n[THREAD] Starting PDF+EMAIL generation...")
        _bg_pdf_email(
            db_cfg=_get_db_cfg(),
            mail_cfg=_get_mail_cfg(),
            template_dir=os.path.join(os.path.dirname(__file__), "app", "templates", "main"),
            articles=[article],  # Pass the article dict
            pub_ids=[pub_id],
            pdf_folder=pdf_folder,
            settings=settings,
            pdf_workers=1,
        )
        print("\n[THREAD] Background thread completed successfully!")
    except Exception as e:
        print(f"\n[THREAD ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

thread = threading.Thread(target=thread_wrapper, daemon=True)
thread.start()
thread.join(timeout=30)  # Wait up to 30 seconds

if thread.is_alive():
    print("\n⚠ Thread still running after 30s (may still be working)")
else:
    print("\n✓ Thread completed")

# Check if PDF was created
pdf_path = os.path.join(pdf_folder, f"news_{pub_id}.pdf")
print(f"\nChecking for PDF file: {pdf_path}")
if os.path.exists(pdf_path):
    size = os.path.getsize(pdf_path)
    print(f"✓ PDF FILE CREATED! Size: {size} bytes")
    
    # Check database
    c = _raw_conn(_get_db_cfg())
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT pdf_path FROM published_news WHERE id=%s", (pub_id,))
    row = cur.fetchone()
    cur.close()
    c.close()
    
    if row and row.get("pdf_path"):
        print(f"✓ DATABASE UPDATED! pdf_path = {row['pdf_path']}")
    else:
        print(f"⚠ DATABASE NOT UPDATED (pdf_path still NULL)")
else:
    print(f"✗ PDF FILE NOT CREATED")
    print(f"  Checked path: {pdf_path}")
    print(f"  Directory contents:")
    for f in os.listdir(pdf_folder):
        fp = os.path.join(pdf_folder, f)
        if os.path.isfile(fp):
            print(f"    {f} ({os.path.getsize(fp)} bytes)")

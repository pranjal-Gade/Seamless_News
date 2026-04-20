# PDF Generation - Quick Start Verification Guide

## What Was Wrong

The PDF generation system **WAS using database data correctly**, but had two critical issues:

1. **Data Truncation Bug** - Article content (headline, type, keywords) was being truncated when inserted into the published_news table because VARCHAR column sizes were too small
2. **Silent Failures** - When generation failed, there was minimal logging to diagnose why

## What's Fixed

✅ Database columns expanded (VARCHAR → LONGTEXT) to prevent truncation
✅ Automatic schema migration on startup
✅ Enhanced error logging and diagnostics
✅ Better article data validation
✅ Parallel PDF generation (3 workers by default)

## Test It Now

### Step 1: Restart Application
Your app needs to restart to run the schema migration:
```powershell
# Kill current Flask app (Ctrl+C if in terminal)
# Then restart: python ./run.py
```

You should see this in console:
```
[DB] Schema migration completed
```

### Step 2: Publish a Test Article
1. Go to "News Processing" → "All Non-Published News"
2. Select one article
3. Click "Publish" button
4. Publish form should show dialog with PDF generation message

### Step 3: Monitor Console Output
Look for these messages in the running Flask console:

```
[BG] Starting PDF generation for pub_id=105
[BG] Headline     : Your article headline (no truncation)
[BG] Text length  : 2456 chars
[BG] Generating 1 PDFs with 3 workers
[PDF] Generating PDF: d:\newapp_seam\news_scrapper\static\pdfs\news_105.pdf
[PDF] Article keys: ['id', 'news_date', 'news_type', 'news_headline', ...]
[PDF] Title: Your full headline text
[PDF] Text length: 2456 chars
[PDF] Keywords: 5 items
[PDF] ✓ Generated successfully: ... (28456 bytes)
[BG] PDF file exists for pub_id=105, size=28456 bytes
[BG] DB updated with pdf_path=news_105.pdf for pub_id=105
```

### Step 4: Check Frontend
1. Navigate to "Today's Published News"
2. Your newly published article should have:
   - "Generating..." spinner → replaced with 📄 download button (within 10 seconds)
3. Click the 📄 button to download PDF
4. **Verify PDF contains:**
   - Full article headline (not truncated)
   - Full article text
   - All keywords
   - Article date, type, source URL

## If PDFs Still Not Generating

### Check These Logs
```
[BG ERROR]        ← Article validation failed
[PDF ERROR]       ← PDF generation failed
[PDF] Traceback   ← ReportLab issue
[DB]              ← Schema migration problem
```

### Verify Database
```sql
-- Check that columns are LONGTEXT
DESCRIBE published_news;
-- Should show:
-- news_type       LONGTEXT
-- news_headline   LONGTEXT  
-- keywords        LONGTEXT
```

### Verify Folder Permissions
```powershell
# Check static/pdfs folder exists and is writable
Test-Path "d:\newapp_seam\news_scrapper\static\pdfs"
Get-Item -Path "d:\newapp_seam\news_scrapper\static\pdfs" | Format-List
```

### Check PDF Worker Configuration
In your running app, PDFs should generate in parallel:
- When publishing multiple articles, should see multiple `[BG] Starting PDF generation` messages
- Currently configured for 3 concurrent workers (configurable in config.py: `PDF_WORKERS = 3`)

## Configuration

To change number of workers, edit `config.py`:
```python
class Config:
    PDF_WORKERS = 3    # Change this number (1-5 recommended)
```

## Expected Behavior Timeline

After clicking "Publish":
1. **Immediate**: Page shows success message "PDFs are being generated..."
2. **0-2 sec**: Background thread starts, logs appear
3. **2-5 sec**: PDF file generated and written to disk
4. **5-8 sec**: Database updated with pdf_path
5. **~10 sec**: Frontend polling detects PDF ready, replaces spinner with download button

If any step takes longer than expected, check the console logs for `[BG ERROR]` or `[PDF ERROR]` messages.

## Files to Review

- **Main Flow**: `app/routes/main.py` - Look for `_bg_pdf_email()` and `_generate_and_store_pdf()`
- **PDF Builder**: `app/pdf_generator.py` - Look for `generate_pdf_from_article()`
- **Database**: `app/db.py` - Look for schema migration code
- **Config**: `config.py` - PDF settings

## Success Indicators

✅ Console shows detailed `[PDF]` diagnostic messages
✅ No `[BG ERROR]` or `[PDF ERROR]` messages
✅ Generated PDF files appear in `static/pdfs/news_*.pdf`
✅ Frontend button changes from "Generating" to download link
✅ Downloaded PDF contains complete article data (no truncation)

---

**Still having issues?** Check the detailed analysis in:
- `PDF_GENERATION_ANALYSIS.md` - Technical diagnosis
- `PDF_GENERATION_FIXES_APPLIED.md` - What was fixed

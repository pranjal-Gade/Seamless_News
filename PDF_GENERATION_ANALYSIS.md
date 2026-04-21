# PDF Generation Flow Analysis

## Data Flow
1. **Publish Route** (`/all-non-published-news/actions`, POST)
   - Fetches articles from `non_published_news` table with columns:
     - id, news_date, news_type, news_headline, news_text, news_url, keywords, date_of_insert
   - Inserts into `published_news` table (with source_id, published_at added)
   - Passes article dicts (from non_published_news) to `_bg_pdf_email()` in background thread

2. **Background PDF Generation** (`_bg_pdf_email()`)
   - Receives: articles (list of dicts), pub_ids (new IDs from published_news)
   - Calls `_generate_and_store_pdf(article, pub_id)` for each pair
   - Updates `published_news.pdf_path` in DB after successful generation
   - Triggers email sending if configured

3. **PDF Generation** (`generate_pdf_from_article()`)
   - Input: article_data dict with keys:
     - news_headline, keywords, news_text, news_date, news_type, news_url
   - Steps:
     - Cleans text (HTML unescaping, tag removal, whitespace normalization)
     - Formats keywords (splits by comma if string, cleans each)
     - Builds ReportLab Platypus story with styled paragraphs
     - Generates PDF via doc.build()
     - Returns True if file exists and size > 500 bytes

## Confirmed Issues & Fixes

### ISSUE 1: Database Column Size Mismatch
**Problem**: published_news has VARCHAR limits but non_published_news uses LONGTEXT
- `news_headline`: VARCHAR(500) vs LONGTEXT → Data truncation on insert
- `news_type`: VARCHAR(255) vs LONGTEXT → Data truncation on insert
- `keywords`: VARCHAR(255) vs LONGTEXT → Data truncation on insert

**Impact**: If original article data exceeds VARCHAR limits, it gets truncated during INSERT into published_news

**Solution**: Expand VARCHAR columns to TEXT/LONGTEXT, or pass original non_published_news data

### ISSUE 2: Missing PDF_WORKERS Import
**Current**: main.py uses `concurrent.futures` but not imported before _bg_pdf_email function definition

**Impact**: If pdf_workers > 1, ThreadPoolExecutor call will fail with NameError

**Solution**: Ensure import is at top of file (ALREADY FIXED in header)

### ISSUE 3: Potential Special Characters in Keywords
**Problem**: PDF generator receives keywords as string or list, but PDF writing may fail with special characters

**Impact**: Keywords with quotes, angle brackets, XML special chars could crash ReportLab

**Solution**: Already handled by safe_para() function with escape() - but verify it works

### ISSUE 4: Empty/None Article Text Handling
**Current**: If news_text is empty/None, replaced with "No article content available."

**Verified**: Working correctly with clean_text() null checking

### ISSUE 5: PDF File Output Permissions
**Problem**: os.makedirs() may fail if disk full or permissions denied

**Impact**: PDF generation fails silently if file write fails

**Solution**: Better error reporting needed (see below)

### ISSUE 6: First Call to _bg_pdf_email Missing pdf_workers
**Location**: Line 517 in _bg_scraper() 
**Problem**: Keyword arguments call doesn't pass pdf_workers parameter
**Impact**: Uses default pdf_workers=3 (fine) but inconsistent with publish route

**Solution**: Add pdf_workers parameter to call

## Recommended Fixes (Priority Order)

### CRITICAL
1. Fix VARCHAR column sizes in published_news schema
2. Enhance error logging in PDF generator and background tasks
3. Verify TextIO/file writing permissions

### HIGH
4. Ensure concurrent.futures import is present
5. Add pdf_workers to all _bg_pdf_email calls for consistency
6. Test with real article data containing special characters

### MEDIUM
7. Add timeout handling for PDF generation
8. Add retry logic for failed PDFs
9. Better progress reporting to frontend (current: 8-second polling)

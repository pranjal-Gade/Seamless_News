#!/usr/bin/env python
"""
Direct PDF generation test - bypass Flask/threading
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.pdf_generator import generate_pdf_from_article

# Test data
test_article = {
    'news_headline': 'Test Article: This Is A Long Headline To Test PDF Generation',
    'news_type': 'Agriculture',
    'news_date': '2026-04-15',
    'news_url': 'https://example.com/article',
    'keywords': 'agriculture, farming, crops, weather',
    'news_text': '''This is a test article with multiple paragraphs.

The PDF generator should properly handle this content and create a formatted PDF document.

Here is another paragraph with some details about the article content.

The system should preserve all the data from the database without any truncation.
'''
}

output_path = os.path.join(os.path.dirname(__file__), 'static', 'pdfs', 'test_pdf.pdf')

print(f"Testing PDF generation...")
print(f"Output path: {output_path}")
print(f"Article keys: {list(test_article.keys())}")

result = generate_pdf_from_article(article_data=test_article, output_path=output_path)

print(f"\nResult: {result}")
if os.path.exists(output_path):
    size = os.path.getsize(output_path)
    print(f"File created: {output_path}")
    print(f"File size: {size} bytes")
else:
    print(f"ERROR: File not created at {output_path}")

import feedparser
import json
import os
import time
import asyncio
import aiohttp
from deep_translator import GoogleTranslator
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from keyword_extractor import KeywordExtractor
from bs4 import BeautifulSoup
from config import config
from logger import logger
from date_utils import DateHandler

# Define cache file paths using config
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), config['cache']['directory'])
TRANSLATION_CACHE_FILE = os.path.join(CACHE_DIR, config['cache']['translation']['file'])
FEED_CACHE_FILE = os.path.join(CACHE_DIR, config['cache']['feed']['file'])

def ensure_cache_dir():
    """Ensure cache directory exists"""
    os.makedirs(CACHE_DIR, exist_ok=True)

def load_cache(cache_file):
    """Load cache from file"""
    try:
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading cache: {e}")
    return {}

def save_cache(cache_data, cache_file):
    """Save cache to file"""
    try:
        ensure_cache_dir()
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving cache: {e}")

def ensure_cache_files():
    """Ensure both cache files exist with valid JSON content"""
    ensure_cache_dir()
    
    # Initialize both cache files if they don't exist
    cache_files = [TRANSLATION_CACHE_FILE, FEED_CACHE_FILE]
    
    for cache_file in cache_files:
        if not os.path.exists(cache_file):
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump({}, f)
                logger.info(f"Created cache file: {cache_file}")
            except Exception as e:
                logger.error(f"Error creating cache file {cache_file}: {e}")

# Call this function during initialization
ensure_cache_files()

class TranslationCache:
    def __init__(self):
        ensure_cache_files()  # Ensure cache files exist before loading
        self.cache = load_cache(TRANSLATION_CACHE_FILE)
        self.max_size = config['cache']['translation']['max_size']
        logger.info(f"Initialized translation cache with {len(self.cache)} entries")

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value):
        self.cache[key] = value
        if len(self.cache) > self.max_size:
            # Remove oldest 20% of entries when cache is full
            items = sorted(self.cache.items(), key=lambda x: x[1].get('timestamp', 0))
            self.cache = dict(items[int(self.max_size * 0.2):])
        self.save()

    def save(self):
        save_cache(self.cache, TRANSLATION_CACHE_FILE)

class FeedCache:
    def __init__(self):
        ensure_cache_files()  # Ensure cache files exist before loading
        self.cache = load_cache(FEED_CACHE_FILE)
        self.cache_duration = timedelta(hours=config['cache']['feed']['duration_hours'])
        logger.info(f"Initialized feed cache with {len(self.cache)} entries")

    def get(self, url):
        if url in self.cache:
            cached_data = self.cache[url]
            cached_time = datetime.fromisoformat(cached_data['timestamp'])
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data['data']
        return None

    def set(self, url, data):
        self.cache[url] = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        self.save()

    def save(self):
        save_cache(self.cache, FEED_CACHE_FILE)

# Initialize caches
translation_cache = TranslationCache()
feed_cache = FeedCache()

def is_recent(date_str, hours=720):
    return DateHandler.is_recent(date_str, hours)

async def translate_text_async(text):
    """Translate text with caching"""
    cached = translation_cache.get(text)
    if cached:
        return cached

    try:
        translator = GoogleTranslator(
            source=config['translation']['source_language'],
            target=config['translation']['target_language']
        )
        translated = translator.translate(text)
        
        translation_cache.set(text, {
            'translation': translated,
            'timestamp': datetime.now().isoformat()
        })
        
        return translated
    except Exception as e:
        print(f"Translation failed: {str(e)}")
        return text

async def process_entry(entry, source_title, url):
    """Process a single feed entry"""
    try:
        translated_title = await translate_text_async(entry.title)
        
        # Get description from the entry
        description = ''
        if hasattr(entry, 'summary'):
            description = entry.summary
        elif hasattr(entry, 'description'):
            description = entry.description
        elif hasattr(entry, 'content'):
            description = entry.content[0].value if entry.content else ''
        
        # Translate description if it exists
        translated_description = ''
        if description:
            try:
                translated_description = await translate_text_async(description)
                # Clean up description (remove HTML tags if present)
                if isinstance(translated_description, str):
                    soup = BeautifulSoup(translated_description, 'html.parser')
                    translated_description = soup.get_text(separator=' ', strip=True)
                    # Truncate if too long
                    if len(translated_description) > 300:
                        translated_description = translated_description[:297] + '...'
            except Exception as e:
                print(f"Error processing description: {e}")
                translated_description = ''
        
        # Extract keywords for categorization
        keyword_extractor = KeywordExtractor.create_default()
        text_for_keywords = f"{translated_title} {translated_description}"
        keywords = keyword_extractor.extract_keywords(text_for_keywords)
        
        # Determine category
        category = keyword_extractor.categorize_content(keywords)
        
        # Debug print
        print(f"Successfully processed: {translated_title}")
        print(f"Description length: {len(translated_description)}")
        
        return {
            'title': translated_title,
            'link': entry.link,
            'source': source_title if source_title else url,
            'published': entry.get('published', 'No date'),
            'description': translated_description,
            'keywords': keywords,
            'category': category
        }
    except Exception as e:
        print(f"Error in process_entry: {e}")
        # Return a minimal valid entry if there's an error
        return {
            'title': getattr(entry, 'title', 'No title'),
            'link': getattr(entry, 'link', '#'),
            'source': source_title if source_title else url,
            'published': entry.get('published', 'No date'),
            'description': '',
            'keywords': [],
            'category': 'Other'
        }

def load_feed_urls():
    """Load and validate feed URLs"""
    try:
        if not os.path.exists('feeds.txt'):
            print("Error: feeds.txt file not found!")
            return []
            
        with open('feeds.txt', 'r', encoding='utf-8') as file:
            urls = [line.strip() for line in file if line.strip() and not line.startswith('#')]
            
        if not urls:
            print("Warning: No valid URLs found in feeds.txt")
        else:
            print(f"Loaded {len(urls)} URLs from feeds.txt:")
            for url in urls:
                print(f"  - {url}")
            
        return urls
    except Exception as e:
        print(f"Error loading feed URLs: {e}")
        return []

async def process_feed(url):
    """Process feed with caching"""
    feed_cache = FeedCache()
    
    # Try to get from cache first
    cached_data = feed_cache.get(url)
    if cached_data:
        print(f"Using cached data for {url}")
        return cached_data
    
    print(f"\nProcessing feed: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        async with aiohttp.ClientSession() as session:
            print(f"Fetching {url}")
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status != 200:
                    print(f"HTTP error {response.status} for {url}")
                    return []
                
                feed_data = await response.text()
                feed = feedparser.parse(feed_data)
                
                if not feed.entries:
                    print(f"No entries found in {url}")
                    return []
                
                source_title = feed.feed.get('title', '')
                recent_entries = feed.entries[:10]  # Get latest 10 entries
                
                processed_entries = []
                for entry in recent_entries:
                    try:
                        processed_entry = await process_entry(entry, source_title, url)
                        if processed_entry:
                            processed_entries.append(processed_entry)
                    except Exception as e:
                        print(f"Error processing entry: {e}")
                        continue
                
                # Cache the processed entries
                feed_cache.set(url, processed_entries)
                
                print(f"Successfully processed {len(processed_entries)} entries from {url}")
                logger.info(f"Successfully processed feed: {url}")
                return processed_entries
                
    except Exception as e:
        logger.error(f"Error processing feed {url}: {e}")
        return []

def generate_feed_report(analytics):
    """Generate a report of feed processing metrics"""
    try:
        report_file = os.path.join(CACHE_DIR, config['reports']['feed_report'])
        
        # Calculate metrics
        feeds_count = analytics['feeds_processed']
        total_time = analytics.get('processing_time_seconds', 0)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"Feed Processing Report\n")
            f.write(f"=====================\n\n")
            f.write(f"Timestamp: {analytics['timestamp']}\n")
            f.write(f"Metrics:\n")
            f.write(f"    feeds_processed: {feeds_count}\n")
            f.write(f"    total_entries: {analytics['total_entries']}\n")
            f.write(f"    processing_time: {total_time:.1f}s\n")
            # Add check for zero division
            if total_time > 0:
                f.write(f"    feeds_per_second: {feeds_count/total_time:.1f}\n")
            else:
                f.write(f"    feeds_per_second: N/A\n")
            
            # Cache metrics
            f.write(f"\nCache Performance:\n")
            f.write(f"    hits: {analytics.get('cache_hits', 0)}\n")
            f.write(f"    misses: {analytics.get('cache_misses', 0)}\n")
            
            # Errors
            if analytics.get('errors'):
                f.write(f"\nErrors:\n")
                for error in analytics['errors']:
                    f.write(f"    - {error}\n")
            
            # Feed metrics
            f.write(f"\nPer-Feed Metrics:\n")
            for metric in analytics.get('feed_metrics', []):
                f.write(f"\n    {metric['url']}:\n")
                f.write(f"        entries: {metric['entries_processed']}\n")
                if metric.get('categories'):
                    f.write(f"        categories:\n")
                    for category, count in metric['categories'].items():
                        f.write(f"            {category}: {count}\n")
                        
    except Exception as e:
        logger.error(f"Error generating feed report: {e}")

def save_feed_entries(entries):
    """Save feed entries to a JSON file"""
    output_dir = 'data'
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, 'feed_entries.json')
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(entries)} entries to {output_file}")
    except Exception as e:
        print(f"Error saving feed entries: {e}")

async def get_feeds_async():
    """Get all feeds with configurable time filter"""
    start_time = datetime.now()
    analytics = {
        'timestamp': start_time.isoformat(),
        'feeds_processed': 0,
        'total_entries': 0,
        'entries_by_category': {},
        'feed_metrics': [],
        'errors': [],
        'cache_hits': 0,
        'cache_misses': 0,
        'processing_time_seconds': 0
    }
    
    feed_urls = load_feed_urls()
    if not feed_urls:
        print("No feeds to process")
        return []
    
    # Process all feeds concurrently
    tasks = [process_feed(url) for url in feed_urls]
    results = await asyncio.gather(*tasks)
    
    # Flatten results list and collect all entries without time filtering
    all_entries = []
    for url, entries in zip(feed_urls, results):
        all_entries.extend(entries)
        analytics['feed_metrics'].append({
            'url': url,
            'entries_processed': len(entries),
            'categories': {
                category: sum(1 for e in entries if e.get('category') == category)
                for category in set(e.get('category', 'Other') for e in entries)
            }
        })
    
    # Update analytics
    analytics['total_entries'] = len(all_entries)
    analytics['feeds_processed'] = len(feed_urls)
    
    # Generate report and save entries
    generate_feed_report(analytics)
    save_feed_entries(all_entries)
    
    return all_entries

def get_feeds():
    return asyncio.run(get_feeds_async())

def format_date(date_str):
    """Format date string to show only day and month"""
    try:
        if not date_str or date_str == 'No date':
            return 'No date'
            
        # Parse the date string
        if isinstance(date_str, str):
            try:
                # Try RFC 2822 format first (common in RSS feeds)
                date = parsedate_to_datetime(date_str)
            except:
                try:
                    # Try ISO format
                    date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    print(f"Unparseable date format: {date_str}")
                    return date_str
        else:
            return str(date_str)

        # Format to "22 Nov" style
        return date.strftime("%d %b")
                
    except Exception as e:
        print(f"Error formatting date: {e}")
        return date_str
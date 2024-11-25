from flask import Flask, render_template, url_for, request
from feed_parser import get_feeds
from collections import defaultdict
from date_utils import DateHandler
from config import config

app = Flask(__name__, static_url_path='/static')

@app.route('/')
def hello_world():
    time_filter = request.args.get('time_filter', '24')
    try:
        time_filter = int(time_filter)
    except ValueError:
        time_filter = 24  # Default to 24 hours if invalid value
    
    # Get all feeds
    feeds = get_feeds()
    
    # Filter feeds based on age
    filtered_feeds = []
    date_handler = DateHandler()
    for feed in feeds:
        age_hours = date_handler.get_age_hours(feed.get('published', 'No date'))
        if age_hours is not None and age_hours < time_filter:
            filtered_feeds.append(feed)
    
    # Organize filtered feeds by category
    categorized_feeds = defaultdict(list)
    for feed in filtered_feeds:
        category = feed.get('category', 'Other')
        categorized_feeds[category].append(feed)
    
    # Sort categories
    sorted_categories = sorted(
        categorized_feeds.keys(),
        key=lambda x: ('ZZZ' if x == 'Other' else x)
    )
    
    # Time filter options
    time_filters = [
        {'hours': 24, 'label': 'Last 24 hours'},
        {'hours': 48, 'label': 'Last 2 days'},
        {'hours': 168, 'label': 'Last week'},
        {'hours': 720, 'label': 'Last month'}
    ]
    
    return render_template('index.html',
                         categorized_feeds=categorized_feeds,
                         categories=sorted_categories,
                         time_filters=time_filters,
                         current_filter=time_filter)

@app.template_filter('format_date')
def format_date_filter(date_str):
    return DateHandler.format_date(date_str)

@app.template_filter('get_age_hours')
def get_age_hours_filter(date_str):
    return DateHandler.get_age_hours(date_str)

if __name__ == '__main__':
    app.run(
        host=config['api']['host'],
        port=config['api']['port'],
        debug=config['api']['debug']
    ) 
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from logger import logger

class DateHandler:
    @staticmethod
    def parse_date(date_str):
        """Parse date string in various formats"""
        try:
            if not date_str or date_str == 'No date':
                return None
                
            if isinstance(date_str, str):
                try:
                    # Try RFC 2822 format first (common in RSS feeds)
                    return parsedate_to_datetime(date_str)
                except:
                    try:
                        # Try ISO format with timezone
                        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    except:
                        try:
                            # Try parsing without timezone and make it timezone-aware
                            date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f')
                            return date.replace(tzinfo=timezone.utc)
                        except:
                            logger.warning(f"Unparseable date format: {date_str}")
                            return None
            return None
        except Exception as e:
            logger.error(f"Date parsing error: {e}")
            return None

    @staticmethod
    def get_age_hours(date_str):
        """Calculate how many hours old an article is"""
        parsed_date = DateHandler.parse_date(date_str)
        if not parsed_date:
            return None
            
        # Ensure now is timezone-aware with UTC
        now = datetime.now(timezone.utc)
        
        # Ensure parsed_date is timezone-aware
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            
        age = now - parsed_date
        return age.total_seconds() / 3600

    @staticmethod
    def is_recent(date_str, hours=720):
        """Check if date is within specified hours"""
        parsed_date = DateHandler.parse_date(date_str)
        if not parsed_date:
            return True  # Accept entries with unparseable dates during testing
            
        # Ensure now is timezone-aware with UTC
        now = datetime.now(timezone.utc)
        
        # Ensure parsed_date is timezone-aware
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            
        time_threshold = now - timedelta(hours=hours)
        return parsed_date > time_threshold

    @staticmethod
    def format_date(date_str):
        """Format date as day and month"""
        parsed_date = DateHandler.parse_date(date_str)
        if not parsed_date:
            return 'No date'
            
        # Ensure parsed_date is timezone-aware
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            
        return parsed_date.strftime("%d %b") 
import logging
from logging.handlers import RotatingFileHandler
from config import config

def setup_logger():
    """Configure logging based on config settings"""
    log_config = config['logging']
    
    logger = logging.getLogger('feed_parser')
    logger.setLevel(log_config['level'])
    
    handler = RotatingFileHandler(
        log_config['file'],
        maxBytes=log_config['max_size_mb'] * 1024 * 1024,
        backupCount=log_config['backup_count']
    )
    
    formatter = logging.Formatter(log_config['format'])
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

# Global logger instance
logger = setup_logger() 
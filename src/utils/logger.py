import logging
from logging.handlers import RotatingFileHandler

def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger instance.

    Args:
        name (str): The name of the logger, typically __name__.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)

    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)

    log_file = "logs/app.log"

    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)-6s | %(name)s | %(filename)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_h = logging.StreamHandler()
    console_h.setLevel(logging.WARNING)
    console_h.setFormatter(formatter)

    file_h = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(formatter)

    logger.addHandler(console_h)
    logger.addHandler(file_h)

    logger.propagate = False

    return logger
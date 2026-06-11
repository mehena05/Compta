"""
إعداد التسجيل الموحد للنظام
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """إرجاع logger مُعدّ مسبقاً باسم الموديول"""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


def configure_file_logging(log_path: Path, level: str = "INFO") -> None:
    """إضافة مُسجّل ملف للـ root logger"""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    root = logging.getLogger()
    root.addHandler(file_handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

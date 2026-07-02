"""结构化日志工具"""
import logging
import sys
from pathlib import Path


def setup_logger(name: str = "liuyao", level: str = "INFO") -> logging.Logger:
    """初始化项目日志器。

    Args:
        name: logger 名称
        level: 日志级别

    Returns:
        配置好的 logging.Logger 实例
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件 handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "liuyao.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()

import os
import sys
import inspect


class Logger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._init_logger()

    def _init_logger(self):
        try:
            from loguru import logger
            self.logger = logger
            self._setup_logger()
        except ImportError:
            self.logger = None

    def _get_log_level_from_env(self):
        """从环境变量获取日志级别，避免循环导入"""
        return os.environ.get("LOG_LEVEL", "ERROR").upper()

    def _setup_logger(self):
        # 移除默认handler
        self.logger.remove()

        # 从环境变量获取日志级别
        level = self._get_log_level_from_env()

        # 设置格式
        format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[filename]}</cyan>:<cyan>{extra[function]}</cyan>:<cyan>{extra[lineno]}</cyan> | "
            "<level>{message}</level>"
        )

        self.handler_id = self.logger.add(
            sys.stderr,
            level=level,
            format=format,
            colorize=True,
            backtrace=True,
            diagnose=True
        )

    def set_level(self, level):
        """动态设置日志级别"""
        if self.logger and hasattr(self, 'handler_id'):
            try:
                # 移除旧的handler
                self.logger.remove(self.handler_id)

                # 设置格式
                format = (
                    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                    "<level>{level: <8}</level> | "
                    "<cyan>{extra[filename]}</cyan>:<cyan>{extra[function]}</cyan>:<cyan>{extra[lineno]}</cyan> | "
                    "<level>{message}</level>"
                )

                # 添加新的handler
                self.handler_id = self.logger.add(
                    sys.stderr,
                    level=level,
                    format=format,
                    colorize=True,
                    backtrace=True,
                    diagnose=True
                )
                return True
            except Exception as e:
                print(f"Failed to set log level: {e}")
                return False
        return False

    def _get_caller_info(self):
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back.f_back
            full_path = caller_frame.f_code.co_filename
            function = caller_frame.f_code.co_name
            lineno = caller_frame.f_lineno

            filename = os.path.basename(full_path)

            return {
                'filename': filename,
                'function': function,
                'lineno': lineno
            }
        finally:
            del frame

    def info(self, message, source="API"):
        if self.logger:
            caller_info = self._get_caller_info()
            self.logger.bind(**caller_info).info(f"[{source}] {message}")
        else:
            print(f"[INFO] [{source}] {message}")

    def error(self, message, source="API"):
        if self.logger:
            caller_info = self._get_caller_info()
            if isinstance(message, Exception):
                self.logger.bind(**caller_info).exception(f"[{source}] {str(message)}")
            else:
                self.logger.bind(**caller_info).error(f"[{source}] {message}")
        else:
            print(f"[ERROR] [{source}] {message}")

    def warning(self, message, source="API"):
        if self.logger:
            caller_info = self._get_caller_info()
            self.logger.bind(**caller_info).warning(f"[{source}] {message}")
        else:
            print(f"[WARNING] [{source}] {message}")

    def debug(self, message, source="API"):
        if self.logger:
            caller_info = self._get_caller_info()
            self.logger.bind(**caller_info).debug(f"[{source}] {message}")
        else:
            print(f"[DEBUG] [{source}] {message}")


logger = Logger()

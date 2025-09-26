import os
import sys
import inspect


class Logger:
    def __init__(self, level="INFO", colorize=True, format=None):
        try:
            from loguru import logger
            self.logger = logger
            logger.remove()
            
            if format is None:
                format = (
                    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                    "<level>{level: <8}</level> | "
                    "<cyan>{extra[filename]}</cyan>:<cyan>{extra[function]}</cyan>:<cyan>{extra[lineno]}</cyan> | "
                    "<level>{message}</level>"
                )
            
            logger.add(
                sys.stderr,
                level=level,
                format=format,
                colorize=colorize,
                backtrace=True,
                diagnose=True
            )
        except ImportError:
            self.logger = None
        
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


logger = Logger(level="INFO")

"""
observability.py - TargetMind Telemetry and Tracing
===================================================
 observability and monitoring engine for your application
Provides structured logging for multi-agent workflows.
Tracks token usage, execution time, and errors for every LLM interaction.

Usage:
    from observability import setup_logging, log_agent_call, log_error

    logger = setup_logging()
    
    @log_agent_call(agent_name="SearchAgent")
    def my_search_function(query):
        ...
"""

import json
import logging
import time
import uuid
import os
from datetime import datetime, timezone
from functools import wraps

# Setup structured JSON logger
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "targetmind_telemetry.log")

def setup_logging():
    logger = logging.getLogger("TargetMindTelemetry")
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate handlers if called multiple times
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        
        # We use a custom formatter to ensure everything is valid JSON per line
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                    "level": record.levelname,
                    "event": record.getMessage(),
                }
                
                # Merge in any extra kwargs passed via logger.info(..., extra={"key": "value"})
                if hasattr(record, "telemetry_data"):
                    log_record.update(record.telemetry_data)
                    
                return json.dumps(log_record)

        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
        
    return logger

telemetry_logger = setup_logging()

def log_error(context: str, error: Exception, **kwargs):
    """Log an error with context."""
    telemetry_data = {
        "context": context,
        "error_type": type(error).__name__,
        "error_message": str(error),
        **kwargs
    }
    telemetry_logger.error("error", extra={"telemetry_data": telemetry_data})

def log_agent_call(agent_name: str):
    """
    Decorator to trace an agent function call.
    Captures latency, inputs, and outputs.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            trace_id = str(uuid.uuid4())
            start_time = time.perf_counter()
            
            # Log the start of the call
            telemetry_logger.info("agent_call_start", extra={"telemetry_data": {
                "trace_id": trace_id,
                "agent": agent_name,
                "action": "start"
            }})
            
            try:
                # Execute the actual agent function
                result = func(*args, **kwargs)
                
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                
                # Optional: if the result is a Phi Agent RunResponse, we could try to extract token metrics here
                # For now, we capture success and latency
                
                telemetry_logger.info("agent_call_complete", extra={"telemetry_data": {
                    "trace_id": trace_id,
                    "agent": agent_name,
                    "action": "complete",
                    "latency_ms": latency_ms,
                    "status": "success"
                }})
                
                return result
                
            except Exception as e:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                
                telemetry_logger.error("agent_call_failed", extra={"telemetry_data": {
                    "trace_id": trace_id,
                    "agent": agent_name,
                    "action": "failed",
                    "latency_ms": latency_ms,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }})
                raise
                
        return wrapper
    return decorator

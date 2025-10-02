"""
Performance monitoring and health check system.
"""
import time
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import deque

from utils.logger import logger

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - system metrics will be limited")


@dataclass
class PerformanceMetric:
    """Individual performance measurement."""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class HealthStatus:
    """System health status."""
    is_healthy: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)


class PerformanceMonitor:
    """Performance monitoring system."""
    
    def __init__(self, max_metrics: int = 1000):
        self.metrics: deque = deque(maxlen=max_metrics)
        self.command_times: Dict[str, deque] = {}
        self.start_time = datetime.now()
        self.health_checks = {}
        
    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a performance metric."""
        metric = PerformanceMetric(
            name=name,
            value=value,
            timestamp=datetime.now(),
            tags=tags or {}
        )
        self.metrics.append(metric)
        
    def record_command_time(self, command: str, execution_time: float):
        """Record command execution time."""
        if command not in self.command_times:
            self.command_times[command] = deque(maxlen=100)
        
        self.command_times[command].append(execution_time)
        self.record_metric(f"command.{command}.time", execution_time)
        
    def get_command_stats(self, command: str) -> Optional[Dict[str, float]]:
        """Get statistics for a specific command."""
        if command not in self.command_times:
            return None
            
        times = list(self.command_times[command])
        if not times:
            return None
            
        return {
            'avg_time': sum(times) / len(times),
            'min_time': min(times),
            'max_time': max(times),
            'total_calls': len(times)
        }
    
    def get_system_metrics(self) -> Dict[str, float]:
        """Get current system performance metrics."""
        if not PSUTIL_AVAILABLE:
            return {
                'uptime_hours': (datetime.now() - self.start_time).total_seconds() / 3600,
            }
        
        try:
            import psutil  # Import here to avoid unbound variable
            process = psutil.Process()
            
            metrics = {
                'cpu_percent': process.cpu_percent(),
                'memory_mb': process.memory_info().rss / 1024 / 1024,
                'memory_percent': process.memory_percent(),
                'uptime_hours': (datetime.now() - self.start_time).total_seconds() / 3600,
                'thread_count': process.num_threads(),
            }
            
            # Add file descriptors for Unix systems only
            try:
                # num_fds is only available on Unix-like systems
                metrics['file_descriptors'] = getattr(process, 'num_fds', lambda: 0)()
            except (AttributeError, OSError):
                # num_fds is not available on Windows or access denied
                pass
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {}
    
    def perform_health_check(self) -> HealthStatus:
        """Perform comprehensive health check."""
        issues = []
        warnings = []
        
        # Check system resources
        metrics = self.get_system_metrics()
        
        # Memory checks
        if metrics.get('memory_percent', 0) > 80:
            issues.append("High memory usage (>80%)")
        elif metrics.get('memory_percent', 0) > 60:
            warnings.append("Elevated memory usage (>60%)")
        
        # CPU checks
        if metrics.get('cpu_percent', 0) > 80:
            issues.append("High CPU usage (>80%)")
        elif metrics.get('cpu_percent', 0) > 60:
            warnings.append("Elevated CPU usage (>60%)")
        
        # Check command performance
        slow_commands = []
        for command, times in self.command_times.items():
            if times:
                avg_time = sum(times) / len(times)
                if avg_time > 5.0:  # Commands taking >5 seconds
                    slow_commands.append(f"{command} ({avg_time:.2f}s avg)")
        
        if slow_commands:
            warnings.extend([f"Slow command: {cmd}" for cmd in slow_commands])
        
        # Check for recent errors
        recent_errors = [m for m in self.metrics 
                        if m.name.startswith('error.') and 
                        m.timestamp > datetime.now() - timedelta(minutes=10)]
        
        if len(recent_errors) > 10:
            issues.append(f"High error rate: {len(recent_errors)} errors in 10 minutes")
        elif len(recent_errors) > 5:
            warnings.append(f"Elevated error rate: {len(recent_errors)} errors in 10 minutes")
        
        return HealthStatus(
            is_healthy=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            metrics=metrics
        )
    
    def get_performance_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Get performance summary for the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff]
        
        # Group metrics by name
        metric_groups = {}
        for metric in recent_metrics:
            if metric.name not in metric_groups:
                metric_groups[metric.name] = []
            metric_groups[metric.name].append(metric.value)
        
        # Calculate summary statistics
        summary = {}
        for name, values in metric_groups.items():
            if values:
                summary[name] = {
                    'count': len(values),
                    'avg': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values)
                }
        
        return {
            'period_hours': hours,
            'total_metrics': len(recent_metrics),
            'metric_summary': summary,
            'command_stats': {cmd: self.get_command_stats(cmd) 
                            for cmd in self.command_times.keys()}
        }


def performance_timer(monitor: PerformanceMonitor, command_name: str):
    """Decorator to automatically time command execution."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                execution_time = time.time() - start_time
                monitor.record_command_time(command_name, execution_time)
        
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                execution_time = time.time() - start_time
                monitor.record_command_time(command_name, execution_time)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# Global performance monitor
performance_monitor = PerformanceMonitor()
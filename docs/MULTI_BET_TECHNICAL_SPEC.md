# 🔧 Multi-Bet Technical Specification

## 📋 Technical Overview

This document provides detailed technical specifications for implementing multiple concurrent betting sessions in BetBot. It complements the `MULTI_BET_OVERVIEW.md` with specific implementation details, code patterns, and technical decisions.

## 🏗️ Core Data Structures

### Session Data Models

```python
from typing import TypedDict, Dict, List, Optional
from enum import Enum

class SessionStatus(Enum):
    OPEN = "open"
    LOCKED = "locked"
    COMPLETED = "completed"
    EXPIRED = "expired"

class TimerConfig(TypedDict):
    lock_duration: Optional[int]      # Seconds until auto-lock
    close_duration: Optional[int]     # Seconds until auto-close  
    update_interval: int              # Live message update frequency
    auto_lock_at: Optional[float]     # Specific timestamp to lock
    auto_close_at: Optional[float]    # Specific timestamp to close

class MultiBettingSession(TypedDict):
    # Identity
    id: str                          # Format: "{timestamp}_{random}"
    title: str                       # User-friendly display name
    
    # Metadata
    created_at: float               # Unix timestamp
    creator_id: int                 # Discord user ID
    channel_id: int                 # Origin channel ID
    server_id: int                  # Discord server ID
    
    # Timing
    timer_config: TimerConfig       # Timing configuration
    lock_time: Optional[float]      # When session will/did lock
    close_time: Optional[float]     # When session will/did close
    
    # State
    status: SessionStatus           # Current session status
    contestants: Dict[str, str]     # contestant_key -> display_name
    bets: Dict[str, BetInfo]       # user_id -> bet_info
    
    # Live messaging
    live_message_id: Optional[int]  # Dedicated live message
    last_update: float             # Last live message update
    
    # Analytics
    total_pot: int                 # Cached total pot value
    total_bettors: int             # Cached bettor count
    winner: Optional[str]          # Winner if completed

class MultiSessionData(TypedDict):
    """Extended data structure for multi-session support."""
    
    # Session management
    betting_sessions: Dict[str, MultiBettingSession]
    active_sessions: List[str]      # IDs of non-completed sessions
    
    # Contestant mapping for auto-detection
    contestant_to_session: Dict[str, str]  # contestant_name -> session_id
    
    # Legacy compatibility  
    legacy_mode: bool              # If true, behave like single-session
    
    # Existing fields remain unchanged
    balances: Dict[str, int]
    settings: Dict[str, Any]
    # ... other existing fields
```

### Migration Strategy

```python
def migrate_to_multi_session(data: Data) -> MultiSessionData:
    """Convert single-session data to multi-session format."""
    
    # Preserve existing session if active
    sessions = {}
    active = []
    
    if data.get("betting", {}).get("open") or data.get("betting", {}).get("locked"):
        # Convert current session to first multi-session
        legacy_session = create_legacy_session(data["betting"])
        sessions[legacy_session["id"]] = legacy_session
        active.append(legacy_session["id"])
    
    return {
        **data,  # Preserve all existing fields
        "betting_sessions": sessions,
        "active_sessions": active,
        "user_contexts": {},
        "legacy_mode": len(sessions) <= 1,  # Single session = legacy mode
    }

def create_legacy_session(betting_data: BettingSession) -> MultiBettingSession:
    """Convert legacy betting session to multi-session format."""
    session_id = f"legacy_{int(time.time())}"
    contestants = betting_data.get("contestants", {})
    
    return {
        "id": session_id,
        "title": f"{contestants.get('1', 'A')} vs {contestants.get('2', 'B')}",
        "created_at": time.time(),
        "creator_id": 0,  # Unknown for legacy
        "channel_id": 0,  # Unknown for legacy
        "server_id": 0,   # Unknown for legacy
        "timer_config": {
            "lock_duration": None,
            "close_duration": None,
            "update_interval": 5,
            "auto_lock_at": data.get("timer_end_time"),
            "auto_close_at": None,
        },
        "lock_time": betting_data.get("timer_end_time"),
        "close_time": None,
        "status": SessionStatus.LOCKED if betting_data.get("locked") else SessionStatus.OPEN,
        "contestants": contestants,
        "bets": betting_data.get("bets", {}),
        "live_message_id": data.get("live_message"),
        "last_update": time.time(),
        "total_pot": sum(bet["amount"] for bet in betting_data.get("bets", {}).values()),
        "total_bettors": len(betting_data.get("bets", {})),
        "winner": None,
    }
```

## 🎮 Command Interface Design

### Enhanced Command Patterns

```python
class MultiSessionCommands:
    
    @commands.command(name="openbet", aliases=["ob"])
    async def openbet_multi(self, ctx, *args):
        """Enhanced openbet with multi-session support."""
        
        # Parse arguments for session configuration
        parser = SessionCommandParser()
        config = parser.parse_openbet_args(args)
        
        if config.is_simple:
            # Traditional: !openbet Alice Bob
            session_id = await self.create_quick_session(ctx, config.contestants)
        else:
            # Advanced: !openbet "Yankees vs Red Sox" --lock-in 7d
            session_id = await self.create_configured_session(ctx, config)
        
        # Update contestant mapping for auto-detection
        await self.update_contestant_mapping(session_id, config.contestants)
        await self.send_session_created_message(ctx, session_id)

    @commands.command(name="listbets", aliases=["list", "sessions"])
    async def list_sessions(self, ctx):
        """List all active betting sessions."""
        
        data = load_data()
        sessions = self.get_active_sessions(data)
        
        if not sessions:
            await self.send_no_sessions_message(ctx)
            return
            
        embed = self.format_sessions_list(sessions)
        await ctx.send(embed=embed)

    @commands.command(name="bet", aliases=["b"])
    async def bet_multi(self, ctx, contestant: str, amount: int):
        """Enhanced bet command with automatic session detection."""
        
        data = load_data()
        
        # Auto-detect session by contestant name
        session_id = self.find_session_by_contestant(contestant, data)
        
        if not session_id:
            # Check if contestant name is ambiguous across sessions
            possible_sessions = self.find_similar_contestants(contestant, data)
            if possible_sessions:
                await self.send_ambiguous_contestant_error(ctx, contestant, possible_sessions)
            else:
                await self.send_contestant_not_found_error(ctx, contestant)
            return
            
        # Process bet for auto-detected session
        await self.process_session_bet(ctx, session_id, contestant, amount)
```

### Command Argument Parsing

```python
class SessionCommandParser:
    """Parse complex command arguments for multi-session commands."""
    
    def parse_openbet_args(self, args: tuple) -> SessionConfig:
        """Parse openbet command arguments."""
        
        if len(args) == 2 and not any(arg.startswith('--') for arg in args):
            # Simple format: !openbet Alice Bob
            return SessionConfig(
                is_simple=True,
                contestants=[args[0], args[1]],
                title=f"{args[0]} vs {args[1]}",
                category=SessionCategory.CUSTOM,
                timer_config=TimerConfig(
                    lock_duration=90,  # Default 90 seconds
                    close_duration=None,
                    update_interval=5,
                    auto_lock_at=None,
                    auto_close_at=None,
                )
            )
        
        # Advanced format parsing
        title = args[0] if args else "Untitled Bet"
        flags = self.parse_flags(args[1:])
        
        return SessionConfig(
            is_simple=False,
            title=title,
            contestants=self.extract_contestants(title, flags),
            timer_config=self.build_timer_config(flags),
        )
    
    def parse_flags(self, args: tuple) -> Dict[str, str]:
        """Parse --flag value pairs from arguments."""
        flags = {}
        i = 0
        while i < len(args):
            if args[i].startswith('--'):
                flag_name = args[i][2:]  # Remove --
                if i + 1 < len(args) and not args[i + 1].startswith('--'):
                    flags[flag_name] = args[i + 1]
                    i += 2
                else:
                    flags[flag_name] = True
                    i += 1
            else:
                i += 1
        return flags
    
    def build_timer_config(self, flags: Dict[str, str]) -> TimerConfig:
        """Build timer configuration from parsed flags."""
        return TimerConfig(
            lock_duration=self.parse_duration(flags.get('lock-in')),
            close_duration=self.parse_duration(flags.get('close-in')),
            update_interval=self.parse_duration(flags.get('update-interval', '5s')),
            auto_lock_at=self.parse_timestamp(flags.get('lock-at')),
            auto_close_at=self.parse_timestamp(flags.get('close-at')),
        )

class ContestantMatcher:
    """Handles automatic session detection by contestant names."""
    
    @staticmethod
    def find_session_by_contestant(contestant: str, data: MultiSessionData) -> Optional[str]:
        """Find session containing the specified contestant."""
        
        # Direct mapping lookup (fastest)
        if contestant in data.get("contestant_to_session", {}):
            return data["contestant_to_session"][contestant]
        
        # Fuzzy matching across all active sessions
        for session_id in data.get("active_sessions", []):
            session = data["betting_sessions"].get(session_id)
            if not session:
                continue
                
            # Check all contestants in session (case-insensitive, partial match)
            for contestant_key, contestant_name in session["contestants"].items():
                if ContestantMatcher._is_contestant_match(contestant, contestant_name):
                    return session_id
        
        return None
    
    @staticmethod
    def find_similar_contestants(contestant: str, data: MultiSessionData) -> List[Dict[str, str]]:
        """Find contestants with similar names across sessions for disambiguation."""
        similar = []
        
        for session_id in data.get("active_sessions", []):
            session = data["betting_sessions"].get(session_id)
            if not session:
                continue
                
            for contestant_key, contestant_name in session["contestants"].items():
                if ContestantMatcher._is_similar_name(contestant, contestant_name):
                    similar.append({
                        "session_id": session_id,
                        "session_title": session["title"],
                        "contestant_name": contestant_name,
                    })
        
        return similar
    
    @staticmethod
    def _is_contestant_match(input_name: str, contestant_name: str) -> bool:
        """Check if input matches contestant name (case-insensitive, partial)."""
        input_lower = input_name.lower().strip()
        contestant_lower = contestant_name.lower().strip()
        
        # Exact match
        if input_lower == contestant_lower:
            return True
        
        # Partial match (input is substring of contestant name)
        if input_lower in contestant_lower:
            return True
        
        # Handle common abbreviations (first 3+ characters)
        if len(input_lower) >= 3 and contestant_lower.startswith(input_lower):
            return True
        
        return False
    
    @staticmethod
    def _is_similar_name(input_name: str, contestant_name: str) -> bool:
        """Check if names are similar enough to suggest as alternatives."""
        input_lower = input_name.lower().strip()
        contestant_lower = contestant_name.lower().strip()
        
        # Similar length and partial overlap
        if abs(len(input_lower) - len(contestant_lower)) <= 3:
            # Check for partial overlap
            overlap = 0
            min_len = min(len(input_lower), len(contestant_lower))
            for i in range(min_len):
                if input_lower[i] == contestant_lower[i]:
                    overlap += 1
            
            # At least 60% overlap suggests similarity
            if overlap / min_len >= 0.6:
                return True
        
        return False

    @staticmethod
    def update_contestant_mapping(session_id: str, contestants: List[str], data: MultiSessionData):
        """Update the contestant-to-session mapping."""
        if "contestant_to_session" not in data:
            data["contestant_to_session"] = {}
        
        for contestant in contestants:
            data["contestant_to_session"][contestant] = session_id
```

## ⚡ Multi-Timer System

### Timer Architecture

```python
class MultiSessionTimer:
    """Manages concurrent timers for multiple betting sessions."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session_timers: Dict[str, asyncio.Task] = {}
        self.update_schedulers: Dict[str, LiveMessageScheduler] = {}
        self.cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Initialize the multi-timer system."""
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        await self._restore_active_timers()
    
    async def stop(self):
        """Shutdown all timers and cleanup."""
        for timer in self.session_timers.values():
            timer.cancel()
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
    
    async def start_session_timer(self, session_id: str, config: TimerConfig):
        """Start timer for specific session."""
        
        # Cancel existing timer for session
        if session_id in self.session_timers:
            self.session_timers[session_id].cancel()
        
        # Start new timer
        timer_task = asyncio.create_task(
            self._run_session_timer(session_id, config)
        )
        self.session_timers[session_id] = timer_task
        
        # Start live message scheduler
        scheduler = SessionLiveMessageScheduler(
            session_id, config.update_interval, self.bot
        )
        self.update_schedulers[session_id] = scheduler
        await scheduler.start()
    
    async def _run_session_timer(self, session_id: str, config: TimerConfig):
        """Run timer for a specific session."""
        try:
            if config.lock_duration:
                await asyncio.sleep(config.lock_duration)
                await self._auto_lock_session(session_id)
            
            if config.close_duration:
                remaining = config.close_duration - (config.lock_duration or 0)
                if remaining > 0:
                    await asyncio.sleep(remaining)
                    await self._auto_close_session(session_id)
                    
        except asyncio.CancelledError:
            logger.info(f"Timer cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Timer error for session {session_id}: {e}")
        finally:
            # Cleanup
            self.session_timers.pop(session_id, None)
    
    async def _cleanup_loop(self):
        """Periodic cleanup of expired sessions and timers."""
        while True:
            try:
                await asyncio.sleep(300)  # Cleanup every 5 minutes
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
```

### Live Message Scheduling

```python
class SessionLiveMessageScheduler:
    """Manages live message updates for a specific session."""
    
    def __init__(self, session_id: str, update_interval: int, bot: commands.Bot):
        self.session_id = session_id
        self.update_interval = update_interval
        self.bot = bot
        self.is_running = False
        self.update_task: Optional[asyncio.Task] = None
        self.pending_update = False
    
    async def start(self):
        """Start the update scheduler."""
        if not self.is_running:
            self.is_running = True
            self.update_task = asyncio.create_task(self._update_loop())
    
    async def stop(self):
        """Stop the update scheduler."""
        self.is_running = False
        if self.update_task:
            self.update_task.cancel()
    
    def schedule_update(self):
        """Schedule a live message update."""
        self.pending_update = True
    
    async def _update_loop(self):
        """Process scheduled updates at configured interval."""
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval)
                
                if self.pending_update:
                    await self._perform_update()
                    self.pending_update = False
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Update loop error for session {self.session_id}: {e}")
    
    async def _perform_update(self):
        """Perform the actual live message update."""
        data = load_data()
        session = data["betting_sessions"].get(self.session_id)
        
        if not session or session["status"] == SessionStatus.COMPLETED:
            await self.stop()
            return
        
        await update_session_live_message(self.bot, session)
```

## 🗄️ Data Management

### Session Storage Optimization

```python
class SessionDataManager:
    """Optimized data management for multi-session storage."""
    
    @staticmethod
    def load_sessions() -> Dict[str, MultiBettingSession]:
        """Load only active sessions to reduce memory usage."""
        data = load_data()
        active_ids = data.get("active_sessions", [])
        all_sessions = data.get("betting_sessions", {})
        
        # Return only active sessions
        return {
            session_id: session 
            for session_id, session in all_sessions.items()
            if session_id in active_ids
        }
    
    @staticmethod
    def archive_completed_session(session_id: str):
        """Move completed session to archive storage."""
        data = load_data()
        
        if session_id not in data["betting_sessions"]:
            return
        
        session = data["betting_sessions"][session_id]
        
        # Move to archive
        if "archived_sessions" not in data:
            data["archived_sessions"] = {}
        
        data["archived_sessions"][session_id] = {
            **session,
            "archived_at": time.time(),
        }
        
        # Remove from active
        del data["betting_sessions"][session_id]
        if session_id in data["active_sessions"]:
            data["active_sessions"].remove(session_id)
        
        save_data(data)
    
    @staticmethod
    def cleanup_old_archives(max_age_days: int = 30):
        """Remove archived sessions older than specified days."""
        data = load_data()
        archived = data.get("archived_sessions", {})
        cutoff = time.time() - (max_age_days * 24 * 60 * 60)
        
        to_remove = [
            session_id for session_id, session in archived.items()
            if session.get("archived_at", 0) < cutoff
        ]
        
        for session_id in to_remove:
            del archived[session_id]
        
        if to_remove:
            save_data(data)
            logger.info(f"Cleaned up {len(to_remove)} old archived sessions")
```

## 🧪 Testing Strategy

### Test Categories

```python
class MultiSessionTestSuite:
    """Comprehensive test suite for multi-session functionality."""
    
    async def test_session_isolation(self):
        """Test that sessions don't interfere with each other."""
        # Create two sessions
        session1 = await self.create_test_session("Sports", category="sports")
        session2 = await self.create_test_session("Esports", category="esports")
        
        # Place bets in both
        await self.place_bet(session1.id, "user1", "team1", 100)
        await self.place_bet(session2.id, "user1", "teamA", 200)
        
        # Verify isolation
        data = load_data()
        assert session1.id in data["betting_sessions"]
        assert session2.id in data["betting_sessions"]
        assert data["betting_sessions"][session1.id]["bets"]["user1"]["amount"] == 100
        assert data["betting_sessions"][session2.id]["bets"]["user1"]["amount"] == 200
    
    async def test_concurrent_timers(self):
        """Test multiple timers running simultaneously."""
        sessions = []
        
        # Create 5 sessions with different timer configs
        for i in range(5):
            config = TimerConfig(
                lock_duration=10 + i * 5,  # 10, 15, 20, 25, 30 seconds
                close_duration=None,
                update_interval=5,
                auto_lock_at=None,
                auto_close_at=None,
            )
            session = await self.create_timed_session(f"Test{i}", config)
            sessions.append(session)
        
        # Wait and verify they lock at correct times
        start_time = time.time()
        
        for i, session in enumerate(sessions):
            expected_lock_time = start_time + 10 + i * 5
            await self.wait_for_session_lock(session.id)
            actual_lock_time = time.time()
            
            # Allow 1 second tolerance
            assert abs(actual_lock_time - expected_lock_time) < 1.0
    
    async def test_automatic_session_detection(self):
        """Test automatic session detection by contestant names."""
        # Create multiple sessions with unique contestants
        session1 = await self.create_test_session("Yankees vs Red Sox", ["Yankees", "Red Sox"])
        session2 = await self.create_test_session("Lakers vs Warriors", ["Lakers", "Warriors"])
        
        # Test automatic detection - no session specification needed
        await self.run_command("bet", "Yankees", 100, user="user1")
        await self.run_command("bet", "Lakers", 200, user="user1")
        
        # Verify bets were placed in correct sessions automatically
        data = load_data()
        assert data["betting_sessions"][session1.id]["bets"]["user1"]["choice"] == "Yankees"
        assert data["betting_sessions"][session2.id]["bets"]["user1"]["choice"] == "Lakers"
    
    async def test_contestant_name_matching(self):
        """Test fuzzy matching of contestant names."""
        session = await self.create_test_session("Match", ["Manchester United", "Chelsea"])
        
        # Test various forms of contestant names
        test_cases = [
            ("Manchester United", "Manchester United"),  # Exact match
            ("manchester united", "Manchester United"),  # Case insensitive
            ("Manchester", "Manchester United"),         # Partial match
            ("Man", "Manchester United"),                # Abbreviation
            ("Chelsea", "Chelsea"),                      # Exact match
        ]
        
        for input_name, expected_match in test_cases:
            await self.run_command("bet", input_name, 100, user="user1")
            data = load_data()
            assert data["betting_sessions"][session.id]["bets"]["user1"]["choice"] == expected_match
    
    async def test_performance_with_many_sessions(self):
        """Test performance with maximum expected session count."""
        sessions = []
        
        # Create 20 concurrent sessions
        for i in range(20):
            session = await self.create_test_session(f"Performance{i}")
            sessions.append(session)
            
            # Add multiple bets to each
            for j in range(10):
                await self.place_bet(session.id, f"user{j}", "team1", 100)
        
        # Measure command response times
        start_time = time.time()
        await self.run_command("listbets")
        list_time = time.time() - start_time
        
        start_time = time.time()
        await self.run_command("mybets", user="user1")
        mybets_time = time.time() - start_time
        
        # Performance assertions
        assert list_time < 2.0  # Should respond within 2 seconds
        assert mybets_time < 1.0  # Should respond within 1 second
```

## 📊 Performance Considerations

### Memory Optimization

```python
class SessionMemoryManager:
    """Manages memory usage for multi-session data."""
    
    def __init__(self, max_active_sessions: int = 10):
        self.max_active_sessions = max_active_sessions
        self.session_cache: Dict[str, MultiBettingSession] = {}
        self.cache_access_times: Dict[str, float] = {}
    
    def get_session(self, session_id: str) -> Optional[MultiBettingSession]:
        """Get session with LRU caching."""
        if session_id in self.session_cache:
            self.cache_access_times[session_id] = time.time()
            return self.session_cache[session_id]
        
        # Load from storage
        data = load_data()
        session = data.get("betting_sessions", {}).get(session_id)
        
        if session:
            self._add_to_cache(session_id, session)
        
        return session
    
    def _add_to_cache(self, session_id: str, session: MultiBettingSession):
        """Add session to cache with LRU eviction."""
        # Evict oldest if at capacity
        if len(self.session_cache) >= self.max_active_sessions:
            oldest_id = min(self.cache_access_times.keys(), 
                          key=lambda k: self.cache_access_times[k])
            del self.session_cache[oldest_id]
            del self.cache_access_times[oldest_id]
        
        self.session_cache[session_id] = session
        self.cache_access_times[session_id] = time.time()
```

### API Rate Limiting

```python
class DiscordAPIManager:
    """Manages Discord API calls across multiple sessions."""
    
    def __init__(self):
        self.message_queue: List[MessageUpdate] = []
        self.rate_limiter = asyncio.Semaphore(5)  # Max 5 concurrent updates
        self.last_update_times: Dict[str, float] = {}
    
    async def schedule_live_message_update(self, session_id: str, priority: int = 0):
        """Schedule live message update with rate limiting."""
        now = time.time()
        last_update = self.last_update_times.get(session_id, 0)
        
        # Enforce minimum interval between updates for same session
        min_interval = 2.0  # 2 seconds minimum
        if now - last_update < min_interval:
            return  # Skip update to prevent spam
        
        update = MessageUpdate(session_id, priority, now)
        self.message_queue.append(update)
        
        # Sort by priority (higher priority first)
        self.message_queue.sort(key=lambda x: (-x.priority, x.timestamp))
        
        # Process queue
        await self._process_update_queue()
    
    async def _process_update_queue(self):
        """Process queued updates with rate limiting."""
        while self.message_queue:
            async with self.rate_limiter:
                update = self.message_queue.pop(0)
                await self._perform_live_message_update(update.session_id)
                self.last_update_times[update.session_id] = update.timestamp
                
                # Small delay between updates
                await asyncio.sleep(0.5)
```

---

## 🔗 Related Files

- **Implementation**: Core multi-session logic in `utils/session_manager.py`
- **Commands**: Enhanced commands in `cogs/multi_betting.py`
- **Storage**: Data layer updates in `data_manager.py`
- **Testing**: Test suite in `tests/test_multi_session.py`
- **Documentation**: User guide in `docs/MULTI_BET_USER_GUIDE.md`

---

*Document Version: 1.0*  
*Last Updated: October 3, 2025*  
*Author: Development Team*
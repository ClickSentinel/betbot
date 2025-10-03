# 🎯 Multi-Bet Implementation Overview

## 📋 Executive Summary

This document provides a comprehensive analysis of implementing multiple concurrent betting sessions in BetBot. The current system supports only one active betting round at a time, but there's demand for supporting multiple concurrent bets with different timing configurations (e.g., a week-long baseball bet alongside quick tournament matches).

## 🎯 Business Requirements

### Primary Use Cases
1. **Long-term Sports Betting**: Baseball games, weekly matches with 7-day betting windows
2. **Short-term Event Betting**: Tournament matches, immediate events with 90-second windows  
3. **Mixed Timing**: Multiple concurrent bets with different lock times and update frequencies
4. **Unique Contestants**: Each bet has unique contestant names, eliminating confusion

### Key Features Needed
- **Multiple Active Sessions**: Support 3-10 concurrent betting rounds
- **Flexible Timing**: Different auto-lock times (minutes to days)
- **Dynamic Updates**: Different live message update frequencies per session
- **Automatic Session Detection**: Users bet by contestant name without specifying sessions
- **Simple User Experience**: No context switching or session management required

## 🏗️ Current Architecture Analysis

### Current System (Single Bet)
```python
# Current data structure - Single session only
data = {
    "betting": {                    # Single BettingSession
        "open": bool,
        "locked": bool, 
        "contestants": Dict[str, str],
        "bets": Dict[str, BetInfo]
    },
    "timer_end_time": Optional[float],  # Single timer
    "live_message": Optional[int],      # Single live message
    # ... other fields
}
```

### Architectural Constraints
1. **Global State**: All commands assume single `data["betting"]` session
2. **Single Timer**: One `BettingTimer` instance manages one session
3. **Single Live Message**: One live message per channel
4. **Command Context**: No session targeting in commands
5. **State Management**: No session isolation or conflict resolution

## 🔄 Proposed Multi-Bet Architecture

### New Data Structure
```python
# Multi-session data structure
data = {
    "betting_sessions": Dict[str, MultiBettingSession],  # Multiple sessions
    "active_sessions": List[str],                        # Session IDs
    "contestant_to_session": Dict[str, str],             # contestant_name -> session_id mapping
    # ... existing fields
}

class MultiBettingSession(TypedDict):
    id: str                           # Unique identifier
    title: str                        # Display name
    category: str                     # "sports", "esports", "custom"
    created_at: float                 # Creation timestamp
    creator_id: int                   # User who created
    channel_id: int                   # Origin channel
    
    # Timing configuration
    lock_time: Optional[float]        # Auto-lock timestamp
    expires_at: Optional[float]       # Auto-close timestamp  
    update_interval: int              # Live message frequency (seconds)
    
    # Session state
    open: bool
    locked: bool
    contestants: Dict[str, str]
    bets: Dict[str, BetInfo]
    live_message_id: Optional[int]    # Dedicated live message
```

### Component Architecture

#### 1. Session Manager
```python
class SessionManager:
    """Central session management and state coordination."""
    
    def create_session(self, config: SessionConfig) -> str:
        """Create new betting session with unique ID."""
        
    def get_active_sessions(self) -> List[MultiBettingSession]:
        """Get all active sessions."""
        
    def switch_context(self, user_id: int, session_id: str):
        """Switch user's default session context."""
        
    def cleanup_expired_sessions(self):
        """Remove completed/expired sessions."""
```

#### 2. Multi-Timer System
```python
class MultiSessionTimer:
    """Manages multiple concurrent timers with different intervals."""
    
    def __init__(self):
        self.session_timers: Dict[str, asyncio.Task] = {}
        self.update_schedulers: Dict[str, LiveMessageScheduler] = {}
    
    async def start_session_timer(self, session_id: str, config: TimerConfig):
        """Start timer for specific session."""
        
    def get_time_remaining(self, session_id: str) -> Optional[int]:
        """Get remaining time for session lock/close."""
```

#### 3. Enhanced Commands
```python
# Simplified command patterns
!openbet "Yankees vs Red Sox" --lock-in 7d
!openbet Alice Bob --lock-in 2h --update-interval 60s  
!listbets                          # Show all active sessions
!bet Yankees 100                   # Auto-detects correct session by contestant name
!bet Alice 100                     # Works seamlessly across all sessions
!mybets                            # Show bets across all sessions
```

## 📊 Implementation Phases

### Phase 1: Foundation (3-4 weeks)
**Objective**: Core multi-session data structures and basic functionality

#### Week 1-2: Data Layer
- [ ] Design and implement `MultiBettingSession` structure
- [ ] Create migration system from single to multi-session format  
- [ ] Implement `SessionManager` class
- [ ] Update `data_manager.py` for multi-session support
- [ ] Create session ID generation and validation

#### Week 3-4: Basic Commands
- [ ] Implement `!listbets` command
- [ ] Add session targeting to `!bet` command (`--session` flag)
- [ ] Create `!switchbet` command for context switching
- [ ] Update `!mybets` to show cross-session bets
- [ ] Add basic session creation with timing options

**Deliverable**: Basic multi-session support with manual session management

### Phase 2: Timer & Automation (2-3 weeks)
**Objective**: Advanced timing features and automated session management

#### Week 1-2: Multi-Timer System
- [ ] Implement `MultiSessionTimer` class
- [ ] Add support for different auto-lock times
- [ ] Create session expiration and cleanup system
- [ ] Implement per-session update intervals
- [ ] Add timer conflict resolution

#### Week 3: Live Message System
- [ ] Update `LiveMessageScheduler` for per-session messaging
- [ ] Implement dynamic update frequencies
- [ ] Add session-specific live message management
- [ ] Create live message cleanup for expired sessions

**Deliverable**: Fully automated multi-session timing with custom intervals

### Phase 3: Enhanced UX (2 weeks)
**Objective**: Polish user experience and advanced features

#### Week 1: Command Enhancement
- [ ] Add natural language session creation
- [ ] Implement smart session context detection
- [ ] Create session categories and filtering
- [ ] Add bulk session management commands

#### Week 2: UI/UX Polish
- [ ] Enhanced `!listbets` with rich formatting
- [ ] Add session status indicators and warnings
- [ ] Implement session search and filtering
- [ ] Create admin session management tools

**Deliverable**: Production-ready multi-session system with excellent UX

### Phase 4: Testing & Performance (1-2 weeks)
**Objective**: Comprehensive testing and performance optimization

#### Testing
- [ ] Create multi-session test scenarios (estimated 200+ new tests)
- [ ] Test session isolation and conflict resolution
- [ ] Performance testing with multiple concurrent sessions
- [ ] Memory usage and cleanup testing

#### Performance
- [ ] Optimize timer management for multiple sessions
- [ ] Reduce memory footprint of session storage
- [ ] API rate limiting for multiple live messages
- [ ] Database cleanup and archival strategies

**Deliverable**: Fully tested, production-ready multi-session system

## 🔧 Technical Challenges

### 1. Contestant Name Conflicts
**Challenge**: What if multiple sessions have similar contestant names
**Solution**: 
- Ensure unique contestant names across all active sessions
- Fuzzy matching with similarity suggestions for typos
- Clear error messages with session disambiguation when needed

### 2. Timer Resource Management
**Challenge**: Multiple timers consuming system resources
**Solution**:
- Efficient asyncio task management
- Timer pooling and reuse
- Automatic cleanup of completed sessions

### 3. User Experience Simplicity  
**Challenge**: Keeping the interface simple despite multiple sessions
**Solution**:
- Automatic session detection by contestant names
- No context switching or session management required
- Familiar betting commands work seamlessly across all sessions

### 4. Performance & Scalability
**Challenge**: Multiple live messages and timers impacting performance
**Solution**:
- Adaptive update frequencies based on session age
- Live message batching across sessions
- Memory-efficient session storage

## 📈 Resource Requirements

### Development Time
- **Total Estimated Time**: 8-12 weeks
- **Developer Hours**: 200-300 hours
- **Testing Time**: 50-80 hours

### System Resources
- **Memory Impact**: +30-50% for multiple session state
- **CPU Impact**: +20-40% for concurrent timers and live updates
- **API Calls**: Potential 2-5x increase depending on session count

### Code Changes
- **Files Modified**: ~40 files (70% of codebase)
- **New Code**: ~3,000-5,000 lines
- **Tests Added**: ~200 additional test cases
- **Breaking Changes**: Yes, requires data migration

## 🎯 Success Metrics

### Functional Goals
- [ ] Support 5+ concurrent betting sessions
- [ ] Handle different timing configurations (minutes to days)
- [ ] Maintain current performance for single-session workflows
- [ ] Zero data loss during migration from single to multi-session

### Performance Goals
- [ ] <2 second response time for session switching
- [ ] <5% CPU overhead per additional active session
- [ ] API rate limiting compliance with multiple live messages
- [ ] Memory usage growth linear with session count

### User Experience Goals
- [ ] Zero additional complexity for users - betting works exactly the same
- [ ] Automatic session detection with 95%+ accuracy
- [ ] Clear error messages for ambiguous contestant names  
- [ ] 100% backwards compatibility for existing workflows

## 🚧 Risk Assessment

### High Risk
- **Data Migration Complexity**: Single to multi-session conversion
- **State Isolation**: Preventing cross-session command interference
- **Performance Degradation**: Multiple timers and live messages

### Medium Risk
- **User Confusion**: Managing multiple session contexts
- **API Rate Limiting**: Increased Discord API usage
- **Testing Complexity**: Exponential test scenario growth

### Low Risk
- **Command Interface**: Additive changes to existing commands
- **Documentation**: Clear upgrade path and user guides
- **Rollback**: Ability to revert to single-session mode

## 🎉 Long-term Benefits

### For Users
- **Flexibility**: Multiple betting types simultaneously active
- **Convenience**: Long-term bets don't block short-term events
- **Organization**: Category-based session management
- **Context**: Better bet tracking across different event types

### For System
- **Scalability**: Foundation for advanced betting features
- **Modularity**: Clean separation of concerns between sessions
- **Extensibility**: Easy to add new session types and timing options
- **Analytics**: Better data collection across different betting patterns

### For Development
- **Architecture**: Modern, scalable multi-session design
- **Testing**: Comprehensive test coverage for complex scenarios
- **Maintainability**: Well-structured session management system
- **Feature Platform**: Foundation for future enhancements

---

## 📚 Related Documentation

- **Technical Specification**: `docs/MULTI_BET_TECHNICAL_SPEC.md` (to be created)
- **Migration Guide**: `docs/SINGLE_TO_MULTI_MIGRATION.md` (to be created)  
- **API Reference**: `docs/MULTI_BET_API.md` (to be created)
- **Testing Strategy**: `docs/MULTI_BET_TESTING.md` (to be created)

## 🤝 Stakeholder Review

**For Review By**:
- [ ] Product Owner: Business requirements and user experience
- [ ] Technical Lead: Architecture and implementation approach  
- [ ] QA Lead: Testing strategy and risk assessment
- [ ] DevOps: Performance and deployment considerations

**Review Deadline**: TBD
**Implementation Start**: Upon stakeholder approval

---

*Document Version: 1.0*  
*Last Updated: October 3, 2025*  
*Author: Development Team*
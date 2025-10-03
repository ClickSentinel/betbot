# Test Warnings Fix Summary

## RuntimeWarnings Fixed ✅

### Warning 1: AsyncMockMixin coroutine never awaited
**Location**: `tests/test_automatic_bet_locking.py::TestAutomaticBetLocking::test_bet_locking_order_of_operations`
**Issue**: The `track_update_message` function was returning `AsyncMock()()` which creates an unawaited coroutine
**Fix**: Changed to `async def track_update_message(*args, **kwargs): return None`

### Warning 2: BettingPermissions coroutine never awaited  
**Location**: `tests/test_betting.py::TestBetting::test_declare_winner`
**Issue**: `BettingPermissions.check_permission` was not properly mocked as an async function
**Fix**: Added proper async mock: `patch("betbot.cogs.betting.BettingPermissions.check_permission", new_callable=AsyncMock, return_value=True)`

## Result: All Warnings Eliminated ✅
- **Before**: 2 RuntimeWarnings 
- **After**: 0 warnings
- **Tests**: 122 passed, 0 failed

## Best Practices for Future Test Development

### 1. Async Function Mocking
```python
# ❌ Wrong - creates unawaited coroutine
def mock_async_func():
    return AsyncMock()()

# ✅ Correct - properly async mock
async def mock_async_func():
    return None

# ✅ Also correct - use patch with AsyncMock
patch("module.async_function", new_callable=AsyncMock, return_value=expected_value)
```

### 2. Permission Check Mocking
```python
# ✅ Always mock permission checks in tests
with patch("betbot.cogs.betting.BettingPermissions.check_permission", 
           new_callable=AsyncMock, return_value=True):
    # Your test code here
```

### 3. Update Function Mocking
```python
# ✅ Mock async update functions properly
async def mock_update_message(*args, **kwargs):
    # Track or assert what you need
    return None
```

### 4. Running Tests with Warning Detection
```bash
# Check for warnings
python -m pytest -W default::RuntimeWarning

# Run quietly (recommended for CI)
python -m pytest -q

# Verbose with short traceback
python -m pytest -v --tb=short
```

### 5. Debugging Async Issues
- Use `tracemalloc` to get better error locations when debugging
- Always use `AsyncMock` for mocking async functions
- Use `new_callable=AsyncMock` in patches for async functions
- Ensure mock functions that replace async functions are also async

## Files Modified:
1. `tests/test_automatic_bet_locking.py` - Fixed async mock function 
2. `tests/test_betting.py` - Added proper permission check mocking

These fixes ensure clean test runs with no warnings while maintaining all functionality.
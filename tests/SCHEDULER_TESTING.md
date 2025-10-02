# Live Message Scheduler Testing

This document describes the test coverage for the batched live message update functionality.

## Overview

The `LiveMessageScheduler` batches Discord message updates on a 5-second interval to reduce API calls from potentially 60+ per minute to a maximum of 12 per minute during busy betting periods.

## Test Categories

### 1. Core Scheduler Tests (`TestLiveMessageScheduler`)

- **Initialization**: Tests scheduler setup and bot assignment
- **Single Updates**: Validates individual update scheduling
- **Batch Processing**: Ensures multiple rapid updates are batched together
- **Deduplication**: Confirms duplicate update IDs are handled correctly
- **Update Loop**: Tests the 5-second batch processing cycle
- **Error Handling**: Validates graceful error recovery
- **Lifecycle Management**: Tests scheduler start/stop behavior

### 2. Global Function Tests (`TestGlobalSchedulerFunctions`)

- **Initialization**: Tests global scheduler setup
- **Schedule Function**: Validates the global scheduling interface
- **Stop Function**: Tests global scheduler shutdown
- **Rapid Scheduling**: Confirms rapid calls are properly batched
- **Integration Flow**: Tests typical betting workflow with batched updates

### 3. Edge Case Tests (`TestSchedulerEdgeCases`)

- **Task Cancellation**: Tests proper async task cleanup
- **Concurrent Calls**: Validates thread safety of scheduling calls
- **State Persistence**: Ensures scheduler maintains state across operations

## Key Test Features

### Async Testing
All tests use `pytest.mark.asyncio` for proper async/await testing of the scheduler's async behavior.

### Mocking Strategy
- **Discord API**: Mock `discord.Client` instances for bot simulation
- **Data Loading**: Mock `data_manager.load_data` to control test data
- **Live Updates**: Mock `update_live_message` to verify API call patterns

### Timing Tests
- Tests use `asyncio.sleep(5.1)` to validate 5-second batch processing
- Cancellation tests include small delays for proper task cleanup

### Integration Testing
Tests simulate real betting scenarios with multiple rapid user interactions to ensure batching works correctly in practice.

## Performance Validation

The tests confirm:
- Multiple rapid bets trigger only one API call per 5-second window
- Duplicate update requests are properly deduplicated
- Error conditions don't cause memory leaks or stuck processes
- Scheduler properly cleans up async tasks when stopped

## Coverage Stats

Total scheduler tests: **16**
- Basic functionality: 8 tests
- Global functions: 5 tests  
- Edge cases: 3 tests

Combined with existing betting system tests: **51 total tests**
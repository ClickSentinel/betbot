# Admin Flow Example — Per-Session Betting

This short example demonstrates the common admin workflow for running per-session betting using BetBot. It assumes you have configured a dedicated betting channel using `!setbetchannel`.

1. Set the betting channel (one-time or when needed)

   Admin:
   ```
   !setbetchannel #betting
   ```

2. Start a session using the familiar `!openbet` command

   Admin:
   ```
   !openbet Patriots Cowboys
   ```

   The bot will:
   - Create a dedicated session object for `Patriots vs Cowboys`
   - Post a live embed in the configured bet channel
   - Start the session timer (if enabled), storing an absolute `auto_close_at` timestamp

3. Monitor and accept bets

   - Users place bets via `!bet <contestant> <amount>` or by reacting to the live embed
   - The live embed is updated (batched) every 5 seconds with precise per-session timer remaining

4. Close the session (optionally declare a winner)

   Admin (close with winner):
   ```
   !closesession patriots_cowboys Patriots
   ```

   Admin (close without immediate winner):
   ```
   !closesession patriots_cowboys
   ```

   The bot will:
   - Update the session state to closed
   - Post the final results to the invoking channel (detailed payouts if a winner is provided)
   - Update the session's dedicated live embed so the final state is visible in the bet channel

Notes
- `!openbet` now creates a session with a dedicated live message and timer; `!opensession` remains available when you want to choose a session ID explicitly.
- The bot uses per-session timers to compute remaining time in the embed; this is resilient across restarts because the absolute close timestamp is stored in the session data.

*** End of example ***

# 🚀 Production Deployment Guide - October 2025 Edition

## Prerequisites
- **Python 3.8+** (3.13+ recommended for optimal performance)
- **Discord Bot Token** with proper permissions
- **Server with persistent storage** and reliable network connection

## 🆕 Recent Improvements
This deployment guide covers the latest enhancements including:
- **Enhanced Timer System**: 90-second timer with selective updates
- **Themed Emoji System**: Power/Victory vs Excellence/Royalty themes
- **Improved User Experience**: Better error messages and visual formatting
- **Rate Limiting Protection**: Discord API optimization
- **Comprehensive Testing**: 35 automated tests ensure reliability

## Setup Steps

### 1. Environment Setup
```bash
# Clone your repository
git clone <your-repo-url>
cd betbot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env
```

Required settings:
- `DISCORD_TOKEN`: Your bot's token from Discord Developer Portal
- `ENVIRONMENT=production`
- `BACKUP_ENABLED=true`

### 3. Database Setup
```bash
# Ensure data directory exists
mkdir -p data/backups

# Set proper permissions
chmod 700 data/
```

### 4. Running the Bot

**Development (with auto-restart):**
```bash
python watcher.py
```

**Standard Development:**
```bash
python bot.py
```



**Production (with systemd):**
```bash
# Create systemd service
sudo nano /etc/systemd/system/betbot.service
```

Service file content:
```ini
[Unit]
Description=Discord Betting Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/betbot
Environment=PATH=/path/to/betbot/.venv/bin
ExecStart=/path/to/betbot/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable betbot
sudo systemctl start betbot

# Check status
sudo systemctl status betbot
```

### 5. Monitoring

**View logs:**
```bash
# Real-time logs
sudo journalctl -u betbot -f

# Bot logs
tail -f bot.log
```

**Health checks:**
- Bot responds to `!help` command with enhanced formatting
- Emoji reactions work properly with themed system (🔥⚡💪🏆 vs 🌟💎🚀👑)
- Timer functionality: Start betting round and verify 90-second countdown
- Check memory usage: `free -h`
- Check disk space: `df -h`
- Run test suite: `python -m pytest` (should show 35/35 passing)

### 6. Backup & Recovery

**Manual backup:**
```bash
# Create backup
cp data.json data/backups/manual_backup_$(date +%Y%m%d_%H%M%S).json
```

**Restore from backup:**
```bash
# List backups
ls -la data/backups/

# Restore specific backup
cp data/backups/backup_filename.json data.json
sudo systemctl restart betbot
```

## Maintenance

### Regular Tasks
- **Weekly**: Check disk space and logs
- **Monthly**: Review bot performance metrics
- **As needed**: Update dependencies

### Updates
```bash
# Stop bot
sudo systemctl stop betbot

# Update code
git pull

# Update dependencies
pip install -r requirements.txt --upgrade

# Run tests to ensure stability
python -m pytest

# If tests pass (35/35), restart bot
sudo systemctl start betbot

# Verify new features work
# Check themed emojis, timer updates, enhanced error messages
```

## 🧪 Post-Deployment Testing

### Essential Feature Verification
After deployment, verify these critical improvements:

**1. Enhanced Timer System:**
```bash
# In Discord: !openbet Alice Bob
# Verify timer shows 90 seconds and updates only at: 90s, 85s, 80s, 75s, etc.
# Verify automatic locking when timer expires
```

**2. Themed Emoji System:**
```bash
# Check live message shows emojis in correct order:
# 🔥⚡💪🏆 ➖ 🌟💎🚀👑
# Verify emojis are grouped by contestant with visual separator
```

**3. Enhanced Error Handling:**
```bash
# Test: !bet 100 Charlie (invalid contestant)
# Should show: "Available contestants: Alice, Bob"
```

**4. Reaction Cleanup:**
```bash
# Place reaction bet (click emoji), then use !bet command
# Verify old reaction is automatically removed
```

**5. Detailed Payout Messages:**
```bash
# Complete a betting round with multiple users
# Verify individual win/loss breakdown in results
```

## Troubleshooting

### New Feature Issues

**Timer not updating correctly:**
1. Check logs for timer-related errors
2. Verify timer duration: should be 90 seconds
3. Updates should only occur at 5s/0s intervals

**Emoji reactions not working:**
1. Verify bot has "Add Reactions" permission
2. Check themed emoji configuration in data.json
3. Test reaction order: contestant 1 → separator → contestant 2

**Enhanced error messages not showing:**
1. Check config.py for enhanced error message constants
2. Verify contestant name validation logic
3. Test with intentionally wrong contestant names

### Common Issues

**Bot won't start:**
1. Check Discord token in `.env`
2. Verify permissions: `ls -la data/`
3. Check logs: `sudo journalctl -u betbot -n 50`

**High memory usage:**
1. Check for memory leaks in logs
2. Restart bot: `sudo systemctl restart betbot`
3. Monitor with: `top -p $(pgrep -f "python.*bot.py")`

**Database corruption:**
1. Check backup files: `ls -la data/backups/`
2. Restore latest backup
3. Restart bot

### Performance Optimization

**✨ New Performance Features (October 2025):**
- **Selective Timer Updates**: Only 19 updates over 90 seconds (not every second)
- **Rate Limiting Protection**: Automatic Discord API optimization
- **Background Processing**: Non-blocking timer and reaction handling

**For high-traffic servers:**
```env
# Enhanced rate limiting (new feature)
ENABLE_RATE_LIMITING=true
REACTION_DELAY_MS=300

# Increase rate limits
MAX_BETS_PER_DAY=100
MIN_BET_INTERVAL=1

# Enable more frequent backups
BACKUP_INTERVAL_HOURS=6
```

**For resource-constrained servers:**
```env
# Optimize timer performance (new)
TIMER_UPDATE_INTERVAL=5  # Only update at 5s intervals
ENABLE_BACKGROUND_PROCESSING=true

# Reduce backup frequency
BACKUP_INTERVAL_HOURS=48
MAX_BACKUPS=3

# Disable debug logging
LOG_LEVEL=WARNING
```

## Security Considerations

1. **Keep bot token secure** - never commit to git
2. **Regular updates** - keep dependencies updated
3. **File permissions** - restrict data directory access
4. **Network security** - use firewall rules if needed
5. **Monitor logs** - watch for unusual activity

## Scaling

**Multiple servers:** Deploy identical instances with separate data files
**High availability:** Use Docker with restart policies
**Load balancing:** Not typically needed for Discord bots
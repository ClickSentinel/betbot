# 🛠️ BetBot Utility Scripts

This directory contains utility scripts for development and maintenance.

## 📋 Available Scripts

### Development Tools
- **watcher.py** - Development file watcher with auto-restart
  ```bash
  python scripts/watcher.py
  ```
  Automatically restarts the bot when source files change during development.

### Maintenance Tools  
- **fix_bot_issues.py** - Issue resolution and debugging utility
  ```bash
  python scripts/fix_bot_issues.py
  ```
  Systematic tool for diagnosing and resolving common bot issues.

## 🎯 Usage Guidelines

**During Development**: Use `watcher.py` for continuous development with auto-restart
**For Troubleshooting**: Use `fix_bot_issues.py` to diagnose problems systematically
**In Production**: Run scripts manually as needed, don't use auto-restart in production

## 🔧 Adding New Scripts

When adding new utility scripts:
1. Place them in this `scripts/` directory
2. Include proper error handling and logging
3. Add documentation to this README
4. Consider adding to the main project structure documentation
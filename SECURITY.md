# 🔒 Security Policy

## Overview

This document outlines the security practices for the BetBot Discord bot project. We take security seriously and follow best practices to protect sensitive information.

## 🚨 Reporting Security Vulnerabilities

If you discover a security vulnerability, please **DO NOT** open a public issue. Instead:

1. Email the maintainers privately
2. Include detailed information about the vulnerability
3. Allow reasonable time for a fix before public disclosure

## 🔐 Secure Configuration

### Environment Variables

**NEVER commit sensitive information to the repository.** All secrets must be stored in environment variables:

```bash
# ✅ CORRECT: Use environment variables
DISCORD_TOKEN=your_token_here

# ❌ WRONG: Never hardcode tokens in code
TOKEN = "MTI3Njk5MDY4ODc5NjY3NjE4OQ.GX9Kxy..."
```

### Required Environment Variables

- `DISCORD_TOKEN`: Your Discord bot token (required)
- Store in `.env` file (automatically ignored by git)

### .env File Security

1. **Never commit `.env` to git** - it's in `.gitignore`
2. **Use `.env.example`** as a template with placeholder values
3. **Set restrictive permissions**: `chmod 600 .env` (Unix/Linux)
4. **Keep backups secure** - encrypted storage only

## 📋 Security Checklist

### Before Committing Code

- [ ] No hardcoded tokens, passwords, or API keys
- [ ] All secrets loaded from environment variables
- [ ] `.env` file is in `.gitignore`
- [ ] `data.json` and `*.log` files are in `.gitignore`
- [ ] No sensitive data in comments or documentation
- [ ] Review `git diff` before committing

### Before Deploying

- [ ] `.env` file exists with correct values
- [ ] File permissions are restrictive (`chmod 600 .env`)
- [ ] Bot token has minimum required permissions
- [ ] Data directory has proper access controls
- [ ] Logging doesn't expose sensitive information

## 🛡️ File Security

### Files That Should NEVER Be Committed

| File/Pattern | Reason | Status |
|-------------|--------|--------|
| `.env` | Contains bot token | ✅ In .gitignore |
| `data.json` | User data and balances | ✅ In .gitignore |
| `*.log` | May contain sensitive runtime info | ✅ In .gitignore |
| `__pycache__/` | Compiled Python bytecode | ✅ In .gitignore |
| `.venv/` | Virtual environment dependencies | ✅ In .gitignore |

### Files That Are Safe to Commit

- `.env.example` - Template with placeholder values
- `*.py` - Source code (if no hardcoded secrets)
- `*.md` - Documentation
- `requirements.txt` - Dependency list
- `.gitignore` - Git ignore rules

## 🔍 Security Testing

### Automated Checks

Run security checks before committing:

```bash
# Check for hardcoded tokens
grep -r "TOKEN\s*=\s*['\"][^'\"]*['\"]" --include="*.py" . | grep -v "os.getenv"

# Check for .env in git
git ls-files | grep "\.env$"

# Check for data.json in git
git ls-files | grep "data\.json$"

# Check for Discord token patterns
grep -r "^M[TN]" --include="*.py" .
```

### Pre-commit Hook (Optional)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Prevent committing sensitive files

if git diff --cached --name-only | grep -q "\.env$\|data\.json$"; then
    echo "❌ Error: Attempting to commit sensitive file (.env or data.json)"
    echo "These files are ignored for security reasons."
    exit 1
fi

# Check for potential hardcoded tokens
if git diff --cached | grep -E "TOKEN.*=.*['\"][A-Za-z0-9]{50,}"; then
    echo "⚠️  Warning: Possible hardcoded token detected"
    echo "Please use environment variables for secrets"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

exit 0
```

Make it executable: `chmod +x .git/hooks/pre-commit`

## 🔧 Discord Bot Token Security

### Obtaining a Token Securely

1. Visit [Discord Developer Portal](https://discord.com/developers/applications)
2. Create or select your application
3. Go to "Bot" section
4. Click "Reset Token" (if you think it's been compromised)
5. Copy the token immediately (it won't be shown again)
6. Store in `.env` file immediately
7. **Never share or commit this token**

### Bot Permissions

Follow the principle of least privilege:

- ✅ **Required**: Send Messages, Add Reactions, Manage Messages, Read Message History, Embed Links
- ❌ **Not Required**: Administrator, Manage Server, Manage Roles (unless needed)

### Token Compromise Response

If your token is compromised:

1. **Immediately** regenerate token in Discord Developer Portal
2. Update `.env` file with new token
3. Review git history for accidental commits: `git log -S "TOKEN" --all`
4. If committed, consider the token permanently compromised
5. Force push history rewrite is NOT recommended - just regenerate the token

## 📁 Data File Security

### data.json Protection

The `data.json` file contains:
- User balances
- Betting session data
- Active bets

**Security measures:**
- ✅ Excluded from git via `.gitignore`
- ✅ Auto-backup system creates `.bak` files
- ✅ Stored locally only (not in repository)

### Production Deployment

```bash
# Set restrictive permissions on production
chmod 700 data/                 # Directory
chmod 600 data.json             # Data file
chmod 600 .env                  # Environment file
```

## 🔐 Log File Security

Logs may contain:
- User IDs and usernames
- Command usage patterns
- Error messages with stack traces

**Best practices:**
- Rotate logs regularly (built-in rotation: 10MB, 5 backups)
- Exclude from git (*.log in .gitignore)
- Review logs before sharing for debugging
- Don't log sensitive user data

## 🌐 Network Security

### Bot Connection

- Uses Discord's official API with TLS/SSL
- Automatic rate limiting to prevent abuse
- Graceful error handling for network issues

### No External Dependencies

BetBot does not:
- Make external API calls (except Discord)
- Store data in external databases
- Transmit data to third-party services

## 📚 Additional Resources

- [Discord Developer Best Practices](https://discord.com/developers/docs/topics/security)
- [OWASP Secure Coding Practices](https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security.html)

## ✅ Current Security Status

Last security audit: 2024
Status: **All checks passing** ✅

- No secrets in repository ✅
- Proper .gitignore configuration ✅
- Environment variable usage ✅
- Secure file permissions recommended ✅
- Security documentation complete ✅

---

**Remember:** When in doubt, don't commit it. Environment variables are your friend!

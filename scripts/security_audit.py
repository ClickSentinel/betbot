#!/usr/bin/env python3
"""
Security audit script for BetBot
Checks for common security issues and sensitive data leaks
"""

import os
import re
import sys
from pathlib import Path

# ANSI color codes for output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_section(title):
    """Print a section header"""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")

def check_gitignore():
    """Check if .gitignore properly excludes sensitive files"""
    print_section("Checking .gitignore")
    
    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists():
        print(f"{RED}❌ .gitignore file not found!{RESET}")
        return False
    
    with open(gitignore_path, 'r') as f:
        content = f.read()
    
    required_patterns = [
        '.env',
        'data.json',
        '*.log',
        '__pycache__',
    ]
    
    all_good = True
    for pattern in required_patterns:
        if pattern in content:
            print(f"{GREEN}✅ {pattern} is in .gitignore{RESET}")
        else:
            print(f"{RED}❌ {pattern} is NOT in .gitignore{RESET}")
            all_good = False
    
    return all_good

def check_env_file():
    """Check if .env file exists and is not in git"""
    print_section("Checking .env file")
    
    env_exists = Path(".env").exists()
    if env_exists:
        print(f"{YELLOW}⚠️  .env file exists (this is normal){RESET}")
    else:
        print(f"{GREEN}✅ No .env file found in working directory{RESET}")
    
    # Check if .env is tracked by git
    result = os.popen("git ls-files .env 2>/dev/null").read().strip()
    if result:
        print(f"{RED}❌ .env is tracked by git! This is a security issue!{RESET}")
        return False
    else:
        print(f"{GREEN}✅ .env is not tracked by git{RESET}")
        return True

def check_data_json():
    """Check if data.json is not in git"""
    print_section("Checking data.json")
    
    result = os.popen("git ls-files data.json 2>/dev/null").read().strip()
    if result:
        print(f"{RED}❌ data.json is tracked by git!{RESET}")
        return False
    else:
        print(f"{GREEN}✅ data.json is not tracked by git{RESET}")
        return True

def check_hardcoded_tokens():
    """Check for hardcoded tokens in Python files"""
    print_section("Checking for hardcoded tokens")
    
    # Pattern to match potential hardcoded tokens
    token_pattern = re.compile(r'TOKEN\s*=\s*[\'"][^\'"]{20,}[\'"]')
    # Pattern to exclude safe patterns
    safe_patterns = [
        r'os\.getenv',
        r'os\.environ',
        r'load_dotenv',
        r'YOUR_BOT_TOKEN_HERE',
        r'your_discord_token_here',
    ]
    
    issues_found = False
    
    for py_file in Path('.').rglob('*.py'):
        # Skip virtual environment and git directories
        if '.venv' in str(py_file) or '.git' in str(py_file):
            continue
            
        with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        matches = token_pattern.finditer(content)
        for match in matches:
            # Check if it's a safe pattern
            line = match.group(0)
            is_safe = any(re.search(pattern, content[max(0, match.start()-100):match.end()+100]) 
                         for pattern in safe_patterns)
            
            if not is_safe:
                print(f"{RED}❌ Potential hardcoded token in {py_file}:{RESET}")
                print(f"   {line}")
                issues_found = True
    
    if not issues_found:
        print(f"{GREEN}✅ No hardcoded tokens found{RESET}")
    
    return not issues_found

def check_discord_token_patterns():
    """Check for Discord token patterns (MTI*, M*, N*, O*)"""
    print_section("Checking for Discord token patterns")
    
    # Discord tokens have specific patterns
    discord_token_pattern = re.compile(
        r'(MTI|M[A-Z]|N[A-Z]|O[A-Z])[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}'
    )
    
    issues_found = False
    
    for file_path in Path('.').rglob('*'):
        # Only check text files
        if file_path.suffix not in ['.py', '.md', '.txt', '.json', '.env']:
            continue
        # Skip virtual environment and git directories
        if '.venv' in str(file_path) or '.git' in str(file_path):
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            matches = discord_token_pattern.finditer(content)
            for match in matches:
                print(f"{RED}❌ Discord token pattern found in {file_path}:{RESET}")
                print(f"   {match.group(0)[:20]}...{RESET}")
                issues_found = True
        except:
            # Skip files that can't be read
            pass
    
    if not issues_found:
        print(f"{GREEN}✅ No Discord token patterns found{RESET}")
    
    return not issues_found

def check_sensitive_file_patterns():
    """Check for other sensitive file patterns"""
    print_section("Checking for sensitive file patterns")
    
    sensitive_patterns = [
        '*.pem',
        '*.key', 
        '*.crt',
        'secrets.json',
        'credentials.json',
    ]
    
    issues_found = False
    
    for pattern in sensitive_patterns:
        files = list(Path('.').rglob(pattern))
        # Filter out git and venv directories
        files = [f for f in files if '.git' not in str(f) and '.venv' not in str(f)]
        
        if files:
            print(f"{YELLOW}⚠️  Found files matching {pattern}:{RESET}")
            for f in files:
                print(f"   {f}")
                # Check if tracked by git
                result = os.popen(f"git ls-files {f} 2>/dev/null").read().strip()
                if result:
                    print(f"{RED}   ❌ This file is tracked by git!{RESET}")
                    issues_found = True
    
    if not issues_found:
        print(f"{GREEN}✅ No sensitive files found in git{RESET}")
    
    return not issues_found

def check_git_history():
    """Check git history for sensitive files"""
    print_section("Checking git history")
    
    # Check if .env or data.json were ever committed
    result = os.popen("git log --all --full-history --oneline -- .env data.json 2>/dev/null").read()
    
    if result.strip():
        print(f"{RED}❌ Sensitive files found in git history:{RESET}")
        print(result)
        print(f"{YELLOW}Note: Even if removed, tokens in git history are compromised!{RESET}")
        return False
    else:
        print(f"{GREEN}✅ No sensitive files found in git history{RESET}")
        return True

def check_env_example():
    """Check if .env.example exists"""
    print_section("Checking .env.example")
    
    if Path(".env.example").exists():
        print(f"{GREEN}✅ .env.example exists{RESET}")
        
        # Make sure it doesn't contain real tokens
        with open(".env.example", 'r') as f:
            content = f.read()
        
        if "YOUR_BOT_TOKEN_HERE" in content or "your_discord_token_here" in content:
            print(f"{GREEN}✅ .env.example contains placeholder values{RESET}")
            return True
        else:
            print(f"{YELLOW}⚠️  .env.example might contain real values{RESET}")
            return False
    else:
        print(f"{YELLOW}⚠️  .env.example not found (recommended to have one){RESET}")
        return True

def main():
    """Run all security checks"""
    print(f"{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}BetBot Security Audit{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")
    
    checks = [
        ("Gitignore configuration", check_gitignore),
        (".env file", check_env_file),
        ("data.json file", check_data_json),
        ("Hardcoded tokens", check_hardcoded_tokens),
        ("Discord token patterns", check_discord_token_patterns),
        ("Sensitive file patterns", check_sensitive_file_patterns),
        ("Git history", check_git_history),
        (".env.example", check_env_example),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"{RED}❌ Error running {check_name}: {e}{RESET}")
            results.append((check_name, False))
    
    # Summary
    print_section("Security Audit Summary")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"{status} - {check_name}")
    
    print(f"\n{BLUE}Results: {passed}/{total} checks passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}🎉 All security checks passed!{RESET}")
        return 0
    else:
        print(f"\n{RED}⚠️  Some security checks failed. Please review the issues above.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

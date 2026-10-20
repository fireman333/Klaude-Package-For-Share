# Security Patterns Checklist / 資安掃描清單

## 1. Files that should NEVER be committed

### Environment & Config Files
- `.env`, `.env.*` (e.g., `.env.local`, `.env.production`, `.env.development`)
- `*.secret`, `*.secrets`
- `config.local.*`, `local_settings.*`

### Key & Certificate Files
- `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`
- `*.cert`, `*.crt`, `*.cer`
- `id_rsa`, `id_ed25519`, `id_ecdsa` (SSH private keys)
- `*.keystore`

### Credential Files
- `credentials.json`, `service-account*.json` (GCP)
- `.aws/credentials`, `.aws/config`
- `.netrc`, `.npmrc` (with tokens)
- `token.json`, `auth.json`
- `*.tfvars` (Terraform variables, may contain secrets)

### Database Files
- `*.sqlite`, `*.db` (may contain real data)
- `dump.sql`, `backup.sql`

## 2. Patterns to search in code (Grep patterns)

### API Keys & Tokens
```
(api[_-]?key|apikey)\s*[:=]\s*['"][A-Za-z0-9]
(secret[_-]?key|secretkey)\s*[:=]\s*['"][A-Za-z0-9]
(access[_-]?token|accesstoken)\s*[:=]\s*['"][A-Za-z0-9]
(auth[_-]?token|authtoken)\s*[:=]\s*['"][A-Za-z0-9]
bearer\s+[A-Za-z0-9\-._~+/]+=*
```

### Known API Key Formats
```
sk-[A-Za-z0-9]{20,}          # OpenAI
AIza[A-Za-z0-9\-_]{35}       # Google API
AKIA[A-Z0-9]{16}             # AWS Access Key
ghp_[A-Za-z0-9]{36}          # GitHub Personal Access Token
gho_[A-Za-z0-9]{36}          # GitHub OAuth Token
xoxb-[0-9]{10,}              # Slack Bot Token
xoxp-[0-9]{10,}              # Slack User Token
sk_live_[A-Za-z0-9]{24,}     # Stripe Secret Key
sq0csp-[A-Za-z0-9\-_]{43}    # Square Access Token
```

### Passwords & Secrets
```
(password|passwd|pwd)\s*[:=]\s*['"][^'"]{3,}
(db_pass|database_password|mysql_pwd)\s*[:=]
(secret|private_key|signing_key)\s*[:=]\s*['"][^'"]{3,}
```

### Database Connection Strings
```
(mysql|postgres|mongodb|redis)://[^\s'"]+@
(jdbc|odbc):.*password
DATABASE_URL\s*=
REDIS_URL\s*=
```

### Private Keys (inline)
```
-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
```

## 3. Personal & Medical Data Patterns (Taiwan-specific)

### Taiwan ID Numbers (身分證字號)
```
[A-Z][12][0-9]{8}            # 中華民國身分證字號格式
```

### Phone Numbers (台灣手機/市話)
```
09[0-9]{8}                    # 台灣手機號碼
0[2-9]-?[0-9]{7,8}           # 台灣市話
\+886[0-9]{9,10}             # 國際格式
```

### Medical Record Numbers (病歷號)
```
(病歷號|chart.?no|mrn|medical.?record)\s*[:=]?\s*[A-Z0-9]{4,}
(patient.?id|病人編號|個案編號)\s*[:=]?\s*[A-Z0-9]{3,}
```

### Diagnosis Codes
```
(ICD-?10|診斷碼)\s*[:=]?\s*[A-Z][0-9]{2}
```

### Other PII (個人識別資訊)
```
(email|信箱)\s*[:=]\s*['"]?[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+
(address|地址)\s*[:=]\s*['"]?.{10,}
(birthday|生日|出生日期)\s*[:=]
(健保卡號|NHI.?card)\s*[:=]
```

## 4. .gitignore Recommended Entries

Every project should have at least these in `.gitignore`:

```gitignore
# Environment variables
.env
.env.*
*.env

# Secrets
*.pem
*.key
*.p12
*.pfx
*.secret

# Credentials
credentials.json
service-account*.json
token.json

# OS files
.DS_Store
Thumbs.db

# IDE
.vscode/settings.json
.idea/

# Dependencies (usually already present)
node_modules/
target/
__pycache__/
*.pyc

# Database files
*.sqlite
*.db

# Logs that might contain sensitive data
*.log
```

## 5. Git History Check Commands

```bash
# Check if any sensitive files were ever committed
git log --all --diff-filter=A -- '*.env' '*.pem' '*.key' '*.secret' 'credentials.json'

# Search commit history for patterns
git log -p --all -S 'password' -- '*.ts' '*.js' '*.rs' '*.py'
git log -p --all -S 'api_key' -- '*.ts' '*.js' '*.rs' '*.py'
git log -p --all -S 'secret' -- '*.ts' '*.js' '*.rs' '*.py'
```

## 6. Remediation Steps

### If sensitive data is in a file but NOT yet committed:
1. Add the file to `.gitignore`
2. Move secrets to `.env` or a secure vault
3. Reference secrets via environment variables in code

### If sensitive data is staged but NOT yet pushed:
1. `git reset HEAD <file>` to unstage
2. Fix the file (remove sensitive data)
3. Add to `.gitignore` if appropriate
4. Re-stage and commit

### If sensitive data is already in git history:
1. **If NOT pushed**: `git filter-branch` or `git rebase -i` to remove
2. **If already pushed**:
   - Immediately rotate/revoke the compromised credentials
   - Use BFG Repo-Cleaner to clean history
   - Force push (coordinate with collaborators)
   - Consider the data permanently compromised

# Log Sanitization

## Never Store Raw Secrets

Do not record:
- API keys
- bearer tokens
- cookies
- basic auth values
- private webhooks
- customer emails or phone numbers
- account IDs or portfolio holdings
- full raw prompts from external users

## Safe Replacements

- `[REDACTED_TOKEN]`
- `[REDACTED_EMAIL]`
- `[REDACTED_PHONE]`
- `[REDACTED_ACCOUNT_ID]`
- `[REDACTED_CUSTOMER_INPUT]`

## Safe Learning Template

Use:
- what failed
- where it failed
- why it failed
- what fixed it
- which files or services were involved

Avoid:
- full transcripts
- full stack traces if they contain customer data
- literal copied headers or payloads

## Cross-Session Safety

If another session must receive a learning:
1. summarize first
2. redact all sensitive values
3. share only the abstract rule or fix

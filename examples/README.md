# Examples

## Quick demo repo

```bash
python examples/setup_demo_repo.py demo-repo
ai-impact analyze --repo demo-repo --diff HEAD~1
```

Creates a tiny real git repo with a signature-breaking change (`auth.validate_token` gains a parameter) and an untested caller (`login.login`), so you can see a real `HIGH` risk finding immediately without writing your own test case first.

Also useful for testing the MCP server against a real repo — see [`../docs/MCP_SETUP.md`](../docs/MCP_SETUP.md).

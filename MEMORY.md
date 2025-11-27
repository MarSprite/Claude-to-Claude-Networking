# C2C Bridge - Project Memory

## Current State (2025-11-27)

### What's Built
A working MCP server enabling secure communication between Claude Code instances on different LAN machines.

**Repository**: https://github.com/MarSprite/Claude-to-Claude-Networking

**Features implemented:**
- Message passing between instances
- Task delegation with status tracking
- Shared context and file synchronization
- TLS encryption (self-signed certificates)
- Token-based authentication
- LAN-only IP validation (RFC 1918)
- Symmetric P2P (either machine can be server)
- User-specified instance names

### How to Run
```bash
cd /mnt/Holodeck/Projects/Claude-to-Claude
source venv/bin/activate

# Server mode (first machine)
python -m c2c_bridge.server --name "instance-name" --mode server --port 8443

# Credentials generated on first run - copy credentials/ folder to other machine
```

## Original Use Case
Troubleshooting Steam communication between two PCs. User was manually copy-pasting code blocks between two Claude Code instances. The bridge eliminates that friction while keeping the user as permission gatekeeper on each machine.

## Current Limitation
**No handling of local permission requirements.** When remote instance delegates a task that requires local tool approval, the remote has no visibility into the permission state. Local user must still approve locally.

**This is actually correct for the original use case** - user is present at both machines during collaborative troubleshooting.

## Future Directions Discussed

### Trust Spectrum Identified
```
Low Risk                                              High Risk
────────────────────────────────────────────────────────────────►
Context Sharing → Coordinated Work → Agent Mode → Full Autonomy
```

### Potential Tier 1: Scoped Permissions
Pre-authorized safe operations that could execute without prompts:
- Read files within allowed paths
- Search/grep codebases
- Check git status/diff
- Run read-only analysis tools (linters, type checkers)

**Not implemented** - user is considering whether to proceed.

### Permission Proxy (Considered, Deferred)
Forward permission requests to remote user for approval. Security concerns:
- Trust chain expansion
- Man-in-the-middle risk
- Context loss for remote approver
- Accountability ambiguity
- Replay attack potential

Would require significant safeguards if implemented.

## Architecture for Future Reference

```
c2c_bridge/
├── server.py           # Main entry point, CLI
├── http_server.py      # HTTPS with TLS, auth middleware, LAN validation
├── security/
│   ├── tls_manager.py    # Certificate generation
│   ├── auth.py           # Token authentication
│   └── lan_validator.py  # RFC 1918 IP validation
├── broker/
│   ├── message_broker.py # Pub/sub message routing
│   ├── state_manager.py  # Shared context persistence
│   └── task_queue.py     # Task delegation tracking
├── tools/
│   ├── messaging.py      # c2c_send_message, c2c_broadcast, etc.
│   ├── discovery.py      # c2c_register, c2c_list_instances, etc.
│   ├── context.py        # c2c_share_context, c2c_sync_file, etc.
│   └── tasks.py          # c2c_delegate_task, c2c_complete_task, etc.
└── config/
    └── settings.py       # Configuration management
```

## If Resuming Development

Potential next steps in order of complexity:
1. **Add Tier 1 scoped permissions** - Define safe read-only operations
2. **Permission state notifications** - Let remote know when task is blocked on local approval
3. **Operation whitelisting config** - Per-instance configuration of allowed operations
4. **Permission proxy with safeguards** - Only if truly needed, with full security measures

## Dependencies
- mcp>=1.0.0
- uvicorn[standard]>=0.30.0
- cryptography>=42.0.0
- pydantic>=2.0.0
- aiofiles>=23.0.0
- httpx>=0.27.0

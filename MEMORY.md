# C2C Bridge - Project Memory

## Current State (2025-11-27)

### What's Built
A working MCP server enabling secure communication between Claude Code instances on different LAN machines, with session-based collaboration and automatic idle timeout.

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
- **Session management with idle timeout**
- **Remote session control (extend/end)**
- **Activity tracking for idle detection**

### How to Run

#### Quick Start - Collaboration Session
```bash
cd /mnt/Holodeck/Projects/Claude-to-Claude
source venv/bin/activate

# On Machine B (the one you're leaving unattended):
python c2c_collab.py --name my-workstation

# Copy credentials/ folder to Machine A
# Configure Claude Code on A to connect to B's URL
# Return to Machine A and collaborate remotely
```

#### Manual Server Mode
```bash
python -m c2c_bridge.server --name "instance-name" --mode server --port 8443
```

### Collaboration Flow

```
1. User at Machine B
   - Runs: python c2c_collab.py --name workstation
   - Sees: Session active banner, connection URL, token
   - Copies credentials folder to Machine A
   - Returns to Machine A

2. User at Machine A
   - Configures Claude Code MCP to connect to B's URL
   - Collaborates freely via Claude A delegating to Claude B
   - Can extend session: c2c_extend_session()
   - Can end session: c2c_end_session()
   - Can check status: c2c_get_session_status()

3. Session ends when:
   - Idle timeout reached (default 15 min)
   - Remote calls c2c_end_session()
   - User presses Ctrl+C at Machine B
```

## Trust Model

**User trusts Claude Code.** Permission friction is considered unnecessary overhead for the user's workflow.

The security model becomes:
1. **Session-based** - Must explicitly start a collaboration session
2. **Time-bounded** - Auto-shutdown on idle prevents forgotten sessions
3. **Visible** - Terminal window open = session active
4. **LAN-only** - Only RFC 1918 private IPs accepted
5. **Encrypted** - TLS for all traffic
6. **Authenticated** - Pre-shared token required

This design assumes the user:
- Controls both machines
- Is comfortable with Claude operating freely during sessions
- Wants minimal friction during collaboration

## Session MCP Tools

Remote instance (Claude A) can use:
- `c2c_get_session_status()` - Check idle time, uptime, activity stats
- `c2c_extend_session()` - Reset idle timer
- `c2c_end_session()` - Gracefully end session and shut down B

## Architecture

```
c2c_bridge/
├── server.py              # Main entry point, CLI, session lifecycle
├── http_server.py         # HTTPS with TLS, auth, activity tracking
├── security/
│   ├── tls_manager.py     # Certificate generation
│   ├── auth.py            # Token authentication
│   └── lan_validator.py   # RFC 1918 IP validation
├── broker/
│   ├── message_broker.py  # Pub/sub message routing
│   ├── state_manager.py   # Shared context persistence
│   ├── task_queue.py      # Task delegation tracking
│   └── session_manager.py # Session lifecycle, idle timeout
├── tools/
│   ├── messaging.py       # c2c_send_message, c2c_broadcast, etc.
│   ├── discovery.py       # c2c_register, c2c_list_instances, etc.
│   ├── context.py         # c2c_share_context, c2c_sync_file, etc.
│   ├── tasks.py           # c2c_delegate_task, c2c_complete_task, etc.
│   └── session.py         # c2c_get_session_status, c2c_extend_session, etc.
└── config/
    └── settings.py        # Configuration management

c2c_collab.py              # Simple launcher for collaboration sessions
```

## What's NOT Implemented (By Design)

- **Permission proxying** - Not needed; user trusts Claude
- **Scoped permissions** - Not needed; full access during session
- **Permission interception** - Not needed; no wrapper required

The user considered these but decided the simpler model (trust Claude + session bounds) fits their workflow better.

## Future Considerations

If needs change:
1. **Longer timeouts** - Adjust `--idle-timeout` as needed
2. **Multiple concurrent sessions** - Currently single-session; could extend
3. **Session persistence** - Resume interrupted sessions (not implemented)
4. **Audit logging** - More detailed logging of operations (basic stats exist)

## Dependencies
- mcp>=1.0.0
- uvicorn[standard]>=0.30.0
- cryptography>=42.0.0
- pydantic>=2.0.0
- aiofiles>=23.0.0
- httpx>=0.27.0

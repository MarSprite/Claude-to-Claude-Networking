# C2C Bridge - Claude Code Context

This project enables secure communication between Claude Code instances running on different machines within a LAN.

## Quick Start

### Starting the Server (First Machine)
```bash
cd /mnt/Holodeck/Projects/Claude-to-Claude
source venv/bin/activate
python -m c2c_bridge.server --name "your-instance-name" --mode server --port 8443
```

On first run, credentials are generated automatically. Copy the `credentials/` folder to any connecting machines.

### Connecting (Other Machines)
Configure Claude Code's MCP settings to connect to the server's URL with the generated token.

## Available MCP Tools

When connected to the C2C Bridge, you have access to these tools:

### Discovery & Status
- `c2c_register(capabilities?)` - Register this instance with the bridge
- `c2c_list_instances()` - List all connected Claude Code instances
- `c2c_set_status(status, current_task?)` - Update your status
- `c2c_get_status(instance?)` - Get status of instances
- `c2c_unregister()` - Unregister from the bridge

### Messaging
- `c2c_send_message(target, message, priority?, message_type?)` - Send message to specific instance
- `c2c_broadcast(message, priority?)` - Send message to all instances
- `c2c_get_messages(limit?, timeout?)` - Retrieve pending messages
- `c2c_get_message_history(since_id?, limit?)` - Get message history

### Task Delegation
- `c2c_delegate_task(target, task_description, context?, wait?, timeout?)` - Assign task to another instance
- `c2c_get_pending_tasks()` - Get tasks assigned to you
- `c2c_accept_task(task_id)` - Accept a delegated task
- `c2c_start_task(task_id)` - Mark task as in progress
- `c2c_complete_task(task_id, result)` - Complete task with result
- `c2c_fail_task(task_id, error)` - Mark task as failed
- `c2c_get_task_result(task_id, wait?, timeout?)` - Get task result
- `c2c_list_my_tasks(role?, include_completed?)` - List your tasks

### Context & File Sharing
- `c2c_share_context(key, value, scope?, notify?)` - Share data with other instances
- `c2c_get_context(key, scope?)` - Retrieve shared data
- `c2c_list_context(scope?)` - List all shared context keys
- `c2c_delete_context(key, scope?, notify?)` - Delete shared data
- `c2c_sync_file(path, content)` - Share a file
- `c2c_get_file(path)` - Retrieve a shared file
- `c2c_list_files()` - List all shared files

## Common Workflows

### Sending a Message to Another Instance
```
Use c2c_send_message with target="other-instance-name" and your message.
For all instances, use c2c_broadcast.
```

### Delegating Work
```
1. Use c2c_delegate_task to assign work to another instance
2. The other instance uses c2c_get_pending_tasks to see it
3. They accept with c2c_accept_task, work on it, then c2c_complete_task
4. You retrieve results with c2c_get_task_result
```

### Sharing Context
```
Use c2c_share_context to share any JSON-serializable data.
Other instances retrieve it with c2c_get_context using the same key.
```

## Architecture

- **Server Mode**: Runs HTTPS server accepting connections from other instances
- **Client Mode**: Connects to a remote server
- **Hybrid Mode**: Both local stdio MCP + remote HTTPS server

## Security

- All traffic is TLS encrypted
- Connections require a pre-shared token
- Only LAN IPs (RFC 1918 private ranges) are accepted
- Non-LAN connection attempts are rejected

## Project Structure

```
c2c_bridge/
├── server.py           # Main entry point & CLI
├── http_server.py      # HTTPS server with middleware
├── security/           # TLS, authentication, LAN validation
├── broker/             # Message routing, state management, task queue
├── tools/              # MCP tool implementations
└── config/             # Settings management
```

## CLI Reference

```bash
python -m c2c_bridge.server --help

Options:
  --name, -n        Instance name (required)
  --mode, -m        server|client|hybrid (default: server)
  --port, -p        HTTPS port (default: 8443)
  --server-url, -s  Remote server URL (client mode)
  --token, -t       Auth token (client mode)
  --generate-creds  Generate credentials and exit
```

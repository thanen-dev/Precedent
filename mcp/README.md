# Precedent MCP Server

Exposes live project data and queue operations as MCP tools for Claude.

## Setup

```bash
pip install fastmcp
```

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "precedent": {
      "command": "python",
      "args": ["mcp/server.py"],
      "cwd": "/Users/thanenpeou/Projects/CS/precedent"
    }
  }
}
```

Restart Claude Code. The tools become available immediately in any conversation.

## Available tools

| Tool | What it does |
|---|---|
| `get_pending_queue` | Show all items awaiting review |
| `get_queue_stats` | Counts of pending/approved/rejected |
| `approve_item(id)` | Approve a pending item |
| `reject_item(id, reason)` | Reject with reason |
| `add_to_queue(...)` | Submit a new claim manually |
| `get_leader_profile(id)` | Full profile for a leader |
| `list_leaders` | All leader IDs, names, titles |
| `get_conflicts(leader_id?)` | Detected doctrine conflicts |
| `get_historical_cases(category?)` | Historical case library |
| `get_twin_matches(leader_id?)` | Twin match results |
| `get_predictions(status?)` | Active/resolved predictions |
| `update_prediction_status(id, status, outcome)` | Mark prediction resolved |
| `check_position_drift(leader_id)` | Compare extractions vs published |
| `get_latest_brief` | Latest weekly brief text |

## Example conversation

> "What's in my review queue?"
> → calls `get_pending_queue`, summarises items

> "Show me Hun Manet's risk tolerance dimension"
> → calls `get_leader_profile("hun_manet")`

> "Draft a prediction about the EBA negotiation"
> → reads profiles + conflicts, writes prediction, calls `add_to_queue`

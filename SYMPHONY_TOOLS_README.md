# Symphony Position Management Tools

Scripts to manage positions on Symphony Finance for AGDG and MILF agents.

## Scripts

1. **`close_all_symphony_positions.py`** - Close all positions for one or both agents
2. **`close_symphony_agdg.py`** - Alternative AGDG-specific closer
3. **`close_symphony_positions.py`** - Original position closer with profit threshold

## Setup

### 1. Set Environment Variables

```bash
# AGDG Agent (Ari Gold Fund - Base Perps)
export SYMPHONY_AGDG_AGENT_ID="01b8c2b7-b210-493f-8c76-dafd97663e2c"
export SYMPHONY_AGDG_API_KEY="your-agdg-api-key-here"

# MILF Agent (Monad Implementation Treasury - Monad Swap)
export SYMPHONY_MILF_AGENT_ID="f6cc5590-ff96-4077-ac80-9775c7f805cc"
export SYMPHONY_MILF_API_KEY="your-milf-api-key-here"
```

### 2. Get API Keys from GCP Secret Manager

```bash
# Fetch from GCP (if you have access)
gcloud secrets versions access latest --secret="SYMPHONY_API_KEY" --project=sapphire-479610
```

Or get them from the Symphony dashboard.

## Usage

### Close All AGDG Positions

```bash
python3 close_all_symphony_positions.py --agent agdg
```

### Close All MILF Positions

```bash
python3 close_all_symphony_positions.py --agent milf
```

### Close All Positions for Both Agents

```bash
python3 close_all_symphony_positions.py --agent both
```

## Features

- ✅ Displays all open positions with P&L
- ✅ Shows total unrealized P&L
- ✅ Asks for confirmation before closing
- ✅ Detailed logging of each closure
- ✅ Success/failure tracking
- ✅ Final summary with total realized P&L

## Example Output

```
🎯 Symphony Position Closer - Close ALL Positions
================================================================================
   Mode: AGDG
================================================================================

🎯 Processing Agent: Ari Gold Fund ($AGDG)
   ID: 01b8c2b7-b210-493f-8c76-dafd97663e2c
   Type: PERPS on BASE

📊 Fetching open positions...
   Found 11 open position(s)

🟢 #1: ETH SHORT 2x | Entry: $3200.00 → Current: $1600.00 | PnL: +$50.00 (+50.0%)
🟢 #2: BTC SHORT 2x | Entry: $98000.00 → Current: $49000.00 | PnL: +$48.00 (+49.0%)
...

📊 SUMMARY FOR Ari Gold Fund ($AGDG)
   Total Positions: 11
   Total Unrealized PnL: +$485.00

🚨 Close ALL 11 position(s) for Ari Gold Fund ($AGDG)? (yes/no): yes

🚀 Closing 11 position(s)...

   ✅ Closed ETH | Realized PnL: +$50.00 (+50.0%)
   ✅ Closed BTC | Realized PnL: +$48.00 (+49.0%)
   ...

🎉 CLOSING COMPLETE FOR Ari Gold Fund ($AGDG)
   Successfully Closed: 11/11
   Failed: 0
   Total Realized PnL: +$485.00
```

## Security Notes

- **NEVER commit API keys to git**
- Always use environment variables for sensitive data
- API keys are stored securely in GCP Secret Manager
- Use the provided export commands to set keys temporarily

## Troubleshooting

### "API key not set" error

Make sure you've exported the environment variables:
```bash
export SYMPHONY_AGDG_API_KEY="your-key-here"
```

### "403 Forbidden" error

- Check that your API key is valid
- Ensure the agent ID matches your account
- Verify API key has permissions for the agent

### "No positions found" when you expect some

- Check you're using the correct agent ID
- Verify on Symphony dashboard
- Ensure positions haven't already been closed

# claudecord

a SoTA claude research discord bot for LLM assisted research primarly in the AI/ML domain. allows for centralized interaction among users in your server, especially helpful for collaborative idea generation/exploration.

merged chat history and conversation among multiple users with the claude bot is a WIP!
<br>
<br>
<div align="center">
  <img src="https://github.com/0xm00n/claudecord/assets/71098497/6af71484-ab86-42eb-b53c-15bce9a40d08" width="650">
</div>
<br>

## installation

i use [uv](https://github.com/astral-sh/uv) for python package and project management. set up your environment:<br>
```bash
uv venv
source .venv/bin/activate  # linux
uv pip sync pyproject.toml
```

create a .env file in repo dir:<br>
```bash
touch .env
```
in the .env file, input your discord bot token, anthropic api key, and openai api key:<br>
```
DISCORD_TOKEN=<INSERT TOKEN>
ANTHROPIC_API_KEY=<INSERT API KEY>
OPENAI_API_KEY=<INSERT API KEY> 
```

## running

with venv active:<br>
```bash
uv python main.py
```

## usage

- mention @claudecord to chat with the bot
- attach images/pdfs to your message for analysis
- commands:
  - `>rag` - toggle research mode
    - analyze papers in local db
    - search external papers if needed
    - attach pdfs to add to knowledge base
  - `>delete_history` - clear your chat history

## current capabilities

- [X] conversation history (stored in sqlite db) allowing for multi-turn conversations w/ claudecord for each user in server
- [X] multimodality - claudecord can read and analyze pdfs and images 
- [X] delete history command to have a fresh conversation memory `>delete_history`
- [X] research-oriented citations in responses via high-quality RAG from PaperQA2
  - two-tier system: local papers db + dynamic paper search fallback
  - auto-processes uploaded PDFs into knowledge base
  - real-time paper discovery when local db lacks info
  - parallel chunk processing for faster PDF ingestion
  - rate-limited API calls to prevent throttling
  - tracks paper metadata (DOIs, citations) in manifest
  - uses LiteLLM under the hood for efficient API management

# claudecord <img src="claudecord.png" width="22"/>

a supercharged claude discord bot for your discord server!
<br>
<br>
<div align="center">
  <img src="https://github.com/0xm00n/claudecord/assets/71098497/6af71484-ab86-42eb-b53c-15bce9a40d08" width="650">
</div>
<br>

## current capabilities

- [X] multi-turn conversations for each user in a discord server
- [X] multimodality - claudecord can read and analyze pdfs and images 
- [X] **test-time scaling mode** (s1 budget forcing implementation)
- [X] normal mode with supercharged metaprompt
- [X] **multi-user conversations** (so you and all your friends can talk to claude!)

```
                discord
                   │
                   ▼
              ┌────────────┐    ┌────────────┐
user a ──►    │            │    │            │
user b ──►    │ claudecord ├───►│ claude api │
user n ──►    │            │    │            │
              └────┬───────┘    └────────────┘
                   │
                   ▼
              conversation
                memory
              (per user)
```

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
in the .env file, input your discord bot token and anthropic api key:<br>
```
DISCORD_TOKEN=<INSERT TOKEN>
ANTHROPIC_API_KEY=<INSERT API KEY>
```

## running

with venv active:<br>
```bash
uv python main.py
```

## usage

- mention @claudecord to chat with the bot
- attach images/pdfs/files to your message
- each user gets their own persistent chat history
- commands:
  - `>scale` - toggle between normal and test-time scaling modes
  - `>effort <number>` - adjust reasoning iterations in test-time scaling mode
  - `>status` - check current mode and settings
  - `>delete-history` - clear your chat history

# claudecord

a simple claude 3.5 sonnet discord bot to centralize access to claude responses! each user in a discord server has their own conversation history.
<br>
<br>
<div align="center">
  <img src="https://github.com/0xm00n/claudecord/assets/71098497/6af71484-ab86-42eb-b53c-15bce9a40d08" width="650">
</div>
<br>

## installation
create a .env file in repo dir:<br>
```
touch .env
```
in the .env file, input your discord bot token and anthropic api key:<br>
```
DISCORD_TOKEN=<INSERT TOKEN>
ANTHROPIC_API_KEY=<INSERT API KEY>
```
install requirements:<br>
```
pip install -r requirements.txt
```
run the bot:<br>
```
python main.py
```
i recommend running the bot on a server.
<br>
<br>

## current capabilities

- [X] conversation history (stored in sqlite db) allowing for multi-turn conversations w/ claudecord 
- [X] multimodality - claudecord can read and analyze pdfs (even if they have images inside) and images 
- [X] delete history command to have a fresh conversation memory


## todo

- [ ] incorporating citations into claudecord's responses 
- [ ] implementing RAG

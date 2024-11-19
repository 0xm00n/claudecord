# claudecord

a simple claude 3.5 sonnet discord bot (specialized for research) to centralize access to claude among people in your discord server!
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

- [X] conversation history (stored in sqlite db) allowing for multi-turn conversations w/ claudecord for each user in server
- [X] multimodality - claudecord can read and analyze pdfs and images 
- [X] delete history command to have a fresh conversation memory `>delete_history`


## todo
- [x] **tentatively fixed** ~⚠️ fix multi-turn conversation history bug (sends incorrectly formed request which throws an error. caused either by trimming behavior when hitting max_memory or some arbitrary anthropic API behavior)~
- [ ] incorporating citations into claudecord's responses 
- [ ] implementing RAG
- [ ] group chat command - merge conversation histories w/ 2 or more users in server
- [ ] increase speed (im lazy)

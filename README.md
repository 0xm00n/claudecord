# claudecord

a claude 3.5 sonnet discord bot specialized for research to centralize access to claude among people in your discord server!
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
OPENAI_API_KEY=<INSERT API KEY>  # Required for academic paper summarization
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
- [X] research-oriented citations in responses via high-quality RAG from PaperQA2
  - automatically processes uploaded PDFs into knowledge base
  - enhances responses with citations from papers
  - parallel chunk processing for faster PDF ingestion
  - rate-limited API calls to prevent throttling


## todo
- [x] **tentatively fixed** ~⚠️ fix multi-turn conversation history bug (sends incorrectly formed request which throws an error. caused either by trimming behavior when hitting max_memory or some arbitrary anthropic API behavior)~
- [x] incorporating citations into claudecord's responses 
- [x] implementing RAG with PaperQA
- [ ] group chat command - merge conversation histories w/ 2 or more users in server
- [ ] extract DOI and title from PDFs automatically
- [ ] implement LRU cache for frequently accessed papers
- [ ] add semantic similarity scoring for citation relevance
- [ ] support for arXiv ID paper downloads

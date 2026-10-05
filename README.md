# HustleHubM - AI Lead Machine

Find local businesses that need help online, see exactly what you could
help them with, and send each one a short, honest first email - all from
one dashboard on your own computer.

Created by **Madjer Mahomed**.

## What it does

1. **Finds businesses** - type a kind of business and a city
   ("dentists", "Johannesburg"). It searches the web (and Google Maps,
   if you add a key).
2. **Checks each website** - does it work on phones, can you book
   online, is it secure (https), is the footer years out of date, is
   there a contact form or WhatsApp button, does it even load? It also
   finds the business email (including emails hidden by Cloudflare),
   phone and WhatsApp number.
3. **Throws out the junk** - a local AI (running free on your PC with
   Ollama) rejects directories, "top 10" lists, booking sites, news
   articles and big chains.
4. **Scores the lead** - from what the check actually found, not from
   guesses. More gaps = higher score = more you can help with.
5. **Checks the email address can receive mail** before you send (stops
   bounces, which get Gmail accounts blocked).
6. **Drafts a first email** - the problem it mentions is written word for
   word from the website check, so it's always true. The AI only adds a
   personal opening line about the business.
7. **You review and send** - open it in Gmail, your email app or WhatsApp
   with one click, then track the lead: New -> Contacted -> Replied -> Won.

Nothing is sent automatically. You read every email before it goes.

## What you need

- **Windows, Mac or Linux** with **Python 3.10 or newer**
  ([python.org](https://www.python.org/downloads/) - on Windows tick
  "Add Python to PATH" when installing)
- **Ollama** for the local AI ([ollama.com](https://ollama.com)) - free.
  The app still works without it (emails use the built-in template), but
  results are better with it.

## Setup (once)

Open a terminal in the project folder and run:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

(On Mac/Linux: `source .venv/bin/activate`)

```bash
pip install -r requirements.txt
```

Download the AI model (about 3 GB):

```bash
ollama pull qwen3.5:4b
```

Any Ollama model works. To use a different one, copy `.env.example` to
`.env` and change `OLLAMA_MODEL`.

## Run it

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

1. Go to **Settings** and put your name and contact line - they go at the
   bottom of every email.
2. On the dashboard, type a kind of business and a city and press
   **Find leads**. You can watch it work; 5 leads take a few minutes.
3. Click a lead. Read the email, change anything you like, then press
   **Open in Gmail** (or email app / WhatsApp) and send it yourself.
4. Press **Save & mark as contacted**. When they answer, set the status to
   **Replied**, and **Won** when they become a client.
5. If someone says no, press **They said no - do not contact**. Future
   searches will skip them forever.

Search results that were rejected (directories, lists, chains), scored too
low, or had no email, phone or WhatsApp are saved under the **Rejected**
and **Skipped** tabs, so the next search doesn't waste time checking them
again.

### From the command line

```bash
python lead_pipeline.py "hair salons" Pretoria --max 5 --min-score 20
```

The leads appear in the dashboard next time you open it.

## How the score works

| Found on the website | Points |
|---|---|
| No website at all | 45 |
| Website did not load | 45 |
| Not set up for phones (no viewport tag) | 20 |
| No online booking | 15 |
| Not secure (no https) | 10 |
| Footer copyright 2+ years old | 10 |
| No contact form or WhatsApp button | 10 |
| No Google description | 5 |
| Slow to start loading (4s+) | 5 |
| No social media links | 5 |

**50+ = HIGH, 25-49 = MEDIUM, under 25 = LOW.** If a website blocks the
checker, or builds its pages with JavaScript so the checker only sees an
empty page, nothing is claimed about it - open it yourself and look.

Businesses **without a website** are the best leads for a website offer,
but a web search can only find businesses that have one. Add a
`GOOGLE_PLACES_API_KEY` to `.env` to also search Google Maps, which lists
businesses with no website plus their phone numbers. (It's a paid Google
API with free monthly credit - set a budget alert.)

## Sending responsibly

- **South Africa's POPIA (section 69)** says you may contact someone
  **once** to ask if they want your marketing, every email must show
  **who you are** and **how to say no**, and you must stop when they do.
  The app adds your details and a "reply no thanks" line to every email,
  and the do-not-contact list makes sure you never email them again.
- **Gmail limits:** start with 10-15 cold emails a day and grow slowly.
  The dashboard counts what you've sent today and warns you at your limit
  (change it in Settings).
- Never send to an address marked **can't receive mail**.

## Tests

```bash
python -m pytest
```

Runs the offline tests in `tests/` (no internet or AI needed). The
`test_*.py` files in the main folder are live checks that use the
internet and the local AI - run them one at a time, e.g.
`python test_ai.py`.

## Project files

| File | What it does |
|---|---|
| `app.py` | The web dashboard |
| `lead_pipeline.py` | Runs the whole search -> check -> score -> email process |
| `business_discovery.py` | Web search (DuckDuckGo) + merging with Google Places |
| `lead_finder.py` | Google Places search (optional) |
| `website_analyzer.py` | Visits a website and records what it has and is missing |
| `lead_scorer.py` | Turns the website check into a score and a list of opportunities |
| `lead_agent.py` | The local AI jobs: sort search results, write the opening line |
| `email_generator.py` | Builds the email, subject line and opt-out footer |
| `email_checker.py` | Checks an email's domain can receive mail |
| `local_ai.py` | Talks to Ollama |
| `database.py` | Saves leads, settings and the do-not-contact list (SQLite) |

# Flight price tracker -- step by step

What it does: checks prices every hour, saves them to `data/prices.csv`,
and sends you a Telegram message with the cheapest option, trends, and
which route/day looks best. Once set up, it runs in the cloud -- your
computer can be off.

Routes tracked: IST->TBZ, IST->OMH, IST->IKA, ADB->IKA.

Do the steps in order. Each grey box is something to paste into Terminal.

---

## Part A -- show the bot how to read the price (10 min, do this first)

I can't load pateh.com or alibaba.ir myself, so the script doesn't yet
know how to click "search" and read the price on those sites. You show
it once, using a recorder, and it writes the code for you.

1. Open Terminal. Go into this folder and set it up:

```
cd ~/Downloads/tabriz-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

2. Run:

```
playwright codegen https://www.pateh.com/flight/int-ist-tbz/
```

3. Two windows pop up. In the **browser window**: pick any date a few
   weeks out, click search, wait until you actually see flights and
   prices on screen.
4. In the other window ("Playwright Inspector"), select all the code
   and copy it.
5. Paste that code back to me in our chat -- I'll do the wiring.
6. Close both windows, then repeat steps 2-5 for:

```
playwright codegen https://www.alibaba.ir/international/IST-TBZ
```

You only need to do this once per site, ever.

---

## Part B -- Telegram alerts (5 min)

1. In Telegram, search for **BotFather**, open the chat, send `/newbot`,
   follow the prompts (pick any name). It replies with a token that
   looks like `123456789:ABC-defGhIJKlmNoPQRstuVwxyZ`. Save it somewhere.
2. Send any message (e.g. "hi") to the bot you just created.
3. In a browser, open this (swap in your real token):

```
https://api.telegram.org/bot123456789:ABC-defGhIJKlmNoPQRstuVwxyZ/getUpdates
```

   Look for `"chat":{"id":` -- the number right after it is your chat ID.
   Save it too.

---

## Part C -- put it on GitHub so it runs by itself (10 min)

1. Go to github.com -> log in -> "New repository" -> name it anything
   (e.g. `flight-tracker`) -> Create.
2. Back in Terminal, in the same project folder:

```
git init
git add .
git commit -m "first version"
git branch -M main
git remote add origin PASTE_THE_URL_GITHUB_JUST_GAVE_YOU
git push -u origin main
```

3. On the repo's GitHub page: **Settings -> Secrets and variables ->
   Actions -> New repository secret.** Add two, one at a time:
   - Name: `TELEGRAM_BOT_TOKEN`  Value: (the token from Part B)
   - Name: `TELEGRAM_CHAT_ID`  Value: (the chat ID from Part B)
4. Still in Settings: **Actions -> General -> Workflow permissions ->**
   select **"Read and write permissions"** -> Save.
5. Click the **Actions** tab at the top -> click "Check Tabriz Flight
   Prices" on the left -> click **"Run workflow"** -> confirm. This
   runs it right now, instead of waiting for the next hour.

---

## Part D -- did it work?

- In the Actions tab, click the run that just happened. Green check =
  it worked. Red X = click in, copy the error, send it to me.
- You should get a Telegram message within a couple of minutes.
- After this, it just runs every hour on its own. Nothing else to do.

---

## If it stops working

Both sites tell automated bots to stay away (their `robots.txt` says so),
and GitHub's servers use IP addresses that are easy for anti-bot systems
to recognize. If runs start failing, or you get a "logged 0 prices"
Telegram message a few times in a row, it likely got blocked. Fix: run
the exact same `scraper.py` from your own Mac instead, on a `cron`
schedule, instead of GitHub Actions -- nothing in the script changes,
just where it runs from.

## Later -- once you have a few days of data

```
python analyze.py
```

Prints the lowest/highest price per route+date and saves a chart per
route+date, so you can see things like "price drops sharply ~36h out."

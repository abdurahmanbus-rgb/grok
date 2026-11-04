most people meet Grok Bot through someone else's pnl screenshot, open it, point it at a chart, and lose the first $50 to a token that was dead before they bought it. the bot wasn't the problem. nobody told it what dead looks like.
this is the setup I'd build again tonight if I had to start over. one bot, one folder, ten small files. it doesn't hunt for 100x. its main job is killing tokens, and the few that survive still need Grok to read X before a single dollar moves.
steps 01 to 07 are the first evening: the bot, the key, the limits, the exits. 08 to 12 are the rug filter, 14 checks, every one of them written down as code. 13 and 14 put it on autopilot, on paper first.
if you read my eight-agent desk post, this is the floor that desk stands on.
 
how to use this: open your Grok Bot, paste this whole article, and say "build this desk in /workspace/desk, paper mode, ask me before anything touches a wallet." it writes every file itself, on its own computer.
the split you hold onto: code kills, Grok reads X, you sign. nobody on the desk does someone else's job.
 
01. get four things before you start
four things. each one says what it is, what you do tonight, and why the desk needs it.
1. Grok Bot
what it is. the app where you hire named bots. each one works on a cloud computer with a browser, files and a terminal, and keeps working with your laptop shut.
what you do. download it at x.ai/bot, sign in, choose Create your own.
why. the whole desk lives on that computer. files, routines, alerts, all in one place you can open from your phone.
2. an xAI API key
what it is. paid access to Grok from code, with X search built in.
what you do. console.x.ai, API Keys, create one. don't paste it anywhere yet, step 03 says where it goes.
why. a routine can't sit and think about forty tokens in a chat. a script that makes one call per token can, and it logs every answer in the same format.
3. Rugcheck and DexScreener
what it is. two free public APIs. Rugcheck reads the contract: authorities, LP, holders, insiders, the dev wallet. DexScreener reads the pool: depth, age, buys against sells.
what you do. nothing. no signup, no key for reads.
why. facts come before opinions. an open mint authority isn't a judgment call, it's a fact, and facts kill first.
4. a burner wallet, but not tonight
what it is. a fresh Solana wallet that has never held anything else.
what you do. nothing yet. week one runs on paper.
why. the desk never holds a key. when you go live, it tells you what to buy and you sign it yourself.
 
02. hire one bot, not eight
my desk runs eight bots now. it didn't start that way, and yours shouldn't either. eight bots on day one is eight things to debug at once. one bot with one job shows you what the other seven will need later.
choose Create your own and give it this, word for word:
 
the last two lines matter more than the first five. a bot that guesses a missing number will eventually guess one that costs you.
 
 
03. keep the key out of the chat
everything you type to a bot lands in a transcript. so the key goes into a file, typed by you, on the bot's computer.
open the bot's computer, click Take over, open the terminal and run this. it asks for the key without echoing it, so it never shows up in history either:
 
then prove the key works before anything else. one call, so you never confuse a bad key with a bad prompt later:
 
click I'm done and hand the computer back. from here on the bot can run the desk, and it still never sees the key in the chat.
 
 
04. see the whole funnel before you build any of it
eight passes. the free ones run first. only what survives the free passes costs a Grok call, and only what Grok calls BUY costs money. this week, not even that.
 
an open mint authority isn't a judgment call. it's a fact, and facts are free. Grok only ever sees tokens that already passed every check a script can do.
 
 
05. put every number in one file
save as config.py. every number on the desk lives here, so when you retune, you edit one file and nothing else. these are mine, tuned for a $25 ticket. they are not a recommendation, they are a starting point you will move.
 
 
 
06. run the limits before anything else
save as book.py. the cheapest check on the desk is the one that never calls an API. if today already lost $50, the desk doesn't even look at the token. if four positions are open, same. this file is also the desk's memory: two files you can open yourself, positions.json and trades.csv.
 
 
07. write the exit before the entry
most people decide when to sell while staring at a green candle. that's the worst moment to decide anything. on this desk every exit exists before the token is bought, and the bot just checks it every 10 minutes:
liquidity pulled 40% from entry: out, all of it, no questions
down 35%: out
up 100%: half goes, the rest is the market's money
up 200%: another quarter goes
after the first take, the rest leaves when price drops 30% from its peak
six hours without +20%: out, the slot is worth more than the hope
save as watch.py:
 
 
 
 
08. learn the 14 ways a token dies
if I had to throw away everything above and keep one thing, it would be this. it also works without any bot: run the same 14 checks by hand on rugcheck.xyz and dexscreener before your next buy and you'll skip most of the tokens you were about to regret.
13 of the checks are code. comparisons, no model, no opinion. the 14th is the only one that needs Grok.
 
 09. let code kill the obvious ones
 
09. let code kill the obvious ones
checks 1 to 9. it fetches one report and keeps only the fields the desk reads. Grok never sees the raw report, a fat payload costs tokens and costs accuracy.
one detail people miss: the pool's own vault and the lockers sit in the top holders list. count them and every token looks like a whale token. the code drops them before it adds up the top 10.
 
 
 
10. check the pool, not just the contract
checks 10 to 13. a contract can be perfect and the pool still won't let you out. this reads the deepest pool for the token and asks four boring questions: is there enough in it, how big is my ticket next to it, how old is it, and is anyone actually selling.
 
 
11. let Grok read what code can't
check 14. this is the reason the desk runs on Grok and not on any other model: it can search X while it thinks. a token can pass all 13 checks and still be a copycat with a different contract address, or a launch where forty accounts made last week posted the same sentence in the same minute. no API returns that. X does.
save as grok.py. it's the only file that reads the key and the only place the desk talks to xAI:
 
save as prompts.py. this is the file you'll actually reread:
 
 
12. wire it into one command
one contract address in, one verdict out. limits, facts, pool, Grok, in that order, and the first one that says no ends it:
 
you don't need a scanner to use it. a CA from a call channel, a post, a friend's message: tell the bot "check <CA>" and it runs one line. what comes back looks like this (example shape, not a real token):
 
 
 
 
13. three routines, one sentence each
no workflow builder. you tell the bot each routine once, in a sentence, and it shows you the next run. these are mine, word for word:
 
 
 
the two files those routines run. save as report.py:
 
and scan.py, the optional lead source. it pulls fresh Solana tokens that just paid for a DexScreener profile. a paid profile is not a quality signal, it only means the dev spent money. the filter decides the rest:
 
last thing tonight: Settings, General, Auto-review. add two Ask first rules, they stop the action and wait for you no matter what any routine thinks:
 
 
 
 
14. a week on paper before a single dollar
PAPER = True means the desk does everything for real except the money. real tokens, real prices, real exits, fake fills. after seven days, open checks.csv and read it like a stranger wrote it.
what you're looking for: which check kills the most, whether the BUYs would have been ones you'd buy, and whether any SKIP reason looks wrong. a paper fill happens at the screen price, a live fill never does, so treat the paper result as the ceiling, not the forecast.
when you go live, flip PAPER to False and nothing else changes except the last step. check.py stops buying and posts an approval line instead: buy $25 yourself in your own wallet, then one command puts it in the book so watch.py starts guarding it.
 
when it breaks
this touches money, so every failure has one answer written down before it happens.
 
 
the bill
everything before the judge is free: the limits, Rugcheck, DexScreener. the only paid step is one Grok call per token that survived all 13 checks, with X search on.
 
the part people get wrong: the bill scales with survivors, not with the scanner. scan.py can feed the desk 240 tokens a day and most of them die for free before Grok ever hears about them.
 
 
important part
this is my setup, not your strategy.
every number in config.py is mine, picked for a $25 ticket and my own tolerance for watching something go to zero. most memecoins do go to zero, and most people who trade them lose money. the filter doesn't make a token good. it removes the obvious ways to lose, and it makes you read why every token died.
run a week on paper. read the kills. move the numbers where you disagree, in writing. copy the shape, not the constants. not financial advice.
 
code kills, Grok reads X, you sign. a script never gets a judgment call, Grok never gets a calculator, and nobody but you ever gets the wallet.
save this before your next buy. follow if you're planning on running the same thing, more of this coming 🫶
my tg - t.me/+8wAXS0nHWgA2MGEy
my github - github.com/0xboan
trade here - fomo.family/r/0xboan
# Getting started — run a scientific debate in your browser

~15 minutes from clicking the link to a finished debate article. No installation, no command line.

## What this does

You give two scientists' names (e.g. *Eric Davidson* and *Alfonso Martínez Arias*) and a topic (e.g. *"gene regulatory networks and the explanation of development"*). The system reads each scientist's published work, then runs a structured debate between two AI agents that faithfully represent their views, with a third scientist agent reviewing both sides. A journalist agent writes a ~2-page summary at the end in *Nature News-and-Views* style.

## What you need

- A [Claude](https://claude.ai) account. Pro or Max plans run smoother (the debate uses several AI agents in parallel and can hit Free-tier limits).
- A web browser. No installation, no command line, no GitHub account needed.
- 15–60 minutes depending on how long a debate you ask for.

---

## Step 1 — Open the package

1. Go to [**claude.ai/code**](https://claude.ai/code) in your browser.
2. Sign in to your Claude account.
3. If prompted, allow Claude to access public GitHub repos. (One-time. We're not asking you to write anything to GitHub.)
4. Click **"Open a repository"** (or similar wording). Paste the repo URL:
   ```
   https://github.com/vitkl/science_debate
   ```
5. Wait ~30 seconds for the workspace to load. You'll see a chat box — that's where you talk to Claude.

## Step 2 — Start the debate

In the chat box, type:

```
/run-debate
```

Claude will:

- Print the debate format (so you see what's coming).
- Run a one-time setup (~2 minutes installing the tools — you don't have to do anything, just wait).
- Ask you a short series of questions, in **small batches** (designed so you only think about 3 questions at a time):
  - **Who's debating?** Three scientist names — two who argue, one who reviews.
  - **What's the topic?** One sentence.
  - **How long should the debate be?** Default 80 minutes of "speaking time" produces ~7000 words of debate. Pick less for a quick taste.
  - **How long should the summary article be?** Default ~500 words (about 2 pages).
  - **Anything special each scientist should focus on?** Just press Enter to accept the defaults; they're sensible.

Then Claude spends 5–10 minutes preparing:

- Downloading each scientist's recent papers (from open-access archives — no logins).
- Reading their blog posts and recorded talks (if available).
- Drafting a "self-introduction" for each agent, refined 3 times so it sounds like the real scientist.
- Drafting each presenter's opening talk, also refined 3 times.

After prep, Claude shows you a summary and **waits for you to type `GO`**. This is your chance to back out or change something.

## Step 3 — Watch the debate

After you type `GO`, the debate plays out in the chat:

1. Opening from scientist A
2. Opening from scientist B
3. B critiques A → A responds
4. A critiques B → B responds
5. Reviewer assessment
6. Both presenters reply
7. Reviewer round 2
8. Both presenters reply again
9. Journalist's summary article

Between most stages Claude pauses and asks if **you (the audience)** want to ask a question. Type your question, or just type `continue`.

## ⚠️ Step 4 — SAVE THE OUTPUTS before closing the tab

> **This is the most important step.** The claude.ai/code workspace is **temporary**. When you close the browser tab, everything is deleted — the article, the transcript, all the briefings. **Save before you close.**

### The easy way — save the whole conversation

In the chat box, type:

```
/export
```

A download dialog appears. Save the `.txt` file somewhere safe (Desktop, Google Drive, wherever).

This file contains **everything that happened in the chat**:

- Your questions and Claude's responses
- Every line of the debate ("Eric Davidson representative agent: …")
- The full journalist article
- Your audience questions

You can open it in any text editor, or paste sections into a Google Doc.

### The minimum-effort way — just grab the article

At the very end of the debate Claude prints the journalist's article directly into the chat. **Scroll up to find it**, select the text with your mouse, and copy-paste it into a doc. You're done.

### Both — recommended for important debates

Use `/export` to keep the full record AND copy-paste the article into a Google Doc you can immediately share. Two seconds of extra work, much safer.

---

## Tips

- **The first batch of setup questions matters.** Read each option. Defaults are sensible but the scientist names and topic shape the whole debate.
- **If a debate feels generic or shallow**, the scientists you picked probably don't have enough open-access writing. Try better-published ones, or skip the next section.
- **Bring your own materials** if a scientist's work isn't well-indexed (e.g. recent books or paywalled papers). When prompted in the "custom sources" question, paste in URLs to specific articles or paste text directly. The agents will read it.
- **If Claude gets stuck or makes a mistake**, type a normal message describing what you want different. It's a conversation, not a form. You can say "back up to the previous step" or "rerun the opening with more emphasis on X".
- **Don't share the debate URL** — your claude.ai/code session is scoped to your account. To let a colleague try, send them this guide; they'll open the same package in their own session.

## What you'll have at the end

- A ~2-page summary article in Nature News-and-Views style.
- A full transcript of the debate (~7000 words at default settings).
- Both saved into the `/export` file you downloaded in Step 4.

That's it. Have fun.

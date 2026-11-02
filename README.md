# storyblok-updater

A command-line tool for reading and editing pages and posts in a Storyblok space. It can
show what is on a page, change fields such as the meta title or a FAQ answer, and create
a new page by copying an existing one.

It does not assume which components a site uses. It edits by field path (for example
`content.seo.title`), so it works on any Storyblok space, whatever the page types are.

**Status.** Written on 2 November 2026, building on the Spendesk uploader scripts, which
have been used in production (new articles and refreshes published to Spendesk's
Storyblok in August and September 2026). Those scripts used the same Storyblok Management
API calls (fetch a story by slug or id, update it, create it, publish it). This tool is
new code on top of them: the path editing, `clone` and the dry-run and backup behaviour
are covered by offline tests only and have not yet been run against a live space. For the
first real run on a client, use `ping`, then `list`, then `show`, and try `set` on one
draft page before anything else.

## What you need

1. **Python 3.9 or newer.** Check with `python --version`.
2. **A Storyblok personal access token.** In Storyblok, go to My account, then Personal
   access tokens, and create one. The person who creates it needs edit access to the space.
3. **The space number.** It is the number after `/spaces/` in the Storyblok editor URL.
4. **The region of the space.** `eu` unless the space was created in the US (`us`), Canada
   (`ca`) or Asia-Pacific (`ap`). A token from the wrong region gets a 401 error.

## Setup

```
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and fill in three lines. Replace `COMPANY_NAME` with a short name for the
company, in capitals with no spaces (for example `ACME`). That same name goes after
`cli.py` on every command, where this README writes `<COMPANY_NAME>`.

```
COMPANY_NAME_STORYBLOK_TOKEN=your-token
COMPANY_NAME_STORYBLOK_SPACE=123456
COMPANY_NAME_STORYBLOK_REGION=eu
```

To work with a second company, add another set of three lines with a different name. The
`.env` file is ignored by git, so the token is never committed. Do not paste a token into
any other file.

Check that it works:

```
python cli.py ping <COMPANY_NAME>
```

This should print the space name. A 401 means the token is wrong, has been revoked, or
belongs to a different region.

## Commands

Run all commands from this folder. Wherever a command asks for a story (written `REF`
below), you can give any of these: the story id, the Storyblok editor URL, the live page
URL, or the slug (such as `pricing` or `blog/my-post`).

| Command | What it does |
|---|---|
| `ping <COMPANY_NAME>` | Checks the token and space, and prints the space name. |
| `list <COMPANY_NAME> [--folder blog]` | Lists stories with id, draft or live status, and slug. |
| `get <COMPANY_NAME> REF [--out file.json]` | Prints a story as JSON, or saves it to a file. |
| `show <COMPANY_NAME> REF [--filter text]` | Lists every field path on the page with its current value. |
| `set <COMPANY_NAME> REF path=value ...` | Changes one or more fields. |
| `clone <COMPANY_NAME> TEMPLATE NEW-SLUG` | Creates a new story by copying an existing one. |
| `push <COMPANY_NAME> file.json` | Writes an edited local JSON file back to its story. |

`set`, `clone` and `push` can write to Storyblok. See the next section for how they are
kept safe.

## Changing a page

The usual order is: look at the fields, preview the change, then apply it.

**Step 1. See what can be changed.**

```
python cli.py show <COMPANY_NAME> pricing --filter seo
```

This prints lines like `content.seo.title = Pricing | Example`. The names differ
between sites and page types, so always take them from this output and never guess them.

**Step 2. Preview the change.** Without `--apply`, nothing is written. The tool prints
each field's old and new value.

```
python cli.py set <COMPANY_NAME> pricing content.seo.title="New title" content.seo.description="New text"
```

**Step 3. Apply it.**

```
python cli.py set <COMPANY_NAME> pricing content.seo.title="New title" content.seo.description="New text" --apply
```

The change is saved as a draft. Add `--publish` to make it live in the same step.

Some notes on paths and values:
- A path is made of field names separated by dots. For a list, use the item number
  starting at 0, such as `content.body.2.headline` for the third block in the body.
- A value of `true`, `false`, a number, or JSON in square or curly brackets is stored as
  that type. Anything else is stored as text.
- If a path does not exist, the command stops with an error. This is on purpose, so a typo
  cannot add a field the Storyblok editor would never show.

## Creating a page from a template

```
python cli.py clone <COMPANY_NAME> pricing pricing-uk --name "Pricing UK" --set content.seo.title="Pricing UK"
python cli.py clone <COMPANY_NAME> pricing pricing-uk --name "Pricing UK" --set content.seo.title="Pricing UK" --apply
```

This copies the content of the `pricing` page into a new story with the slug
`pricing-uk`, in the same folder as the template (use `--parent-id` to choose another).
It gives every block in the copy a new internal id and leaves out the fields Storyblok
fills in itself, such as id and publish dates. The new story is a draft.
Image and link fields keep the template's values until you change them with `--set`.

## How it keeps changes safe

- Nothing is written unless you add `--apply`. Without it you only get a before and
  after list.
- Writes save drafts. Going live needs `--publish`.
- Before any write, the current version of the story is saved to
  `backups/<company_name>/`. To undo a change, run `push` on that backup file with `--apply`.
- The tool only sends the story name and content. It does not touch the slug, folder,
  publish date or translations of an existing story.
- If Storyblok rate-limits a request, the tool waits and retries.

## What it does not do

- **Rich text.** Long text fields (headings, lists, FAQ answers in a rich text field) are
  stored as nested JSON. You can edit them by path, but there is no conversion from
  markdown. The Spendesk uploader has one for blog articles, in the geo-local-apps repo at
  `clients/spendesk/upload to storyblok/Upload to Storyblok code/create_article.py`. It
  can be moved here if the new client needs it.
- **Images and files.** It does not upload assets. A copied page keeps the template's
  image ids.
- **Translations.** Stories in other languages are treated as separate stories.
- **Deleting, moving or renaming stories.**
- **Bulk changes.** Each command handles one story. See the next section.

## Upgrading it to do bulk updates

Bulk editing is a loop over the single-story functions that already exist in
`sb_client.py`: `find_story`, `set_path`, `diff`, `update_story`. What needs adding is the
following, in this order.

1. **A change file.** A CSV with one row per change, with the columns `story`, `path`,
   `value`. Several rows can name the same story. The `story` column takes any of the
   references listed above.
2. **A `bulk` command.** It reads the CSV, groups the rows by story, and for each story
   reads it, applies all of its changes with `set_path`, and compares the result with
   `diff`. This is the same flow as `set`, repeated.
3. **A full dry run first.** Without `--apply`, `bulk` prints every story's before and
   after list and writes a summary file. A person reads this before anything is written.
   Stories whose changes would leave them unchanged are skipped.
4. **A check for edits made in between.** Before writing a story, read it again and
   compare its `updated_at` with the value from the first read. If someone changed it
   meanwhile, skip that story and report it, rather than overwrite their work.
5. **Per-story error handling.** If one story fails (a bad path, a 404, a 422), record
   the error and carry on with the rest. Do not stop the whole run.
6. **A results file.** One row per story with the outcome (changed, unchanged, skipped,
   failed), the error message if any, and the path of its backup. This is what you
   check afterwards and what you use to retry only the failures.
7. **A run limit.** A `--limit N` option so the first live run can be done on 3 stories
   before the full set.
8. **Tests.** The existing tests cover the single-story pieces. Add tests for grouping the
   CSV rows by story, skipping unchanged stories, and the edited-in-between check, using
   a fake client instead of the network.

Time and limits: Storyblok's management API allows about 3 requests a second, and each
story needs a read and a write, so the tool already pauses 0.35 seconds after each
request. At that pace 100 stories take about 1 to 2 minutes. Larger runs are fine but
should be split by folder so a failure is easy to find.

Before the first bulk run on a real site, try it on a staging server.

## Files

| File | Purpose |
|---|---|
| `cli.py` | The commands. |
| `sb_client.py` | The Storyblok API calls and the helper functions the commands use. |
| `test_sb_client.py` | Offline tests. Run with `python test_sb_client.py`. No token needed. |
| `.env.example` | Template for the credentials file. |
| `DEVELOPMENT.md` | Working rules for anyone developing this tool. |

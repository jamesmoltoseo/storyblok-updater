#!/usr/bin/env python3
"""storyblok-updater CLI: read and edit stories (pages, posts) in a client's Storyblok space.

Run from this folder. <COMPANY_NAME> is the prefix used in .env, for example ACME.

    python cli.py ping <COMPANY_NAME>
    python cli.py list <COMPANY_NAME> --folder blog
    python cli.py get <COMPANY_NAME> https://example.com/pricing/
    python cli.py show <COMPANY_NAME> pricing
    python cli.py set <COMPANY_NAME> pricing content.seo.title="New title"
    python cli.py set <COMPANY_NAME> pricing content.seo.title="New title" --apply
    python cli.py clone <COMPANY_NAME> pricing pricing-uk --name "Pricing UK" --apply
    python cli.py push <COMPANY_NAME> backups/<company_name>/pricing.<stamp>.json --apply

Every command that writes is a dry run until --apply is given. Writes save drafts;
add --publish to go live. Before any write the current story is saved to
backups/<prefix>/ so it can be put back with `push`.
"""
import argparse
import json
import os
import sys
from datetime import datetime

from sb_client import SBClient, SBError, build_clone, diff, flatten, parse_assignment, repo_root, set_path


def backup(client_prefix, story):
    folder = os.path.join(repo_root(), "backups", client_prefix.lower())
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(folder, f"{story['full_slug'].replace('/', '__')}.{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"story": story}, f, indent=2, ensure_ascii=False)
    return path


def short(v, n=90):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 3] + "..."


def print_diff(changes):
    if not changes:
        print("No changes.")
        return
    for path, old, new in changes:
        print(f"  {path}\n    was: {short(old)}\n    now: {short(new)}")


def editor_url(client, story):
    return f"https://app.storyblok.com/#/me/spaces/{client.space}/stories/0/0/{story['id']}"


def cmd_ping(c, a):
    s = c.ping()
    print(f"OK: space {s.get('id')} '{s.get('name')}'")


def cmd_list(c, a):
    for s in c.list_stories(starts_with=a.folder):
        kind = "folder" if s.get("is_folder") else ("live" if s.get("published") else "draft")
        print(f"{s['id']:>16}  {kind:<6}  {s['full_slug']}")


def cmd_get(c, a):
    story = c.find_story(a.ref)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"story": story}, f, indent=2, ensure_ascii=False)
        print(f"Saved {story['full_slug']} (id {story['id']}) to {a.out}")
    else:
        print(json.dumps(story, indent=2, ensure_ascii=False))


def cmd_show(c, a):
    """List every field path and value, so you know what `set` can change."""
    story = c.find_story(a.ref)
    print(f"{story['full_slug']}  (id {story['id']}, component {story['content'].get('component')})\n")
    for path, value in flatten(story["content"], "content"):
        if path.endswith("_uid") or path.endswith(".component") or value in ("", None, [], {}):
            continue
        if a.filter and a.filter.lower() not in path.lower():
            continue
        print(f"{path} = {short(value)}")


def cmd_set(c, a):
    story = c.find_story(a.ref)
    before = json.loads(json.dumps(story))
    for text in a.assignments:
        path, value = parse_assignment(text)
        set_path(story, path, value)
    changes = diff(before, story)
    print(f"{story['full_slug']} (id {story['id']})")
    print_diff(changes)
    if not changes or not a.apply:
        print("\nDry run. Add --apply to write." if changes else "")
        return
    print(f"\nBackup: {backup(a.prefix, before)}")
    done = c.update_story(story["id"], {"name": story["name"], "content": story["content"]}, publish=a.publish)
    print(f"{'Published' if a.publish else 'Saved as draft'}: {editor_url(c, done)}")


def cmd_clone(c, a):
    template = c.find_story(a.template)
    parent_id = a.parent_id if a.parent_id is not None else template.get("parent_id")
    new = build_clone(template, a.name or a.slug, a.slug, parent_id)
    before = json.loads(json.dumps(new))
    for text in a.assignments:
        path, value = parse_assignment(text)
        set_path(new, path, value)
    print(f"Clone of {template['full_slug']} -> slug '{a.slug}', parent_id {new.get('parent_id')}")
    print_diff(diff(before, new) if a.assignments else [])
    if not a.apply:
        print("\nDry run. Add --apply to create the story (draft).")
        return
    done = c.create_story(new, publish=a.publish)
    print(f"Created {done['full_slug']}: {editor_url(c, done)}")


def cmd_push(c, a):
    with open(a.file, encoding="utf-8") as f:
        local = json.load(f)
    local = local.get("story", local)
    live = c.get_story(local["id"])
    changes = diff(live, local)
    print(f"{live['full_slug']} (id {live['id']})")
    print_diff([ch for ch in changes if ch[0].startswith("content.") or ch[0] == "name"])
    if not a.apply:
        print("\nDry run. Add --apply to write.")
        return
    print(f"\nBackup: {backup(a.prefix, live)}")
    done = c.update_story(live["id"], {"name": local["name"], "content": local["content"]}, publish=a.publish)
    print(f"{'Published' if a.publish else 'Saved as draft'}: {editor_url(c, done)}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, ref=None):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("prefix")
        if ref:
            sp.add_argument(ref, help="story id, editor URL, live URL or slug")
        sp.set_defaults(fn=fn)
        return sp

    add("ping", cmd_ping, "Check the token and space")
    add("list", cmd_list, "List stories").add_argument("--folder", help="only slugs starting with this")
    sp = add("get", cmd_get, "Print or save one story as JSON", "ref")
    sp.add_argument("--out")
    sp = add("show", cmd_show, "List editable field paths and values", "ref")
    sp.add_argument("--filter", help="only paths containing this text")
    sp = add("set", cmd_set, "Change fields by path (dry run unless --apply)", "ref")
    sp.add_argument("assignments", nargs="+", help="content.path=value")
    sp = add("clone", cmd_clone, "Create a new story from a template story", "template")
    sp.add_argument("slug", help="slug of the new story (last part only)")
    sp.add_argument("--name")
    sp.add_argument("--parent-id", type=int)
    sp.add_argument("--set", dest="assignments", action="append", default=[], metavar="path=value")
    sp = add("push", cmd_push, "Write an edited local JSON back to its story")
    sp.add_argument("file")

    for name in ("set", "clone", "push"):
        s = sub.choices[name]
        s.add_argument("--apply", action="store_true", help="really write (default is a dry run)")
        s.add_argument("--publish", action="store_true", help="publish instead of saving a draft")

    a = p.parse_args()
    try:
        a.fn(SBClient.from_env(a.prefix), a)
    except SBError as e:
        sys.exit(f"STOP: {e}")


if __name__ == "__main__":
    main()

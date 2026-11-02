"""Thin Storyblok Management API client, plus the pure helpers the CLI uses.

Nothing here knows about a particular client or content type. Pages, posts and
folders are all "stories", and edits are made by path into story["content"], so the
same code works whatever components a client's space uses.

Credentials come from a .env file next to this file, with a client prefix:
    {PREFIX}_STORYBLOK_TOKEN    personal access token (Storyblok > My account)
    {PREFIX}_STORYBLOK_SPACE    numeric space id
    {PREFIX}_STORYBLOK_REGION   eu (default), us, ca or ap
"""
import copy
import json
import os
import re
import time
import uuid

import requests
from dotenv import load_dotenv

REGION_HOSTS = {
    "eu": "https://mapi.storyblok.com",
    "us": "https://api-us.storyblok.com",
    "ca": "https://api-ca.storyblok.com",
    "ap": "https://api-ap.storyblok.com",
}

# Keys Storyblok sets itself. They are dropped when a story is cloned.
SERVER_KEYS = (
    "id", "uuid", "created_at", "updated_at", "published_at", "first_published_at",
    "full_slug", "path", "alternates", "translated_slugs", "group_id", "sort_by_date",
    "position", "parent", "last_author", "last_author_id", "release_id", "meta_data",
    "localized_paths", "default_full_slug", "published", "unpublished_changes",
)


class SBError(RuntimeError):
    pass


def repo_root():
    return os.path.dirname(os.path.abspath(__file__))


class SBClient:
    def __init__(self, token, space, region="eu"):
        if region not in REGION_HOSTS:
            raise SBError(f"Unknown region {region!r}. Use one of {sorted(REGION_HOSTS)}.")
        self.space = str(space)
        self.base = f"{REGION_HOSTS[region]}/v1/spaces/{self.space}"
        self.headers = {"Authorization": token}

    @classmethod
    def from_env(cls, prefix):
        load_dotenv(os.path.join(repo_root(), ".env"))
        p = prefix.upper()
        token = os.getenv(f"{p}_STORYBLOK_TOKEN")
        space = os.getenv(f"{p}_STORYBLOK_SPACE")
        if not token or not space:
            raise SBError(
                f"Set {p}_STORYBLOK_TOKEN and {p}_STORYBLOK_SPACE in .env (copy .env.example) "
                f"(optional {p}_STORYBLOK_REGION, default eu)."
            )
        return cls(token, space, os.getenv(f"{p}_STORYBLOK_REGION", "eu").lower())

    # --- transport -------------------------------------------------------------

    def _request(self, method, path, **kw):
        # Storyblok allows about 3 requests a second; back off when told to.
        for attempt in range(4):
            r = requests.request(method, self.base + path, headers=self.headers, timeout=60, **kw)
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            if not r.ok:
                raise SBError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
            time.sleep(0.35)
            return r.json()
        raise SBError(f"{method} {path} kept returning 429 (rate limit).")

    # --- reads -----------------------------------------------------------------

    def ping(self):
        return self._request("GET", "/")["space"]

    def list_stories(self, starts_with=None, per_page=100):
        out, page = [], 1
        while True:
            params = {"per_page": per_page, "page": page}
            if starts_with:
                params["starts_with"] = starts_with
            batch = self._request("GET", "/stories/", params=params)["stories"]
            out.extend(batch)
            if len(batch) < per_page:
                return out
            page += 1

    def get_story(self, story_id):
        return self._request("GET", f"/stories/{story_id}")["story"]

    def find_story(self, ref):
        """Resolve an id, editor URL, live URL or slug to a full story."""
        story_id, candidates = parse_ref(ref)
        if story_id:
            return self.get_story(story_id)
        for slug in candidates:
            hits = self._request("GET", "/stories/", params={"with_slug": slug})["stories"]
            hits = [h for h in hits if h.get("full_slug") == slug] or hits
            if hits:
                return self.get_story(hits[0]["id"])
        raise SBError(f"No story found for {ref!r} (tried {candidates}).")

    # --- writes ----------------------------------------------------------------

    def update_story(self, story_id, story, publish=False):
        body = {"story": story}
        if publish:
            body["publish"] = 1
        return self._request("PUT", f"/stories/{story_id}", json=body)["story"]

    def create_story(self, story, publish=False):
        body = {"story": story}
        if publish:
            body["publish"] = 1
        return self._request("POST", "/stories/", json=body)["story"]


# --- pure helpers (no network, covered by test_sb_client.py) ----------------------

def parse_ref(ref):
    """Return (story_id, [candidate full_slugs]). One of the two is empty."""
    ref = str(ref).strip()
    if ref.isdigit():
        return int(ref), []
    m = re.search(r"stories/\d+/\d+/(\d+)", ref)
    if m:
        return int(m.group(1)), []
    path = re.sub(r"^https?://[^/]+", "", ref).split("?")[0].split("#")[0].strip("/")
    if not path:
        return None, ["home"]
    out = [path]
    # Live URLs often carry a language prefix that is not part of the slug.
    first, _, rest = path.partition("/")
    if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", first) and rest:
        out.append(rest)
    return None, out


def _split(path):
    return [int(p) if p.isdigit() else p for p in path.split(".")]


def get_path(obj, path):
    for key in _split(path):
        obj = obj[key]
    return obj


def set_path(obj, path, value):
    """Set obj at a dotted path such as content.body.0.headline. The path must exist.

    Refusing to create new keys is deliberate: a typo should fail, not add a field
    that the Storyblok editor will never show.
    """
    keys = _split(path)
    for key in keys[:-1]:
        obj = obj[key]
    last = keys[-1]
    if isinstance(obj, dict) and last not in obj:
        raise SBError(f"{path}: key {last!r} does not exist. Run `show` to see valid paths.")
    obj[last] = value


def flatten(obj, prefix=""):
    """Yield (path, value) for every scalar in a nested dict or list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, f"{prefix}.{i}" if prefix else str(i))
    else:
        yield prefix, obj


def diff(before, after):
    """List (path, old, new) for every scalar that differs between two stories."""
    a, b = dict(flatten(before)), dict(flatten(after))
    return [(p, a.get(p), b.get(p)) for p in sorted(set(a) | set(b)) if a.get(p) != b.get(p)]


def parse_assignment(text):
    """'content.seo.title=Hello' -> ('content.seo.title', 'Hello'). A value of JSON
    (true, 12, ["a"]) is decoded; anything else stays a plain string."""
    if "=" not in text:
        raise SBError(f"Expected path=value, got {text!r}.")
    path, _, raw = text.partition("=")
    try:
        value = json.loads(raw)
    except ValueError:
        value = raw
    return path.strip(), value


def refresh_uids(node):
    """Give every component block a new _uid. Used when cloning a story."""
    if isinstance(node, dict):
        if "_uid" in node:
            node["_uid"] = str(uuid.uuid4())
        for v in node.values():
            refresh_uids(v)
    elif isinstance(node, list):
        for v in node:
            refresh_uids(v)


def build_clone(template, name, slug, parent_id=None):
    """Make a POST-ready story from a template story. Content is copied, ids are not."""
    story = {k: copy.deepcopy(v) for k, v in template.items() if k not in SERVER_KEYS}
    story["name"] = name
    story["slug"] = slug
    if parent_id is not None:
        story["parent_id"] = parent_id
    refresh_uids(story.get("content", {}))
    return story

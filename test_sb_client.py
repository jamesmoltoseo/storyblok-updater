"""Offline checks for the pure helpers. Run: python tools/storyblok-api/test_sb_client.py"""
import unittest

from sb_client import SBError, build_clone, diff, flatten, parse_assignment, parse_ref, set_path

STORY = {
    "id": 1, "uuid": "u", "name": "Pricing", "slug": "pricing", "full_slug": "pricing",
    "parent_id": 5, "is_startpage": False,
    "content": {
        "_uid": "a", "component": "page", "seo": {"title": "Old"},
        "body": [{"_uid": "b", "component": "hero", "headline": "Hi"}],
    },
}


class Helpers(unittest.TestCase):
    def test_parse_ref(self):
        self.assertEqual(parse_ref("123"), (123, []))
        self.assertEqual(parse_ref("https://app.storyblok.com/#/me/spaces/9/stories/0/0/456/x"), (456, []))
        self.assertEqual(parse_ref("https://x.com/fr/blog/a/"), (None, ["fr/blog/a", "blog/a"]))
        self.assertEqual(parse_ref("pricing"), (None, ["pricing"]))
        self.assertEqual(parse_ref("https://x.com/"), (None, ["home"]))

    def test_set_path_existing_and_list_index(self):
        s = {"content": {"seo": {"title": "a"}, "body": [{"headline": "h"}]}}
        set_path(s, "content.seo.title", "b")
        set_path(s, "content.body.0.headline", "z")
        self.assertEqual(s["content"]["seo"]["title"], "b")
        self.assertEqual(s["content"]["body"][0]["headline"], "z")

    def test_set_path_refuses_new_key(self):
        with self.assertRaises(SBError):
            set_path({"content": {"seo": {}}}, "content.seo.titel", "x")

    def test_assignment_decoding(self):
        self.assertEqual(parse_assignment("a.b=Hello = world"), ("a.b", "Hello = world"))
        self.assertEqual(parse_assignment("a=true"), ("a", True))
        self.assertEqual(parse_assignment("a=12"), ("a", 12))

    def test_diff(self):
        import copy
        after = copy.deepcopy(STORY)
        after["content"]["seo"]["title"] = "New"
        self.assertEqual(diff(STORY, after), [("content.seo.title", "Old", "New")])

    def test_clone_drops_server_keys_and_refreshes_uids(self):
        new = build_clone(STORY, "Pricing UK", "pricing-uk")
        self.assertNotIn("id", new)
        self.assertNotIn("full_slug", new)
        self.assertEqual((new["name"], new["slug"], new["parent_id"]), ("Pricing UK", "pricing-uk", 5))
        self.assertNotEqual(new["content"]["_uid"], "a")
        self.assertNotEqual(new["content"]["body"][0]["_uid"], "b")
        self.assertEqual(STORY["content"]["_uid"], "a")  # template untouched
        self.assertEqual(new["content"]["body"][0]["headline"], "Hi")

    def test_flatten(self):
        self.assertIn(("content.body.0.headline", "Hi"), list(flatten(STORY["content"], "content")))


if __name__ == "__main__":
    unittest.main()

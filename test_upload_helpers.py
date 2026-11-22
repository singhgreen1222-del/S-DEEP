import unittest
import upload


class UploadHelperTests(unittest.TestCase):
    def test_tags_are_deduplicated_and_bounded(self):
        tags = upload.build_tags({"keywords": ["Nifty", "nifty", "#Sensex"], "tags": ["Sensex", "RBI"]})
        self.assertEqual(tags, ["Nifty", "Sensex", "RBI"])

    def test_description_includes_disclaimer_and_sources(self):
        text = upload.build_description({"description": "Market update", "sources": ["https://example.com"],
                                         "hashtags": ["Nifty"], "mode": "short"})
        self.assertIn("Market update", text)
        self.assertIn("https://example.com", text)
        self.assertIn("personal investment advice nahi hai", text)
        self.assertIn("#Shorts", text)


if __name__ == "__main__":
    unittest.main()

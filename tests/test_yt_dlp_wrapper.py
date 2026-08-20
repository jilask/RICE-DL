import json
import unittest
from unittest.mock import MagicMock, patch

import yt_dlp_wrapper as ytw


class TestFetchInfo(unittest.TestCase):
    @patch("yt_dlp_wrapper.subprocess.run")
    def test_fetch_info_single_video(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({
            "title": "Never Gonna Give You Up",
            "uploader": "Rick Astley",
            "duration_string": "3:33",
            "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "extractor_key": "Youtube",
            "playlist": None,
            "view_count": 1400000000,
        })
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        info = ytw.fetch_info("yt-dlp", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", download_playlist=False)

        self.assertFalse(info["is_playlist"])
        self.assertEqual(info["title"], "Never Gonna Give You Up")
        self.assertEqual(info["uploader"], "Rick Astley")
        self.assertEqual(info["duration_string"], "3:33")
        self.assertEqual(info["webpage_url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(info["extractor"], "Youtube")
        self.assertEqual(info["view_count"], 1400000000)

        # Ensure --no-playlist was passed
        cmd = mock_run.call_args[0][0]
        self.assertIn("--no-playlist", cmd)
        self.assertNotIn("--flat-playlist", cmd)

    @patch("yt_dlp_wrapper.subprocess.run")
    def test_fetch_info_flat_playlist_multiline(self, mock_run):
        entries = [
            {"_type": "url", "id": f"vid_{i}", "title": f"Video #{i}", "playlist_title": "Best of Chill", "playlist_count": 10}
            for i in range(1, 11)
        ]
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "\n".join(json.dumps(e) for e in entries) + "\n"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        info = ytw.fetch_info("yt-dlp", "https://www.youtube.com/playlist?list=PL12345", download_playlist=True)

        self.assertTrue(info["is_playlist"])
        self.assertEqual(info["playlist_title"], "Best of Chill")
        self.assertEqual(info["entry_count"], 10)
        self.assertEqual(len(info["entries"]), 5)  # preview first 5 entries
        self.assertEqual(info["entries"][0], {"title": "Video #1", "id": "vid_1"})
        self.assertEqual(info["entries"][4], {"title": "Video #5", "id": "vid_5"})

        # Ensure --flat-playlist was passed
        cmd = mock_run.call_args[0][0]
        self.assertIn("--flat-playlist", cmd)
        self.assertNotIn("--no-playlist", cmd)

    @patch("yt_dlp_wrapper.subprocess.run")
    def test_fetch_info_playlist_single_object(self, mock_run):
        playlist_obj = {
            "_type": "playlist",
            "title": "Album Playlist",
            "playlist_count": 2,
            "entries": [
                {"title": "Track 1", "id": "t1"},
                {"title": "Track 2", "id": "t2"},
            ],
        }
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps(playlist_obj)
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        info = ytw.fetch_info("yt-dlp", "https://example.com/playlist", download_playlist=True)

        self.assertTrue(info["is_playlist"])
        self.assertEqual(info["playlist_title"], "Album Playlist")
        self.assertEqual(info["entry_count"], 2)
        self.assertEqual(len(info["entries"]), 2)
        self.assertEqual(info["entries"][0], {"title": "Track 1", "id": "t1"})

    @patch("yt_dlp_wrapper.subprocess.run")
    def test_fetch_info_empty_output_raises_runtime_error(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "   \n\n  "
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with self.assertRaises(RuntimeError) as ctx:
            ytw.fetch_info("yt-dlp", "https://www.youtube.com/watch?v=123")
        self.assertIn("empty output", str(ctx.exception).lower())

    @patch("yt_dlp_wrapper.subprocess.run")
    def test_fetch_info_malformed_json_raises_runtime_error(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "invalid json line\n"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with self.assertRaises(RuntimeError) as ctx:
            ytw.fetch_info("yt-dlp", "https://www.youtube.com/watch?v=123")
        self.assertIn("could not parse yt-dlp output", str(ctx.exception).lower())

    @patch("yt_dlp_wrapper.subprocess.run")
    def test_fetch_info_playlist_hint_on_error(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "ERROR: [youtube:tab] This playlist does not have a video. Use --yes-playlist"
        mock_run.return_value = mock_proc

        with self.assertRaises(RuntimeError) as ctx:
            ytw.fetch_info("yt-dlp", "https://www.youtube.com/playlist?list=PL123", download_playlist=False)
        self.assertIn("Whole playlist", str(ctx.exception))

    @patch("yt_dlp_wrapper.subprocess.run")
    def test_fetch_info_other_error_no_playlist_hint(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "ERROR: Video unavailable"
        mock_run.return_value = mock_proc

        with self.assertRaises(RuntimeError) as ctx:
            ytw.fetch_info("yt-dlp", "https://www.youtube.com/watch?v=123", download_playlist=False)
        self.assertEqual(str(ctx.exception), "ERROR: Video unavailable")


if __name__ == "__main__":
    unittest.main()

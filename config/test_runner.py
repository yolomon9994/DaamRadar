"""Reject unmocked requests HTTP calls while retaining normal database access."""
from unittest.mock import patch

from django.test.runner import DiscoverRunner


class OfflineDiscoverRunner(DiscoverRunner):
    def run_tests(self, *args, **kwargs):
        with patch("requests.sessions.Session.send", side_effect=AssertionError(
            "Unmocked HTTP is disabled in tests. Use a saved fixture and mock the source request."
        )):
            return super().run_tests(*args, **kwargs)

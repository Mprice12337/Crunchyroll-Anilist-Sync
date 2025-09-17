"""
Simple FlareSolverr client for Cloudflare bypass
"""

import logging
from typing import Dict, Any, Optional, List

import requests

logger = logging.getLogger(__name__)


class FlareSolverrClient:
    """Client for FlareSolverr API to bypass Cloudflare protection"""

    def __init__(self, flaresolverr_url: str):
        self.flaresolverr_url = flaresolverr_url.rstrip('/')
        self.session_id = None

    def create_session(self, session_name: str = "crunchyroll_session") -> bool:
        """Create a new FlareSolverr session"""
        try:
            response = requests.post(
                f"{self.flaresolverr_url}/v1",
                json={
                    "cmd": "sessions.create",
                    "session": session_name
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'ok':
                    self.session_id = session_name
                    logger.info("FlareSolverr session created successfully")
                    return True
                else:
                    logger.error(f"Failed to create FlareSolverr session: {result.get('message')}")
            else:
                logger.error(f"FlareSolverr request failed: {response.status_code}")

            return False

        except Exception as e:
            logger.error(f"Failed to connect to FlareSolverr: {e}")
            return False

    def solve_challenge(self, url: str, cookies: Optional[List[Dict]] = None,
                        post_data: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Solve Cloudflare challenge for a given URL"""
        try:
            if not self.session_id:
                if not self.create_session():
                    return None

            payload = {
                "cmd": "request.post" if post_data else "request.get",
                "url": url,
                "session": self.session_id,
                "maxTimeout": 60000
            }

            if cookies:
                payload["cookies"] = cookies

            if post_data:
                payload["postData"] = post_data

            logger.info(f"Sending FlareSolverr request: {payload['cmd']} {url}")

            response = requests.post(
                f"{self.flaresolverr_url}/v1",
                json=payload,
                timeout=70
            )

            if response.status_code == 200:
                result = response.json()

                if result.get("status") == "ok":
                    solution = result.get("solution", {})
                    logger.info("✅ FlareSolverr request successful")

                    return {
                        'response': solution.get('response', ''),
                        'cookies': solution.get('cookies', []),
                        'url': solution.get('url', url),
                        'status': solution.get('status', 200),
                        'headers': solution.get('headers', {}),
                        'userAgent': solution.get('userAgent', '')
                    }
                else:
                    logger.error(f"FlareSolverr error: {result.get('message')}")
            else:
                logger.error(f"FlareSolverr HTTP error: {response.status_code}")

            return None

        except Exception as e:
            logger.error(f"FlareSolverr request failed: {e}")
            return None

    def destroy_session(self) -> None:
        """Destroy the FlareSolverr session"""
        if self.session_id:
            try:
                requests.post(
                    f"{self.flaresolverr_url}/v1",
                    json={
                        "cmd": "sessions.destroy",
                        "session": self.session_id
                    },
                    timeout=10
                )
                logger.info("FlareSolverr session destroyed")
                self.session_id = None
            except Exception as e:
                logger.debug(f"Error destroying FlareSolverr session: {e}")
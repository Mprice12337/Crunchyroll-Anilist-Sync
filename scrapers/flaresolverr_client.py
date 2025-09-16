"""FlareSolverr client for Cloudflare bypass"""
import time
import requests
import logging

logger = logging.getLogger(__name__)


class FlareSolverrClient:
    """Client for FlareSolverr API"""

    def __init__(self, flaresolverr_url):
        self.flaresolverr_url = flaresolverr_url
        self.session_id = None

    def create_session(self, session_name="crunchyroll_session"):
        """Create a new FlareSolverr session"""
        try:
            logger.info(f"Setting up FlareSolverr session at {self.flaresolverr_url}")

            response = requests.post(f"{self.flaresolverr_url}/v1", json={
                "cmd": "sessions.create",
                "session": session_name
            }, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'ok':
                    self.session_id = session_name
                    logger.info("FlareSolverr session created successfully")
                    return True
                else:
                    logger.error(f"Failed to create FlareSolverr session: {result.get('message', 'Unknown error')}")
            else:
                logger.error(f"FlareSolverr request failed with status {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to FlareSolverr: {e}")

        return False

    def solve_challenge(self, url, cookies=None, post_data=None):
        """Solve Cloudflare challenge for a given URL"""
        try:
            # Create session if it doesn't exist
            if not self.session_id:
                if not self.create_session():
                    logger.error("Failed to create FlareSolverr session")
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
                logger.info(f"Sending POST request with data: {list(post_data.keys()) if isinstance(post_data, dict) else 'form data'}")
            
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
                    
                    # Extract more detailed response info
                    return {
                        'response': solution.get('response', ''),
                        'cookies': solution.get('cookies', []),
                        'url': solution.get('url', url),
                        'status': solution.get('status', 200),
                        'headers': solution.get('headers', {}),
                        'userAgent': solution.get('userAgent', '')
                    }
                else:
                    logger.error(f"FlareSolverr error: {result.get('message', 'Unknown error')}")
                    return None
            else:
                logger.error(f"FlareSolverr HTTP error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"FlareSolverr request failed: {e}")
            return None

    def destroy_session(self):
        """Destroy the FlareSolverr session"""
        if self.session_id:
            try:
                requests.post(f"{self.flaresolverr_url}/v1", json={
                    "cmd": "sessions.destroy",
                    "session": self.session_id
                }, timeout=10)
                logger.info("FlareSolverr session destroyed")
            except:
                pass  # Ignore cleanup errors
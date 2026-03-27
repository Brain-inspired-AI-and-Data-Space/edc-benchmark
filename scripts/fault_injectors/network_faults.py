from __future__ import annotations

import requests


class NetworkFaultError(Exception):
    pass


class ToxiproxyClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _check(self, response: requests.Response) -> dict:
        if not response.ok:
            raise NetworkFaultError(
                f"HTTP {response.status_code} calling {response.request.method} "
                f"{response.request.url}: {response.text}"
            )
        if response.text.strip():
            return response.json()
        return {}

    def create_latency(self, proxy_name: str, latency_ms: int, jitter_ms: int = 0) -> dict:
        payload = {
            "name": f"latency_{latency_ms}",
            "type": "latency",
            "stream": "downstream",
            "attributes": {
                "latency": latency_ms,
                "jitter": jitter_ms,
            },
        }
        resp = self.session.post(
            f"{self.base_url}/proxies/{proxy_name}/toxics",
            json=payload,
            timeout=10,
        )
        return self._check(resp)

    def create_packet_loss(self, proxy_name: str, toxicity: float = 1.0, percent: float = 10.0) -> dict:
        payload = {
            "name": f"packet_loss_{int(percent)}",
            "type": "limit_data",
            "stream": "downstream",
            "toxicity": toxicity,
            "attributes": {
                "bytes": 1
            },
        }
        resp = self.session.post(
            f"{self.base_url}/proxies/{proxy_name}/toxics",
            json=payload,
            timeout=10,
        )
        return self._check(resp)

    def create_timeout(self, proxy_name: str, timeout_ms: int = 30000) -> dict:
        payload = {
            "name": f"timeout_{timeout_ms}",
            "type": "timeout",
            "stream": "downstream",
            "attributes": {
                "timeout": timeout_ms
            },
        }
        resp = self.session.post(
            f"{self.base_url}/proxies/{proxy_name}/toxics",
            json=payload,
            timeout=10,
        )
        return self._check(resp)

    def clear_toxics(self, proxy_name: str) -> None:
        resp = self.session.get(
            f"{self.base_url}/proxies/{proxy_name}/toxics",
            timeout=10,
        )
        toxics = self._check(resp)
        if not isinstance(toxics, list):
            return

        for toxic in toxics:
            toxic_name = toxic["name"]
            delete_resp = self.session.delete(
                f"{self.base_url}/proxies/{proxy_name}/toxics/{toxic_name}",
                timeout=10,
            )
            if delete_resp.status_code not in (200, 204):
                raise NetworkFaultError(
                    f"Failed deleting toxic={toxic_name}: {delete_resp.text}"
                )

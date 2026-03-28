from __future__ import annotations

import requests


class NetworkFaultError(Exception):
    pass


class ToxiproxyClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _check(self, response: requests.Response):
        if not response.ok:
            raise NetworkFaultError(
                f"HTTP {response.status_code} calling {response.request.method} "
                f"{response.request.url}: {response.text}"
            )
        if response.text.strip():
            return response.json()
        return {}

    def create_latency(self, proxy_name: str, latency_ms: int, jitter_ms: int = 0):
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

    def create_packet_loss(self, proxy_name: str, average_size: int = 512, size_variation: int = 128, delay_us: int = 0):
        """
        用 slicer 近似模拟 packet loss / 分片抖动场景。
        这不是严格意义的真实丢包，但对 benchmark 的鲁棒性测试足够有代表性。
        """
        payload = {
            "name": f"slicer_{average_size}",
            "type": "slicer",
            "stream": "downstream",
            "attributes": {
                "average_size": average_size,
                "size_variation": size_variation,
                "delay": delay_us,
            },
        }
        resp = self.session.post(
            f"{self.base_url}/proxies/{proxy_name}/toxics",
            json=payload,
            timeout=10,
        )
        return self._check(resp)

    def create_timeout(self, proxy_name: str, timeout_ms: int = 30000):
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

    def create_bandwidth(self, proxy_name: str, rate_kb: int = 128):
        payload = {
            "name": f"bandwidth_{rate_kb}",
            "type": "bandwidth",
            "stream": "downstream",
            "attributes": {
                "rate": rate_kb
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

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from technician_ai import api, workspaces
from technician_ai import database as db


class WorkspaceIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        registry = {
            "code-a": {"name": "A", "db": str(root / "a" / "tech.db"), "manuals": str(root / "a" / "manuals")},
            "code-b": {"name": "B", "db": str(root / "b" / "tech.db"), "manuals": str(root / "b" / "manuals")},
        }
        self.registry_path = root / "workspaces.json"
        self.registry_path.write_text(json.dumps(registry), encoding="utf-8")
        self._orig_registry = workspaces.REGISTRY_PATH
        workspaces.REGISTRY_PATH = self.registry_path

        # Seed a manual into workspace A only.
        token = workspaces.set_current(registry["code-a"])
        try:
            db.insert_document("manual_chunk", "Glass loader alarm E12", None,
                               {"manual_title": "loader.pdf", "source_path": "loader.pdf"})
            manuals = workspaces.manuals_dir()
            manuals.mkdir(parents=True, exist_ok=True)
            (manuals / "loader.pdf").write_bytes(b"%PDF-1.4 test")
        finally:
            workspaces.reset_current(token)

    def tearDown(self):
        workspaces.REGISTRY_PATH = self._orig_registry
        self.tmp.cleanup()

    def _client(self, code=None):
        client = TestClient(api.app)
        if code:
            self.assertEqual(client.post("/api/login", json={"code": code}).status_code, 200)
        return client

    def test_data_routes_require_code(self):
        client = self._client()
        self.assertEqual(client.get("/api/manuals").status_code, 401)
        self.assertEqual(client.get("/manuals/file/loader.pdf").status_code, 401)
        self.assertEqual(client.post("/api/login", json={"code": "wrong"}).status_code, 401)

    def test_workspace_sees_only_its_own_manuals(self):
        a = self._client("code-a")
        self.assertEqual(a.get("/api/me").json()["name"], "A")
        self.assertEqual([m["title"] for m in a.get("/api/manuals").json()["manuals"]], ["loader.pdf"])
        self.assertEqual(a.get("/manuals/file/loader.pdf").status_code, 200)

        b = self._client("code-b")
        self.assertEqual(b.get("/api/manuals").json()["manuals"], [])
        self.assertEqual(b.get("/api/manuals/files").json()["files"], [])
        self.assertEqual(b.get("/manuals/file/loader.pdf").status_code, 404)
        self.assertEqual(b.delete("/api/manuals/loader.pdf").status_code, 404)

        # B's delete attempt must not have touched A's manual.
        self.assertEqual(len(a.get("/api/manuals").json()["manuals"]), 1)

    def test_logout_clears_access(self):
        a = self._client("code-a")
        a.post("/api/logout")
        self.assertEqual(a.get("/api/manuals").status_code, 401)


if __name__ == "__main__":
    unittest.main()

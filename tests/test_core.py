from fastapi.testclient import TestClient

from app.ai import merge_labels
from app.cluster import category_of, pre_cluster, sanitize_folder, split_group
from app.main import app
from app.models import FileMeta

client = TestClient(app)
DAY = 86_400_000


def fm(name, mtime=1_760_000_000_000):
    return FileMeta(name=name, size=10, mtime=mtime)


def test_categories():
    assert category_of("Screenshot 2026-01-02 at 10.00.00.png") == "screenshots"
    assert category_of("invoice_123.pdf") == "invoices"
    assert category_of("resume_final3.docx") == "resumes"
    assert category_of("notes (1).pdf") == "duplicates"
    assert category_of("ChromeSetup.exe") == "installers"
    assert category_of("IMG_1234.jpg") == "images"
    assert category_of("weird") == "misc"


def test_sanitize_blocks_traversal_and_absolute_paths():
    assert sanitize_folder("../../etc/passwd") == "etc/passwd"
    assert sanitize_folder("/abs/path") == "abs/path"
    assert sanitize_folder("a/b/c/d/e") == "a/b/c"
    assert sanitize_folder("") == "Misc"
    assert sanitize_folder(".hidden/ok") == "hidden/ok"  # dots stripped: never creates hidden dirs
    assert sanitize_folder("Fin@nce/In<v>oices") == "Finnce/Invoices"


def test_pre_cluster_covers_every_file_exactly_once():
    names = [f"IMG_{i}.jpg" for i in range(10)] + [f"invoice_{i}.pdf" for i in range(5)] + ["odd.xyz", "x.exe"]
    groups = pre_cluster([fm(n) for n in names])
    seen = [f for g in groups for f in g.files]
    assert sorted(seen) == sorted(names)
    assert len(seen) == len(set(seen))
    # tiny buckets (1 installer, 1 odd file) fold into misc
    assert any(g.category == "misc" and len(g.files) == 2 for g in groups)


def test_split_by_month():
    files = [fm("a.pdf", 1_760_000_000_000), fm("b.pdf", 1_760_000_000_000 + 40 * DAY)]
    groups = split_group("Documents/PDFs", files)
    assert len(groups) == 2
    assert all(g.target_folder.startswith("Documents/PDFs/") for g in groups)


def test_merge_labels_validates_ai_output():
    groups = pre_cluster([fm(f"IMG_{i}.jpg") for i in range(5)])
    bad = [{"group_id": groups[0].group_id, "boss_name": "X" * 100, "target_folder": "../../root",
            "action": "delete", "confidence": 7, "reason": "r"}]
    out = merge_labels(groups, bad)[0]
    assert out.action in ("move", "archive")       # 'delete' rejected
    assert out.confidence == 1.0                    # clamped
    assert ".." not in out.target_folder
    assert len(out.boss_name) <= 40


def test_api_cluster_works_without_ai(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    files = [{"name": f"Screenshot {i}.png", "size": 1, "mtime": 1_760_000_000_000} for i in range(6)]
    r = client.post("/api/cluster", json={"files": files})
    assert r.status_code == 200
    body = r.json()
    assert body["ai"] is False and body["total_files"] == 6
    assert body["groups"][0]["target_folder"] == "Pictures/Screenshots"


def test_api_rejects_bad_input():
    assert client.post("/api/cluster", json={"files": [{"name": "", "size": 1, "mtime": 0}]}).status_code == 422
    assert client.post("/api/cluster", json={"files": [{"name": "a", "size": -1, "mtime": 0}]}).status_code == 422


def test_health_and_index():
    assert client.get("/api/health").json()["ok"] is True
    r = client.get("/")
    assert r.status_code == 200 and "ChoreRaid" in r.text
    assert r.headers["x-content-type-options"] == "nosniff"

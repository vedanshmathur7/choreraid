from app.cache import PlanCache
from app.models import FileMeta


def fm(name, size=1):
    return FileMeta(name=name, size=size, mtime=0)


def test_key_is_order_independent_and_size_sensitive():
    a = PlanCache.key_for([fm("a.pdf"), fm("b.jpg")])
    b = PlanCache.key_for([fm("b.jpg"), fm("a.pdf")])
    c = PlanCache.key_for([fm("a.pdf", 2), fm("b.jpg")])
    assert a == b
    assert a != c


def test_lru_evicts_least_recently_used():
    cache: PlanCache[int] = PlanCache(max_entries=2)
    cache.put("x", 1)
    cache.put("y", 2)
    assert cache.get("x") == 1  # x is now most recent
    cache.put("z", 3)           # evicts y
    assert cache.get("y") is None
    assert cache.get("x") == 1 and cache.get("z") == 3
    assert len(cache) == 2


def test_rejects_bad_size():
    try:
        PlanCache(max_entries=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")

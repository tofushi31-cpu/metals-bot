from datetime import datetime

from history import active_subscribers, add_subscription, is_subscriber


def test_subscription_lifecycle(tmp_path):
    db = tmp_path / "test.db"

    assert is_subscriber(111, db_path=db) is False
    assert active_subscribers(db_path=db) == []

    expires = add_subscription(111, 30, db_path=db)

    assert is_subscriber(111, db_path=db) is True
    assert active_subscribers(db_path=db) == [111]
    assert datetime.fromisoformat(expires) > datetime.now()


def test_renewal_extends_from_current_expiry(tmp_path):
    db = tmp_path / "test.db"

    first = add_subscription(222, 30, db_path=db)
    second = add_subscription(222, 30, db_path=db)

    delta = datetime.fromisoformat(second) - datetime.fromisoformat(first)
    assert 29 <= delta.days <= 30  # продлилось от конца, а не от "сейчас"


def test_expired_subscription_gives_no_access(tmp_path):
    db = tmp_path / "test.db"

    add_subscription(333, -1, db_path=db)  # подписка в прошлом

    assert is_subscriber(333, db_path=db) is False
    assert active_subscribers(db_path=db) == []

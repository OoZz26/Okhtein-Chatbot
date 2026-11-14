from typing import Any

from app.infra.whatsapp.waha_mapper import map_webhook


def event(**payload: Any) -> dict[str, Any]:
    base = {
        "id": "false_201001234567@c.us_ABC",
        "from": "201001234567@c.us",
        "fromMe": False,
        "body": "I want a black clutch",
        "hasMedia": False,
        "_data": {"notifyName": "Sara"},
    }
    return {"event": "message", "session": "default", "payload": {**base, **payload}}


def test_maps_a_text_message() -> None:
    msg = map_webhook(event())
    assert msg is not None
    assert (msg.message_id, msg.chat_id, msg.text, msg.sender_name) == (
        "false_201001234567@c.us_ABC",
        "201001234567@c.us",
        "I want a black clutch",
        "Sara",
    )
    assert not (msg.from_me or msg.is_group or msg.is_status or msg.has_media)


def test_flags_groups_status_media_and_own_messages() -> None:
    assert map_webhook(event(**{"from": "123@g.us"})).is_group  # type: ignore[union-attr]
    assert map_webhook(event(**{"from": "status@broadcast"})).is_status  # type: ignore[union-attr]
    assert map_webhook(event(hasMedia=True)).has_media  # type: ignore[union-attr]
    own = map_webhook(event(fromMe=True, to="209999@c.us"))
    assert own is not None
    assert own.from_me
    assert own.chat_id == "209999@c.us"


def test_other_events_and_malformed_payloads_are_ignored() -> None:
    assert map_webhook({"event": "session.status", "payload": {}}) is None
    assert map_webhook({"event": "message"}) is None
    assert map_webhook({"event": "message", "payload": {"body": "no ids"}}) is None

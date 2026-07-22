"""Quản trị: xem kết quả/thống kê, đăng ký nhận realtime, mở/đóng bầu cử. Yêu cầu token admin."""

from src import protocol
from src.handlers import require_role


@require_role("admin")
def handle_get_results(ctx, data):
    return ctx.store.tally()


@require_role("admin")
def handle_get_stats(ctx, data):
    return ctx.store.stats()


@require_role("admin")
def handle_subscribe(ctx, data):
    # Gắn chính connection này vào hub; từ đây nó sẽ nhận mọi RESULTS_UPDATE
    ctx.hub.subscribe(ctx.conn)
    return {}


@require_role("admin")
def handle_unsubscribe(ctx, data):
    ctx.hub.unsubscribe(ctx.conn)
    return {}


@require_role("admin")
def handle_open_election(ctx, data):
    election = ctx.store.set_election_status(protocol.ELECTION_OPEN)
    status = election["status"]
    ctx.hub.publish(protocol.make_push(
        protocol.ELECTION_STATE_CHANGED, {"election_status": status}))
    return {"election_status": status}


@require_role("admin")
def handle_close_election(ctx, data):
    election = ctx.store.set_election_status(protocol.ELECTION_CLOSED_STATE)
    status = election["status"]
    ctx.hub.publish(protocol.make_push(
        protocol.ELECTION_STATE_CHANGED, {"election_status": status}))
    return {"election_status": status}

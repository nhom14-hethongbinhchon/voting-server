"""Bỏ phiếu: GET_CANDIDATES, CAST_VOTE, GET_MY_STATUS. Đều yêu cầu token cử tri."""

from src import protocol
from src.handlers import require_int, require_role


@require_role("voter")
def handle_get_candidates(ctx, data):
    return {"candidates": ctx.store.get_candidates()}


@require_role("voter")
def handle_cast_vote(ctx, data):
    candidate_id = require_int(data, "candidate_id")
    voter_id = ctx.session.principal_id

    # record_vote kiểm tra và ghi trong cùng một lock; raise VoteError nếu vi phạm điều kiện
    result = ctx.store.record_vote(voter_id, candidate_id)

    # Phát cập nhật realtime NGOÀI lock của store để không treo server khi client nhận chậm
    ctx.hub.publish(protocol.make_push(protocol.RESULTS_UPDATE, ctx.store.tally()))
    return result


@require_role("voter")
def handle_get_my_status(ctx, data):
    voter_id = ctx.session.principal_id
    voter = ctx.store.find_voter(voter_id)
    election = ctx.store.get_election()
    return {
        "has_voted": bool(voter and voter["has_voted"]),
        "election_status": election["status"],
    }

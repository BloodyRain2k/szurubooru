import logging
from time import perf_counter

from szurubooru import db, rest
from szurubooru.rest import middleware

logger = logging.getLogger(__name__)


@middleware.pre_hook
def process_request(_ctx: rest.Context) -> None:
    db.reset_query_count()
    if _ctx._perf == -1:
        _ctx._perf = perf_counter()


@middleware.post_hook
def process_response(ctx: rest.Context) -> None:
    logger.info(
        "%s %s (user=%s, queries=%d, time=%dms)",
        ctx.method,
        ctx.url,
        ctx.user.name,
        db.get_query_count(),
        round((perf_counter() - ctx._perf) * 1000),
    )
    ctx._perf = -1

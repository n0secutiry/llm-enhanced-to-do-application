import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class BodyLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, logger, exclude_paths=None):
        super().__init__(app)
        self.logger = logger
        self.exclude_paths = set(exclude_paths or [])

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        start_time = time.perf_counter()

        request_body = await request.body()
        try:
            request_body_parsed = json.loads(request_body) if request_body else None
        except json.JSONDecodeError:
            request_body_parsed = request_body.decode("utf-8", errors="replace")

        self.logger.info(
            "Request: %s %s | query=%s | body=%s",
            request.method,
            request.url.path,
            dict(request.query_params),
            request_body_parsed,
        )

        try:
            response = await call_next(request)
            process_time_ms = (time.perf_counter() - start_time) * 1000

            body_chunks = []
            async for chunk in response.body_iterator:
                body_chunks.append(chunk)
            raw_body = b"".join(body_chunks)

            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type or "text/" in content_type:
                try:
                    response_body_parsed = json.loads(raw_body) if raw_body else None
                except json.JSONDecodeError:
                    response_body_parsed = raw_body.decode("utf-8", errors="replace")
            else:
                response_body_parsed = f"<binary {len(raw_body)} bytes>"

            self.logger.info(
                "Response: %s %s | status=%s | time=%.2fms | body=%s",
                request.method,
                request.url.path,
                response.status_code,
                process_time_ms,
                response_body_parsed,
            )

            return Response(
                content=raw_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        except Exception as err:
            self.logger.exception(
                "Request failed: %s %s | error=%s",
                request.method,
                request.url.path,
                err,
            )
            raise

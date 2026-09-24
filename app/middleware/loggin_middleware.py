import json
import time
import uuid

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class LoggingMiddleware(BaseHTTPMiddleware):
    async def iterate_over_body(self, body: bytes):
        yield body

    async def dispatch(self, request: Request, call_next):
        log_id = uuid.uuid4().hex[:8]
        start_time = time.perf_counter()

        x_forwarded_for = request.headers.get("x-forwarded-for")

        if x_forwarded_for:
            user_ip = x_forwarded_for.split(",")[0].strip()
        else:
            user_ip = request.client.host if request.client else "unknown"

        try:
            request_body = await request.body()

            if request_body:
                try:
                    user_body = json.loads(request_body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    user_body = request_body.decode("utf-8", errors="replace")
            else:
                user_body = None

        except Exception:
            user_body = None

        query_params = dict(request.query_params)
        headers = dict(request.headers)

        data_request_log = {
            "Action": "Request",
            "Log ID": log_id,
            "Method": request.method,
            "IP": user_ip,
            "URL Path": request.url.path,
            "Body": user_body,
            "Query Params": query_params,
            "Headers": headers,
        }
        logger.info(data_request_log)

        response = await call_next(request)

        response_body = b""

        async for chunk in response.body_iterator:
            response_body += chunk

        response = Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

        ignored_paths = {
            "/openapi.json",
            "/docs",
            "/redoc",
        }

        if request.url.path not in ignored_paths:
            try:
                response_data = json.loads(response_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                response_data = response_body.decode("utf-8", errors="replace")

            duration = time.perf_counter() - start_time

            data_response_log = {
                "Action": "Response",
                "Log ID": log_id,
                "Status Code": response.status_code,
                "Duration": round(duration, 4),
                "Data": response_data,
            }

            logger.info(data_response_log)

        return response

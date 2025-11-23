import typing
from functools import partial

import anyio
from fastapi.responses import StreamingResponse
from starlette.types import Send, Scope, Receive



class PathMatchingTree:
    """
    PathMatchingTree is a data structure that can be used to match a path with a value.
    It supports exact match, partial match, and wildcard match.
    For example, if the tree is built with the following config:
      {
          "/foo/bar": "value1",
          "/baz/qux": "value2",
          "/foo/*": "value3",
          "/foo/*/bar": "value4"
      }
    Then the following path will match the corresponding value:
      /foo/bar -> value1
      /baz/qux -> value2
      /foo/baz -> value3
      /foo/baz/bar -> value4
      /foo/baz/bar2 -> value3
    """
    child = dict
    value = None

    def __init__(self, config):
        self.child = {}
        self._build_tree(config)

    def _build_tree(self, config):
        for k, v in config.items():
            parts = k.split('/')
            self._add(parts, v)

    def _add(self, parts, value):
        node = self
        for part in parts:
            if part == '':
                continue
            if part not in node.child:
                node.child[part] = PathMatchingTree(dict())
            node = node.child[part]
        node.value = value

    def get_matching(self, path):
        parts = path.split('/')
        matched = self
        for part in parts:
            if part == '':
                continue
            if part in matched.child:
                matched = matched.child[part]
            elif '*' in matched.child:
                matched = matched.child['*']
            else:
                break
        return matched.value.rstrip('/')


class OverrideStreamResponse(StreamingResponse):
    """
    Override StreamingResponse to support lazy send response status_code and response headers
    """

    async def stream_response(self, send: Send) -> None:
        first_chunk = True
        async for chunk in self.body_iterator:
            if first_chunk:
                await self.send_request_header(send)
                first_chunk = False
            if not isinstance(chunk, bytes):
                chunk = chunk.encode(self.charset)
            await send({'type': 'http.response.body', 'body': chunk, 'more_body': True})

        if first_chunk:
            await self.send_request_header(send)
        await send({'type': 'http.response.body', 'body': b'', 'more_body': False})

    async def send_request_header(self, send: Send) -> None:
        await send(
            {
                'type': 'http.response.start',
                'status': self.status_code,
                'headers': self.raw_headers,
            }
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with anyio.create_task_group() as task_group:
            async def wrap(func: typing.Callable[[], typing.Coroutine]) -> None:
                await func()
                await task_group.cancel_scope.cancel()

            task_group.start_soon(wrap, partial(self.stream_response, send))
            await wrap(partial(self.listen_for_disconnect, receive))

        if self.background is not None:
            await self.background()

from aiohttp import web, ClientSession
import json
import tempfile

async def fetch(req):
    if req.method == "OPTIONS":
        return web.Response(body="", headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*'}, status=204)

    # 解析请求数据
    body = await req.json()

    messages = body.get("messages", [])
    model_name = body.get("model", "claude-instant-1.2")
    stream = body.get("stream", False)

    # 构造新的请求体
    new_messages = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        new_messages.append({"role": role, "content": content})

    chat_data = {
        "model": model_name,
        "messages": new_messages
    }

    url = "https://duckduckgo.com/duckchat/v1/chat"

    # Get the token from the Authorization header
    auth_header = req.headers.get('Authorization', '')
    token = auth_header.split(' ')[1] if ' ' in auth_header else ''

    headers = {
        "Accept": "text/event-stream",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "Cookie": "dcm=3",
        "Origin": "https://duckduckgo.com",
        "Referer": "https://duckduckgo.com/",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        "X-Vqd-4": token
    }

    async with ClientSession() as session:
        async with session.post(url, headers=headers, data=json.dumps(chat_data)) as resp:
            if resp.status != 200:
                return web.Response(status=resp.status)

            if stream:
                return await stream_response(req, resp)
            else:
                response_data = await resp.text()
                return web.json_response(response_data)


async def stream_response(req, resp):
    writer = web.StreamResponse()
    writer.headers['Access-Control-Allow-Origin'] = '*'
    writer.headers['Access-Control-Allow-Headers'] = '*'
    writer.headers['Content-Type'] = 'text/event-stream; charset=UTF-8'

    await writer.prepare(req)  # Prepare the writer before starting to receive chunks

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp:
        async for chunk in resp.content.iter_any():
            chunk_str = chunk.decode('utf-8')
            if chunk_str == 'data: [DONE]':
                break
            temp.write(chunk_str + '\n')  # Write each chunk to the temporary file

    # Open the temporary file and process each chunk
    with open(temp.name, 'r') as file:
        for chunk_str in file:
            try:
                chunk_json = json.loads(chunk_str[6:])  # Remove the 'data: ' prefix and parse the JSON
            except json.JSONDecodeError:
                continue  # Ignore chunks that are not valid JSON

            message = chunk_json.get("message", "")
            model = chunk_json.get("model", "")
            message_id = chunk_json.get("id", "")
            created_time = chunk_json.get("created", "")

            wrapped_chunk = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": message
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                },
                "system_fingerprint": None
            }

            event_data = f"data: {json.dumps(wrapped_chunk, ensure_ascii=False)}\n\n"
            await writer.write(event_data.encode('utf-8'))  # Write the chunk to the stream immediately

    return writer


async def onRequest(request):
    return await fetch(request)


app = web.Application()
app.router.add_route("*", "/v1/chat/completions", onRequest)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=3033)

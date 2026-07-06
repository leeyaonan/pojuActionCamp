<ApiReference>

<ApiHeader method="POST" path="https://api.longcat.chat/anthropic/v1/messages" title="Anthropic 消息">
使用 <b>Anthropic Claude API 格式</b> 创建消息。仅支持文本输入，支持流式（SSE）与非流式两种返回。
</ApiHeader>

<ApiSection title="Authorizations" />

<ParamField name="Authorization" type="string" location="header" :required="true">

身份验证密钥，需以 `Bearer YOUR_API_KEY` 形式置于请求头。

</ParamField>

<ApiSection title="Body" meta="application/json" />

<ParamField name="model" type="string" :required="true">

模型标识符。目前支持 `LongCat-2.0`。

</ParamField>

<ParamField name="messages" type="array" :required="true">

消息对象数组，仅允许文本输入。

<template #children>

<ParamField name="role" type="string" :required="true" :nested="true">

消息作者角色，必须为 `user` · `assistant` 之一。系统消息通过 `system` 参数单独传递。

</ParamField>

<ParamField name="content" type="string" :required="true" :nested="true">

消息内容，纯文本字符串。

</ParamField>

</template>

</ParamField>

<ParamField name="max_tokens" type="integer">

生成的最大 Token 数。

</ParamField>

<ParamField name="stream" type="boolean" :default="false">

是否以 SSE 流式返回响应。

</ParamField>

<ParamField name="temperature" type="number">

采样温度，范围 `0 ~ 1`。

</ParamField>

<ParamField name="top_p" type="number">

核采样（nucleus sampling）参数。

</ParamField>

<ParamField name="system" type="string">

用于设置上下文的系统消息。

</ParamField>

<ParamField name="thinking" type="object">

是否开启思考。`{"type":"enabled"}` 开启思考，`{"type":"disabled"}` 关闭思考。

</ParamField>

<template #rail>

<RequestExample
  title="请求示例"
  :langs="[{ key: 'curl', label: 'cURL' }, { key: 'py', label: 'Python' }]"
  :scenarios="[{ key: 'basic', label: '基础调用' }, { key: 'stream', label: '流式响应' }]">

<template #curl-basic>

```bash
curl --location --request POST 'https://api.longcat.chat/anthropic/v1/messages' \
  --header "Authorization: Bearer $LONGCAT_API_KEY" \
  --header "Content-Type: application/json" \
  --data-raw '{
    "model": "LongCat-2.0",
    "max_tokens": 1000,
    "messages": [{ "role": "user", "content": "你好，LongCat" }],
    "thinking": {
      "type": "enabled"
    }
  }'
```

</template>
<template #curl-stream>

```bash
curl --location --request POST 'https://api.longcat.chat/anthropic/v1/messages' \
  --header "Authorization: Bearer $LONGCAT_API_KEY" \
  --header "Content-Type: application/json" \
  --data-raw '{
    "model": "LongCat-2.0",
    "max_tokens": 1000,
    "messages": [{ "role": "user", "content": "你好" }],
    "stream": true
  }'
```

</template>
<template #py-basic>

```python
import anthropic

client = anthropic.Anthropic(
    api_key="YOUR_API_KEY",
    base_url="https://api.longcat.chat",
)
message = client.messages.create(
    model="LongCat-2.0",
    max_tokens=1000,
    messages=[{"role": "user", "content": "你好，LongCat！"}],
)
print(message.content[0].text)
```

</template>
<template #py-stream>

```python
import anthropic

client = anthropic.Anthropic(
    api_key="YOUR_API_KEY",
    base_url="https://api.longcat.chat",
)
with client.messages.stream(
    model="LongCat-2.0",
    max_tokens=1000,
    messages=[{"role": "user", "content": "你好"}],
) as stream:
    for text in stream.text_stream:
        print(text, end="")
```

</template>
</RequestExample>

<ResponseExample
  title="响应示例"
  :langs="[{ key: 'json', label: '非流式' }, { key: 'sse', label: '流式 SSE' }]">

<template #json>

```json
{
  "id": "msg_123",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "你好！有什么可以帮你的吗？",
      "thinking": "\n用户用中文向我打招呼，我应该用中文回复以保持一致。问候简单友好，因此礼貌而温暖的回应较为合适。我会简洁地致意，并以一个开放式的问题鼓励进一步交流。"
    }
  ],
  "model": "LongCat-2.0",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": { "input_tokens": 10, "output_tokens": 8 }
}
```

</template>
<template #sse>

```text
event: message_start
data: {"type":"message_start","message":{"id":"msg_123","type":"message","role":"assistant","content":[],"model":"LongCat-2.0","usage":{"input_tokens":10,"output_tokens":0}}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"你好"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"你好"}}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":8}}

event: message_stop
data: {"type":"message_stop"}
```

</template>
</ResponseExample>

</template>

</ApiReference>

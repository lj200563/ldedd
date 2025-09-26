import json
import time
from flask import stream_with_context, Response, jsonify
from curl_cffi import requests as curl_requests
from logger import logger
from config import config_manager
from token_manager import AuthTokenManager
from message_processor import MessageProcessor


class RequestHandler:
    def __init__(self, token_manager: AuthTokenManager):
        self.token_manager = token_manager
        
        self.default_headers = {
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Content-Type': 'text/plain;charset=UTF-8',
            'Connection': 'keep-alive',
            'Origin': 'https://grok.com',
            'Priority': 'u=1, i',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Sec-Ch-Ua': '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Baggage': 'sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c',
            'x-statsig-id': 'ZTpUeXBlRXJyb3I6IENhbm5vdCByZWFkIHByb3BlcnRpZXMgb2YgdW5kZWZpbmVkIChyZWFkaW5nICdjaGlsZE5vZGVzJyk='
        }
    
    def get_proxy_options(self):
        proxy = config_manager.get("API.PROXY")
        proxy_options = {}

        if proxy:
            logger.info(f"使用代理: {proxy}", "Server")
            
            if proxy.startswith("socks5://"):
                proxy_options["proxy"] = proxy
                
                if '@' in proxy:
                    auth_part = proxy.split('@')[0].split('://')[1]
                    if ':' in auth_part:
                        username, password = auth_part.split(':')
                        proxy_options["proxy_auth"] = (username, password)
            else:
                proxy_options["proxies"] = {"https": proxy, "http": proxy}     
        return proxy_options

    def handle_non_stream_response(self, response, model):
        try:
            logger.info("开始处理非流式响应（拼接流式内容）", "Server")
            
            # 解析流式响应的所有行，拼接完整内容和思考内容
            stream = response.iter_lines()
            full_content = ""
            thinking_content = ""
            model_response = None
            
            for chunk in stream:
                if not chunk:
                    continue
                try:
                    line_json = json.loads(chunk.decode("utf-8").strip())
                    
                    if line_json.get("error"):
                        logger.error(json.dumps(line_json, indent=2), "Server")
                        raise ValueError("RateLimitError")
                        
                    response_data = line_json.get("result", {}).get("response")
                    if not response_data:
                        continue
                    
                    # 处理 grok-4 和 grok-4-fast 的思考内容
                    if model in ["grok-4", "grok-4-fast"]:
                        # 收集思考内容 (isThinking: true)
                        if response_data.get("isThinking") and response_data.get("token"):
                            thinking_content += response_data["token"]

                        # 收集最终内容 (isThinking: false, messageTag: "final")
                        elif not response_data.get("isThinking") and response_data.get("messageTag") == "final" and response_data.get("token"):
                            full_content += response_data["token"]

                    # 处理 grok-3 和其他非推理模型
                    else:
                        # 获取token并拼接内容
                        token = response_data.get("token", "")
                        if token:
                            full_content += token
                    
                    # 检查是否有最终响应（modelResponse）
                    if response_data.get("modelResponse"):
                        model_response = response_data["modelResponse"]
                        break
                        
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.error(f"处理非流式响应行时出错: {str(e)}", "Server")
                    continue
            
            # 如果有 modelResponse，优先使用它的内容
            if model_response:
                if model in ["grok-4", "grok-4-fast"] and model_response.get("thinkingTrace"):
                    # 对于推理模型，将思考内容包装在 think 标签中
                    thinking_trace = model_response["thinkingTrace"]
                    final_message = f"<think>{thinking_trace}</think>{model_response.get('message', '')}"
                else:
                    final_message = model_response.get('message', '')
            else:
                # 如果没有 modelResponse，手动拼接内容
                if model in ["grok-4", "grok-4-fast"] and thinking_content:
                    final_message = f"<think>{thinking_content}</think>{full_content}"
                else:
                    final_message = full_content
            
            if not final_message:
                logger.warning("未找到响应内容", "Server")
                final_message = ""
            
            # 构建标准OpenAI兼容格式响应
            openai_response = {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": final_message
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            }
            
            logger.info(f"成功构建OpenAI响应，内容长度: {len(final_message)}", "Server")
            return openai_response
            
        except Exception as error:
            logger.error(f"处理非流式响应时出错: {str(error)}", "Server")
            raise

    def handle_stream_response(self, response, model):
        def generate():
            logger.info("开始处理流式响应", "Server")
            
            stream = response.iter_lines()
            thinking_started = False
            thinking_content = ""
            
            for chunk in stream:
                if not chunk:
                    continue
                try:
                    line_json = json.loads(chunk.decode("utf-8").strip())
                    
                    if line_json.get("error"):
                        logger.error(json.dumps(line_json, indent=2), "Server")
                        yield json.dumps({"error": "RateLimitError"}) + "\n\n"
                        return
                        
                    response_data = line_json.get("result", {}).get("response")
                    if not response_data:
                        continue
                    
                    # 处理 grok-4 和 grok-4-fast 的特殊流式响应
                    if model in ["grok-4", "grok-4-fast"]:
                        # 处理思考内容的开始
                        if response_data.get("isThinking") and not thinking_started:
                            thinking_started = True
                            # 发送开始思考标签
                            yield f"data: {json.dumps(MessageProcessor.create_chat_response('<think>', model, True))}\n\n"

                        # 处理思考内容
                        if response_data.get("isThinking") and response_data.get("token"):
                            thinking_content += response_data["token"]
                            yield f"data: {json.dumps(MessageProcessor.create_chat_response(response_data['token'], model, True))}\n\n"

                        # 处理思考结束和最终内容开始
                        elif not response_data.get("isThinking") and thinking_started and response_data.get("messageTag") == "final" and response_data.get("token"):
                            # 发送结束思考标签
                            yield f"data: {json.dumps(MessageProcessor.create_chat_response('</think>', model, True))}\n\n"
                            thinking_started = False
                            # 发送最终内容
                            yield f"data: {json.dumps(MessageProcessor.create_chat_response(response_data['token'], model, True))}\n\n"

                        # 处理最终内容的后续部分
                        elif not response_data.get("isThinking") and not thinking_started and response_data.get("messageTag") == "final" and response_data.get("token"):
                            yield f"data: {json.dumps(MessageProcessor.create_chat_response(response_data['token'], model, True))}\n\n"

                    # 处理 grok-3 和其他非推理模型
                    else:
                        result = MessageProcessor.process_model_response(response_data, model)
                        if result["token"]:
                            yield f"data: {json.dumps(MessageProcessor.create_chat_response(result['token'], model, True))}\n\n"
                        
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.error(f"处理流式响应行时出错: {str(e)}", "Server")
                    continue
                    
            yield "data: [DONE]\n\n"
            
        return generate()

    def make_grok_request(self, data, model, stream=False):
        response_status_code = 500
        
        try:
            retry_count = 0
            
            while retry_count < config_manager.get("RETRY.MAX_ATTEMPTS", 2):
                retry_count += 1
                
                token = self.token_manager.get_next_token_for_model(model)
                if not token:
                    raise ValueError('无可用令牌')
                
                config_manager.set("API.SIGNATURE_COOKIE", token)
                logger.info(f"当前令牌: {token[:50]}...", "Server")
                
                try:
                    request_payload = MessageProcessor.prepare_chat_messages(data.get("messages", []), model)
                    
                    proxy_options = self.get_proxy_options()
                    response = curl_requests.post(
                        f"{config_manager.get('API.BASE_URL')}/rest/app-chat/conversations/new",
                        headers={
                            **self.default_headers, 
                            "Cookie": token
                        },
                        data=json.dumps(request_payload),
                        impersonate="chrome133a",
                        stream=True,
                        **proxy_options
                    )
                    
                    logger.info(f"请求状态码: {response.status_code}", "Server")
                    
                    if response.status_code == 200:
                        response_status_code = 200
                        logger.info("请求成功", "Server")
                        
                        if stream:
                            return Response(
                                stream_with_context(self.handle_stream_response(response, model)),
                                content_type='text/event-stream'
                            )
                        else:
                                return self.handle_non_stream_response(response, model)
                            
                    elif response.status_code == 403:
                        response_status_code = 403
                        logger.error("IP暂时被封禁，请稍后重试或者更换IP", "Server")
                        raise ValueError('IP暂时被封无法破盾，请稍后重试或者更换ip')
                        
                    elif response.status_code == 429:
                        response_status_code = 429
                        logger.warning(f"令牌配额已用完，继续轮询其他令牌: {token[:20]}...", "Server")
                    else:
                        logger.warning(f"令牌返回异常状态码 {response.status_code}，继续轮询: {token[:20]}...", "Server")
                        
                except Exception as e:
                    logger.error(f"请求处理异常: {str(e)}", "Server")
                    continue
            
            if response_status_code == 403:
                raise ValueError('IP暂时被封无法破盾，请稍后重试或者更换ip')
            elif response_status_code == 500:
                raise ValueError('请求失败，请检查网络连接或稍后重试')    
                
        except Exception as error:
            logger.error(str(error), "ChatAPI")
            raise
            
    def validate_request(self, request_data):
        model = request_data.get("model")
        if not model:
            raise ValueError("模型参数缺失")
            
        if not config_manager.is_valid_model(model):
            raise ValueError(f"不支持的模型: {model}")
            
        messages = request_data.get("messages")
        if not messages or not isinstance(messages, list):
            raise ValueError("消息参数缺失或格式错误")
            
        return True

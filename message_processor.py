import uuid
import time
import json
import re
from logger import logger
from config import config_manager


class MessageProcessor:
    @staticmethod
    def create_chat_response(message, model, is_stream=False):
        base_response = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "created": int(time.time()),
            "model": model
        }

        if is_stream:
            return {
                **base_response,
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "content": message
                    }
                }]
            }

        return {
            **base_response,
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": message
                },
                "finish_reason": "stop"
            }],
            "usage": None
        }
    
    @staticmethod
    def process_message_content(content):
        if isinstance(content, str):
            return content
        return None

    @staticmethod
    def remove_think_tags(text):
        if not isinstance(text, str):
            return text
            
        text = re.sub(r'<think>[\s\S]*?<\/think>', '', text).strip()
        text = re.sub(r'!\[image]\(data:.*?base64,.*?\)', '[图片]', text)
        return text

    @staticmethod
    def process_tool_response(response_data):
        """规范化响应内容"""
        if isinstance(response_data, str):
            text = response_data
        elif isinstance(response_data, dict):
            # 过滤重复的 xai:tool_usage_card
            if (response_data.get("messageTag") == "tool_usage_card" and
                "xai:tool_usage_card" in response_data["token"]):
                return ''

            # 处理web搜索结果
            if response_data.get("webSearchResults"):
                web_results = response_data["webSearchResults"].get("results", [])
                if web_results:
                    formatted_results = []
                    for result in web_results:
                        if result.get("title") and result.get("url"):
                            title = result["title"].strip()
                            url = result["url"].strip()
                            if title and url:
                                formatted_results.append(f"[{title}]({url})")

                    if formatted_results:
                        return '\n' + '\n'.join(formatted_results) + '\n'
                return ''

            # 如果是字典但没有web搜索结果，提取token字段
            text = response_data.get("token", "")
            if not text:
                return ''
        else:
            return ''

        # 移除 grok:render 标签及内容
        text = re.sub(r'<grok:render[^>]*>.*?</grok:render>', '', text, flags=re.DOTALL)

        # 仅保留CDATA参数
        cdata_pattern = r'!\[CDATA\[(.*?)\]\]'
        matches = re.findall(cdata_pattern, text, re.DOTALL)

        if matches:
            # 过滤不含 "query" 的 CDATA
            filtered_matches = []
            for match in matches:
                if '"query"' in match:
                    filtered_matches.append(match)

            if filtered_matches:
                return '\n' + '\n'.join(filtered_matches) + '\n'

        if '<xai:tool_usage_card>' in text:
            return ''

        return text

    @staticmethod
    def process_content(content):
        if isinstance(content, list):
            text_content = ''
            for item in content:
                if item["type"] == 'image_url':
                    text_content += ("[图片]" if not text_content else '\n[图片]')
                elif item["type"] == 'text':
                    processed_text = MessageProcessor.remove_think_tags(item["text"])
                    text_content += (processed_text if not text_content else '\n' + processed_text)
            return text_content
        elif isinstance(content, dict) and content is not None:
            if content["type"] == 'image_url':
                return "[图片]"
            elif content["type"] == 'text':
                return MessageProcessor.remove_think_tags(content["text"])
        return MessageProcessor.remove_think_tags(MessageProcessor.process_message_content(content))

    @staticmethod
    def prepare_chat_messages(messages, model):
        processed_messages = []
        last_role = None
        last_content = ''
        
        for current in messages:
            role = 'assistant' if current["role"] == 'assistant' else 'user'
            text_content = MessageProcessor.process_content(current.get("content", ""))
            
            if text_content:
                if role == last_role and last_content:
                    last_content += '\n' + text_content
                    processed_messages[-1] = f"{role.upper()}: {last_content}"
                else:
                    processed_messages.append(f"{role.upper()}: {text_content}")
                    last_content = text_content
                    last_role = role
        
        conversation = '\n'.join(processed_messages)
        
        if not conversation.strip():
            raise ValueError('消息内容为空!')
        
        # 基础请求结构
        base_request = {
            "temporary": config_manager.get("API.IS_TEMP_CONVERSATION", False),
            "modelName": model,
            "message": conversation,
            "fileAttachments": [],
            "imageAttachments": [],
            "disableSearch": True,
            "enableImageGeneration": False,
            "returnImageBytes": False,
            "returnRawGrokInXaiRequest": False,
            "enableImageStreaming": False,
            "imageGenerationCount": 0,
            "forceConcise": False,
            "toolOverrides": {
                "imageGen": False,
                "webSearch": False,
                "xSearch": False,
                "xMediaSearch": False,
                "trendsSearch": False,
                "xPostAnalyze": False
            },
            "enableSideBySide": True,
            "sendFinalMetadata": True,
            "customPersonality": "",
            "deepsearchPreset": "",
            "isReasoning": config_manager.is_reasoning_model(model),
            "disableTextFollowUps": True
        }
        
        # 为 grok-4 添加特殊字段
        if model == "grok-4":
            grok4_request = {
                **base_request,
                "disableSearch": False,
                "enableImageGeneration": True,
                "imageGenerationCount": 2,
                "forceConcise": False,
                "toolOverrides": {},
                "enableSideBySide": True,
                "sendFinalMetadata": True,
                "customPersonality": "",
                "isReasoning": False,
                "webpageUrls": [],
                "metadata": {
                    "requestModelDetails": {
                        "modelId": "grok-4"
                    }
                },
                "disableTextFollowUps": True,
                "isFromGrokFiles": False,
                "disableMemory": False,
                "forceSideBySide": False,
                "modelMode": "MODEL_MODE_EXPERT",
                "isAsyncChat": False,
                "supportedFastTools": {
                    "calculatorTool": "1",
                    "unitConversionTool": "1"
                },
                "isRegenRequest": False
            }
            return grok4_request

        # 为 grok-4-fast 添加特殊字段
        if model == "grok-4-fast":
            grok4_fast_request = {
                **base_request,
                "modelName": config_manager.get_models()[model],
                "disableSearch": False,
                "enableImageGeneration": True,
                "returnImageBytes": False,
                "returnRawGrokInXaiRequest": False,
                "enableImageStreaming": True,
                "imageGenerationCount": 2,
                "forceConcise": False,
                "toolOverrides": {},
                "enableSideBySide": True,
                "sendFinalMetadata": True,
                "isReasoning": False,
                "webpageUrls": [],
                "responseMetadata": {
                    "requestModelDetails": {
                        "modelId": config_manager.get_models()[model]
                    }
                },
                "disableTextFollowUps": True,
                "disableMemory": False,
                "forceSideBySide": False,
                "modelMode": "MODEL_MODE_GROK_4_MINI_THINKING",
                "isAsyncChat": False
            }
            return grok4_fast_request
        
        return base_request
    
    @staticmethod
    def process_model_response(response, model):
        result = {"token": None}
        
        if model in ["grok-3", "grok-4", "grok-4-fast"]:
            result["token"] = response.get("token")
        
        return result

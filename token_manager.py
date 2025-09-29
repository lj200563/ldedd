import os
from logger import logger


class AuthTokenManager:
    def __init__(self):
        self.tokens = []
        self.current_index = 0
        self.last_round_index = -1
        
    def add_token(self, token_str):
        if isinstance(token_str, dict):
            token_str = token_str.get("token", "")
        
        if token_str and token_str not in self.tokens:
            self.tokens.append(token_str)
            self.current_index = 0
            self.last_round_index = -1
            logger.info(f"令牌添加成功: {token_str[:20]}...", "TokenManager")
            return True
        return False
    
    def add_tokens_batch(self, token_strs):
        """批量添加tokens，优化性能"""
        if not token_strs:
            return {"success": 0, "failed": 0, "duplicates": 0}
        
        # 转换为列表如果是其他类型
        if isinstance(token_strs, str):
            token_strs = [token_strs]
        
        # 使用set进行快速去重检查
        existing_tokens_set = set(self.tokens)
        new_tokens = []
        duplicates = 0
        failed = 0
        
        for token_str in token_strs:
            if isinstance(token_str, dict):
                token_str = token_str.get("token", "")
            
            if not token_str:
                failed += 1
                continue
                
            # 如果输入的是完整的cookie字符串，直接使用
            if 'sso=' in token_str and 'sso-rw=' in token_str:
                formatted_token = token_str
            else:
                # 如果只是cookie值，构造完整的cookie字符串
                formatted_token = f"sso-rw={token_str};sso={token_str}"
            
            if formatted_token in existing_tokens_set:
                duplicates += 1
            else:
                new_tokens.append(formatted_token)
                existing_tokens_set.add(formatted_token)
        
        # 批量添加新tokens
        if new_tokens:
            self.tokens.extend(new_tokens)
            # 只在最后重置索引一次
            self.current_index = 0
            self.last_round_index = -1
            logger.info(f"批量添加令牌完成: 成功 {len(new_tokens)} 个，重复 {duplicates} 个，失败 {failed} 个", "TokenManager")
        
        return {
            "success": len(new_tokens), 
            "failed": failed, 
            "duplicates": duplicates
        }
        
    def set_token(self, token_str):
        if isinstance(token_str, dict):
            token_str = token_str.get("token", "")
            
        self.tokens = [token_str]
        self.current_index = 0
        self.last_round_index = -1
        logger.info(f"设置单个令牌: {token_str[:20]}...", "TokenManager")

    def delete_token(self, token):
        try:
            if isinstance(token, dict):
                token = token.get("token", "")
            
            # 首先尝试直接匹配
            if token in self.tokens:
                self.tokens.remove(token)
                # 重置轮询状态以避免索引越界
                self.current_index = 0
                self.last_round_index = -1
                logger.info(f"令牌已成功移除: {token[:20]}...", "TokenManager")
                return True
            
            # 如果直接匹配失败，尝试通过SSO值匹配完整token
            for stored_token in self.tokens[:]:  # 创建副本以避免在迭代时修改列表
                if "sso=" in stored_token:
                    sso_value = stored_token.split("sso=")[1].split(";")[0]
                    if sso_value == token:
                        self.tokens.remove(stored_token)
                        # 重置轮询状态以避免索引越界
                        self.current_index = 0
                        self.last_round_index = -1
                        logger.info(f"令牌已成功移除: {stored_token[:20]}...", "TokenManager")
                        return True
            
            logger.warning(f"未找到要删除的令牌: {token[:20]}...", "TokenManager")
            return False
        except Exception as error:
            logger.error(f"令牌删除失败: {str(error)}", "TokenManager")
            return False
    
    def get_next_token_for_model(self, model_id):
        if not self.tokens:
            return None
            
        # 检查是否开始新的一轮轮询
        if self.current_index == 0 and self.last_round_index != -1:
            # 开始新一轮轮询，重置索引
            self.current_index = 0
        else:
            # 记录上一轮的最后索引
            if self.current_index == len(self.tokens) - 1:
                self.last_round_index = self.current_index
        
        # 按序号依次轮询
        token = self.tokens[self.current_index]
        
        # 移动到下一个索引
        self.current_index = (self.current_index + 1) % len(self.tokens)
        
        return token


    def get_all_tokens(self):
        return self.tokens.copy()
        
    def get_token_status_map(self):
        status_map = {}
        for i, token in enumerate(self.tokens):
            if "sso=" in token:
                sso = token.split("sso=")[1].split(";")[0]
            else:
                sso = f"token_{i}"
                
            status_map[sso] = {
                "isValid": True,
                "index": i
            }
        return status_map
    
    def load_from_env(self):
        sso_array = os.environ.get("TOK_E", "").split(',')
        if sso_array and sso_array[0]:
            for value in sso_array:
                if value.strip():
                    token_str = f"sso-rw={value.strip()};sso={value.strip()}"
                    self.add_token(token_str)
        
        logger.info(f"令牌加载完成，共加载: {len(self.get_all_tokens())}个令牌", "TokenManager")
    
    def is_empty(self):
        return len(self.tokens) == 0

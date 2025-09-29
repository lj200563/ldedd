import os
from logger import logger
from database import get_db, Token

class AuthTokenManager:
    def __init__(self):
        self.tokens = []
        self.current_index = 0
        self.last_round_index = -1

    def add_token(self, token_str):
        if isinstance(token_str, dict):
            token_str = token_str.get("token", "")

        if token_str and token_str not in self.tokens:
            db_gen = get_db()
            db = next(db_gen, None)
            if db:
                try:
                    if not db.query(Token).filter(Token.cookie == token_str).first():
                        db_token = Token(cookie=token_str)
                        db.add(db_token)
                        db.commit()
                        self.tokens.append(token_str)
                        self.current_index = 0
                        self.last_round_index = -1
                        logger.info(f"令牌添加成功: {token_str[:20]}...", "TokenManager")
                        return True
                finally:
                    next(db_gen, None)
            else:
                logger.warning("数据库未连接，令牌仅添加到内存中", "TokenManager")
                self.tokens.append(token_str)
                self.current_index = 0
                self.last_round_index = -1
                return True
        return False

    def add_tokens_batch(self, token_strs):
        if not token_strs:
            return {"success": 0, "failed": 0, "duplicates": 0}

        if isinstance(token_strs, str):
            token_strs = [token_strs]

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

            if 'sso=' in token_str and 'sso-rw=' in token_str:
                formatted_token = token_str
            else:
                formatted_token = f"sso-rw={token_str};sso={token_str}"

            if formatted_token in existing_tokens_set:
                duplicates += 1
            else:
                new_tokens.append(formatted_token)
                existing_tokens_set.add(formatted_token)

        if new_tokens:
            db_gen = get_db()
            db = next(db_gen, None)
            if db:
                try:
                    added_count = 0
                    for token in new_tokens:
                        if not db.query(Token).filter(Token.cookie == token).first():
                            db_token = Token(cookie=token)
                            db.add(db_token)
                            added_count += 1
                    db.commit()
                    self.tokens.extend(new_tokens)
                    self.current_index = 0
                    self.last_round_index = -1
                    logger.info(f"批量添加令牌完成: 成功 {added_count} 个，重复 {duplicates} 个，失败 {failed} 个", "TokenManager")
                finally:
                    next(db_gen, None)
            else:
                logger.warning(f"数据库未连接，{len(new_tokens)} 个令牌仅添加到内存中", "TokenManager")
                self.tokens.extend(new_tokens)
                self.current_index = 0
                self.last_round_index = -1

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
        db_gen = get_db()
        db = next(db_gen, None)
        try:
            if isinstance(token, dict):
                token = token.get("token", "")

            if db:
                db_token = db.query(Token).filter(Token.cookie == token).first()
                if db_token:
                    db.delete(db_token)
                    db.commit()
            else:
                logger.warning("数据库未连接，令牌仅从内存中删除", "TokenManager")

            if token in self.tokens:
                self.tokens.remove(token)
                self.current_index = 0
                self.last_round_index = -1
                logger.info(f"令牌已成功移除: {token[:20]}...", "TokenManager")
                return True

            for stored_token in self.tokens[:]:
                if "sso=" in stored_token:
                    sso_value = stored_token.split("sso=")[1].split(";")[0]
                    if sso_value == token:
                        if db:
                            db_token = db.query(Token).filter(Token.cookie == stored_token).first()
                            if db_token:
                                db.delete(db_token)
                                db.commit()
                        self.tokens.remove(stored_token)
                        self.current_index = 0
                        self.last_round_index = -1
                        logger.info(f"令牌已成功移除: {stored_token[:20]}...", "TokenManager")
                        return True
            
            logger.warning(f"未找到要删除的令牌: {token[:20]}...", "TokenManager")
            return False
        except Exception as error:
            logger.error(f"令牌删除失败: {str(error)}", "TokenManager")
            return False
        finally:
            if db:
                next(db_gen, None)

    def get_next_token_for_model(self, model_id):
        if not self.tokens:
            return None
        if self.current_index == 0 and self.last_round_index != -1:
            self.current_index = 0
        else:
            if self.current_index == len(self.tokens) - 1:
                self.last_round_index = self.current_index
        token = self.tokens[self.current_index]
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

    def load_from_db(self):
        db_gen = get_db()
        db = next(db_gen, None)
        if db:
            try:
                db_tokens = db.query(Token).all()
                self.tokens = [token.cookie for token in db_tokens]
                logger.info(f"从数据库加载了 {len(self.tokens)} 个令牌", "TokenManager")
            finally:
                next(db_gen, None)

    def load_from_env(self):
        sso_array = os.environ.get("SSO", "").split(',')
        if sso_array and sso_array[0]:
            for value in sso_array:
                if value.strip():
                    token_str = f"sso-rw={value.strip()};sso={value.strip()}"
                    self.add_token(token_str)
        logger.info(f"从环境变量加载了 {len(self.tokens)} 个令牌", "TokenManager")

    def is_empty(self):
        return len(self.tokens) == 0

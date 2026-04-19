import re
import json
from typing import List, Dict, Optional
import os
from openai import OpenAI
from loguru import logger


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')


def load_marketing_config(item_id=None):
    config_path = os.path.join(CONFIG_DIR, 'marketing_config.json')
    if not os.path.exists(config_path):
        return None
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    if not cfg.get('enabled'):
        return None
    strategy_name = cfg.get('items', {}).get(item_id, {}).get('strategy', 'default') if item_id else 'default'
    return cfg.get('strategies', {}).get(strategy_name)


def load_bargain_config():
    config_path = os.path.join(CONFIG_DIR, 'bargain_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"global": {"discount_rate": 0.85, "min_amount": 10, "max_bargain_rounds": 3}, "items": {}}


class XianyuReplyBot:
    def __init__(self):
        # 初始化OpenAI客户端
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
        self._init_system_prompts()
        self._init_agents()
        self.router = IntentRouter(self.agents['classify'])
        self.last_intent = None
        self.last_marketing = None
        self.last_reply_is_excuse = False


    def _init_agents(self):
        """初始化各领域Agent"""
        self.agents = {
            'classify':ClassifyAgent(self.client, self.classify_prompt, self._safe_filter),
            'price': PriceAgent(self.client, self.price_prompt, self._safe_filter),
            'tech': TechAgent(self.client, self.tech_prompt, self._safe_filter),
            'default': DefaultAgent(self.client, self.default_prompt, self._safe_filter),
        }

    def _init_system_prompts(self):
        """初始化各Agent专用提示词，优先加载用户自定义文件，否则使用Example默认文件"""
        prompt_dir = os.path.join(CONFIG_DIR, "prompts")
        
        def load_prompt_content(name: str) -> str:
            """尝试加载提示词文件"""
            # 优先尝试加载 target.txt
            target_path = os.path.join(prompt_dir, f"{name}.txt")
            if os.path.exists(target_path):
                file_path = target_path
            else:
                # 尝试默认提示词 target_example.txt
                file_path = os.path.join(prompt_dir, f"{name}_example.txt")

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"已加载 {name} 提示词，路径: {file_path}, 长度: {len(content)} 字符")
                return content

        try:
            # 加载分类提示词
            self.classify_prompt = load_prompt_content("classify_prompt")
            # 加载价格提示词
            self.price_prompt = load_prompt_content("price_prompt")
            # 加载技术提示词
            self.tech_prompt = load_prompt_content("tech_prompt")
            # 加载默认提示词
            self.default_prompt = load_prompt_content("default_prompt")
                
            logger.info("成功加载所有提示词")
        except Exception as e:
            logger.error(f"加载提示词时出错: {e}")
            raise

    def _safe_filter(self, text: str) -> str:
        """安全过滤模块"""
        blocked_phrases = ["微信", "QQ", "支付宝", "银行卡", "线下"]
        return "[安全提醒]请通过平台沟通" if any(p in text for p in blocked_phrases) else text

    def format_history(self, context: List[Dict]) -> str:
        """格式化对话历史，返回完整的对话记录"""
        # 过滤掉系统消息，只保留用户和助手的对话
        user_assistant_msgs = [msg for msg in context if msg['role'] in ['user', 'assistant']]
        return "\n".join([f"{msg['role']}: {msg['content']}" for msg in user_assistant_msgs])

    def generate_reply(self, user_msg: str, item_desc: str, context: List[Dict], image_urls: Optional[List[str]] = None, item_id: str = None) -> str:
        """生成回复主流程"""
        formatted_context = self.format_history(context)

        # 1. 路由决策（图片消息默认走 default Agent）
        if image_urls:
            detected_intent = 'default'
        else:
            detected_intent = self.router.detect(user_msg, item_desc, formatted_context)

        # 2. 获取对应Agent
        internal_intents = {'classify'}

        if detected_intent == 'no_reply':
            logger.info(f'意图识别完成: no_reply - 无需回复')
            self.last_intent = 'no_reply'
            return "-"
        elif detected_intent in self.agents and detected_intent not in internal_intents:
            agent = self.agents[detected_intent]
            logger.info(f'意图识别完成: {detected_intent}')
            self.last_intent = detected_intent
        else:
            agent = self.agents['default']
            logger.info(f'意图识别完成: default')
            self.last_intent = 'default'

        # 3. 获取议价次数
        bargain_count = self._extract_bargain_count(context)
        logger.info(f'议价次数: {bargain_count}')

        # 4. 加载议价配置（议价和图片消息都需要）
        bargain_cfg = None
        if (detected_intent == 'price' or image_urls) and item_id:
            cfg = load_bargain_config()
            bargain_cfg = cfg.get("items", {}).get(item_id, cfg.get("global", {}))

        # 5. 加载营销策略
        marketing = load_marketing_config(item_id)
        if marketing:
            actual_rate = marketing.get("actual_discount_rate")
            if actual_rate and bargain_cfg:
                bargain_cfg = dict(bargain_cfg)
                bargain_cfg["discount_rate"] = actual_rate

        # 6. 生成回复
        reply = agent.generate(
            user_msg=user_msg,
            item_desc=item_desc,
            context=formatted_context,
            bargain_count=bargain_count,
            image_urls=image_urls,
            bargain_config=bargain_cfg,
            marketing=marketing
        )

        # 7. 标记是否触发了借口话术（供 main.py 发送截图用）
        self.last_marketing = marketing
        self.last_reply_is_excuse = False
        if marketing and reply:
            excuse_replies = marketing.get("excuse_replies", [])
            for excuse in excuse_replies:
                if excuse[:6] in reply:
                    self.last_reply_is_excuse = True
                    break

        return reply
    
    def _extract_bargain_count(self, context: List[Dict]) -> int:
        """
        从上下文中提取议价次数信息
        
        Args:
            context: 对话历史
            
        Returns:
            int: 议价次数，如果没有找到则返回0
        """
        # 查找系统消息中的议价次数信息
        for msg in context:
            if msg['role'] == 'system' and '议价次数' in msg['content']:
                try:
                    # 提取议价次数
                    match = re.search(r'议价次数[:：]\s*(\d+)', msg['content'])
                    if match:
                        return int(match.group(1))
                except Exception:
                    pass
        return 0

    def reload_prompts(self):
        """重新加载所有提示词"""
        logger.info("正在重新加载提示词...")
        self._init_system_prompts()
        self._init_agents()
        logger.info("提示词重新加载完成")


class IntentRouter:
    """意图路由决策器"""

    def __init__(self, classify_agent):
        self.rules = {
            'tech': {  # 技术类优先判定
                'keywords': ['参数', '规格', '型号', '连接', '对比'],
                'patterns': [
                    r'和.+比'             
                ]
            },
            'price': {
                'keywords': ['便宜', '价', '砍价', '少点'],
                'patterns': [r'\d+元', r'能少\d+']
            }
        }
        self.classify_agent = classify_agent

    def detect(self, user_msg: str, item_desc, context) -> str:
        """三级路由策略（技术优先）"""
        text_clean = re.sub(r'[^\w\u4e00-\u9fa5]', '', user_msg)
        
        # 1. 技术类关键词优先检查
        if any(kw in text_clean for kw in self.rules['tech']['keywords']):
            # logger.debug(f"技术类关键词匹配: {[kw for kw in self.rules['tech']['keywords'] if kw in text_clean]}")
            return 'tech'
            
        # 2. 技术类正则优先检查
        for pattern in self.rules['tech']['patterns']:
            if re.search(pattern, text_clean):
                # logger.debug(f"技术类正则匹配: {pattern}")
                return 'tech'

        # 3. 价格类检查
        for intent in ['price']:
            if any(kw in text_clean for kw in self.rules[intent]['keywords']):
                # logger.debug(f"价格类关键词匹配: {[kw for kw in self.rules[intent]['keywords'] if kw in text_clean]}")
                return intent
            
            for pattern in self.rules[intent]['patterns']:
                if re.search(pattern, text_clean):
                    # logger.debug(f"价格类正则匹配: {pattern}")
                    return intent
        
        # 4. 大模型兜底
        # logger.debug("使用大模型进行意图分类")
        return self.classify_agent.generate(
            user_msg=user_msg,
            item_desc=item_desc,
            context=context
        )


class BaseAgent:
    """Agent基类"""

    def __init__(self, client, system_prompt, safety_filter):
        self.client = client
        self.system_prompt = system_prompt
        self.safety_filter = safety_filter

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0, image_urls: Optional[List[str]] = None, bargain_config: dict = None, marketing: dict = None) -> str:
        """生成回复模板方法"""
        messages = self._build_messages(user_msg, item_desc, context, image_urls=image_urls, bargain_config=bargain_config, marketing=marketing)
        response = self._call_llm(messages)
        return self.safety_filter(response)

    IMAGE_ANALYSIS_PROMPT = (
        "用户发送了一张图片，请仔细识别图片内容。\n"
        "如果是账单/收据/小票：\n"
        "1. 识别商家名称和账单总金额\n"
        "2. 按照【议价规则】中的折扣计算优惠后价格（金额x折扣率，四舍五入到分）\n"
        "3. 回复格式：'XX店账单XX元，打X折后XX元，确认的话直接拍，拍完我改价哈'\n"
        "如果是其他图片：简要描述内容并礼貌回复。\n"
        "回复要求：简短友好，总字数不超过60字。"
    )

    def _build_messages(self, user_msg: str, item_desc: str, context: str, image_urls: Optional[List[str]] = None, bargain_config: dict = None, marketing: dict = None) -> List[Dict]:
        """构建消息链，支持图片和营销策略"""
        marketing_info = ""
        if marketing:
            display = marketing.get("display_discount", "")
            excuses = marketing.get("excuse_replies", [])
            if display:
                marketing_info += f"\n【营销策略】对外宣传折扣为{display}，但实际按议价规则中的折扣率计算。"
            if excuses:
                marketing_info += f"\n【差价解释话术】当买家质疑折扣和宣传不一致时，使用以下话术回复：\n- " + "\n- ".join(excuses)

        if image_urls:
            discount_info = ""
            if bargain_config:
                rate = bargain_config.get("discount_rate", 0.85)
                discount_display = int(rate * 10)
                discount_info = f"\n【议价规则】折扣率：{discount_display}折（即金额x{rate}）"
            system_content = f"【商品信息】{item_desc}\n【你与客户对话历史】{context}{discount_info}{marketing_info}\n{self.IMAGE_ANALYSIS_PROMPT}"
            system_msg = {"role": "system", "content": system_content}
            user_content = [{"type": "text", "text": user_msg if user_msg and user_msg.strip() != '[图片]' else "请分析这张图片"}]
            for url in image_urls:
                user_content.append({"type": "image_url", "image_url": {"url": url}})
            user_msg_obj = {"role": "user", "content": user_content}
        else:
            system_content = f"【商品信息】{item_desc}\n【你与客户对话历史】{context}{marketing_info}\n{self.system_prompt}"
            system_msg = {"role": "system", "content": system_content}
            user_msg_obj = {"role": "user", "content": user_msg}

        return [system_msg, user_msg_obj]

    def _call_llm(self, messages: List[Dict], temperature: float = 0.4) -> str:
        """调用大模型"""
        response = self.client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "qwen-max"),
            messages=messages,
            temperature=temperature,
            max_tokens=500,
            top_p=0.8
        )
        return response.choices[0].message.content


class PriceAgent(BaseAgent):
    """议价处理Agent"""

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0, image_urls: Optional[List[str]] = None, bargain_config: dict = None, marketing: dict = None) -> str:
        dynamic_temp = self._calc_temperature(bargain_count)
        messages = self._build_messages(user_msg, item_desc, context, image_urls=image_urls, bargain_config=bargain_config, marketing=marketing)

        cfg_info = f"\n▲当前议价轮次：{bargain_count}"
        if bargain_config:
            rate = bargain_config.get("discount_rate", 0.85)
            discount_display = int(rate * 10)
            max_rounds = bargain_config.get("max_bargain_rounds", 3)
            bottom_msg = bargain_config.get("bottom_line_message", "已经是最低价了")
            cfg_info += f"\n▲议价规则：账单金额按{discount_display}折计算，不能再低，最多议价{max_rounds}轮"
            if bargain_count >= max_rounds:
                cfg_info += f"\n▲已达议价上限，请坚守底线：{bottom_msg}"
        messages[0]['content'] += cfg_info

        response = self.client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "qwen-max"),
            messages=messages,
            temperature=dynamic_temp,
            max_tokens=500,
            top_p=0.8
        )
        return self.safety_filter(response.choices[0].message.content)

    def _calc_temperature(self, bargain_count: int) -> float:
        return min(0.3 + bargain_count * 0.15, 0.9)


class TechAgent(BaseAgent):
    """技术咨询Agent"""

    def generate(self, user_msg: str, item_desc: str, context: str, bargain_count: int = 0, image_urls: Optional[List[str]] = None, bargain_config: dict = None, marketing: dict = None) -> str:
        messages = self._build_messages(user_msg, item_desc, context, image_urls=image_urls, marketing=marketing)

        response = self.client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "qwen-max"),
            messages=messages,
            temperature=0.4,
            max_tokens=500,
            top_p=0.8,
            extra_body={
                "enable_search": True,
            }
        )
        return self.safety_filter(response.choices[0].message.content)


class ClassifyAgent(BaseAgent):
    """意图识别Agent"""
    pass


class DefaultAgent(BaseAgent):
    """默认处理Agent"""

    def _call_llm(self, messages: List[Dict], *args) -> str:
        """限制默认回复长度"""
        response = super()._call_llm(messages, temperature=0.7)
        return response
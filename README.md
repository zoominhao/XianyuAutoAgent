# XianyuAutoAgent - 闲鱼智能客服机器人

基于 [shaxiu/XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent) 二次开发，增加了账单识别、自动改价、营销策略等功能。

## 功能

| 功能 | 说明 |
|------|------|
| AI 自动回复 | 通义千问驱动，支持意图识别（议价/技术/通用） |
| 图片识别 | 识别账单/收据图片，自动提取金额和商家 |
| 自动算价 | 按配置折扣计算优惠价，引导买家下单 |
| 自动改价 | 买家下单后自动调用闲鱼 API 修改订单价格 |
| 邮件通知 | 改价成功后发送邮件通知（支持 QQ/163/Gmail） |
| 营销策略 | 可配置对外宣传折扣与实际折扣差异，含借口话术 |
| 议价控制 | 按商品配置最大折扣、议价轮数、底线话术 |
| 人工接管 | 发送 `。` 切换人工/AI 模式 |

## 项目结构

```
XianyuAutoAgent/
├── main.py                    # 入口
├── start.bat                  # Windows 一键启动
├── .env                       # 环境变量（敏感信息，不提交）
├── .env.example               # 环境变量模板
├── config/                    # 配置文件
│   ├── bargain_config.json    #   折扣/议价配置
│   ├── marketing_config.json  #   营销策略配置
│   ├── prompts/               #   AI 提示词
│   └── marketing_images/      #   营销截图素材
├── core/                      # 业务逻辑
│   ├── agent.py               #   AI Agent（意图路由 + 多专家）
│   ├── apis.py                #   闲鱼 API（Token/商品/改价）
│   ├── context_manager.py     #   对话上下文 + SQLite
│   └── notifier.py            #   通知模块（邮件/微信）
├── utils/                     # 工具函数
│   └── xianyu_utils.py        #   签名/解密/设备ID
└── data/                      # 运行时数据（自动生成）
    └── chat_history.db
```

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/zoominhao/XianyuAutoAgent.git
cd XianyuAutoAgent
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填写以下必填项：

```env
API_KEY=你的通义千问API Key        # 阿里云百炼平台获取
COOKIES_STR=你的闲鱼Cookie          # 浏览器F12获取
```

#### 获取 Cookie

1. 浏览器打开 https://www.goofish.com/ 登录
2. F12 → Network → 筛选 `h5api`
3. 点击页面触发请求 → 找到 `h5api.m.goofish.com` 的请求
4. Headers → Cookie 字段 → 复制完整值

#### 通知配置（可选）

邮件通知需要 SMTP 授权码：QQ 邮箱 → 设置 → 账户 → POP3/SMTP → 开启 → 获取授权码

### 3. 配置折扣

编辑 `config/bargain_config.json`：

```json
{
  "global": {
    "discount_rate": 0.85,
    "max_bargain_rounds": 3,
    "bottom_line_message": "这个折扣已经是最低了"
  },
  "items": {
    "商品ID": {
      "discount_rate": 0.80,
      "max_bargain_rounds": 5
    }
  }
}
```

### 4. 运行

```bash
python main.py
```

或 Windows 双击 `start.bat`。

## 配置说明

### 折扣配置 (`config/bargain_config.json`)

| 字段 | 说明 | 示例 |
|------|------|------|
| `discount_rate` | 折扣率 | `0.80` = 8折 |
| `min_amount` | 最低起算金额 | `10` |
| `max_bargain_rounds` | 最多议价轮数 | `3` |
| `bottom_line_message` | 底线话术 | `"不能再低了"` |

`items` 按商品 ID 单独配置，未配置的走 `global`。

### 营销策略 (`config/marketing_config.json`)

| 字段 | 说明 |
|------|------|
| `display_discount` | 对外宣传的折扣（如"8折"） |
| `actual_discount_rate` | 实际计算折扣（如 0.90 = 9折） |
| `excuse_replies` | 买家质疑时的解释话术 |
| `excuse_image` | 解释时附带的截图 URL |

### 提示词 (`config/prompts/`)

| 文件 | 用途 |
|------|------|
| `default_prompt.txt` | 通用客服（引导发账单） |
| `price_prompt.txt` | 议价专家 |
| `classify_prompt_example.txt` | 意图分类 |
| `tech_prompt_example.txt` | 技术咨询 |

自定义版优先于 `_example` 版加载。

## 业务流程

```
买家咨询 → 引导发账单图片
    ↓
收到账单 → AI 识别金额/商家 → 按折扣算价
    ↓
告知买家优惠价 → 引导拍下
    ↓
买家下单 → 自动改价 → 邮件通知
```

## 致谢

- 原项目：[shaxiu/XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent)
- API 参考：[cv-cat/XianYuApis](https://github.com/cv-cat/XianYuApis)

## 注意事项

本项目仅供学习与交流，请遵守闲鱼平台规则。

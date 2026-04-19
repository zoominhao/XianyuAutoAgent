import os
import requests
from datetime import datetime
from loguru import logger


def send_order_notification(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id=""):
    notify_type = os.getenv("NOTIFY_TYPE", "").lower()
    if notify_type == "wxpusher":
        return _send_wxpusher(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id)
    elif notify_type == "pushplus":
        return _send_pushplus(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id)
    elif notify_type == "email":
        return _send_email(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id)
    else:
        logger.debug("通知未启用")
        return False


def _build_content(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    discount_display = int(discount_rate * 10) if discount_rate else '-'
    return (
        f"<h2>闲鱼订单改价通知</h2>"
        f"<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse;'>"
        f"<tr><td><b>订单号</b></td><td>{order_id or '待确认'}</td></tr>"
        f"<tr><td><b>商家</b></td><td>{store_name or '未知'}</td></tr>"
        f"<tr><td><b>账单原价</b></td><td>¥{original_amount}</td></tr>"
        f"<tr><td><b>折扣</b></td><td>{discount_display}折</td></tr>"
        f"<tr><td><b>改后价格</b></td><td><b>¥{agreed_price}</b></td></tr>"
        f"<tr><td><b>买家ID</b></td><td>{buyer_id or '未知'}</td></tr>"
        f"<tr><td><b>时间</b></td><td>{now}</td></tr>"
        f"</table>"
        f"<p>订单已自动改价，请确认金额无误。买家付款后请及时处理。</p>"
    )


def _send_wxpusher(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id):
    app_token = os.getenv("WXPUSHER_APP_TOKEN", "")
    uid = os.getenv("WXPUSHER_UID", "")
    if not app_token or not uid:
        logger.warning("WXPUSHER 配置不完整，跳过通知")
        return False

    content = _build_content(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id)
    summary = f"闲鱼改价 - {store_name or '未知'} ¥{agreed_price}"

    try:
        resp = requests.post("https://wxpusher.zjiecode.com/api/send/message", json={
            "appToken": app_token,
            "content": content,
            "summary": summary,
            "contentType": 2,
            "uids": [uid]
        }, timeout=10)
        result = resp.json()
        if result.get("code") == 1000:
            logger.info(f"📱 微信通知已推送")
            return True
        else:
            logger.warning(f"推送失败: {result.get('msg')}")
            return False
    except Exception as e:
        logger.error(f"推送异常: {e}")
        return False


def _send_pushplus(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id):
    token = os.getenv("PUSHPLUS_TOKEN", "")
    if not token:
        logger.warning("PUSHPLUS_TOKEN 未配置，跳过通知")
        return False

    content = _build_content(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id)

    try:
        resp = requests.post("http://www.pushplus.plus/send", json={
            "token": token,
            "title": f"闲鱼改价 - {store_name or '未知'} ¥{agreed_price}",
            "content": content,
            "template": "html"
        }, timeout=10)
        result = resp.json()
        if result.get("code") == 200:
            logger.info(f"📱 微信通知已推送")
            return True
        else:
            logger.warning(f"推送失败: {result.get('msg')}")
            return False
    except Exception as e:
        logger.error(f"推送异常: {e}")
        return False


def _send_email(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    notify_to = os.getenv("EMAIL_NOTIFY_TO", "")
    smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.qq.com")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "465"))
    smtp_user = os.getenv("EMAIL_SMTP_USER", "")
    smtp_password = os.getenv("EMAIL_SMTP_PASSWORD", "")
    use_ssl = os.getenv("EMAIL_USE_SSL", "true").lower() == "true"

    if not all([notify_to, smtp_server, smtp_user, smtp_password]):
        logger.warning("邮件配置不完整，跳过通知")
        return False

    content = _build_content(order_id, store_name, original_amount, agreed_price, discount_rate, buyer_id)
    subject = f"闲鱼订单改价通知 - {store_name or '未知商家'} ¥{agreed_price}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = notify_to
    msg.attach(MIMEText(content, 'html', 'utf-8'))

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [notify_to], msg.as_string())
        server.quit()
        logger.info(f"📧 邮件通知已发送到 {notify_to}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False

"""
messenger_api.py — Kết nối Meta Graph API (Page Inbox + Conversations)
======================================================================
Đọc hội thoại từ Facebook Page Inbox, extract thông tin lead,
và match ngược về Ad ID để tính lead quality.

Giới hạn API:
  - Chỉ đọc được tin nhắn gửi VÀO Page (không phải chat cá nhân)
  - Cần permission: pages_messaging, pages_read_engagement
  - Conversations chứa sender_id có thể match với facebook_uid trong CustomerProfile
"""
import os
import re
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

import requests

log = logging.getLogger("messenger_api")

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
PAGE_ID      = os.getenv("META_PAGE_ID", "")
API_VERSION  = os.getenv("META_API_VERSION", "v20.0")
BASE_URL     = f"https://graph.facebook.com/{API_VERSION}"
MOCK_MODE    = not bool(ACCESS_TOKEN) or os.getenv("ADS_MOCK_MODE", "false").lower() == "true"

# Từ khóa intent quan tâm BĐS (càng nhiều từ khóa, chất lượng càng cao)
HIGH_INTENT_KEYWORDS = [
    "mua", "đặt cọc", "cọc", "giá bao nhiêu", "diện tích", "căn hộ",
    "vốn", "lãi suất", "thanh toán", "hỗ trợ vay", "bao giờ bàn giao",
    "pháp lý", "sổ đỏ", "sổ hồng", "chính sách", "chiết khấu",
    "xem nhà", "xem dự án", "đặt lịch", "tư vấn", "đầu tư"
]
MEDIUM_INTENT_KEYWORDS = [
    "thông tin", "dự án", "vị trí", "khu vực", "đường", "quận",
    "cho thuê", "giá", "bao nhiêu", "hướng", "tầng", "view"
]


class MessengerAPI:
    """Kết nối Meta Graph API để đọc hội thoại Page Inbox."""

    def __init__(self):
        self.token   = ACCESS_TOKEN
        self.page_id = PAGE_ID
        self.mock    = MOCK_MODE
        if self.mock:
            log.warning("⚠️  MessengerAPI chạy ở MOCK MODE")

    def _get(self, endpoint: str, params: dict = None) -> dict:
        if self.mock:
            return {}
        params = params or {}
        params["access_token"] = self.token
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    # ── Conversations ─────────────────────────────────────────────────────────

    def get_conversations(self, limit: int = 100) -> list[dict]:
        """
        Lấy danh sách hội thoại từ Page Inbox.
        Mỗi conversation có thể chứa thông tin ad_id nếu người dùng đến từ Facebook Ad.
        """
        if self.mock:
            return _mock_conversations(limit)

        fields = "id,participants,snippet,unread_count,message_count,updated_time,thread_key"
        data   = self._get(f"{self.page_id}/conversations",
                           {"fields": fields, "limit": limit, "platform": "messenger"})
        return data.get("data", [])

    def get_messages_in_conversation(self, conversation_id: str) -> list[dict]:
        """Lấy tất cả tin nhắn trong 1 cuộc hội thoại."""
        if self.mock:
            return _mock_messages(conversation_id)

        fields = "id,message,from,created_time,attachments"
        data   = self._get(f"{conversation_id}/messages",
                           {"fields": fields, "limit": 200})
        return data.get("data", [])

    def get_lead_info_from_conversation(self, conversation_id: str) -> dict:
        """
        Extract thông tin khách từ hội thoại:
          - Tên + Page-scoped ID (PSID) của sender
          - SĐT / email nếu họ cung cấp trong chat
          - Ad ID nếu conversation bắt đầu từ quảng cáo
        """
        conv_data = self.get_messages_in_conversation(conversation_id)
        all_text  = " ".join([m.get("message", "") for m in conv_data]).lower()

        # Extract phone từ nội dung chat
        phone_match = re.findall(r"0[3-9]\d{8}", all_text)
        email_match = re.findall(r"[\w.+-]+@[\w-]+\.\w+", all_text)

        # Tính intent score từ keywords
        intent_score = _compute_intent_score(all_text)

        # Lấy sender info (người đầu tiên không phải page)
        sender_name = ""
        sender_id   = ""
        for msg in reversed(conv_data):  # reversed = tin đầu tiên
            frm = msg.get("from", {})
            if str(frm.get("id", "")) != str(self.page_id):
                sender_name = frm.get("name", "")
                sender_id   = str(frm.get("id", ""))
                break

        return {
            "conversation_id": conversation_id,
            "sender_name":     sender_name,
            "sender_psid":     sender_id,   # Page-scoped ID (≠ FB UID)
            "phone":           phone_match[0] if phone_match else None,
            "email":           email_match[0] if email_match else None,
            "message_count":   len(conv_data),
            "full_text":       all_text[:2000],  # Giới hạn lưu
            "intent_score":    intent_score,
        }

    def match_conversation_to_ad(self, conversation_id: str,
                                 thread_key: str = None) -> Optional[str]:
        """
        Cố gắng trích xuất ad_id từ thread metadata.
        Thread key của Messenger Ad thường có format: m_<ad_id> hoặc có ref param.
        Trong thực tế dùng Click-to-Messenger ads ref tracking.
        """
        if thread_key and "ad_" in thread_key:
            return thread_key.split("ad_")[-1].split("_")[0]
        return None

    def fetch_lead_form_submissions(self, ad_id: str,
                                    form_id: str = None) -> list[dict]:
        """
        Dùng Lead Ads API để lấy form submissions cho một ad cụ thể.
        Đây là cách CHẮC CHẮN nhất để map lead → ad_id.
        """
        from .fb_ads_api import FacebookAdsAPI
        fb = FacebookAdsAPI()

        target_form_id = form_id or ad_id  # fallback: dùng ad_id như form_id
        submissions    = fb.get_lead_form_submissions(target_form_id)

        enriched = []
        for sub in submissions:
            fields_data = {f["name"]: f["values"][0] if f["values"] else ""
                           for f in sub.get("field_data", [])}
            enriched.append({
                "lead_form_id":   target_form_id,
                "fb_ad_id":       ad_id,
                "submission_id":  sub.get("id"),
                "created_time":   sub.get("created_time"),
                "name":           fields_data.get("full_name") or fields_data.get("name", ""),
                "phone":          fields_data.get("phone_number") or fields_data.get("phone", ""),
                "email":          fields_data.get("email", ""),
                "raw_fields":     json.dumps(fields_data),
            })
        return enriched

    def sync_messenger_leads(self, limit: int = 200) -> dict:
        """
        Orchestrate: đọc hội thoại → extract leads → ghi vào DB.
        Returns dict với counts.
        """
        log.info("🔄 Sync Messenger leads bắt đầu...")
        conversations = self.get_conversations(limit=limit)
        log.info(f"   Tìm thấy {len(conversations)} hội thoại")

        synced = 0
        errors = 0

        try:
            from src.database import SessionLocal, MessengerLead
            db = SessionLocal()

            for conv in conversations:
                try:
                    conv_id  = conv.get("id") or conv.get("conversation_id")
                    existing = db.query(MessengerLead).filter_by(
                        conversation_id=conv_id
                    ).first()

                    lead_info = self.get_lead_info_from_conversation(conv_id)

                    if existing:
                        # Cập nhật message count và score
                        existing.message_count = lead_info["message_count"]
                        existing.intent_score  = lead_info["intent_score"]
                        existing.last_message_at = datetime.now()
                    else:
                        ml = MessengerLead(
                            conversation_id  = conv_id,
                            fb_ad_id         = self.match_conversation_to_ad(
                                conv_id, conv.get("thread_key", "")),
                            page_id          = self.page_id,
                            sender_name      = lead_info["sender_name"],
                            sender_psid      = lead_info["sender_psid"],
                            phone            = lead_info["phone"],
                            email            = lead_info["email"],
                            message_count    = lead_info["message_count"],
                            first_message_at = datetime.now(),
                            last_message_at  = datetime.now(),
                            intent_score     = lead_info["intent_score"],
                            raw_messages_json = lead_info["full_text"],
                        )
                        db.add(ml)
                    synced += 1
                except Exception as e:
                    log.warning(f"   Lỗi xử lý conv {conv.get('id')}: {e}")
                    errors += 1

            db.commit()
            db.close()

        except Exception as e:
            log.error(f"DB error trong sync_messenger_leads: {e}")
            errors += 1

        log.info(f"✅ Sync xong: {synced} synced, {errors} lỗi")
        return {"synced": synced, "errors": errors, "total": len(conversations)}


# ── Intent scoring ────────────────────────────────────────────────────────────

def _compute_intent_score(text: str) -> float:
    """Tính điểm intent từ nội dung chat (0-10)."""
    score = 0.0
    text_lower = text.lower()

    high_hits   = sum(1 for kw in HIGH_INTENT_KEYWORDS   if kw in text_lower)
    medium_hits = sum(1 for kw in MEDIUM_INTENT_KEYWORDS if kw in text_lower)

    score += min(6.0, high_hits * 1.5)
    score += min(3.0, medium_hits * 0.5)

    # Bonus: cung cấp số điện thoại
    if re.search(r"0[3-9]\d{8}", text_lower):
        score += 1.5
    # Bonus: đề cập số tiền/ngân sách
    if re.search(r"\d+\s*(tỷ|triệu|tr\b|ty\b)", text_lower):
        score += 0.5

    return round(min(score, 10.0), 2)


# ── Mock data ─────────────────────────────────────────────────────────────────

def _mock_conversations(limit: int) -> list[dict]:
    names = [
        "Nguyễn Văn Hùng", "Trần Thị Mai", "Lê Minh Tuấn",
        "Phạm Thị Lan", "Hoàng Đức Anh", "Vũ Thị Hoa",
        "Đặng Văn Bình", "Bùi Thị Kim", "Phan Văn Long",
        "Ngô Thị Thúy",
    ]
    ad_ids = ["ad_camp_1000_1", "ad_camp_1001_0", "ad_camp_1002_1",
              "ad_camp_1003_0", None]
    n      = min(limit, 10)
    return [
        {
            "id":            f"conv_{100 + i}",
            "participants":  {"data": [{"name": names[i], "id": f"psid_{2000+i}"}]},
            "snippet":       _random_snippet(i),
            "message_count": random.randint(3, 25),
            "updated_time":  (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat(),
            "thread_key":    f"m_ad_{ad_ids[i % len(ad_ids)]}" if ad_ids[i % len(ad_ids)] else None,
            "fb_ad_id":      ad_ids[i % len(ad_ids)],
        }
        for i in range(n)
    ]

def _mock_messages(conversation_id: str) -> list[dict]:
    import hashlib, random
    seed = int(hashlib.md5(conversation_id.encode()).hexdigest()[:8], 16)
    rng  = random.Random(seed)

    sample_exchanges = [
        ("user", "Cho tôi hỏi giá căn hộ 2PN hiện tại là bao nhiêu ạ?"),
        ("page", "Dạ chào bạn! Hiện dự án có các căn 2PN từ 2.8 tỷ. Bạn muốn tư vấn thêm không ạ?"),
        ("user", "Bạn cho mình xem mặt bằng được không? Mình đang cân nhắc đặt cọc"),
        ("page", "Dạ được ạ! Mình gửi ngay. Bạn có thể cho mình số điện thoại để liên hệ chi tiết hơn không?"),
        ("user", "Số mình là 0912345678. Lãi suất vay ưu đãi như thế nào ạ?"),
        ("page", "Dạ hiện ngân hàng hỗ trợ vay 70%, lãi suất ưu đãi 7.5%/năm trong 24 tháng đầu"),
        ("user", "OK để mình suy nghĩ thêm. Bao giờ có thể đặt lịch xem dự án?"),
    ]

    n_msgs = rng.randint(3, min(len(sample_exchanges), 7))
    msgs   = []
    for j, (role, text) in enumerate(sample_exchanges[:n_msgs]):
        msgs.append({
            "id":           f"msg_{conversation_id}_{j}",
            "message":      text,
            "from":         {"id": "page_000", "name": "Fanpage"} if role == "page"
                             else {"id": f"psid_user", "name": "Khách"},
            "created_time": (datetime.now() - timedelta(hours=n_msgs - j)).isoformat(),
        })
    return msgs

def _random_snippet(idx: int) -> str:
    snippets = [
        "Cho hỏi giá căn hộ mình muốn đặt cọc",
        "Lãi suất vay bao nhiêu ạ",
        "Bao giờ bàn giao nhà vậy bạn",
        "Có mặt bằng gửi cho mình xem không",
        "OK để mình suy nghĩ thêm nhé",
        "Diện tích tối thiểu là bao nhiêu",
        "Chính sách chiết khấu như thế nào",
        "Sổ đỏ hay sổ hồng vậy bạn",
        "Tôi muốn xem nhà mẫu",
        "Giá đã bao gồm phí không",
    ]
    return snippets[idx % len(snippets)]

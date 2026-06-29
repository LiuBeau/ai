"""
用户画像模块 (User Profile)
负责结构化存储和管理用户个人数据，为 Agent 提供个性化服务支持

【面试知识点】记忆系统设计要点：
1. 记忆层次 (Memory Hierarchy): 工作记忆→短期记忆→长期记忆
2. 记忆巩固 (Memory Consolidation): 短期记忆到期前评估并升级到长期
3. 遗忘曲线 (Ebbinghaus Forgetting Curve): 置信度随时间衰减，确认时增强
4. 混合检索 (Hybrid Retrieval): SQLite结构化 + ChromaDB语义 + 短期上下文
"""

import sqlite3
import json
import time
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
from enum import Enum

# ===== 配置 =====
DB_PATH = "user_profile.db"
CHROMA_PATH = "./chroma_memory"

# 记忆系统常量（面试时可以解释设计理由）
CONSOLIDATION_THRESHOLD_HOURS = 6      # 短期记忆6小时后开始评估是否升级
CONFIDENCE_BOOST_ON_CONFIRM = 0.2      # 用户确认偏好时的置信度提升
CONFIDENCE_DECAY_ON_NEGATE = 0.3       # 用户否定偏好时的置信度下降
CONFIDENCE_DECAY_PER_DAY = 0.01        # 每天的自然衰减（遗忘曲线）
CONFIDENCE_VALID_THRESHOLD = 0.3       # 置信度低于此值标记为待验证
LLM_EXTRACT_INTERVAL = 5               # 每5轮对话执行一次LLM深度提取

# ===== ChromaDB 向量记忆同步 =====
try:
    import chromadb
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
    
    _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    _embedding_fn = ONNXMiniLM_L6_V2()
    _profile_collection = _chroma_client.get_or_create_collection(
        name="profile_memory",
        embedding_function=_embedding_fn
    )
    _context_collection = _chroma_client.get_or_create_collection(
        name="context_memory",
        embedding_function=_embedding_fn
    )
    CHROMA_AVAILABLE = True
    print("✅ 用户画像向量库初始化成功")
except ImportError:
    CHROMA_AVAILABLE = False
    _profile_collection = None
    _context_collection = None
    print("⚠️ ChromaDB 未安装，跳过画像向量同步")

def _sync_to_chroma(collection_name: str, category: str, key: str, value: str, doc_id: str = None):
    """同步到 ChromaDB（用于语义检索）"""
    if not CHROMA_AVAILABLE:
        return
    
    collection = _profile_collection if collection_name == "profile" else _context_collection
    
    if doc_id is None:
        doc_id = f"{collection_name}_{category}_{key}"
    
    content = f"[{category}] {key}: {value}"
    try:
        collection.upsert(
            documents=[content],
            metadatas=[{"category": category, "key": key, "source": collection_name}],
            ids=[doc_id]
        )
    except Exception as e:
        print(f"⚠️ ChromaDB 同步失败: {e}")

def _delete_from_chroma(collection_name: str, doc_id: str):
    """从 ChromaDB 删除记录"""
    if not CHROMA_AVAILABLE:
        return
    try:
        collection = _profile_collection if collection_name == "profile" else _context_collection
        collection.delete(ids=[doc_id])
    except:
        pass

def _query_chroma(query: str, n_results: int = 3) -> List[Dict]:
    """语义检索（混合检索的一部分）"""
    if not CHROMA_AVAILABLE:
        return []
    
    results = []
    
    # 同时查两个 collection
    for collection_name, collection in [("profile", _profile_collection), ("context", _context_collection)]:
        try:
            res = collection.query(query_texts=[query], n_results=n_results)
            if res.get('documents') and res['documents'][0]:
                for i, doc in enumerate(res['documents'][0]):
                    metadata = res['metadatas'][0][i] if res['metadatas'] else {}
                    results.append({
                        "content": doc,
                        "source": collection_name,
                        "category": metadata.get('category', ''),
                        "key": metadata.get('key', '')
                    })
        except:
            pass
    
    return sorted(results, key=lambda x: x.get('content', ''))

# ===== 偏好分类枚举 =====
class PreferenceCategory(str, Enum):
    WEATHER = "weather"           # 天气相关偏好
    CLOTHING = "clothing"         # 穿衣搭配偏好
    FOOD = "food"                 # 饮食偏好
    TRAVEL = "travel"            # 出行/旅游偏好
    ACTIVITY = "activity"         # 活动偏好
    PAYMENT = "payment"           # 支付偏好

# ===== 数据类 =====
@dataclass
class PreferenceItem:
    category: str
    key: str
    value: str
    confidence: float = 1.0      # 置信度 0-1
    source: str = "explicit"      # explicit(明确)/implicit(推断)/consolidated(巩固)
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

@dataclass
class ContextItem:
    key: str
    value: str
    expires_at: str
    hit_count: int = 0            # 被检索到的次数（用于评估是否值得升级）
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()

# ===== 数据库初始化 =====
def init_profile_db():
    """初始化用户画像数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 基本信息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS basic_info (
            key TEXT PRIMARY KEY,
            value TEXT,
            confidence REAL DEFAULT 1.0,
            updated_at TEXT
        )
    """)
    
    # 2. 偏好表（多维度）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            category TEXT,
            key TEXT,
            value TEXT,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'explicit',
            hit_count INTEGER DEFAULT 0,
            last_hit_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (category, key)
        )
    """)
    
    # 3. 习惯表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            key TEXT PRIMARY KEY,
            value TEXT,
            confidence REAL DEFAULT 1.0,
            updated_at TEXT
        )
    """)
    
    # 4. 财务信息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial (
            key TEXT PRIMARY KEY,
            value TEXT,
            confidence REAL DEFAULT 1.0,
            updated_at TEXT
        )
    """)
    
    # 5. 短期上下文表（带过期时间和命中计数）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recent_context (
            key TEXT PRIMARY KEY,
            value TEXT,
            expires_at TEXT,
            hit_count INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    
    # 6. 画像版本（用于追踪更新）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_version (
            id INTEGER PRIMARY KEY,
            version INTEGER DEFAULT 1,
            updated_at TEXT
        )
    """)
    
    # 7. 对话统计（用于控制提取频率）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_stats (
            key TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ 用户画像数据库初始化完成")

# ===== 基础 CRUD 操作 =====
def _get_connection():
    return sqlite3.connect(DB_PATH)

def set_basic_info(key: str, value: str, confidence: float = 1.0):
    """设置基本信息"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO basic_info (key, value, confidence, updated_at)
        VALUES (?, ?, ?, ?)
    """, (key, value, confidence, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"📝 [画像] 基本信息: {key} = {value}")
    _sync_to_chroma("profile", "basic", key, value, f"basic_{key}")

def get_basic_info(key: str) -> Optional[str]:
    """获取基本信息"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM basic_info WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_basic_info() -> Dict[str, str]:
    """获取所有基本信息"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM basic_info")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def set_preference(category: str, key: str, value: str, confidence: float = 1.0, source: str = "explicit"):
    """设置偏好"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO preferences (category, key, value, confidence, source, hit_count, updated_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
    """, (category, key, value, confidence, source, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"📝 [画像] 偏好[{category}]: {key} = {value} (置信度:{confidence})")
    _sync_to_chroma("profile", category, key, value, f"pref_{category}_{key}")

def update_preference_confidence(category: str, key: str, delta: float):
    """
    更新偏好置信度（遗忘曲线的工程实现）
    
    Args:
        delta: 正数=提升（用户确认），负数=下降（用户否定或时间衰减）
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT confidence FROM preferences WHERE category = ? AND key = ?
    """, (category, key))
    row = cursor.fetchone()
    
    if row:
        old_confidence = row[0]
        new_confidence = max(0.1, min(1.0, old_confidence + delta))
        
        cursor.execute("""
            UPDATE preferences SET confidence = ?, updated_at = ?
            WHERE category = ? AND key = ?
        """, (new_confidence, datetime.now().isoformat(), category, key))
        
        conn.commit()
        print(f"📊 [置信度] {category}.{key}: {old_confidence:.2f} → {new_confidence:.2f}")
        
        # 如果置信度太低，标记为待验证
        if new_confidence < CONFIDENCE_VALID_THRESHOLD:
            print(f"⚠️ [置信度] {category}.{key} 置信度过低，标记为待验证")
    
    conn.close()

def increment_preference_hit(category: str, key: str):
    """增加偏好的命中次数（用于评估重要性）"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE preferences SET hit_count = hit_count + 1, last_hit_at = ?
        WHERE category = ? AND key = ?
    """, (datetime.now().isoformat(), category, key))
    conn.commit()
    conn.close()

def get_preference(category: str, key: str) -> Optional[str]:
    """获取单个偏好"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT value FROM preferences WHERE category = ? AND key = ?
    """, (category, key))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_preferences_by_category(category: str) -> List[PreferenceItem]:
    """获取某个分类的所有偏好"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, key, value, confidence, source, updated_at 
        FROM preferences WHERE category = ?
    """, (category,))
    rows = cursor.fetchall()
    conn.close()
    return [
        PreferenceItem(
            category=r[0], key=r[1], value=r[2], 
            confidence=r[3], source=r[4], updated_at=r[5]
        ) for r in rows
    ]

def get_all_preferences() -> List[PreferenceItem]:
    """获取所有偏好"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, key, value, confidence, source, updated_at 
        FROM preferences
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        PreferenceItem(
            category=r[0], key=r[1], value=r[2], 
            confidence=r[3], source=r[4], updated_at=r[5]
        ) for r in rows
    ]

def set_habit(key: str, value: str, confidence: float = 1.0):
    """设置习惯"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO habits (key, value, confidence, updated_at)
        VALUES (?, ?, ?, ?)
    """, (key, value, confidence, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"📝 [画像] 习惯: {key} = {value}")
    _sync_to_chroma("profile", "habit", key, value, f"habit_{key}")

def get_habit(key: str) -> Optional[str]:
    """获取习惯"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM habits WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_habits() -> Dict[str, str]:
    """获取所有习惯"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM habits")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def set_financial(key: str, value: str, confidence: float = 1.0):
    """设置财务信息"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO financial (key, value, confidence, updated_at)
        VALUES (?, ?, ?, ?)
    """, (key, value, confidence, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"📝 [画像] 财务: {key} = {value}")
    _sync_to_chroma("profile", "financial", key, value, f"financial_{key}")

def get_financial(key: str) -> Optional[str]:
    """获取财务信息"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM financial WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_financial() -> Dict[str, str]:
    """获取所有财务信息"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM financial")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

# ===== 短期上下文（带过期和命中计数）=====
def set_recent_context(key: str, value: str, expire_hours: int = 24):
    """设置短期上下文（自动过期）"""
    expires_at = (datetime.now() + timedelta(hours=expire_hours)).isoformat()
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO recent_context (key, value, expires_at, hit_count, updated_at)
        VALUES (?, ?, ?, 0, ?)
    """, (key, value, expires_at, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    _sync_to_chroma("context", "recent", key, value, f"context_{key}")

def get_recent_context(key: str) -> Optional[str]:
    """获取短期上下文（检查过期，增加命中计数）"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT value, expires_at FROM recent_context WHERE key = ?
    """, (key,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    value, expires_at = row
    
    if datetime.now() > datetime.fromisoformat(expires_at):
        delete_recent_context(key)
        conn.close()
        return None
    
    # 增加命中计数
    cursor.execute("""
        UPDATE recent_context SET hit_count = hit_count + 1, updated_at = ?
        WHERE key = ?
    """, (datetime.now().isoformat(), key))
    conn.commit()
    conn.close()
    
    return value

def delete_recent_context(key: str):
    """删除短期上下文"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recent_context WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    _delete_from_chroma("context", f"context_{key}")

def cleanup_expired_context():
    """清理所有已过期的短期上下文"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recent_context WHERE expires_at < ?", (datetime.now().isoformat(),))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        print(f"🧹 清理了 {deleted} 条过期的短期上下文")

# ===== 记忆巩固机制（核心）=====
def consolidate_memories():
    """
    记忆巩固：评估即将过期的短期记忆，将高价值信息升级到长期记忆
    
    【面试知识点】记忆巩固机制：
    - 模拟海马体→新皮层的记忆转移过程
    - 评估标准：命中次数、与现有偏好的关联性、是否涉及核心属性
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    # 查找即将过期的上下文（剩余时间 < CONSOLIDATION_THRESHOLD_HOURS）
    threshold_time = (datetime.now() + timedelta(hours=CONSOLIDATION_THRESHOLD_HOURS)).isoformat()
    cursor.execute("""
        SELECT key, value, hit_count FROM recent_context
        WHERE expires_at < ? AND hit_count >= 1
    """, (threshold_time,))
    
    rows = cursor.fetchall()
    consolidated_count = 0
    
    for key, value, hit_count in rows:
        # 评估是否值得升级
        if _should_consolidate(key, value, hit_count):
            # 尝试解析为结构化偏好
            consolidated = _parse_context_to_profile(key, value)
            if consolidated:
                batch_update_profile(consolidated, category="consolidated")
                consolidated_count += 1
                print(f"🔄 [巩固] '{key}': {value[:30]}... → 升级为长期记忆")
            
            # 删除已处理的短期上下文
            delete_recent_context(key)
    
    conn.close()
    
    if consolidated_count > 0:
        print(f"✅ 记忆巩固完成，共升级 {consolidated_count} 条短期记忆")
    else:
        print("📭 暂无需要巩固的记忆")

def _should_consolidate(key: str, value: str, hit_count: int) -> bool:
    """
    判断短期记忆是否值得升级到长期记忆
    
    评估标准：
    1. 命中次数 >= 2（被多次检索到，说明重要）
    2. 内容涉及用户核心属性（姓名、偏好、习惯等）
    3. 与现有长期记忆有较强关联
    """
    # 规则1：命中次数足够多
    if hit_count >= 2:
        return True
    
    # 规则2：涉及核心属性关键词
    core_keywords = ["喜欢", "爱好", "习惯", "过敏", "忌口", "职业", "姓名", "年龄", "性别"]
    if any(kw in value for kw in core_keywords):
        return True
    
    # 规则3：与现有偏好相关
    all_prefs = get_all_preferences()
    for pref in all_prefs:
        if pref.key in value or pref.value in value:
            return True
    
    return False

def _parse_context_to_profile(key: str, value: str) -> Optional[Dict[str, Any]]:
    """
    将短期上下文解析为结构化画像数据
    
    例如："我喜欢吃辣" → {"preferences": {"food": {"口味": "辣"}}}
    """
    extracts = {}
    
    # 尝试解析为基本信息
    basic_patterns = [
        (r"(我叫|我的名字是|姓名)[：:]\s*([^\s，。]+)", ("name",)),
        (r"(我今年|年龄|岁)[：:]\s*(\d+)", ("age",)),
        (r"(住在|常住|地区)[：:]\s*([^\s，。]+)", ("location",)),
    ]
    for pattern, keys in basic_patterns:
        match = re.search(pattern, value)
        if match:
            extracts["basic"] = {keys[0]: match.group(2)}
            return extracts
    
    # 尝试解析为偏好
    pref_patterns = [
        (r"我(喜欢|爱吃).{0,20}(辣|甜的?|清淡|火锅|川菜|粤菜)", ("food", "口味")),
        (r"(不吃|不能吃|过敏).{0,20}(海鲜|羊肉|牛肉|花生)", ("food", "忌口")),
        (r"我(怕冷|怕热|喜欢冷|喜欢热)", ("weather", "体感偏好")),
        (r"我喜欢.{0,10}(休闲|正式|运动|潮流|简约)风格", ("clothing", "风格")),
        (r"我(喜欢|倾向).{0,10}(飞机|高铁|自驾|火车)", ("travel", "出行方式")),
    ]
    for pattern, (cat, key) in pref_patterns:
        match = re.search(pattern, value)
        if match:
            extracts["preferences"] = {cat: {key: match.group(0)}}
            return extracts
    
    # 如果无法结构化，存入长期记忆的"其他"分类
    extracts["preferences"] = {"other": {key: value}}
    return extracts

# ===== 置信度衰减（遗忘曲线）=====
def apply_forgetting_curve():
    """
    应用遗忘曲线：所有长期记忆的置信度随时间衰减
    
    【面试知识点】遗忘曲线工程实现：
    - 每天衰减 CONFIDENCE_DECAY_PER_DAY
    - 用户再次提及该偏好时，置信度提升 CONFIDENCE_BOOST_ON_CONFIRM
    - 置信度低于阈值的偏好标记为待验证
    """
    conn = _get_connection()
    cursor = conn.cursor()
    
    # 计算需要衰减的时间阈值（超过1天）
    day_ago = (datetime.now() - timedelta(days=1)).isoformat()
    
    # 更新 preferences 表
    cursor.execute("""
        UPDATE preferences 
        SET confidence = MAX(0.1, confidence - ?), updated_at = ?
        WHERE updated_at < ? AND confidence > 0.1
    """, (CONFIDENCE_DECAY_PER_DAY, datetime.now().isoformat(), day_ago))
    
    # 更新 habits 表
    cursor.execute("""
        UPDATE habits 
        SET confidence = MAX(0.1, confidence - ?), updated_at = ?
        WHERE updated_at < ? AND confidence > 0.1
    """, (CONFIDENCE_DECAY_PER_DAY, datetime.now().isoformat(), day_ago))
    
    # 更新 basic_info 表
    cursor.execute("""
        UPDATE basic_info 
        SET confidence = MAX(0.1, confidence - ?), updated_at = ?
        WHERE updated_at < ? AND confidence > 0.1
    """, (CONFIDENCE_DECAY_PER_DAY, datetime.now().isoformat(), day_ago))
    
    conn.commit()
    conn.close()
    print("⏳ 已应用遗忘曲线衰减")

# ===== 对话统计（控制提取频率）=====
def increment_conversation_count() -> int:
    """增加对话计数，返回当前轮数"""
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO conversation_stats (key, value, updated_at)
        VALUES ('turn_count', COALESCE((SELECT value FROM conversation_stats WHERE key = 'turn_count'), 0) + 1, ?)
    """, (datetime.now().isoformat(),))
    conn.commit()
    cursor.execute("SELECT value FROM conversation_stats WHERE key = 'turn_count'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def should_run_llm_extract() -> bool:
    """判断是否应该执行 LLM 深度提取（每 LLM_EXTRACT_INTERVAL 轮）"""
    count = increment_conversation_count()
    return count % LLM_EXTRACT_INTERVAL == 0

# ===== 批量操作 =====
def batch_update_profile(profile_data: Dict[str, Any], category: str = "implicit"):
    """批量更新画像数据"""
    if "basic" in profile_data:
        for key, value in profile_data["basic"].items():
            set_basic_info(key, value)
    
    if "preferences" in profile_data:
        for cat, prefs in profile_data["preferences"].items():
            for key, value in prefs.items():
                # 如果已存在，提升置信度；否则新建
                existing = get_preference(cat, key)
                if existing == value:
                    update_preference_confidence(cat, key, CONFIDENCE_BOOST_ON_CONFIRM)
                elif existing:
                    update_preference_confidence(cat, key, -CONFIDENCE_DECAY_ON_NEGATE)
                else:
                    set_preference(cat, key, value, source=category)
    
    if "habits" in profile_data:
        for key, value in profile_data["habits"].items():
            set_habit(key, value)
    
    if "financial" in profile_data:
        for key, value in profile_data["financial"].items():
            set_financial(key, value)
    
    print(f"✅ 批量更新画像完成")

# ===== 混合检索（核心）=====
def hybrid_retrieval(query: str) -> Dict[str, Any]:
    """
    混合检索：同时从多个来源获取相关信息
    
    【面试知识点】混合检索架构：
    1. SQLite 结构化查询 → 精确匹配用户偏好
    2. ChromaDB 语义检索 → 模糊匹配相关记忆
    3. 短期上下文 → 获取近期临时信息
    
    返回格式：
    {
        "structured": {...},      # SQLite 结构化数据
        "semantic": [...],        # ChromaDB 语义检索结果
        "recent": {...},          # 短期上下文
        "summary": "..."          # 综合摘要（供 Agent 使用）
    }
    """
    result = {
        "structured": {},
        "semantic": [],
        "recent": {},
        "summary": ""
    }
    
    # 1. SQLite 结构化查询
    result["structured"]["basic"] = get_all_basic_info()
    result["structured"]["preferences"] = [asdict(p) for p in get_all_preferences()]
    result["structured"]["habits"] = get_all_habits()
    result["structured"]["financial"] = get_all_financial()
    
    # 2. ChromaDB 语义检索
    result["semantic"] = _query_chroma(query, n_results=5)
    
    # 3. 短期上下文
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM recent_context WHERE expires_at > ?", (datetime.now().isoformat(),))
    rows = cursor.fetchall()
    conn.close()
    result["recent"] = {row[0]: row[1] for row in rows}
    
    # 4. 生成综合摘要（供 Agent 使用）
    result["summary"] = _generate_context_summary(result)
    
    return result

def _generate_context_summary(retrieval_result: Dict[str, Any]) -> str:
    """生成综合上下文摘要（供 Agent 使用）"""
    parts = []
    
    # 基本信息
    if retrieval_result["structured"]["basic"]:
        basic = retrieval_result["structured"]["basic"]
        parts.append("【基本信息】" + ", ".join([f"{k}={v}" for k, v in basic.items()]))
    
    # 偏好（按置信度排序，高置信度优先）
    prefs = retrieval_result["structured"]["preferences"]
    if prefs:
        sorted_prefs = sorted(prefs, key=lambda x: x['confidence'], reverse=True)
        by_cat = {}
        for p in sorted_prefs:
            cat = p['category']
            if cat not in by_cat:
                by_cat[cat] = []
            by_cat[cat].append(f"{p['key']}={p['value']}(置信度:{p['confidence']:.1f})")
        
        for cat, items in by_cat.items():
            parts.append(f"【{cat}偏好】" + ", ".join(items))
    
    # 习惯
    if retrieval_result["structured"]["habits"]:
        habits = retrieval_result["structured"]["habits"]
        parts.append("【习惯】" + ", ".join([f"{k}={v}" for k, v in habits.items()]))
    
    # 财务
    if retrieval_result["structured"]["financial"]:
        financial = retrieval_result["structured"]["financial"]
        parts.append("【财务】" + ", ".join([f"{k}={v}" for k, v in financial.items()]))
    
    # 短期上下文
    if retrieval_result["recent"]:
        recent = retrieval_result["recent"]
        parts.append("【近期计划】" + ", ".join([f"{k}: {v}" for k, v in recent.items()]))
    
    # 语义检索结果
    if retrieval_result["semantic"]:
        semantic = retrieval_result["semantic"]
        semantic_texts = [f"- {s['content'][:50]}..." for s in semantic]
        parts.append("【相关记忆】\n" + "\n".join(semantic_texts))
    
    if not parts:
        return "📋 用户画像尚为空，请多与助手交流以建立画像"
    
    return "📋 用户上下文摘要：\n" + "\n".join(parts)

# ===== 画像查询接口（给 Agent 用）=====
def get_user_profile_summary() -> str:
    """生成用户画像摘要"""
    return hybrid_retrieval("")["summary"]

# ===== 画像自动提取（从对话中学习）=====
EXTRACT_PROMPT_TEMPLATE = """你是一个用户画像提取助手。请从对话历史中提取用户的相关信息。

对话历史：
{history}

请提取以下类型的用户信息（如果没有相关信息则跳过）：

1. 基本信息 (basic): 姓名、年龄、性别、职业、地区、常住地、家乡等
2. 天气偏好 (weather): 怕冷/怕热、喜欢晴/阴/雨等
3. 穿衣偏好 (clothing): 风格、尺码、颜色偏好、常穿类型等
4. 饮食偏好 (food): 口味（辣/甜/清淡等）、忌口、过敏、喜欢的菜系等
5. 出行偏好 (travel): 出行方式偏好、旅游频率、喜欢的旅游类型等
6. 活动偏好 (activity): 运动习惯、休闲方式等
7. 习惯 (habits): 作息时间、活动频率等
8. 财务 (financial): 消费水平、预算范围等

返回格式（只返回JSON，不要其他文字）：
{{
    "basic": {{"key": "value", ...}},
    "preferences": {{
        "weather": {{"怕冷": "是", ...}},
        "clothing": {{"风格": "休闲", ...}},
        "food": {{"口味": "辣", ...}},
        "travel": {{"出行方式": "飞机", ...}},
        "activity": {{...}},
        "payment": {{...}}
    }},
    "habits": {{"wake_up_time": "7:30", ...}},
    "financial": {{"budget_level": "中等", ...}}
}}

如果对话中没有提取到任何信息，返回空JSON：{{}}
只返回JSON，不要有其他文字。
"""

async def extract_and_save_profile(history: List[Dict], client=None) -> str:
    """
    从对话历史中自动提取用户画像并保存
    
    【面试知识点】提取策略：
    1. 每次用户发言后：轻量级规则提取（无API成本）
    2. 每3-5轮对话：LLM深度提取（更全面但有成本）
    
    Args:
        history: 对话历史列表，格式 [{"role": "user/assistant", "content": "..."}]
        client: OpenAI 客户端（可选）
    
    Returns:
        str: 更新说明
    """
    # 1. 每次都执行规则提取（轻量级，无API成本）
    quick_extracts = _quick_pattern_extract(history)
    if quick_extracts:
        batch_update_profile(quick_extracts, category="implicit")
    
    # 2. 按频率执行 LLM 深度提取
    if client and should_run_llm_extract():
        try:
            recent = history[-6:] if len(history) > 6 else history
            history_text = "\n".join([
                f"{'用户' if msg.get('role') == 'user' else '助手'}: {msg.get('content', '')[:200]}"
                for msg in recent
            ])
            
            response = await client.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": EXTRACT_PROMPT_TEMPLATE.format(history=history_text)}],
                temperature=0.1,
            )
            
            content = response.choices[0].message.content.strip()
            
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            extracted = json.loads(content)
            
            if extracted:
                batch_update_profile(extracted, category="implicit")
                print(f"🤖 [画像] LLM提取到 {len(extracted)} 个维度的信息")
            else:
                print("🤖 [画像] 未从对话中提取到新信息")
                
        except Exception as e:
            print(f"⚠️ [画像] LLM提取失败: {e}")
    
    # 3. 定期执行记忆巩固
    consolidate_memories()
    
    return get_user_profile_summary()

def _quick_pattern_extract(history: List[Dict]) -> Dict[str, Any]:
    """基于规则快速提取高确定性偏好（无API成本）"""
    extracts = {"preferences": {}}
    
    patterns = [
        (r"我(喜欢|爱吃|爱吃).{0,20}(辣|甜的?|清淡|火锅|川菜|粤菜|湘菜)", ("food", "口味")),
        (r"(不吃|不能吃|过敏).{0,20}(辣|海鲜|羊肉|牛肉|花生)", ("food", "忌口")),
        (r"我(怕冷|怕热|喜欢冷|喜欢热)", ("weather", "体感偏好")),
        (r"我喜欢.{0,10}(休闲|正式|运动|潮流|简约)风格", ("clothing", "风格")),
        (r"我(喜欢|倾向).{0,10}(飞机|高铁|自驾|火车)", ("travel", "出行方式")),
        (r"我(叫|的名字是)[：:]\s*([^\s，。]+)", ("basic", "name")),
        (r"(我今年|年龄|岁)[：:]\s*(\d+)", ("basic", "age")),
        (r"(住在|常住|地区)[：:]\s*([^\s，。]+)", ("basic", "location")),
    ]
    
    for msg in history:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        
        for pattern, (cat, key) in patterns:
            match = re.search(pattern, content)
            if match:
                value = match.group(0).replace("我喜欢", "").replace("我", "").replace("的", "")
                if cat == "basic":
                    if "basic" not in extracts:
                        extracts["basic"] = {}
                    extracts["basic"][key] = value
                else:
                    if cat not in extracts["preferences"]:
                        extracts["preferences"][cat] = {}
                    extracts["preferences"][cat][key] = value
    
    return extracts

# ===== 初始化 =====
init_profile_db()

# ===== 测试 =====
if __name__ == "__main__":
    print("\n" + "="*50)
    print("用户画像模块测试（完整记忆系统）")
    print("="*50)
    
    # 测试基本操作
    set_basic_info("name", "小明")
    set_basic_info("age", "28")
    set_basic_info("location", "北京")
    
    set_preference(PreferenceCategory.WEATHER, "怕冷", "是", confidence=0.9)
    set_preference(PreferenceCategory.CLOTHING, "风格", "休闲", confidence=0.8)
    set_preference(PreferenceCategory.FOOD, "口味", "辣", confidence=1.0, source="explicit")
    set_preference(PreferenceCategory.FOOD, "过敏", "海鲜", confidence=1.0, source="explicit")
    
    set_habit("wake_up_time", "7:30")
    set_habit("sleep_time", "23:00")
    
    set_financial("budget_level", "中等", confidence=0.7)
    
    set_recent_context("current_trip", "计划去上海旅游", expire_hours=48)
    
    print("\n" + "="*50)
    print("画像摘要:")
    print("="*50)
    print(get_user_profile_summary())
    
    print("\n" + "="*50)
    print("混合检索测试:")
    print("="*50)
    result = hybrid_retrieval("穿衣")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n" + "="*50)
    print("记忆巩固测试:")
    print("="*50)
    # 模拟命中两次
    get_recent_context("current_trip")
    get_recent_context("current_trip")
    consolidate_memories()
    
    print("\n" + "="*50)
    print("置信度更新测试:")
    print("="*50)
    update_preference_confidence("food", "口味", CONFIDENCE_BOOST_ON_CONFIRM)
    
    print("\n" + "="*50)
    print("遗忘曲线测试:")
    print("="*50)
    apply_forgetting_curve()
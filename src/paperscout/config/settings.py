from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    from PySide6.QtCore import QStandardPaths  # type: ignore
except Exception:  # PySide6 not installed / headless usage
    QStandardPaths = None  # type: ignore

logger = logging.getLogger(__name__)

# ==========================
# Settings schema (v5)
# ==========================
# {
#   "llm": {
#     "active_profile_id": "<profile_id>",
#     "profiles": [
#       {
#         "id": "p_xxxxxxxx",
#         "name": "配置集A",
#         "default_agent": "openai",  # 主界面默认聊天用哪个 provider
#         "agents": {
#           "deepseek": {"model": "...", "api_key_keyring": "keyring:service:user", "base_url": "...", "temperature": 0.2, "top_p": 1.0, "max_tokens": 2048},
#           "openai":   {"model": "...", "api_key_keyring": "keyring:service:user", "base_url": "...", "temperature": 0.2, "top_p": 1.0, "max_tokens": 2048},
#           "google":   {"model": "...", "api_key_keyring": "keyring:service:user", "base_url": "...", "temperature": 0.2, "top_p": 1.0, "max_tokens": 2048},
#           "doubao":   {"model": "...", "api_key_keyring": "keyring:service:user", "base_url": "...", "temperature": 0.2, "top_p": 1.0, "max_tokens": 2048}
#         }
#       }
#     ]
#   }
# }
#
# Backward compatibility:
# - v1: llm.default_provider/default_model + xxx_api_key
# - v2: llm.active + llm.providers
# - v3: llm.active_profile + llm.profiles dict(profile1/2/3)
# - v4: llm.active_profile_id + profiles(list) with single provider fields
# - v5: llm.active_profile_id + profiles(list) with agents dict + keyring-backed API keys
# Will be migrated to v5 on load.

PROVIDERS = ["deepseek", "openai", "google", "doubao"]

DEFAULT_MODELS = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "openai": ["gpt-4.1", "gpt-4o-mini"],
    "google": ["gemini-2.5-flash", "gemini-2.0-flash"],
    "doubao": [],
}

DEFAULT_AGENT_CFG = {
    "deepseek": {
        "model": "deepseek-chat",
        "api_key_keyring": "",  # 指向 keyring 中的位置
        "base_url": "https://api.deepseek.com/v1",
        "temperature": 0.2,
        "top_p": 1.0,
        "max_tokens": 2048,
    },
    "openai": {
        "model": "gpt-4.1",
        "api_key_keyring": "",
        "base_url": "https://api.v3.cm/v1",
        "temperature": 0.2,
        "top_p": 1.0,
        "max_tokens": 2048,
    },
    "google": {
        "model": "gemini-2.5-flash",
        "api_key_keyring": "",
        "base_url": "",
        "temperature": 0.2,
        "top_p": 1.0,
        "max_tokens": 2048,
    },
    "doubao": {
        "model": "",
        "api_key_keyring": "",
        "base_url": "",
        "temperature": 0.2,
        "top_p": 1.0,
        "max_tokens": 2048,
    },
}

DEFAULT_SYSTEM_CFG = {
    "final_output_paper_count": 5,
    "arxiv_fetch_max_results": 20,
}

# ===========================
# Keyring 加密存储接口
# ===========================
def _get_keyring_service_name(profile_id: str) -> str:
    """生成 keyring 服务名"""
    return f"paperscout_{profile_id}"


def store_api_key(profile_id: str, provider: str, api_key: str) -> str:
    """
    存储 API Key 到系统密钥库，返回指向该密钥的引用字符串
    
    Args:
        profile_id: 配置集 ID
        provider: provider 名称 (deepseek/openai/google/doubao)
        api_key: API Key 值
    
    Returns:
        keyring 引用字符串，格式为 "keyring:service:username"
    """
    try:
        import keyring
        service = _get_keyring_service_name(profile_id)
        username = f"api_key_{provider}"
        keyring.set_password(service, username, api_key)
        logger.info(f"API key for {provider} stored in keyring")
        return f"keyring:{service}:{username}"
    except Exception as e:
        logger.error(f"Failed to store API key in keyring: {e}")
        # 降级：如果 keyring 失败，返回空字符串（不存储到本地）
        return ""


def retrieve_api_key(keyring_ref: str) -> str:
    """
    从系统密钥库读取 API Key
    
    Args:
        keyring_ref: keyring 引用字符串，格式为 "keyring:service:username"
    
    Returns:
        API Key 值，如果未找到返回空字符串
    """
    if not keyring_ref or not keyring_ref.startswith("keyring:"):
        return ""
    
    try:
        import keyring
        parts = keyring_ref.split(":", 2)
        if len(parts) != 3:
            return ""
        service, username = parts[1], parts[2]
        key = keyring.get_password(service, username)
        return key or ""
    except Exception as e:
        logger.error(f"Failed to retrieve API key from keyring: {e}")
        return ""


def delete_api_key(keyring_ref: str) -> bool:
    """
    从系统密钥库删除 API Key
    
    Args:
        keyring_ref: keyring 引用字符串
    
    Returns:
        删除成功返回 True，否则 False
    """
    if not keyring_ref or not keyring_ref.startswith("keyring:"):
        return False
    
    try:
        import keyring
        parts = keyring_ref.split(":", 2)
        if len(parts) != 3:
            return False
        service, username = parts[1], parts[2]
        keyring.delete_password(service, username)
        logger.info(f"API key deleted from keyring: {service}/{username}")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete API key from keyring: {e}")
        return False


def _settings_path() -> str:
    """Return settings file path.

    Prefer Qt's per-OS config location when PySide6 is available.
    Fall back to a standard per-OS user config directory when running headless
    (e.g., running core scripts/tests without PySide6 installed).
    """

    # 1) Qt path (GUI install)
    if QStandardPaths is not None:
        base = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "paperscout_settings.json")

    # 2) Headless fallback (no PySide6)
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support", "PaperScout")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "PaperScout")
    else:
        base = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "paperscout")

    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "paperscout_settings.json")


def app_data_dir() -> str:
    """Return writable application data directory."""
    return os.path.dirname(_settings_path())


def _deep_copy(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


def _new_profile_id() -> str:
    return f"p_{uuid4().hex[:8]}"


def get_safe_str(data: Optional[dict], key: str, default: str = "") -> str:
    """安全获取字符串值，自动 strip 空白"""
    if not isinstance(data, dict):
        return default
    val = data.get(key)
    return str(val).strip() if val is not None else default


def _safe_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_system_param_int(
    settings: Dict[str, Any],
    key: str,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    system_cfg = (settings.get("system", {}) or {}) if isinstance(settings, dict) else {}
    value = _safe_int(system_cfg.get(key), default) if isinstance(system_cfg, dict) else default
    return max(min_value, min(max_value, value))


# ===========================
# 版本检测
# ===========================
def _detect_version(data: Dict[str, Any]) -> int:
    """
    检测配置文件版本。
    
    - v5: profiles 是列表，每个 profile 有 agents dict，API keys 用 keyring_ref
    - v4: profiles 是列表，每个 profile 有 provider/model/api_key 等单一字段
    - v3: profiles 是 dict (profile1/profile2/...)，active_profile 字段
    - v2: active + providers 字段
    - v1: default_provider/default_model + xxx_api_key 字段
    - v0: 无效格式
    """
    if not isinstance(data, dict):
        return 0
    
    llm = data.get("llm", {})
    if not isinstance(llm, dict):
        return 0
    
    # 检测 v5：profiles 是列表且包含 agents 字段
    if isinstance(llm.get("profiles"), list) and llm.get("profiles"):
        first = llm["profiles"][0]
        if isinstance(first, dict) and "agents" in first:
            # 检查是否已使用 keyring
            if isinstance(first.get("agents"), dict):
                return 5
    
    # 检测 v4：profiles 是列表且第一项有 provider 字段
    if isinstance(llm.get("profiles"), list) and llm.get("profiles"):
        first = llm["profiles"][0]
        if isinstance(first, dict) and "provider" in first:
            return 4
    
    # 检测 v3：profiles 是 dict，有 active_profile 字段
    if isinstance(llm.get("profiles"), dict) and "active_profile" in llm:
        return 3
    
    # 检测 v2：有 active + providers 字段
    if "active" in llm and "providers" in llm and isinstance(llm.get("providers"), dict):
        return 2
    
    # 检测 v1：有 default_provider 或 default_model 字段
    if "default_provider" in llm or "default_model" in llm:
        return 1
    
    return 0


# ===========================
# 分步迁移函数
# ===========================
def _migrate_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """v1 -> v2: 从简单字段迁移到 active + providers 结构"""
    logger.info("Migrating settings v1 -> v2")
    llm = data.get("llm", {}) or {}
    
    default_provider = get_safe_str(llm, "default_provider", "deepseek")
    default_model = get_safe_str(llm, "default_model", "")
    deepseek_key = get_safe_str(llm, "deepseek_api_key", "")
    openai_key = get_safe_str(llm, "openai_api_key", "")
    google_key = get_safe_str(llm, "google_api_key", "")
    openai_base = get_safe_str(llm, "openai_base_url", "")
    
    providers = {}
    for prov in PROVIDERS:
        providers[prov] = {
            "api_key": {
                "deepseek": deepseek_key,
                "openai": openai_key,
                "google": google_key,
                "doubao": "",
            }.get(prov, ""),
            "selected_model": default_model if prov == default_provider else "",
            "models": DEFAULT_MODELS.get(prov, []),
            "base_url": openai_base if prov == "openai" else "",
        }
    
    data["llm"] = {
        "active": {"provider": default_provider, "model": default_model},
        "providers": providers,
    }
    return data


def _migrate_v2_to_v3(data: Dict[str, Any]) -> Dict[str, Any]:
    """v2 -> v3: 从 active + providers 迁移到 profiles dict 结构"""
    logger.info("Migrating settings v2 -> v3")
    llm = data.get("llm", {}) or {}
    
    active = llm.get("active", {}) or {}
    providers = llm.get("providers", {}) or {}
    
    ap = get_safe_str(active, "provider", "deepseek")
    am = get_safe_str(active, "model", "")
    
    profiles = {}
    for prov in PROVIDERS:
        cfg = providers.get(prov, {}) or {}
        profile_key = f"profile_{prov}"
        profiles[profile_key] = {
            "name": f"{prov.capitalize()} Configuration",
            "provider": prov,
            "model": get_safe_str(cfg, "selected_model", DEFAULT_MODELS.get(prov, [""])[0]),
            "api_key": get_safe_str(cfg, "api_key", ""),
            "base_url": get_safe_str(cfg, "base_url", DEFAULT_AGENT_CFG.get(prov, {}).get("base_url", "")),
        }
    
    active_profile = f"profile_{ap}" if ap in PROVIDERS else ""
    if not active_profile or active_profile not in profiles:
        active_profile = next(iter(profiles.keys()), "")

    data["llm"] = {
        "active_profile": active_profile,
        "profiles": profiles,
    }
    return data


def _migrate_v3_to_v4(data: Dict[str, Any]) -> Dict[str, Any]:
    """v3 -> v4: 从 profiles dict 迁移到 profiles list 结构"""
    logger.info("Migrating settings v3 -> v4")
    llm = data.get("llm", {}) or {}
    
    profiles_dict = llm.get("profiles", {}) or {}
    active_profile = get_safe_str(llm, "active_profile", "")
    
    profiles = []
    for key, pcfg in profiles_dict.items():
        if not isinstance(pcfg, dict):
            continue
        profile = {
            "id": key,
            "name": get_safe_str(pcfg, "name", key),
            "provider": get_safe_str(pcfg, "provider", "deepseek"),
            "model": get_safe_str(pcfg, "model", ""),
            "api_key": get_safe_str(pcfg, "api_key", ""),
            "base_url": get_safe_str(pcfg, "base_url", ""),
            "temperature": _safe_float(pcfg.get("temperature", 0.2), 0.2),
            "top_p": _safe_float(pcfg.get("top_p", 1.0), 1.0),
            "max_tokens": _safe_int(pcfg.get("max_tokens", 2048), 2048),
        }
        profiles.append(profile)
    
    if not profiles:
        profiles = [{"id": "profile1", "name": "Default", "provider": "deepseek"}]
    
    if not active_profile or not any(p["id"] == active_profile for p in profiles):
        active_profile = profiles[0]["id"]
    
    data["llm"] = {
        "active_profile_id": active_profile,
        "profiles": profiles,
    }
    return data


def _migrate_v4_to_v5(data: Dict[str, Any]) -> Dict[str, Any]:
    """v4 -> v5: 从单一 provider 迁移到多 provider agents 结构，并使用 keyring 存储 API Key"""
    logger.info("Migrating settings v4 -> v5")
    llm = data.get("llm", {}) or {}
    
    profiles_list = llm.get("profiles", []) or []
    active_profile_id = get_safe_str(llm, "active_profile_id", "")
    
    new_profiles = []
    for p in profiles_list:
        if not isinstance(p, dict):
            continue
        
        pid = get_safe_str(p, "id", _new_profile_id())
        pname = get_safe_str(p, "name", "未命名配置集")
        old_provider = get_safe_str(p, "provider", "deepseek")
        old_api_key = get_safe_str(p, "api_key", "")
        
        # 构建四个 provider 的 agents 配置
        agents = {}
        for prov in PROVIDERS:
            agent_cfg = _deep_copy(DEFAULT_AGENT_CFG[prov])
            
            # 如果这是旧的默认 provider，迁移其配置
            if prov == old_provider:
                agent_cfg["model"] = get_safe_str(p, "model", agent_cfg["model"])
                agent_cfg["base_url"] = get_safe_str(p, "base_url", agent_cfg["base_url"])
                
                # 存储 API Key 到 keyring
                if old_api_key:
                    api_key_ref = store_api_key(pid, prov, old_api_key)
                    agent_cfg["api_key_keyring"] = api_key_ref
            
            # 数值字段标准化
            try:
                agent_cfg["temperature"] = float(p.get("temperature", agent_cfg["temperature"]))
            except (TypeError, ValueError):
                agent_cfg["temperature"] = agent_cfg["temperature"]
            
            try:
                agent_cfg["top_p"] = float(p.get("top_p", agent_cfg["top_p"]))
            except (TypeError, ValueError):
                agent_cfg["top_p"] = agent_cfg["top_p"]
            
            try:
                agent_cfg["max_tokens"] = int(p.get("max_tokens", agent_cfg["max_tokens"]))
            except (TypeError, ValueError):
                agent_cfg["max_tokens"] = agent_cfg["max_tokens"]
            
            agents[prov] = agent_cfg
        
        new_profile = {
            "id": pid,
            "name": pname,
            "default_agent": old_provider if old_provider in PROVIDERS else "deepseek",
            "agents": agents,
        }
        new_profiles.append(new_profile)
    
    if not new_profiles:
        # 创建默认配置
        new_profiles = [_create_default_profile()]
    
    if not active_profile_id or not any(p["id"] == active_profile_id for p in new_profiles):
        active_profile_id = new_profiles[0]["id"]
    
    data["llm"] = {
        "active_profile_id": active_profile_id,
        "profiles": new_profiles,
    }
    logger.info(f"Migrated {len(new_profiles)} profile(s) to v5")
    return data


def _create_default_profile() -> Dict[str, Any]:
    """创建一个默认配置集"""
    pid = _new_profile_id()
    agents = {}
    for prov in PROVIDERS:
        agents[prov] = _deep_copy(DEFAULT_AGENT_CFG[prov])
    
    return {
        "id": pid,
        "name": "默认配置集",
        "default_agent": "openai",
        "agents": agents,
    }


def _migrate_to_v5(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    逐步迁移配置到 v5 版本。
    
    版本检测 → 按序应用迁移函数 → 验证最终结果
    """
    version = _detect_version(data)
    logger.info(f"Detected settings version: v{version}")
    
    if version >= 5:
        logger.info("Settings already at v5, skipping migration")
        return data
    
    if version == 0:
        logger.info("Invalid settings format, creating defaults")
        return _deep_copy(_default_settings())
    
    # 按序应用迁移
    migrations = [
        (1, _migrate_v1_to_v2),
        (2, _migrate_v2_to_v3),
        (3, _migrate_v3_to_v4),
        (4, _migrate_v4_to_v5),
    ]
    
    for from_v, migrate_func in migrations:
        if version <= from_v:
            data = migrate_func(data)
    
    # 验证最终结果
    if _detect_version(data) != 5:
        logger.warning("Migration did not reach v5, using defaults")
        return _deep_copy(_default_settings())
    
    return data


def _default_settings() -> Dict[str, Any]:
    profiles = []
    for i in range(1, 4):
        pid = f"profile{i}"
        agents = {}
        for prov in PROVIDERS:
            agents[prov] = _deep_copy(DEFAULT_AGENT_CFG[prov])
        
        profiles.append({
            "id": pid,
            "name": f"模型配置{chr(64+i)}",  # A, B, C
            "default_agent": "openai",
            "agents": agents,
        })
    
    return {
        "llm": {
            "active_profile_id": profiles[0]["id"],
            "profiles": profiles,
        },
        "system": _deep_copy(DEFAULT_SYSTEM_CFG),
    }


DEFAULT_SETTINGS = _default_settings()


# ===========================
# 配置加载和保存
# ===========================
def load_settings() -> Dict[str, Any]:
    """
    加载配置文件。如果文件不存在或格式无效，返回默认配置。
    自动检测版本并迁移到 v5。
    """
    path = _settings_path()
    
    try:
        if not os.path.exists(path):
            logger.info("Settings file not found, creating defaults")
            return _deep_copy(DEFAULT_SETTINGS)
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info("Settings loaded from disk")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse settings JSON: {e}, using defaults")
        return _deep_copy(DEFAULT_SETTINGS)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}, using defaults")
        return _deep_copy(DEFAULT_SETTINGS)
    
    # 迁移到 v5
    data = _migrate_to_v5(data)
    
    # 验证配置的完整性
    llm = data.get("llm", {})
    if not isinstance(llm, dict):
        return _deep_copy(DEFAULT_SETTINGS)
    
    profiles = llm.get("profiles", [])
    if not profiles:
        logger.warning("No profiles found after migration, using defaults")
        return _deep_copy(DEFAULT_SETTINGS)
    
    # 确保 active_profile_id 有效
    active_id = get_safe_str(llm, "active_profile_id", "")
    if not active_id or not any(p.get("id") == active_id for p in profiles):
        active_id = profiles[0].get("id", "")
        llm["active_profile_id"] = active_id

    system_cfg = data.get("system") if isinstance(data, dict) else {}
    system_cfg = system_cfg if isinstance(system_cfg, dict) else {}
    merged_system = _deep_copy(DEFAULT_SYSTEM_CFG)
    for k in merged_system.keys():
        merged_system[k] = _safe_int(system_cfg.get(k), merged_system[k])
    data["system"] = merged_system
    
    return data


def save_settings(settings: Dict[str, Any]) -> None:
    """
    保存配置到文件。捕获异常并记录日志。
    """
    path = _settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        logger.info(f"Settings saved to {path}")
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")


# ===========================
# 公共工具函数
# ===========================
def find_profile_by_id(profiles: List[Dict], profile_id: str) -> Dict[str, Any]:
    """
    从配置集列表中查找指定 ID 的配置集。
    
    Args:
        profiles: 配置集列表
        profile_id: 要查找的配置集 ID
    
    Returns:
        找到的配置集，如果未找到返回空字典
    """
    for p in profiles:
        if isinstance(p, dict) and get_safe_str(p, "id") == profile_id:
            return p
    return {}


def get_profile_agent_info(profile: Dict, agent_name: str) -> Dict[str, Any]:
    """
    获取配置集中指定 agent 的信息。
    
    Args:
        profile: 配置集字典
        agent_name: agent 名称 (deepseek/openai/google/doubao)
    
    Returns:
        agent 配置字典，如果不存在返回空字典
    """
    if not isinstance(profile, dict):
        return {}
    
    agents = profile.get("agents", {})
    if not isinstance(agents, dict):
        return {}
    
    agent = agents.get(agent_name, {})
    if not isinstance(agent, dict):
        return {}
    
    # 解析 API Key：优先从 keyring 读取，否则将 api_key_keyring 当作原始 key 使用
    keyring_ref = agent.get("api_key_keyring", "")
    agent = dict(agent)  # 创建副本，不修改原始数据
    if keyring_ref:
        if keyring_ref.startswith("keyring:"):
            # 正式的 keyring 引用 → 从系统密钥库读取
            api_key = retrieve_api_key(keyring_ref)
        else:
            # 兼容：字段存的是原始 API Key（非 keyring 引用）
            api_key = keyring_ref
        agent["api_key"] = api_key
    
    return agent


def set_profile_agent_api_key(profile: Dict, agent_name: str, api_key: str) -> bool:
    """
    设置配置集中指定 agent 的 API Key。
    API Key 将被存储到系统密钥库。
    
    Args:
        profile: 配置集字典
        agent_name: agent 名称
        api_key: API Key 值
    
    Returns:
        设置成功返回 True，否则 False
    """
    if not isinstance(profile, dict):
        return False
    
    agents = profile.get("agents", {})
    if not isinstance(agents, dict):
        return False
    
    agent = agents.get(agent_name, {})
    if not isinstance(agent, dict):
        return False
    
    # 删除旧的 keyring 引用（如果存在）
    old_keyring_ref = agent.get("api_key_keyring", "")
    if old_keyring_ref and old_keyring_ref.startswith("keyring:"):
        delete_api_key(old_keyring_ref)
    
    # 存储新的 API Key
    profile_id = get_safe_str(profile, "id", "default")
    keyring_ref = store_api_key(profile_id, agent_name, api_key)
    
    if keyring_ref:
        agent["api_key_keyring"] = keyring_ref
        return True
    
    # 如果 keyring 失败，直接存原始 key 到 api_key_keyring（降级方案）
    agent["api_key_keyring"] = api_key
    return True

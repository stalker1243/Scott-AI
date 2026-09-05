"""
Scott AI v3.0 - Version Management API
REST API endpoints for version checking and update management
"""

import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import Dict, Optional
from datetime import datetime

try:
    from . import updates
except ImportError:
    import updates

version_router = APIRouter(prefix="/api/version", tags=["version"])

PROJECT_ROOT = Path(__file__).parent.parent
VERSION_FILE = PROJECT_ROOT / "VERSION.json"

def load_version_info() -> Dict:
    """Load version information from VERSION.json"""
    try:
        if VERSION_FILE.exists():
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading VERSION.json: {e}")
    
    return {
        "app_name": "Scott AI",
        "version": "3.0.0",
        "build_number": 300,
        "release_date": "2026-06-13"
    }

def save_version_info(data: Dict) -> bool:
    """Save version information to VERSION.json"""
    try:
        with open(VERSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving VERSION.json: {e}")
        return False

@version_router.get("/current")
async def get_current_version():
    """
    Get current version information
    
    Returns:
        - app_name: Application name
        - version: Current version (e.g., "3.0.0")
        - build_number: Build number
        - release_date: Release date
    """
    version_info = load_version_info()
    return {
        "status": "success",
        "data": {
            "app_name": version_info.get("app_name"),
            "version": version_info.get("version"),
            "build_number": version_info.get("build_number"),
            "release_date": version_info.get("release_date"),
            "timestamp": datetime.now().isoformat()
        }
    }

@version_router.get("/changelog")
async def get_changelog():
    """
    Get changelog for all versions
    
    Returns:
        - changelog: Dictionary with version history
    """
    version_info = load_version_info()
    changelog = version_info.get("changelog", {})
    
    return {
        "status": "success",
        "data": {
            "changelog": changelog,
            "versions": list(changelog.keys())
        }
    }

@version_router.get("/changelog/{version}")
async def get_version_changelog(version: str):
    """
    Get changelog for specific version
    
    Args:
        version: Version string (e.g., "3.0.0")
    
    Returns:
        - changelog entry for specified version
    """
    version_info = load_version_info()
    changelog = version_info.get("changelog", {})
    
    if version not in changelog:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    
    return {
        "status": "success",
        "data": {
            "version": version,
            "changelog": changelog[version]
        }
    }

@version_router.get("/update-check")
async def check_for_updates(force: bool = False):
    """
    Вышла ли новая версия.

    Раньше эта проверка была фикцией: она сравнивала версию из локального
    VERSION.json с ней же самой и всегда отвечала «обновлений нет», никуда не
    обращаясь. Теперь спрашиваем у GitHub Releases по-настоящему.

    Ответ кэшируется на сутки (`force=true` обходит кэш): GitHub ограничивает
    число запросов, а выпуски выходят куда реже.

    Сетевой поход вынесен в отдельный поток — синхронный requests в async-
    обработчике вешает весь backend, включая /health.
    """
    info = await asyncio.to_thread(updates.check, force)

    return {
        "status": "success",
        "data": info.as_dict(),
    }


@version_router.get("/requirements")
async def get_system_requirements():
    """
    Get system requirements
    
    Returns:
        - os: Operating system
        - memory_min_gb: Minimum RAM required
        - disk_space_mb: Disk space required
        - internet: Internet connection required
    """
    version_info = load_version_info()
    requirements = version_info.get("system_requirements", {})
    
    return {
        "status": "success",
        "data": {
            "app_name": version_info.get("app_name"),
            "version": version_info.get("version"),
            "requirements": requirements
        }
    }

@version_router.get("/installers")
async def get_installers():
    """
    Get available installers information
    
    Returns:
        - windows: Windows installer info
        - portable: Portable exe info
    """
    version_info = load_version_info()
    installers = version_info.get("installers", {})
    
    return {
        "status": "success",
        "data": {
            "version": version_info.get("version"),
            "installers": installers
        }
    }

@version_router.post("/update-settings")
async def update_settings(auto_update: bool = False, check_interval_hours: int = 24):
    """
    Update application settings
    
    Args:
        auto_update: Enable automatic updates
        check_interval_hours: Check for updates every N hours
    
    Returns:
        - success: Boolean
    """
    # Settings would be saved to a config file
    settings = {
        "auto_update": auto_update,
        "check_interval_hours": check_interval_hours,
        "last_check": datetime.now().isoformat()
    }
    
    return {
        "status": "success",
        "data": {
            "message": "Settings updated",
            "settings": settings
        }
    }

@version_router.get("/status")
async def get_status():
    """
    Get application status
    
    Returns:
        - status: Application status
        - version: Current version
        - uptime: Application uptime
    """
    version_info = load_version_info()
    
    return {
        "status": "success",
        "data": {
            "app_name": version_info.get("app_name"),
            "version": version_info.get("version"),
            "build_number": version_info.get("build_number"),
            "timestamp": datetime.now().isoformat(),
            "api_version": "1.0"
        }
    }

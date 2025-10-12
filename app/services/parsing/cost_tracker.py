"""
Cost tracking and budget management for parser services.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class UserBudget:
    """User budget configuration."""
    user_id: str
    tier: str  # "free", "premium", "enterprise"
    monthly_ocr_limit: int
    monthly_llm_limit: int
    monthly_cost_limit: float
    current_month_ocr: int = 0
    current_month_llm: int = 0
    current_month_cost: float = 0.0
    last_reset: datetime = None
    
    def __post_init__(self):
        if self.last_reset is None:
            self.last_reset = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# Cost per service (in USD)
SERVICE_COSTS = {
    "text_extraction": 0.00,
    "ocr_tesseract": 0.00,
    "ocr_easyocr": 0.02,
    "llm_gpt4": 0.30,
    "llm_claude": 0.25,
    "manual_review": 0.00
}

class CostTracker:
    """Track usage and enforce budget limits."""
    
# Default budgets by tier
DEFAULT_BUDGETS = {
    "free": UserBudget(
        user_id="",
        tier="free",
        monthly_ocr_limit=10,
        monthly_llm_limit=3,
        monthly_cost_limit=200.00  # $200 initial budget for development
    ),
    "premium": UserBudget(
        user_id="",
        tier="premium",
        monthly_ocr_limit=100,
        monthly_llm_limit=20,
        monthly_cost_limit=25.00
    ),
    "enterprise": UserBudget(
        user_id="",
        tier="enterprise",
        monthly_ocr_limit=1000,
        monthly_llm_limit=200,
        monthly_cost_limit=200.00
    )
}

class CostTracker:
    """Tracks usage and enforces budget limits for parsing services."""
    
    def __init__(self, db_connection=None):
        """Initialize cost tracker with optional database connection."""
        self.db = db_connection
        self.user_budgets: Dict[str, UserBudget] = {}
        
        # In-memory storage for development (replace with DB in production)
        self.usage_log: Dict[str, list] = {}
    
    def get_user_budget(self, user_id: str) -> UserBudget:
        """Get user budget, creating default if not exists."""
        if user_id not in self.user_budgets:
            # Default to free tier for new users
            budget = UserBudget(
                user_id=user_id,
                tier="free",
                monthly_ocr_limit=DEFAULT_BUDGETS["free"].monthly_ocr_limit,
                monthly_llm_limit=DEFAULT_BUDGETS["free"].monthly_llm_limit,
                monthly_cost_limit=DEFAULT_BUDGETS["free"].monthly_cost_limit
            )
            self.user_budgets[user_id] = budget
            logger.info(f"Created default free tier budget for user {user_id}")
        
        budget = self.user_budgets[user_id]
        
        # Reset monthly counters if new month
        self._check_monthly_reset(budget)
        
        return budget
    
    def _check_monthly_reset(self, budget: UserBudget):
        """Reset monthly counters if it's a new month."""
        now = datetime.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if budget.last_reset < current_month_start:
            budget.current_month_ocr = 0
            budget.current_month_llm = 0
            budget.current_month_cost = 0.0
            budget.last_reset = current_month_start
            logger.info(f"Reset monthly budget for user {budget.user_id}")
    
    def can_use_service(self, user_id: str, service: str) -> tuple[bool, str]:
        """
        Check if user can use a service based on budget limits.
        
        Returns:
            (can_use: bool, reason: str)
        """
        budget = self.get_user_budget(user_id)
        cost = SERVICE_COSTS.get(service, 0.0)
        
        # Check monthly cost limit
        if budget.current_month_cost + cost > budget.monthly_cost_limit:
            return False, f"Monthly cost limit exceeded (${budget.monthly_cost_limit})"
        
        # Check service-specific limits
        if service in ["ocr_tesseract", "ocr_easyocr"]:
            if budget.current_month_ocr >= budget.monthly_ocr_limit:
                return False, f"Monthly OCR limit exceeded ({budget.monthly_ocr_limit})"
        
        if service in ["llm_gpt4", "llm_claude"]:
            if budget.current_month_llm >= budget.monthly_llm_limit:
                return False, f"Monthly LLM limit exceeded ({budget.monthly_llm_limit})"
        
        return True, "OK"
    
    def track_usage(self, user_id: str, service: str, cost: float = None) -> bool:
        """Track service usage and update budget."""
        if cost is None:
            cost = SERVICE_COSTS.get(service, 0.0)
        
        budget = self.get_user_budget(user_id)
        
        # Update counters
        budget.current_month_cost += cost
        
        if service in ["ocr_tesseract", "ocr_easyocr"]:
            budget.current_month_ocr += 1
        elif service in ["llm_gpt4", "llm_claude"]:
            budget.current_month_llm += 1
        
        # Log usage
        usage_entry = {
            "timestamp": datetime.now(),
            "service": service,
            "cost": cost,
            "user_id": user_id
        }
        
        if user_id not in self.usage_log:
            self.usage_log[user_id] = []
        self.usage_log[user_id].append(usage_entry)
        
        logger.info(f"Tracked usage: {user_id} used {service} (${cost:.2f})")
        
        # Save to database if available
        if self.db:
            self._save_usage_to_db(usage_entry)
        
        return True
    
    def get_usage_summary(self, user_id: str) -> Dict[str, any]:
        """Get current month usage summary for user."""
        budget = self.get_user_budget(user_id)
        
        return {
            "user_id": user_id,
            "tier": budget.tier,
            "current_month": {
                "ocr_used": budget.current_month_ocr,
                "ocr_limit": budget.monthly_ocr_limit,
                "llm_used": budget.current_month_llm,
                "llm_limit": budget.monthly_llm_limit,
                "cost_used": budget.current_month_cost,
                "cost_limit": budget.monthly_cost_limit
            },
            "remaining": {
                "ocr": budget.monthly_ocr_limit - budget.current_month_ocr,
                "llm": budget.monthly_llm_limit - budget.current_month_llm,
                "cost": budget.monthly_cost_limit - budget.current_month_cost
            }
        }
    
    def upgrade_user_tier(self, user_id: str, new_tier: str) -> bool:
        """Upgrade user to new tier."""
        if new_tier not in DEFAULT_BUDGETS:
            logger.error(f"Invalid tier: {new_tier}")
            return False
        
        budget = self.get_user_budget(user_id)
        new_budget = DEFAULT_BUDGETS[new_tier]
        
        budget.tier = new_tier
        budget.monthly_ocr_limit = new_budget.monthly_ocr_limit
        budget.monthly_llm_limit = new_budget.monthly_llm_limit
        budget.monthly_cost_limit = new_budget.monthly_cost_limit
        
        logger.info(f"Upgraded user {user_id} to {new_tier} tier")
        return True
    
    def _save_usage_to_db(self, usage_entry: Dict):
        """Save usage entry to database (implement based on your DB choice)."""
        # TODO: Implement database persistence
        pass
    
    def get_cost_estimate(self, service: str) -> float:
        """Get estimated cost for a service."""
        return SERVICE_COSTS.get(service, 0.0)
    
    def get_available_services(self, user_id: str) -> Dict[str, Dict]:
        """Get available services for user based on budget."""
        budget = self.get_user_budget(user_id)
        available = {}
        
        for service, cost in SERVICE_COSTS.items():
            can_use, reason = self.can_use_service(user_id, service)
            available[service] = {
                "available": can_use,
                "cost": cost,
                "reason": reason
            }
        
        return available

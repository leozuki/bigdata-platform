"""
ads_engine — Module tự động hóa Facebook Ads cho BigData Pipeline
===============================================================
Xuất các function chính để sử dụng từ dashboard và CLI.
"""

from .fb_ads_api import FacebookAdsAPI
from .messenger_api import MessengerAPI
from .cost_analyzer import CostAnalyzer
from .lead_quality_scorer import LeadQualityScorer
from .optimizer import AdsOptimizer
from .campaign_recommender import CampaignRecommender

__all__ = [
    "FacebookAdsAPI",
    "MessengerAPI",
    "CostAnalyzer",
    "LeadQualityScorer",
    "AdsOptimizer",
    "CampaignRecommender",
]

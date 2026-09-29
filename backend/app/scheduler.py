"""
app/scheduler.py
================
APScheduler configuration for background data refreshing.
"""

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.database import SessionLocal
from app.models import Product
from connectors import get_registry

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_connector(platform: str, cls, query: str):
    """Run a single connector in a thread pool."""
    try:
        connector = cls()
        results = await asyncio.to_thread(connector.search, query)
        return results
    except Exception:
        logger.exception(f"Scheduler: Connector {platform} failed for query {query}")
        return []


async def refresh_all_categories():
    """
    Background job to refresh all unique product categories currently in the DB.
    Re-runs all registered connectors and updates the products.
    """
    logger.info("Starting scheduled background refresh of all categories...")
    
    db: Session = SessionLocal()
    try:
        # Get all distinct categories that are not empty/null
        categories = db.query(Product.category).filter(
            Product.category.isnot(None), 
            Product.category != ""
        ).distinct().all()
        
        category_list = [c[0] for c in categories]
        logger.info(f"Found {len(category_list)} distinct categories to refresh.")
        
        registry = get_registry()
        
        for category in category_list:
            logger.info(f"Refreshing category: '{category}'")
            tasks = []
            for platform, cls in registry.items():
                tasks.append(_run_connector(platform, cls, category))
                
            results_lists = await asyncio.gather(*tasks, return_exceptions=True)
            
            all_results = []
            for res in results_lists:
                if isinstance(res, list):
                    all_results.extend(res)
                    
            for r in all_results:
                product = db.query(Product).filter(Product.product_url == r["product_url"]).first()
                if product:
                    product.name = r.get("name", product.name)
                    if r.get("price") is not None:
                        product.price = r["price"]
                    if r.get("rating") is not None:
                        product.rating = r["rating"]
                    if r.get("review_count") is not None:
                        product.review_count = r.get("review_count", 0) or 0
                    if r.get("image_url"):
                        product.image_url = r["image_url"]
                    # Force update last_scraped_at even if values haven't changed
                    product.last_scraped_at = func.now()
                else:
                    product = Product(
                        platform=r["platform"],
                        product_url=r["product_url"],
                        name=r["name"],
                        category=category,
                        price=r.get("price"),
                        rating=r.get("rating"),
                        review_count=r.get("review_count", 0) or 0,
                        image_url=r.get("image_url"),
                    )
                    db.add(product)
            
            try:
                db.commit()
                logger.info(f"Successfully refreshed and saved category: '{category}'")
            except Exception:
                db.rollback()
                logger.exception(f"Failed to save refreshed products for category '{category}'")
                
    except Exception:
        logger.exception("Error during scheduled refresh job")
    finally:
        db.close()
        
    logger.info("Background refresh job completed.")


def start_scheduler():
    """
    Configure and start the APScheduler.
    """
    # Run every 6 hours
    scheduler.add_job(
        refresh_all_categories, 
        "interval", 
        hours=6, 
        id="refresh_categories_job", 
        replace_existing=True
    )
    scheduler.start()
    logger.info("APScheduler started: refresh job scheduled every 6 hours.")

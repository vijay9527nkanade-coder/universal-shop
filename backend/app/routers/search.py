from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import asyncio
import logging

from app.database import get_db
from app import models
from connectors import get_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])

async def _run_connector(platform: str, cls, query: str):
    try:
        connector = cls()
        # Playwright connectors are synchronous, so we run them in a thread
        # to avoid blocking the FastAPI async event loop.
        results = await asyncio.to_thread(connector.search, query)
        return results
    except Exception as e:
        logger.exception(f"Connector {platform} failed for query {query}")
        return []

@router.get("/search")
async def search_products(q: str, db: Session = Depends(get_db)):
    """
    Search across all registered platforms in parallel.
    Upserts results to the database and returns the raw combined results.
    """
    if not q or not q.strip():
        return []
        
    query = q.strip()
    registry = get_registry()
    
    # 1. Run all connectors in parallel
    tasks = []
    for platform, cls in registry.items():
        tasks.append(_run_connector(platform, cls, query))
        
    # Gather results, ensuring one failure doesn't crash the others
    results_lists = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 2. Combine results
    all_results = []
    for res in results_lists:
        if isinstance(res, list):
            all_results.extend(res)
        elif isinstance(res, Exception):
            logger.error(f"A connector task crashed: {res}")
            
    # 3. Store or update matching rows in the products table
    for r in all_results:
        # Check if product exists by unique product_url
        product = db.query(models.Product).filter(models.Product.product_url == r["product_url"]).first()
        
        if product:
            # Update existing product
            product.name = r.get("name", product.name)
            if r.get("price") is not None:
                product.price = r["price"]
            if r.get("rating") is not None:
                product.rating = r["rating"]
            if r.get("review_count") is not None:
                product.review_count = r.get("review_count", 0) or 0
            if r.get("image_url"):
                product.image_url = r["image_url"]
        else:
            # Create new product
            product = models.Product(
                platform=r["platform"],
                product_url=r["product_url"],
                name=r["name"],
                category=query,  # Use search query as the category
                price=r.get("price"),
                rating=r.get("rating"),
                review_count=r.get("review_count", 0) or 0,
                image_url=r.get("image_url"),
            )
            db.add(product)
            
        # Temporarily save the product object to grab its ID later
        r["_db_obj"] = product

    # Commit all upserts to the database to generate IDs
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Database commit failed during product upsert.")
        
    # 4. Fetch average sentiment for each product and rank them
    from app.sentiment import get_product_average_sentiment
    from app.ranking import rank_products
    
    for r in all_results:
        db_obj = r.pop("_db_obj", None)
        if db_obj and db_obj.id:
            r["id"] = db_obj.id
            r["sentiment_score"] = get_product_average_sentiment(db, db_obj.id)
        else:
            r["sentiment_score"] = 0.0
            
    # Rank and return the top 3 products
    top_3_products = rank_products(all_results)
    
    # 5. Fallback Mechanism: Fill remaining slots if live connectors returned < 3 results
    if len(top_3_products) < 3:
        import json
        import os
        
        fallback_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fallback_data.json")
        try:
            with open(fallback_file, "r", encoding="utf-8") as f:
                fallback_data = json.load(f)
                
            # Naively match query against category or name
            query_lower = query.lower()
            matching_fallbacks = [
                item for item in fallback_data
                if query_lower in item.get("category", "").lower() or query_lower in item.get("name", "").lower()
            ]
            
            # If no direct match, use generic fallbacks
            if not matching_fallbacks:
                matching_fallbacks = fallback_data
                
            for fb_item in matching_fallbacks:
                if len(top_3_products) >= 3:
                    break
                    
                # Avoid inserting a duplicate product
                existing_urls = {p["product_url"] for p in top_3_products}
                if fb_item["product_url"] not in existing_urls:
                    fb_item["is_fallback"] = True
                    fb_item.setdefault("sentiment_score", 0.0)
                    fb_item.setdefault("rank_score", 0.0)
                    top_3_products.append(fb_item)
                    
        except Exception as e:
            logger.error(f"Failed to load fallback data: {e}")

    return top_3_products

